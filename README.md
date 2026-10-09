# Agent Process Platform / Агент 00Х

Исследовательский прототип для проверки гипотезы: поможет ли явное представление
целей, данных, состояния, процедур, полномочий и результатов агенту исполнять
проработанную бизнес-функцию. Первый сценарий — `repository-change`.

Наблюдатель, контрольные точки каждого решения и вызова инструмента, а также
обучение через ветвление исполнения входят в замысел прототипа. Контракты,
структурный отчёт и локальный file-backed SQLite journal покрыты unit-тестами;
опциональный collector частичный: он фиксирует Worker, independent verifier,
target-test, verifier-replay, stage-save и exact-digest readback calls, но не
охватывает весь runtime. Реализованы metadata-only объявления simulation
branches и проверка/materialization content-addressed workspace в памяти для
подходящего checkpoint. Исполнение альтернативной ветки и оценка переноса
корректировок пока отсутствуют. Материал для коллег:
[объяснение проекта](docs/29-agent-explained.md).
Память будет слоистой и ограниченной: после шести месяцев — месячные, после года
— годовые сводки; [полная политика](docs/30-memory-model.md).

## Состояние

Есть 24 JSON Schema: 17 базовых, 4 контракта наблюдателя, 2 trust-enrollment
и 1 формат caller-pinned authority key set,
а также fixtures, детерминированный reference flow подготовки изменений,
SQLite runtime, mock
publication boundary, sandbox-профили и отдельные GitHub App spikes. Это не
равнозначно готовому агенту или доказанной сквозной безопасности: нарушения
привязки проверенного изменения к manifest и approval к запросу публикации
закрыты локальными fail-closed regression. Batch AA добавил composed local
harness для approval → policy → manifest → Broker → journal → recovery на
mock/in-memory/ephemeral doubles, а Batch AB закрепил gateway-before-broker
порядок в компоненте. Batch AD добавил deterministic twin-workspace и
same-workspace interleaving проверки подготовки. Это не production
orchestrator, доказательство реальной параллельной записи, filesystem locking,
сквозной безопасности или external publication. Batch AE добавил локальную
SQLite persistence/reopen и fail-closed проверки ObservationEvent/Checkpoint;
они не доказывают power-loss durability, защиту от привилегированного изменения,
collector completeness, access control или многопроцессную конкурентность.
Batch AF добавил локальный детерминированный executor shell с injected Worker,
Verifier и sandbox backend. Это не реальный LLM Worker, проверенный remote
snapshot, production sandbox или publication chain; детали и открытые границы —
в документе 27. Batch AG добавил экспорт дерева точного commit из локальной
Git object database и повторный запуск allowlisted-команды в отдельной локальной
sandbox-сессии. Batch AH (R2, локальный батч 3/3, 20 карточек) проверил
controlled publication и reconciliation только на локальном mock endpoint,
in-memory broker и SQLite journal. Это не remote provenance и не independently
trusted verifier: backend/verifier остаются injected doubles, а process backend
 — development fallback; real provider/credentials, production isolation и
durability остаются вне подтверждённого scope. Batch AI — отдельный локальный
R2 follow-up (20 карточек): bounded subprocess JSON handoff ограниченного
`VerifierInput` в дочерний процесс и приём только bound `VerifierResult`
(AI-1—AI-4 — wire contract, AI-5—AI-12 — процессный адаптер и fail-closed
поведение, AI-13—AI-19 — интеграция и отказная матрица). На 2026-10-01 приняты
все 20 карточек Batch AI (EXP-348—367). Это process-boundary prototype на
текущем host, а не independently trusted verifier. Process separation не
означает security isolation; remote provenance, production sandbox, реальная
модель и external providers остаются открытыми.

Batch AK добавил ограниченное read-only evidence для одного публичного GitHub
репозитория: pinned commit/tree, inventory метаданных и проверку четырёх
allowlisted blobs с selected-content digest (`full_snapshot=false`), а также
один not-found ответ HTTP 404. Исходная серия: 7/10 ACCEPTED, три карточки
исторически BLOCKED; последующие bounded follow-ups сняли TLS gate и подтвердили
GitHub REST `verified=false, reason=unsigned` для pinned commit. Это только
утверждение API, не независимая проверка подписи, authorship, полный snapshot
или законченная publication chain.

