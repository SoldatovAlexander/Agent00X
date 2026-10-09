# Граница Worker и model egress — проект решения

**Статус: design-only proposal; one inconclusive local socket-mount probe,
2026-10-09.** Это не реализованный или проверенный security boundary. Probe
использовал только synthetic bytes; сетевой запрос, credential или live Worker
call не выполнялись. Измеренный исход и непокрытые проверки отделены от
предлагаемой архитектуры.

## Требование и текущее состояние

VP-02 из [плана валидации](12-validation-plan-v1.md) требует Worker в sandbox
без прямой сети и доступа к host filesystem; критерий 2 Thin Vertical Slice
проверяет отсутствие GitHub network path и credential у Worker. MVP-срез
уточняет, что Worker может обращаться к модели, но не должен получать право
GitHub publication. R5 допускает только синтетические проверки, пока нет новой
точной live-карточки и свежего разрешения.

Сейчас `scripts/run_pinned_deepseek_worker.py` создаёт
`DeepSeekProposalWorker(channel=DeepSeekHTTPChannel(credential_source))` в
host-процессе. Канал закрепляет HTTPS host `api.deepseek.com`, path
`/chat/completions`, модель `deepseek-flash`, ограничивает payload 128,000
байт, ответ — 65,536 байт и request deadline — максимум 30 секунд. Это
ограничения прикладного HTTP-адаптера, а не изоляция процесса Worker: код
Worker и канал находятся в одном host execution context.

`DockerSandboxBackend` запускает target/verifier с `--network none`, read-only
root filesystem, `cap-drop ALL`, `no-new-privileges`, non-root user, лимитами
ресурсов и только двумя bind mounts: snapshot read-only и workspace read-write.
Этот профиль не используется для текущего live DeepSeek Worker и не доказывает
его сетевую изоляцию.

## Сравнение вариантов

| Вариант | Что даёт | Основной остаточный риск | Решение |
|---|---|---|---|
| Прямой HTTPS из Worker | Уже существующий fixed-host TLS channel, bounded JSON и timeout | Worker исполняется в host-процессе, имеет обычный host egress и разделяет process boundary с кодом, которому нужен credential source | Не считать выполнением VP-02; оставить только как явно обозначенный development/legacy path, отключённый для security gate |
| IP egress proxy/firewall | Может направлять трафик только к model proxy/provider и блокировать GitHub | Worker всё ещё имеет сетевой интерфейс; нужны доказанные правила хоста/daemon, запрет обхода и DNS/IPv6/redirect paths; proxy может стать привилегированным каналом | Допустимая альтернатива только при отдельном тесте реальных firewall rules и всех обходов; не полагаться на hostname allowlist внутри Worker |
| Host-side credential-owning broker через IPC | Worker container может сохранить `network=none`; credential и прямой HTTPS остаются в host broker, а Worker получает только разрешённый model result | Broker/host/daemon остаются доверенными; IPC — capability; socket bind mount и permissions на закреплённом Docker Desktop ещё не проверены; broker может получить произвольный prompt от Worker | **Рекомендуемый прототип для проверки:** узкий one-shot broker через приватный Unix-domain socket на macOS/Linux; не считать подтверждённым до opt-in Docker test. Для Windows потребуется отдельно спроектированный named-pipe transport и ACL; универсальность не заявлена. |

## Предлагаемая граница broker

Будущий prototype должен запускать модельный Worker в pinned контейнере с
`network=none`, без host project mount и без API key в argv, environment,
filesystem, process list или Worker memory. Единственная дополнительная
capability — узкий IPC endpoint для обращения к model broker. Предпочтительный
исследовательский вариант — private Unix-domain socket, bind-mounted только в
Worker container. Snapshot/workspace mounts и ресурсы остаются ограниченными
текущим Docker профилем. Socket mount пока **не подтверждён** на текущей
связке macOS/Docker Desktop и pinned image; до этой проверки это только проект.

