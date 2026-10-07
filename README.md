# Agent Process Platform / Агент 00Х

Исследовательский прототип для проверки гипотезы: поможет ли явное представление
целей, данных, состояния, процедур, полномочий и результатов агенту исполнять
проработанную бизнес-функцию. Первый сценарий — `repository-change`.

Наблюдатель, контрольные точки каждого решения и вызова инструмента, а также
обучение через ветвление исполнения входят в замысел прототипа. Контракты
наблюдателя и локальный file-backed SQLite journal покрыты unit-тестами;
collector, отчёты и учебные ветки отсутствуют. Материал для коллег:
[объяснение проекта](docs/29-agent-explained.md).
Память будет слоистой и ограниченной: после шести месяцев — месячные, после года
— годовые сводки; [полная политика](docs/30-memory-model.md).

## Состояние

Есть 20 JSON Schema (16 базовых и 4 контракта наблюдателя), fixtures,
детерминированный reference flow подготовки изменений, SQLite runtime, mock
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

Полный offline suite после Batch GC / EXP-589 на 2026-10-08: 1096 тестов,
1087 прошли, 9 пропущено.
Это подтверждает только покрытые тестами локальные свойства на текущей машине,
не безопасность всей цепочки, live Worker, независимость verifier или реальную
публикацию. Подробнее — в документе 27.

Для повторного прогона уже сохранённого verified candidate есть отдельная
безсекретная команда `scripts/replay_staged_candidate.py`. Ей нужны существующая
SQLite-стадия, её точный digest и новый абсолютный путь для output DB; output не
перезаписывается. Команда ограничена закреплённым публичным snapshot, target и
verifier, требует явный `RUN_DOCKER_SANDBOX_TESTS=1`, делает только anonymous
read-only GitHub запросы и Docker verification. Она не вызывает модель, не
читает credentials, не создаёт approval и не публикует изменения. Повторно
полученный stage остаётся same-host evidence, а snapshot — GitHub API claim.

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

`ProcessEnvironmentCredentialSource` — только lazy-адаптер к одному явно
переданному process mapping. Он не читает ambient environment или `.env` сам,
не хранит/не шифрует секрет и не заменяет OS vault. Для ограниченного MVP fixed
Worker CLI по умолчанию запрашивает ключ через интерактивный скрытый ввод
(`TerminalPromptCredentialSource`) после точного подтверждения запуска; при
небезопасном echo fallback ввод отклоняется. Источник указывается в task card;
сам Worker запуск всё равно требует точную READY-карточку и свежее подтверждение
live-вызова.

Для фиксированной remote композиции подготовлен
`scripts/run_pinned_deepseek_worker.py <new-absolute-stage.sqlite3>`: он
показывает target, model, endpoint и путь, проверяет наличие только закреплённых
Docker images, затем требует фразу `RUN EXP-566 ONCE`. После отдельного
подтверждения EXP-566 он делает только anonymous GitHub reads и максимум одну
DeepSeek попытку, сохраняя verified SQLite stage. По умолчанию эту команду
запускать нельзя: текущая карточка разработки не разрешает live-вызов, а
пер-канальный лимит не является account-level USD spend cap.

Remote runtime принимает явный абсолютный `stage_database_path`. Только при
результате `verified` evidence содержит этот путь, если файл существует и
открывается как SQLite в read-only режиме; неуспешные запуски и синтетические
профили без locator его не раскрывают. Для последующего локального ревью
оператору следует выбирать стабильный путь вне автоматически удаляемого
каталога. Это locator локальной стадии, а не гарантия резервного копирования,
crash recovery или production durability.

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