Batch AM (5 карточек EXP-400—404) добавил pinned snapshot в bounded verifier
handoff, отдельный контейнерный verifier runtime и привязку результата к trusted
image/code identity. Все пять карточек приняты. EXP-404 добавил nonce-bound
replay rejection; второй targeted прогон прошёл (21 тест), но команда была
запущена дважды с live verifier invocation в каждом прогоне при лимите в один.
По явному решению пользователя это принято как раскрытое локальное исключение;
дополнительных запусков не будет. Для Batch AN пользователь выбрал публичный
`SoldatovAlexander/brainbooster_full_v11` (`master`), а approval owner — сам
пользователь. Текущий scope ограничен публичным read-only доступом и локальными
fake/SQLite-reopen проверками; GitHub App credentials и provider writes не
разрешены без отдельных точных карточек и подтверждений. EXP-405 добавил
bounded content-bearing GitHub snapshot record, но он ещё не передаётся executor-у.
Локальная recovery-проверка Batch AN подтвердила, что unknown/conflicting fake
outcome остаётся fail-closed после reopen SQLite без повторного publish.
Runtime smoke не является independent
kernel/daemon attestation. Актуальный статус и решение Control Plane — в
[документе 27](docs/27-implementation-status.md) и [.opencode/tasks/WORK_QUEUE.md](.opencode/tasks/WORK_QUEUE.md).

Batch EL / EXP-546 принял обязательный `allowed_approver_ids` allowlist и
fail-closed проверку `approver_id` до downstream effects. Это контроль
заявленного identity claim, а не аутентификация пользователя; R2 остаётся OPEN.
Batch EM / EXP-547 добавил Ed25519-подпись всего approval payload и проверку
по ключу из явной policy-конфигурации. Synthetic mock signer и тестовый ключ
доказывают только владение конкретным ключом, не личность человека или
production approval.

Единственный актуальный статус реализации и границ доказательств:
[документ 27](docs/27-implementation-status.md). Порядок работ R0—R5:
[план исследовательского прототипа](docs/24-mvp-final-plan.md).

Проверка существующего кода:

```bash
python3 -m pip install -e .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Последний полный offline suite на 2026-10-09 после EXP-747: 1353 теста,
1337 прошли, 16 пропущено. Это локальное regression evidence; MVP и R2
остаются OPEN.
После Batch KJ / EXP-703: 1300 тестов, 1289 прошли, 11 пропущено.
Это подтверждает только покрытые тестами локальные свойства на текущей машине,
не безопасность всей цепочки, live Worker, независимость verifier или реальную
публикацию. Подробнее — в документе 27.

Подписанный verifier protocol и клиентский контроль ответа реализованы; transport
по-прежнему подключается явно. Batch HX добавил one-shot HTTPS adapter с
фиксированным `/v1/verify`, проверкой TLS и bounded request/response. Удалённый
endpoint не настроен и не вызывался; имеющийся subprocess adapter запускает
verifier на том же host. Подпись и HTTPS сами по себе не аутентифицируют
независимый trust domain. Развёртывание сервиса и out-of-band enrollment/pinning
ключа не подтверждены; receipts остаются audit-only и не разрешают executor
trust promotion. `scripts/serve_signed_verifier_http.py` добавляет одноразовый
loopback-only HTTP service на явно заданном непривилегированном порту; для
удалённого доступа потребуются отдельно управляемые TLS termination и access
control. Скрипт не запускался. Поэтому текущий локальный verifier PASS не
является evidence независимой проверки.

Batch IA / EXP-638 добавляет локальную проверку OpenPGP-подписи точного raw
Git commit через изолированные Git/GnuPG временные среды и явно закреплённый
primary fingerprint. Это подтверждает только подпись конкретного объекта
этим ключом; соответствие ключа владельцу репозитория, human authorship и
независимость GitHub/TLS остаются непроверенными. Реальный commit/key в этом
batch не загружались, snapshot origin остаётся `github_rest_api_claim`.

Для повторного прогона уже сохранённого verified candidate есть отдельная
безсекретная команда `scripts/replay_staged_candidate.py`. Ей нужны существующая
SQLite-стадия, её точный digest и новый абсолютный путь для output DB; output не
перезаписывается. Команда ограничена закреплённым публичным snapshot, target и
verifier, требует явный `RUN_DOCKER_SANDBOX_TESTS=1`, делает только anonymous
read-only GitHub запросы и Docker verification. Она не вызывает модель, не
читает credentials, не создаёт approval и не публикует изменения. Повторно
полученный stage остаётся same-host evidence, а snapshot — GitHub API claim.
Необязательный `--observer-database <new-absolute-path>` включает отдельный
SQLite-журнал частичного replay: от readiness/quota и snapshot intake до
сохранения и exact-digest readback. Он не перезаписывает базу; отчёт строится
отдельной командой `scripts/report_observation_history.py`. Replay использует
сохранённое предложение, не вызывает Worker/model, а отчёт не доказывает
полноту collector или независимость локального журнала.

Для сохранения отдельной локальной копии существующей SQLite-стадии есть
`scripts/copy_staged_evidence.py <source-database> <staged-change-digest>
<new-destination-database>`. CLI требует абсолютный путь source, точный stage
digest и отсутствующий destination; отклоняет WAL/SHM sidecars, не
перезаписывает файлы, проверяет byte-identical copy и read-only exact-digest
readback. Вывод содержит только digest/file-hash/size metadata. Копия на том же
volume не является cross-host backup, replication, power-loss proof или
production durability.

Для локального просмотра того, что именно потребует отдельного human approval,
есть `scripts/create_approval_request.py`. Команда читает одну существующую
SQLite-стадию по точному digest в read-only режиме и печатает ограниченный JSON
со stage/intent, patch для ревью и точными canonical Ed25519 signing bytes.
Нужны явные branch, base branch, approval ID, approver ID и policy version; из
окружения берутся только несекретные `AGENT_GITHUB_TEST_REPOSITORY`,
`AGENT_GITHUB_INSTALLATION_ID` и `AGENT_GITHUB_REPOSITORY_ID`. Результат всегда
`unsigned`, `approval=not_created`, `provider_write=false`: команда не подписывает,
не создаёт approval и не обращается к GitHub. Человеческая подпись, enrollment
доверенного signer и publication остаются отдельными незакрытыми gates.

Если сначала нужно только посмотреть сохранённый patch, не выбирая approver,
ветку или policy version, используйте read-only preview по точному digest:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m app_contracts.stage_preview <database> <staged-change-digest>
```

Он печатает bounded review JSON с patch и сообщает `approval=not_created` и
`publication=not_attempted`. Эта команда не создаёт approval и не подписывает
данные; после просмотра отдельно решается, готовить ли request через
`scripts/create_approval_request.py`.

Для проверки внешней подписи предусмотрен read-only
`scripts/verify_signed_approval.py`: ему нужны та же SQLite-стадия, исходный
request JSON, подписанный конверт `signed-approval/v1` и JSON
`approval-trust-profile/v1` с target binding, policy allowlists и публичными
Ed25519 keys. Он заново строит request из stage и пропускает подпись через
policy; результат не вызывает Gateway/Broker и всегда сообщает
`identity_authenticated=false` и `provider_write=false`. Trust profile здесь
явно передан оператором, но его источник не аутентифицирован: это не signer
enrollment и не разрешение на публикацию.

Для воспроизводимой локальной композиции доступен
`scripts/publish_signed_stage_mock.py <database> <staged-change-digest>
<request.json> <signed-approval.json> <trust-profile.json>`. Он заново
проверяет точную stage/request/signature/profile связку, повторно прогоняет
Policy → slow Gateway → одноразовый in-memory Broker → временный digest-only
SQLite journal и создаёт ровно один receipt только в `MockGitHubEndpoint`.
Вывод ограничен receipt metadata и явно содержит
`destination=in_memory_mock_only`, `external_write=false`,
`identity_authenticated=false` и `trust_profile_origin=operator_supplied_unverified`.
Файлы входов не изменяются. Это не human enrollment, доверенный production
profile, внешний PR, production recovery или live provider permission.