Broker работает отдельным host-side объектом, получает credential через
назначенный Control Plane credential source только при фактическом вызове и
сам вызывает существующий HTTPS channel. Worker не может указывать host, URL,
HTTP method, path, redirects, authentication headers или увеличить лимиты.
Если IPC не поднимается, permit невалиден, ответ неполон или истёк deadline,
операция завершается fail-closed: без host-process fallback, прямого Worker
egress и повторного provider call.

### Предлагаемый запрос

Передавать один length-prefixed UTF-8 JSON object по socket. Broker принимает
только фиксированную версию и поля для ограниченного Chat Completions payload;
unknown fields, extra messages, tool calls, stream, другой model/reasoning
profile, oversized frame и повторное использование permit отвергаются до
credential lookup. Рабочий payload соответствует уже проверяемому профилю:

- `model="deepseek-flash"`, `reasoning_effort="low"`;
- `max_tokens` — целое число `1..4096`, `stream=false`;
- `response_format={"type":"json_object"}`;
- ровно system и user messages со строковым content;
- тело запроса не более 128,000 bytes, ответ не более 65,536 bytes;
- endpoint только HTTPS `api.deepseek.com/chat/completions`, без redirects;
- deadline не больше 30 секунд, лимит попыток задаётся карточкой и не
  может быть поднят сообщением Worker; текущий one-shot профиль — один вызов,
  retry запрещён.

Неизменяемый run permit должен поступать от runner/Control Plane, а не от
Worker, и фиксировать task/run ID, endpoint/model profile, максимальное число
вызовов, byte/deadline bounds и срок действия. Socket path — предоставленная
Worker capability, но не самостоятельный trust anchor. Если Docker не
предоставляет достаточную проверку владельца/процесса клиента, это явно
фиксируется как ограничение общей host/daemon trust domain; не имитировать
peer-authentication, которого transport не даёт.

### Credential, ошибки и cleanup

API key существует только в broker/HTTPS-channel execution context и только
на срок вызова. Он не сериализуется в IPC, prompt, output, environment Worker,
stdout/stderr, audit/evidence, exception, temp file или Docker configuration.
Worker получает только ограниченный parsed completion result; сырой HTTP body,
headers и provider errors не возвращаются. Ошибки наружу — фиксированные
категории без raw exception/details. Audit может хранить provider/model profile
ID, run/task ID, count, duration, request/response digests, outcome и
redacted request ID, но не prompt, source content, key или response body.

Runner создаёт приватный runtime directory/socket, затем broker и ограниченный
Worker; после результата сначала останавливает и удаляет Worker, закрывает
broker/channel, очищает secret source/injection по правилам источника, удаляет
socket и временный runtime directory. Ошибка cleanup — отдельный bounded audit
факт и не повод повторять live call. Нельзя утверждать гарантированное
стирание байтов из памяти средствами обычного Python.

## Проверочный план до любого live Worker

Следующая implementation/test карточка должна быть отдельной и offline-only;
Docker opt-in должен называть точные образы и команды. Обязательные проверки:

1. Fake provider/broker transport: exact valid round-trip; capture только
   безопасные метаданные; нулевое число реальных HTTP/provider calls.
2. Negative IPC: malformed/oversized JSON, неизвестные поля, неразрешённый
   endpoint/model, истёкший/повторный permit, повторный call, timeout, socket
   отсутствует/неверные права — fail-closed до credential lookup.
3. Worker контейнер: Docker inspect подтверждает `NetworkMode=none`, отсутствие
   GitHub DNS/egress, только разрешённые mounts, non-root и точные resource
   limits; попытки raw socket/network/DNS и host path traversal не проходят.
4. Canary-проверка всех Worker process surfaces: environment/process list,
   stdout/stderr, IPC errors, observer/SQLite, stage, report и cleanup evidence;
   при незапускаемом/нечитаемом surface — fail closed.
