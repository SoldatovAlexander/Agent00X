# Agent Process Platform / Агент 00Х

Исследовательский прототип для проверки гипотезы: поможет ли явное представление
целей, данных, состояния, процедур, полномочий и результатов агенту исполнять
проработанную бизнес-функцию. Первый сценарий — `repository-change`.

Наблюдатель, контрольные точки каждого решения и вызова инструмента, а также
обучение через ветвление исполнения входят в замысел прототипа. Контракты,
структурный отчёт с cursor-, recorded-time и occurred-time срезами и локальный
file-backed SQLite journal покрыты unit-тестами;
опциональный collector частичный: он фиксирует Worker, independent verifier,
target-test, verifier-replay, stage-save и exact-digest readback calls, а также
decision проверки соответствия sandbox скопированному pinned snapshot; он не
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

Последний принятый полный offline suite (2026-10-16, EXP-1345): 1,789 тестов,
1,764 прошли, 25 пропущено. Это локальное regression evidence, не подтверждение
полного MVP; сведения о запуске — в `.opencode/tasks/WORK_QUEUE.md`. EXP-856
подтвердил fail-closed отказ approval request без caller-pinned verifier trust;
EXP-857 лишь уточнил диагностику при SQLite WAL/SHM sidecars. Это локальное
regression evidence; MVP и R2 остаются OPEN.
После Batch KJ / EXP-703: 1300 тестов, 1289 прошли, 11 пропущено.
Это подтверждает только покрытые тестами локальные свойства на текущей машине,
не безопасность всей цепочки, live Worker, независимость verifier или реальную
публикацию. Подробнее — в документе 27.

Подписанный verifier protocol и клиентский контроль ответа реализованы; transport
по-прежнему подключается явно. Batch HX добавил one-shot HTTPS adapter с
фиксированным `/v1/verify`, проверкой TLS и bounded request/response. Batch NW
добавил возможность caller-pinned CA для `.local`; Batch NX — подписанные
enrollment и host-trust decision для `https://testdev.local/v1/verify`; Batch NY
подключил этот backend к pinned operator CLI через явный
`--verifier-backend trusted-https`. Для него обязательны caller-pinned SHA-256
authority-key-set, enrollment, host-decision и CA bundle; остальные endpoint
не принимаются. Синтетические тесты доказывают только local wiring, не удалённый
вызов. `testdev.local` не разрешался и не настраивался; TLS proxy, verifier
service, signer credential и out-of-band host-separation evidence отсутствуют.
Read-only SSH checks EXP-996/997 confirmed that the pinned verifier image ID
and expected tag are not listed on `testdev`; no import or host setup followed.
EXP-999 remains DRAFT pending fresh, exact authorization for the SSH identity
and remote image import. Host package/service configuration still needs an
explicit elevation path and a fresh exact task card.
EXP-840 adds optional `--verifier-connect-address` for this trusted HTTPS path:
it can dial an IP literal while the endpoint, TLS SNI/certificate hostname,
signed enrollment and host-trust decision remain bound to `testdev.local`.
The override is shown in CLI preflight evidence and does not configure DNS or
prove that the remote endpoint is running; its real-TLS evidence is loopback
only. No testdev network call or host change was made.
EXP-841 restricts the override to exact local IPv4 ranges, loopback or IPv6 ULA
and proves that a trusted certificate with the wrong SAN is rejected before
the HTTP handler receives a request. The dial override remains routing only,
not a trust decision.
EXP-842 adds an explicitly selected, credential-free Ollama backend at the
fixed loopback Chat Completions endpoint using `qwen2.5-coder:7b`. It keeps the
proposal Worker inside the existing network-none container and sends the model
request only from the host-side channel. The separate `EXP-842` confirmation
profile cannot be combined with DeepSeek cards or the host-process Worker.
Offline fixtures prove bounded one-shot request/response handling and zero
credential-source access. EXP-843 installed Ollama and pulled the one approved
model, but its confirmation prompt was opened in a hidden execution session;
no GitHub snapshot request or model inference occurred, and EXP-843 is blocked.
EXP-844 adds a distinct confirmation profile for a future user-visible,
one-shot attempt. Its offline profile/mismatch tests passed (94 tests, 2 skipped);
the full suite passed (1462 tests, 22 skipped). No local-model inference or
verifier PASS is evidenced yet.
Focused EXP-842 suites: 93 tests, 2 skipped; full offline suite: 1461 tests,
1439 passed, 22 skipped; `git diff --check` passed.
`scripts/serve_signed_verifier_http.py` остаётся loopback-only service; для
удалённого доступа потребуется отдельно управляемая TLS termination и access
control. `--signing-seed-source systemd-credential` читает фиксированный seed
через systemd `CREDENTIALS_DIRECTORY`, но реальный unit/credential не
настраивались. Batch OJ adds `scripts/provision_systemd_verifier_credential.py`
for root-only creation of a fresh host-encrypted seed without a plaintext file; its offline
tests use a fake `systemd-creds` process only. It has not been run on testdev,
and its public-key output is not authority enrollment or independent-host
evidence. Подпись и HTTPS сами по себе не аутентифицируют независимый trust
domain; receipts остаются audit-only и не разрешают trust promotion.