Для синтетического enrolled approval есть отдельная функция
`run_enrolled_signed_approval_local_mock_publication`: она сама перечитывает
stage/request/signature/profile/enrollment, проверяет caller-pinned authority и
проводит approval через те же freshness/policy/gateway/broker/journal gates.
Этот путь принимает только in-memory broker и mock endpoint; он не разрешает
GitHub App transport и всё ещё выставляет `identity_authenticated=false`.

CLI `publish_signed_stage_mock.py` поддерживает ту же проверку через три
обязательных вместе параметра enrolled-режима:
`--approver-enrollment`, `--authority-key-set` и
`--authority-key-set-digest sha256:<digest>`. Файл key-set соответствует
`schemas/control-plane-authority-key-set.schema.json` и содержит только
публичные ключи. Ожидаемый digest нужно сверить/закрепить внеполосно; один путь
к локальному файлу не является trust anchor. CLI сверяет его до approval,
показывает digest и enrollment/authority IDs, но не доказывает личность человека
и по-прежнему создаёт receipt только в in-memory mock.

`ProcessEnvironmentCredentialSource` — только lazy-адаптер к одному явно
переданному process mapping. Он не читает ambient environment или `.env` сам,
не хранит/не шифрует секрет и не заменяет OS vault. Для ограниченного MVP fixed
Worker CLI по умолчанию запрашивает ключ через интерактивный скрытый ввод
(`TerminalPromptCredentialSource`) после точного подтверждения запуска; при
небезопасном echo fallback ввод отклоняется. Источник указывается в task card;
сам Worker запуск всё равно требует точную READY-карточку и свежее подтверждение
live-вызова. Если доверенный менеджер уже внедрил `AI_PROCESS_API` только в
процесс запуска, оператор может явно выбрать `--credential-source
process-environment`; после подтверждения CLI проверит наличие имени до
readiness/network, а значение прочтёт только lazy source при обращении Worker.
Значение никогда не печатается; без флага по-прежнему используется скрытый
terminal prompt.

Для ограниченного локального прототипа доступен `NativeKeyringCredentialSource`
(`python3 -m pip install -e '.[native-keyring]'`): он явно выбирает только
нативный backend текущей ОС — macOS Keychain, Windows Credential Manager или
Linux Secret Service. Имя элемента фиксировано: service `Agent00X`, account
`AI_PROCESS_API`; adapter только читает его при фактическом вызове Worker и
сам не создаёт, не импортирует и не сохраняет credentials. Внесите/удалите
элемент через системный менеджер секретов, не через CLI, shell или файлы.
Например, Linux backend требует доступной пользовательской Secret Service
сессии и может быть неприменим к headless-запуску.

Выбор источника: `--credential-source native-keyring`. Проверка
`--check-credential-source --credential-source native-keyring` сообщает только
доступность разрешённого backend (`credential_item_checked=false`,
`value_read=false`); она намеренно не проверяет наличие/валидность записи.
Это экспериментальная интеграция с библиотекой `keyring`, а не доказательство
безопасности любого системного backend, универсальное хранилище продукта или
межпроектный инжектор. До реального вызова нужны отдельная точная task card,
доступная запись в менеджере и свежее разрешение пользователя; этот прототип
не извлекает значение из AI Process Architect.

Проверить только наличие process injection, не читая значение и не запуская
Docker/сеть/Worker, можно командой
`python3 scripts/run_pinned_deepseek_worker.py --check-credential-source --credential-source process-environment`.
Результат содержит только `available`/`unavailable` и `value_read=false`; это не
проверка корректности ключа и не разрешение на live-вызов.

Для фиксированной remote композиции подготовлен
`scripts/run_pinned_deepseek_worker.py <new-absolute-stage.sqlite3>`: он
показывает target, model, endpoint и путь, проверяет наличие только закреплённых
Docker images, затем требует фразу `RUN EXP-634 ONCE`. После отдельного
подтверждения EXP-634 он делает только anonymous GitHub reads и максимум одну
DeepSeek попытку, сохраняя verified SQLite stage. Новая инструкция EXP-634
требует signed-64 границы для пяти numeric полей. На 2026-10-08 пользователь
разрешил ровно один вызов с пользовательским потолком USD 1, но безопасный
`process-environment` preflight вернул `unavailable` (`value_read=false`).
Карточка заблокирована до readiness/network: Worker и Docker не запускались,
credential не читался. Потолок расходов пользовательский, не account-enforced.