5. Отдельная capability-проверка socket mount на закреплённой macOS/Docker
   Desktop версии: доступ только из intended container и отказ соседнему
   локальному principal. До неё socket-mount support остаётся unverified.
6. Ни один offline test не является evidence настоящего DeepSeek вызова,
   account-level spend cap, независимости host/daemon, production key custody,
   human identity или PR publication. Live Worker потребует отдельную точную
   карточку, credential source, бюджет/число вызовов, срок и свежее разрешение.

## Вывод

Рекомендуется развивать one-shot broker-over-IPC при сохранении `network=none`
у Worker. Локальный synthetic прототип протокола описан ниже, но сам по себе он
не проверяет требование «Worker не имеет GitHub network path и не получает
credential»: остаются host/daemon trust, безопасность IPC, владение socket,
полнота canary scan и отдельный live boundary. Остальные части предлагаемой
архитектуры не объявляются реализованными.

## EXP-757: результат локального capability probe

Точный pinned target image inspect прошёл и вернул ожидаемый ID
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`.
Единственный opt-in test invocation завершился за 2.102 секунды с exit 1:
Docker `run` вернул code 125 до выдачи container ID. Диагностика намеренно
ограничена фиксированной фразой; raw host/Docker error и временный socket path
не сохранены. По карточке retry/fallback не выполнялся.

Следовательно, этот прогон не достиг обмена synthetic bytes, Docker inspect
контейнера или IP/DNS probes. Он не доказывает ни поддержку, ни отсутствие
поддержки Unix-socket bind mount: результат **unverified**, возможная причина
не установлена. Функция теста задала `--rm` и удаляет локальные временные
ресурсы в `finally`/`TemporaryDirectory`, но Docker cleanup после ошибки daemon
отдельно не проверялся. До отдельной точной карточки дальнейшие Docker-повторы
не разрешены; сетевая изоляция live Worker и criterion 2 остаются открытыми.

## EXP-758: результат локального synthetic IPC-прототипа

Добавлены одноразовые `UnixSocketChatCompletionsChannel` и
`UnixSocketChatCompletionsBroker`: versioned length-prefixed JSON, строгая
проверка существующего Chat Completions payload, фиксированная схема полей,
ограничения кадра и deadline, redacted ошибки, socket в существующем приватном
каталоге с mode `0600` и удалением только совпавшего inode. Тесты используют
только deterministic fake channel и синтетический payload.

Проверка `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_worker_model_ipc -q` завершилась успешно: 11 tests, 0.220 s.
`git diff --check` также прошёл. Docker, network, credentials, live provider
или внешнее действие не использовались.

Это только host-local protocol prototype. Он не аутентифицирует peer и не
доказывает, что контейнер может или должен монтировать socket; не подтверждает
изоляцию Worker, защиту от hostile worker, credential custody/erasure,
настоящий model call или provider write. Docker socket mounting, контейнерный
canary и критерий 2 остаются OPEN.

## EXP-759: безопасная классификация socket-mount startup failure

Exact pinned image inspect подтвердил целевой image ID. Единственный новый
opt-in invocation завершился за 6.323 секунды: Docker `run` вернул exit 125 до
container ID; расширенный вывод свёрнут в фиксированную категорию
`socket-mount-denied-or-unsupported`. Синтетические тесты классификатора
прошли. Raw stdout/stderr, host/socket paths и exception не сохранялись.

Из-за отсутствия container ID config inspect, synthetic exchange и IP/DNS
probes не состоялись. Локальный broker и временный каталог закрыты/удалены;
удаление возможного daemon-side контейнера отдельно не подтверждено, хотя
команда использовала `--rm`. Следующая гипотеза — mount только приватного
каталога с socket, read-only, с уникальным именем и без любого project mount.
Socket-mount support, cleanup после ошибки daemon и Worker isolation остаются
unverified/OPEN; этот результат не является security evidence.

## EXP-760: read-only private-directory mount attempt

Exact image inspect прошёл. Единственный новый opt-in invocation стартовал
контейнер с exit 0 и вернул container ID, используя read-only mount приватного
runtime-каталога. Test остановился при parsing успешного `docker inspect`:
`--format={{json .}}` возвращает один JSON object, тогда как assertion ожидал
array. Поэтому runtime security config, mount source/permissions, socket
exchange и IP/DNS probes не были подтверждены. `finally` вызвал forced cleanup
по уникальному имени, но код возврата cleanup не сохранился; cleanup не
считается подтверждённым. Raw inspect/Docker output не записывался.

Результат показывает только, что Docker принял `run` и запустил контейнер с
вариантом directory mount; это не подтверждает конфигурацию или IPC-доступ.
Один повтор той же карточки не выполнялся. Нужна отдельная карточка: исправить
обработку object-shaped inspect result, сохранить bounded cleanup status и
сделать ровно один новый проверочный запуск. Worker isolation остаётся OPEN.

## EXP-761: inspect parsing and cleanup evidence

Exact image preflight прошёл. Единственный новый invocation разобрал
object-shaped inspect response и прошёл assertions `network=none`, read-only
root, dropped capabilities, no-new-privileges, non-root UID, resource limits и
один read-only mount только приватного каталога. Следующий container `exec`
вернул exit 1 на synthetic socket exchange. Его stdout/stderr не сохранялись;
причина и факт host `accept` неизвестны. IP/DNS probes не выполнялись.

Forced cleanup по точному уникальному имени завершился успешно (тест сообщил
бы отказ, если бы контейнер не удалился); локальный socket закрыт. Выход
server-thread после ограниченного join не проверялся. Это доказывает только
успешный старт и проверенную network-none конфигурацию, но не IPC-доступ.
Read-only directory/socket bridge и Worker isolation остаются OPEN.

## EXP-762: mount-free attached-stdio IPC attempt

Exact pinned image inspect passed. The one opt-in run started the network-none
container, which sent the exact synthetic versioned request frame over its
attached stdout; the host parsed and matched that request. The test then
stopped at `docker inspect`: the Python f-string reduced the Go-template braces,
so its successful output was not JSON and no security assertions or fake
channel response followed. No IP/DNS probes ran. The child process was
interrupted and forced cleanup by its unique name was attempted, but cleanup
status was not retained.

This establishes only the container-to-host stdio request direction. It does
not establish the reverse response direction, full-duplex operation, container
configuration, cleanup, Worker integration or security boundary. No raw Docker
output was retained; a separate exact card is needed for one corrected run.

## EXP-763: successful synthetic attached-stdio exchange

After replacing the malformed f-string with a literal `--format={{json .}}`,
the exact pinned-image inspect succeeded and the test completed one full
synthetic request/response exchange. Three tests passed in 0.491 seconds,
including framing/parser and format-argument tests. The running container's
inspected config had `NetworkMode=none`, read-only root, all capabilities
dropped, `no-new-privileges`, non-root UID, bounded CPU/memory/PIDs, no mounts,
and only the pinned image's own environment. The fake channel was called once;
the child exited cleanly, and post-run inspect confirmed `--rm` cleanup.

This is the first successful mount-free host/container stdio capability test.
It uses a fixed child program and synthetic payload, not Agent00X Worker code,
real prompt/source content, credentials or a provider. It does not prove
hostile-worker resistance, authenticated IPC peer identity, Worker integration,
live-model credential custody, independent host trust or publication. Criterion
2 and MVP remain OPEN.

## EXP-765: actual Worker in the pinned container (incomplete attempt)

Exact pinned image inspect passed. The one opt-in invocation ran three tests:
the two local frame/cleanup-classifier tests passed, while the container test
failed before receiving its first stdout frame. It therefore did not establish
that the mounted package imported, that the synthetic task was accepted, that
the IP/DNS probes ran, or that the model request/fake response/proposal path
worked. Raw stderr was sent to `/dev/null`; no exception or host path was
retained, so the exit phase/cause is unknown.

The `finally` path terminated the process if needed, attempted forced cleanup
by the unique generated container name, and confirmed the name was absent.
No provider, network-enabled container, credential, or GitHub action was used.
This is not Worker-in-container evidence. A new one-shot task should add only
fixed phase/status frames (imports, task decode, network-denial probes, ready)
and retain a bounded exit category, then make one separately authorized test
invocation. Criterion 2 and MVP remain OPEN.

## EXP-766: bounded startup phase probe

Exact image inspect passed. The one new opt-in invocation ran four tests: three
offline tests passed and the container integration stopped on the first fixed
child status, `worker-import-failed`. The child process therefore started far
enough to execute its standard-library wrapper, but imported Worker/IPC modules
did not complete. Task acceptance, IP/DNS probes, config inspection, model
request, fake response and proposal were not reached. The underlying import
exception was intentionally not retained, so the missing module/dependency or
other cause remains unknown.

Cleanup by the unique name was attempted and verified; no raw Docker output,
traceback, host path or credentials were retained. This is useful phase
evidence, not an isolated Worker pass. Criterion 2 and MVP remain OPEN.

## EXP-767: fixed import-boundary classification

The exact target image preflight passed. The single new opt-in invocation ran
five tests: four offline tests passed and the container emitted the fixed
`worker-module-import-failed` phase. Before this status, its package-location
check confirmed that `app_contracts` was visible at the exact fixed in-container
mount destination. The broad Worker/IPC import block did not complete; no
module/exception detail was retained. Task acceptance, network denial probes,
container inspection, model request/response and candidate remain unverified.

The container cleanup check passed. This narrows the failure from an absent
mount/PYTHONPATH to execution of one or more package imports, but does not show
which import failed. Criterion 2 and MVP remain OPEN.

## EXP-769: explicit executor-first import order

The exact image preflight passed. The single opt-in invocation ran six tests:
five offline tests passed; after confirming the source package location, the
child emitted `worker-input-import-failed` for the explicit
`app_contracts.executor` import. The DeepSeek Worker, IPC adapter, task decode,
network probes and fake model exchange were not reached. No exception or module
message was retained. Container cleanup passed. This identifies the first
failing import stage but not its transitive dependency/cause; criterion 2 and
MVP remain OPEN.

## EXP-770: fixed pre-import stages for executor dependencies

The offline focused suite passed (six tests, with the opt-in container test
skipped). The exact pinned image preflight passed. The one authorized opt-in
invocation ran six tests and stopped at the fixed `dependency-2-import-failed`
status for `observer_runtime`; the preceding `repository_process` dependency
status passed. The child did not reach the remaining dependency imports,
executor, DeepSeek Worker, IPC, task acceptance, network probes or synthetic
model exchange. No exception or dynamic module detail was retained. The
test's cleanup path completed. No credentials, provider, network-enabled
container or external action was used. This narrows the first failing startup
boundary only; it does not establish the cause or Worker-in-container success.
Criterion 2 and MVP remain OPEN.

## EXP-771: split observation-store and observer-runtime imports

The offline focused suite passed (six tests; the opt-in container case was
skipped), and the exact pinned image preflight passed. The one opt-in invocation
ran six tests and stopped at the fixed `observation-store-import-failed`
status; `repository_process` had imported successfully and `observer_runtime`
was not reached. Source inspection shows that `observation_store` loads two
schema files via a path resolving to `/opt/schemas` in the current container,
but only `/opt/agent00x/app_contracts` was mounted. This is a source/config
explanation, not raw exception evidence. Cleanup completed. No credentials,
provider or external action was used. Criterion 2 and MVP remain OPEN.

## EXP-772: stage only Worker startup schemas

The offline focused suite passed (seven tests; the opt-in container case was
skipped), and the exact pinned image preflight passed. The one opt-in invocation
ran seven tests and passed the schema-backed `observation_store` and
`observer_runtime` imports, executor import and DeepSeek Worker import. It then
stopped at fixed `stdio-ipc-import-failed`. No task acceptance, network probe,
model request/response or proposal was reached. The test mounted only the app
package and a temporary directory containing the two required schemas,
read-only; both container and temporary staging cleanup passed. Source
inspection identifies the IPC-to-HTTPS-module import as a dependency boundary
to remove, not as a proven raw exception cause. No credentials, provider or
external action was used. Criterion 2 and MVP remain OPEN.

## EXP-773: transport-independent Worker model protocol

The focused suite passed 53 tests, with two opt-in Docker cases skipped. The
exact pinned image preflight passed. In the one opt-in invocation, fixed
startup statuses advanced through IPC, task acceptance and network-denial
probes; the child reached `ready` and emitted a valid bounded model request.
The test then stopped at an exact environment-list assertion: Docker ordered
the `PYTHONPATH` override first, while the environment entries themselves
matched. The fake response/candidate exchange was not reached. Container and
temporary schema staging cleanup passed. No credentials, provider or external
action was used. This establishes import/startup/request progress, not the
Worker proposal round trip; criterion 2 and MVP remain OPEN.

## EXP-774: Worker synthetic round trip in the pinned restricted container

The offline focused suite passed (eight tests; container case skipped), and
the exact image preflight passed. The one opt-in invocation passed all eight
tests. The actual `DeepSeekProposalWorker` ran in the pinned `network=none`
container, accepted a fixed synthetic task, observed blocked direct-IP and DNS
probes, exchanged one bounded request and one fake host response over stdio,
and returned the exact expected proposal with a clean exit. Inspection verified
the pinned image, read-only root, non-root identity, dropped capabilities,
no-new-privileges, resource limits, exact environment entries and exactly two
read-only mounts (package source plus the two-schema staging directory).
Container and temporary staging cleanup passed. No credentials, live provider,
or GitHub action was used. This is synthetic Worker IPC evidence, not a live
model call, repository-change end-to-end slice, independent verifier,
digest-bound approval or publication. Criterion 2 and MVP remain OPEN.

## EXP-768: split the Worker import stages

The exact image preflight passed. The one new opt-in invocation ran six tests:
five offline tests passed, then the child emitted `deepseek-worker-import-failed`
after confirming the exact package mount location. It did not reach the explicit
WorkerInput or IPC imports, task decoding, network probes or model path. The
exception was not retained; cleanup passed. This localizes the failure to the
DeepSeek Worker import (including its transitive imports), not an absent package
directory, but does not identify the dependency/module. Criterion 2 remains
OPEN.

## EXP-764: actual DeepSeek Worker over local stdio pipes

Added `StdioChatCompletionsChannel`, a one-call adapter over injected anonymous
binary pipes. It reuses the existing fixed Chat Completions request validator,
versioned length-prefixed JSON, 128,000/65,536-byte bounds, a maximum 30-second
deadline, strict duplicate/unknown-field rejection, typed one-choice response
serialization and fixed redacted errors. Pipe I/O uses `select` and temporarily
nonblocking descriptors so a stalled reader/writer cannot defeat the deadline;
the original blocking modes are restored.

The focused command ran 7 tests in 0.255 seconds: six offline tests passed and
the opt-in Docker case was skipped. A real `DeepSeekProposalWorker` ran in a
child process over local pipes; its request matched the fixed task payload,
one deterministic fake host-channel response produced the expected candidate,
reasoning data was omitted, and a replay attempt was rejected without a second
request (fake call count one). Invalid input was rejected before pipe output;
duplicate response keys produced only a fixed error; timeout was bounded under
one second. No Docker, network, credentials, provider or external action was
used. This is local synthetic Worker/IPC evidence, not Worker-container
integration, authenticated peer identity, credential custody or independent
host trust. Criterion 2 and MVP remain OPEN.