EXP-801 делает restricted-container Worker backend значением по умолчанию в
pinned operator CLI; host-process Worker выбирается только явным legacy/dev
флагом. EXP-802 добавляет opt-in Docker composition с synthetic model channel:
контейнерный Worker, target tests, pinned verifier, stage/readback и локальный
mock receipt завершаются в одном observer run. Это не live model, deployed
`.local` verifier, authenticated human approval или реальный Pull Request.
EXP-804 добавляет отдельный opt-in `AGENT00X_PUBLIC_STAGE_DESTINATION` для
no-overwrite сохранения exact stage в последующем публичном read-only прогоне;
это лишь review material с synthetic verifier trust, не approval-eligible
evidence.

EXP-810 повторил публичный pinned-snapshot прогон после quota readiness: 23
blob snapshot, один restricted Docker Worker runtime, target tests и pinned
verifier PASS, точные SQLite stage/readback и local-mock receipt прошли с одним
digest. Stage сохранён отдельным no-overwrite evidence artifact. Receipt остаётся
mock-only (`external_write=false`, `identity_authenticated=false`); это не live
model, deployed `.local` verifier, human approval или Pull Request publication.

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

Если stage находится в WAL/SHM-backed SQLite состоянии, отдельная локальная
команда `scripts/snapshot_wal_stage.py <source-database>
<staged-change-digest> <new-destination-database>` сначала копирует только
файлы DB/WAL/SHM в закрытый временный каталог, сверяет их fingerprints до и
после чтения, затем через SQLite backup API создаёт standalone DELETE-mode
копию. Исходные файлы не открываются SQLite и не изменяются; destination
создаётся без перезаписи с mode 0600 и exact-stage readback. Это локальный
consistency snapshot, не cross-host backup, power-loss proof или production
durability.

Для локальной no-overwrite копии одного завершённого observer run есть
`scripts/copy_observer_evidence.py <source-database> <run-id>
<new-destination-database>`. Команда принимает только quiescent валидную SQLite
базу с точным run ID, сверяет byte-identical copy и повторное чтение событий и
checkpoint-ов. Выводит только run ID, количества записей, SHA-256 и размер — без
локальных путей и payload событий. Это локальное сохранение, не доказательство
полноты collector, отсутствия неизвестных секретов, защиты от подмены,
cross-host durability или production audit trust.

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

Для однократной подписи уже просмотренного request есть
`scripts/sign_approval_request.py <stage.sqlite3> <staged-change-digest>
<request.json>`. Команда заново строит request из exact stage в read-only режиме,
показывает action и patch, требует ввести точную фразу
`SIGN APPROVAL <approval-id> <staged-change-digest>` и только после этого
обращается к единственному process-injected источнику
`AGENT_APPROVER_SIGNING_SEED`. Значение seed должно поступить через доверенный
менеджер непосредственно в процесс; не задавайте его в командной строке, shell
history, `.env` или файле проекта. Команда пишет `signed-approval/v1` только в
stdout и не создаёт файлов, не пишет в GitHub и не подтверждает личность
approver. Enrollment доверенного публичного ключа остаётся отдельным gate.

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

Операторский CLI дополнительно принимает `--verifier-backend trusted-https`
и caller-pinned trust-артефакты для фиксированного `testdev.local`; список флагов
доступен через `--help`. Этот режим пока не запускался против удалённого хоста.
Не указывайте synthetic test keys как production trust и не запускайте live
Worker без отдельной точной карточки, безопасного credential source и свежего
подтверждения.

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