Remote runtime принимает явный абсолютный `stage_database_path`. Только при
результате `verified` evidence содержит этот путь, если файл существует и
открывается как SQLite в read-only режиме; неуспешные запуски и синтетические
профили без locator его не раскрывают. Для последующего локального ревью
оператору следует выбирать стабильный путь вне автоматически удаляемого
каталога. Это locator локальной стадии, а не гарантия резервного копирования,
crash recovery или production durability.

## Observer history report

`python3 scripts/report_observation_history.py <existing-observation.sqlite3>`
reads one versioned SQLite journal in immutable read-only mode and emits a
deterministic structural report. Optional `--process-id`, `--run-id`,
`--branch-id` and `--as-of-cursor` narrow the view. Output omits free-text
rationale and tool payloads, verifies stored row digests and checkpoint links,
and always labels coverage `partial` / `local_unattested`; gap markers include
unknown outcomes, sequence/causal omissions, redaction and unresolved artifact
contents. This is not a runtime collector, full replay, artifact resolver or
proof that all events were recorded.

## GitHub App: локальная подготовка

`.env.github-app.example` содержит только metadata отдельного allowlisted
тестового репозитория. Private key и `.env.github-app` не должны попадать в Git;
не загружайте этот файл целиком в shell: в нём могут быть секреты, не нужные
preflight. Для запуска оператор должен отдельно подготовить
процессное окружение с metadata (`AGENT_GITHUB_APP_ID`,
`AGENT_GITHUB_INSTALLATION_ID`, `AGENT_GITHUB_REPOSITORY_ID`,
`AGENT_GITHUB_TEST_REPOSITORY`, `AGENT_GITHUB_PRIVATE_KEY_PATH`) через
утверждённый manager/процесс supervisor. `scripts/github_app_preflight.py`
проверяет только metadata и тип/права файла по указанному пути: содержимое
ключа не читает, GitHub API не вызывает и не разрешает публикацию.

Broker preflight service на `testdev` проверяет metadata при boot. Он не создаёт
token и не выполняет публикацию. Наличие App и успешные тестовые PR не означают,
что сквозной Authority Plane завершён: см. документ 27.

## Документы

- [Описание для коллег: назначение, цели, принципы и архитектура](docs/29-agent-explained.md)
- [Наблюдатель, контрольные точки и обучение](docs/28-observer-and-learning.md)
- [Модель памяти и сроков хранения](docs/30-memory-model.md)
- [План исследовательского прототипа](docs/24-mvp-final-plan.md)
- [Статус реализации и доказательств](docs/27-implementation-status.md)
- [Карта всего комплекта](docs/22-documentation-map.md)
- [Видение и границы](docs/00-vision-and-scope.md)
- [Архитектура](docs/01-architecture.md)
- [Модель процессов](docs/02-process-model.md)
- [Реестр архитектурных решений](docs/06-decision-register.md)
- [Гипотезы и backlog проверок](docs/07-validation-backlog.md)
- [План валидации](docs/12-validation-plan-v1.md)
- [Матрица трассируемости](docs/13-traceability-matrix.md)
- [Полный бриф широкого продукта](docs/23-project-brief.md)

Остальные специализированные документы перечислены в карте комплекта.

Batch IB / EXP-639 performed one bounded anonymous signature check for the
pinned public commit. No key from the selected public signer key set verified
the exact raw commit; the probe returned only a sanitized failure marker and
did not retry. This does not authenticate snapshot provenance. Full offline
suite: 1172 tests (1163 passed, 9 skipped); R2/MVP remain OPEN.

Supplemental full offline suite after EXP-747 on 2026-10-09: 1353 tests
(1337 passed, 16 skipped). This is local regression evidence only; R2/MVP
remain OPEN.