EXP-844's one local Ollama call failed during cold model loading (HTTP 499 at
30.273 seconds). EXP-845 raises only the local Worker timeout to 180 seconds;
DeepSeek remains at 30 seconds. EXP-846 made one local call (HTTP 200, about
58.1 seconds) but the CLI returned the sanitized `remote-snapshot-execution-failed`
marker; its integrity-valid stage contains zero artifacts. Ollama was stopped
without retry. Focused tests passed (75 tests, 1 skipped); full suite passed
(1465 tests, 22 skipped), and `git diff --check` is clean. No proposal or
verifier pass exists; R2/MVP remain OPEN.
EXP-847 adds sanitized snapshot-preparation vs execution-pipeline failure
markers (no raw exception text); 59 CLI tests passed (2 skipped), and the full
offline suite passed (1467 tests, 22 skipped). This does not retroactively
diagnose EXP-846. R2/MVP remain OPEN.
EXP-848 stopped before local inference (`pinned-worker-runtime-failed`); EXP-849
made one readiness attempt and stopped at `github-readiness-ineligible` with
zero model attempts. Status/quota details were not emitted; no snapshot, stage,
or retry occurred. EXP-849 CLI tests passed (31). R2/MVP remain OPEN.
EXP-851 passed the pinned public snapshot, restricted Worker, target tests and
pinned same-host verifier; it retained one integrity-valid candidate stage at
`/private/tmp/agent00x-exp851-stage.sqlite3` with staged digest
`sha256:a034c79c6552b5ebc4a2a788d439c579d0024f178675415e586192d0b4403209`.
No approval or publication occurred; independent testdev trust remains open.

Control Plane update (2026-10-15): EXP-1274's separately authorized single
read-only SSH inspect returned only `REMOTE_INSPECT_FAILED` (exit 11). The image
identity on testdev remains unconfirmed; the marker does not distinguish SSH
unavailability from a Docker inspect failure. No retry, diagnostics, or cleanup
ran. EXP-1274 is BLOCKED and R2/MVP remain OPEN.

Control Plane result (2026-10-15): EXP-1269 completed one post-reset,
credential-free public-snapshot run through restricted local Worker, target
tests, current same-host pinned verifier and exact stage/readback (`status=verified`).
Stage digest: `sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0`.
Observer run `run-dacc14f7789d4d35aafca58cfe5cf8d1` is partial at cursor 88;
both databases passed integrity and mode checks. Approval/publication were not
attempted; no provider write occurred. This does not establish independent
verifier trust, authenticated approval, or a real PR; R2/MVP remain OPEN.

EXP-1275's exact current-pin synthetic Docker canary composition passed
(1 test, 2.568s), including the test's bounded canary scans and same-digest
local-mock receipt. It used no live model or external provider and does not
establish independent verifier trust; R2/MVP remain OPEN.

EXP-1276 improved the one-shot inspector's bounded failure classification;
focused tests (5) and the full offline suite (1,715 tests, 25 skipped) passed.
EXP-1277's separately authorized read-only inspect ran once after its exact
gate and returned only `REMOTE_INSPECT_FAILED` (exit 11). The image tuple was
not confirmed; the marker cannot distinguish SSH unavailability from Docker
inspect failure. No retry, diagnostics, cleanup or other remote action ran.
EXP-1277 is BLOCKED; R2/MVP remain OPEN.

EXP-1278 added a local-only, fake-tested one-shot testdev probe that classifies
Docker CLI, daemon, exact-image inspect and transport outcomes using fixed
markers. Six focused tests passed, including shell syntax validation without
execution; full offline suite: 1,721 tests, 25 skipped;
`git diff --check` passed. No SSH, Docker or network ran. EXP-1279 is DRAFT and
requires separate fresh authorization before its single read-only probe;
R2/MVP remain OPEN.

EXP-1280 narrowed verifier-host packaging from the entire `app_contracts`
package to the service's static local import closure. Two sequential in-memory
builds matched at `sha256:31ca7d3df0ad03bd64e0924d34b107f1f25a6157fecbd132d7b4a4e50875a3c4`
(31 members, 541,323 source bytes). The focused bundle suite passed 13 tests;
the full offline suite passed 1,721 tests (25 skipped). The source is still from
the dirty worktree and has not been deployed or independently trusted; R2/MVP
remain OPEN.

EXP-1281 split the `CredentialSource` protocol from the module implementing
systemd-file, terminal-prompt and native keyring readers. The verifier service
imports only the protocol; compatibility re-exports preserve the same type
identity. The current 31-member host bundle now contains the protocol module and
excludes those unused readers. Two in-memory builds matched at
`sha256:261fce4785b2b0fd17c369d3faf9c53873a8319af66d7ec03abacc32eda3e791`
(533,249 source bytes). Full offline suite: 1,723 tests, 25 skipped. No
credential or external operation was used; R2/MVP remain OPEN.
