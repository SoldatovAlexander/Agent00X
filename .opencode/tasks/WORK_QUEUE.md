# Controlled work queue

Control Plane (пользователь и Codex) добавляет в эту очередь утверждённые task
cards. Executor исполняет только карточки со статусом `READY`.

## Batch A — последовательное исполнение

В этом batch executor исполняет только `READY` карточки строго по возрастанию ID:
одна карточка → её проверки → `git status`/diff → один локальный commit →
следующая карточка. Не пропускай карточку и не переходи к `DRAFT`, `REVIEW` или
`CLOSED`. При ошибке проверки, неясном scope или конфликте предсуществующих правок
останови весь batch и верни evidence. Review Batch A выполняет Control Plane после
всех его commit.

## EXP-001 — smoke-проверка управляемого исполнителя

Статус: CLOSED
Цель: подтвердить, что executor читает очередь, выполняет утверждённую read-only
проверку и возвращает воспроизводимое evidence без изменения репозитория.
Гипотеза: executor соблюдает READY task card, запускает штатный набор тестов и не
расширяет scope до правок, commit, сети или внешних сред.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: любые изменения файлов, Docker, testdev, Agent00X-sandbox, сеть,
создание branch/PR, commit и push.
Разрешённые пути:
- (none; задача только для чтения и запуска указанной проверки)
Критерии приёмки:
- штатная команда проверки выполнена;
- в evidence есть её точная команда, результат и число выполненных/пропущенных тестов;
- `git status` и `git diff` не показывают изменений, созданных executor;
- нет commit, внешних обращений или изменений конфигурации.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: DENIED
Ограничения и риски:
- результат подтверждает только соблюдение OpenCode workflow и локальный набор тестов;
  он не доказывает изоляцию, testdev, Docker или GitHub publication chain.
Результат Control Plane:
- ACCEPTED 2026-09-10: executor выполнил штатный прогон, получил `Ran 83 tests`
  и `OK (skipped=1)`, не изменил файлы, не создал commit и не использовал внешние
  среды. Evidence проверен Control Plane.

## EXP-002 — зафиксировать verified manifest

Статус: CLOSED
Цель: устранить подмену workspace и повторно переданного mapping после `prepare_change`.
Гипотеза: manifest строится только из immutable content, зафиксированного в `PreparedChange` до verification.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: GitHub Actuator, Broker, schemas, deployment, Docker, testdev и Agent00X-sandbox.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- regression test меняет и workspace-файл, и повторно переданный mapping на одинаковое новое содержание; manifest отклоняет попытку;
- успешный сценарий manifest остаётся рабочим, пустой или незафиксированный список файлов отклоняется;
- проверка не доверяет повторному аргументу mapping.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- закрывает только локальную связь prepared change → manifest, не GitHub publication chain.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `e98cce3` добавил immutable verified contents и
  regression cases для подменённого workspace/mapping; полный suite прошёл.

## EXP-003 — связать policy decision с одобренным digest

Статус: CLOSED
Цель: исключить allow decision при подмене `actuator_request.staged_change_digest`.
Гипотеза: `DeterministicPolicy.decide` fail-closed отклоняет request с подменённым digest даже при valid approval/intent и allowlisted IDs.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: GitHub API, Broker credential, manifest, schemas, deployment, Docker, testdev и Agent00X-sandbox.
Разрешённые пути:
- src/app_contracts/authority.py
- src/app_contracts/actuator.py
- src/app_contracts/github_actuator.py
- tests/test_authority.py
- tests/test_actuator.py
- tests/test_github_app.py
Критерии приёмки:
- regression test меняет только `actuator_request.staged_change_digest` и ожидает deny;
- matching chain возвращает schema-valid allow decision;
- decision не сообщает digest, не совпадающий с проверенным staged change;
- причина deny описывает mismatch без чувствительных данных.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- это локальный policy gate, а не доказательство publication/recovery.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `274fbdc` fail-closed отклоняет request digest,
  отличный от verified staged digest; полный suite прошёл.

## EXP-004 — добавить контракт ObservationEvent

Статус: CLOSED
Цель: реализовать строгую JSON Schema и unit tests для минимального `ObservationEvent` из документа 28.
Гипотеза: validation принимает безопасное структурированное событие и отклоняет неизвестные поля, неверный event type, ID и время.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: SQLite, Collector, Observer, subagents, prompts, runtime instrumentation, Docker, testdev и внешние сервисы.
Разрешённые пути:
- schemas/observation-event.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- schema использует поддерживаемый проектом JSON Schema subset и `additionalProperties: false`;
- определены version, ID, event type из документа 28, process/run/branch/task/agent identity, sequence, timestamps, classification и redaction status;
- позитивный fixture валидируется; unknown field, неверный event type, ID и `date-time` отклоняются;
- tests не содержат secrets или raw prompts.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- schema не реализует append-only журнал, causality runtime или redaction service.
Результат Control Plane:
- ACCEPTED 2026-09-10 после remediation `EXP-008`: базовая schema/tests из
  `ea4fd5a` и строгий allowlist `safe_parameters` из `f734226` прошли review.

## EXP-005 — добавить контракт Checkpoint

Статус: CLOSED
Цель: реализовать строгую JSON Schema и unit tests для минимального `Checkpoint` из документа 28.
Гипотеза: schema фиксирует принадлежность checkpoint, его тип, cursor и versioned references, не выдавая agent новых полномочий.
Зависит от: EXP-004
Среда исполнения: local
Внешняя цель: none
Вне scope: восстановление процесса, запись до dispatch, SQLite, authority mutation, Docker, testdev и внешние сервисы.
Разрешённые пути:
- schemas/checkpoint.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- schema строго валидирует ID, kind `decision|tool_call`, process/run/branch/agent identity, trigger event, cursor, versioned refs, completeness и restore mode;
- позитивный fixture проходит; unknown field, неверный kind, ID и время (если включено) отклоняются;
- checkpoint содержит references, но не credentials, approval values или secret contents.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- schema не доказывает запись checkpoint до dispatch.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `627f06a` добавил строгую Checkpoint schema и
  negative/positive tests; полный suite прошёл.

## EXP-006 — добавить контракт LearningCorrection

Статус: CLOSED
Цель: реализовать строгую JSON Schema и unit tests для versioned `LearningCorrection` из документа 28.
Гипотеза: correction связывается с checkpoint/evidence и review, но не становится capability, approval или policy decision.
Зависит от: EXP-005
Среда исполнения: local
Внешняя цель: none
Вне scope: применение correction, обучение модели, branch runtime, изменение policy, Docker, testdev и внешние сервисы.
Разрешённые пути:
- schemas/learning-correction.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- schema строго валидирует ID, immutable version, checkpoint/target-event refs, author, timestamps, applicability, evidence refs и review status;
- lifecycle ограничен `proposed`, `evaluated`, `approved`, `rejected`;
- позитивный fixture проходит; unknown field, неверный status, отсутствующая обязательная ссылка и secret-like поле отклоняются;
- schema не содержит capability, credential, token или direct policy mutation.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- контракт не заменяет human review и не реализует применение correction.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `fe3326e` добавил изолированный versioned contract
  без capability/credential fields; полный suite прошёл.

## EXP-007 — добавить контракт MemorySummary

Статус: CLOSED
Цель: реализовать строгую JSON Schema и unit tests для `MemorySummary` из документа 30.
Гипотеза: summary хранит scope, refs, digest, completeness и retention metadata как отдельный артефакт, не подменяя source или process state.
Зависит от: EXP-006
Среда исполнения: local
Внешняя цель: none
Вне scope: retention scheduler, Context Compiler, deletion, legal hold, SQLite, Docker, testdev и внешние сервисы.
Разрешённые пути:
- schemas/memory-summary.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- schema валидирует summary kind `monthly|yearly|topic`, period, scope, source refs/digest, content, omissions, redaction/completeness, build, timestamps и retention status;
- позитивный fixture проходит; unknown field, неверный kind, invalid period/date-time и secret-like поле отклоняются;
- schema не содержит approval, capability, credential, token или изменение process state.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- schema не реализует retention policy или Context Compiler.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `4869b42` добавил строгий summary contract и
  отрицательные проверки; полный suite прошёл.

## EXP-008 — исключить произвольные secret-like параметры из ObservationEvent

Статус: CLOSED
Цель: устранить неограниченный `safe_parameters` в контракте ObservationEvent.
Гипотеза: event хранит только typed, redacted metadata или artifact reference, а
schema и tests отвергают token/secret-like keys и raw prompt-like payload.
Зависит от: EXP-004
Среда исполнения: local
Внешняя цель: none
Вне scope: Collector, runtime instrumentation, redaction service, SQLite,
Docker, testdev и внешние сервисы.
Разрешённые пути:
- schemas/observation-event.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- `safe_parameters` больше не допускает произвольный object с неограниченными
keys/values; выбрана строгая безопасная representation, совместимая с проектным
validator subset;
- отдельные tests отклоняют token/secret-like keys и raw prompt-like payload;
- valid event сохраняет возможность сослаться на допустимые redacted parameters
или artifact reference;
- existing observation tests остаются зелёными.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- schema не заменяет реальную redaction pipeline; она лишь не допускает сырой
payload через этот контракт.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `f734226` ввёл allowlist typed metadata и negative
  tests для secret-like keys и prompt-like payload; полный suite прошёл.

## EXP-009 — зарегистрировать R0 schemas в contract catalog

Статус: CLOSED
Цель: дать единую проверяемую точку для всех R0 schema files, не добавляя runtime.
Гипотеза: catalog test обнаруживает отсутствующую или невалидную R0 schema.
Зависит от: EXP-007
Среда исполнения: local
Внешняя цель: none
Вне scope: schema semantics, SQLite, Docker, testdev и внешние сервисы.
Разрешённые пути:
- tests/test_contracts.py
- tests/test_observer_contracts.py
Критерии приёмки:
- тест перечисляет ObservationEvent, Checkpoint, LearningCorrection и MemorySummary;
- отсутствие или невалидный JSON любого файла делает тест красным;
- существующие chain checks не ослаблены.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- catalog не связывает новые contracts с runtime event store.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `ec2f7a4` регистрирует все четыре R0 schema и
  проверяет их JSON/fixtures, не ослабляя существующие chain checks.

## EXP-010 — добавить append-only ObservationStore

Статус: CLOSED
Цель: реализовать минимальное in-memory append-only хранилище валидных ObservationEvent.
Гипотеза: повтор event ID с тем же content идемпотентен, с иным content отклоняется.
Зависит от: EXP-009
Среда исполнения: local
Внешняя цель: none
Вне scope: SQLite migration, distributed locking, Observer UI, Docker и testdev.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- store принимает только schema-valid events;
- duplicate ID с тем же digest не создаёт вторую запись;
- duplicate ID с отличным content отклоняется;
- чтение возвращает insertion order без mutable internal state.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- in-memory store не является durable audit journal.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `5a3d34e` реализует schema validation,
  idempotency/conflict и detached ordered reads; полный suite прошёл.

## EXP-011 — связать Checkpoint с event cursor

Статус: CLOSED
Цель: добавить deterministic validation связи Checkpoint с ранее записанным event cursor.
Гипотеза: checkpoint не может ссылаться на несуществующий event или cursor впереди истории.
Зависит от: EXP-010
Среда исполнения: local
Внешняя цель: none
Вне scope: dispatch, recovery, SQLite, Docker, testdev и внешние сервисы.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
- tests/test_observer_contracts.py
Критерии приёмки:
- валидная checkpoint reference принимается;
- отсутствующий trigger event и cursor за концом журнала отклоняются;
- проверка не возвращает event payload без явного read API.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не доказывает checkpoint-before-dispatch.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `a06956f` fail-closed отклоняет отсутствующий
  trigger и cursor за журналом; payload без read API не возвращается.

## EXP-012 — fail-closed checkpoint pre-dispatch gate

Статус: CLOSED
Цель: добавить один локальный pre-dispatch gate, который запрещает действие при ошибке записи checkpoint.
Гипотеза: tool invocation не стартует, если checkpoint/event intent не сохранены.
Зависит от: EXP-011
Среда исполнения: local
Внешняя цель: none
Вне scope: LLM Worker, network, production tool execution, Docker и testdev.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- тест фиксирует checkpoint и intent до mock dispatch;
- injected store failure блокирует mock dispatch;
- success path сохраняет устойчивую последовательность событий.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- это один local path, не общее инструментирование Runtime.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-10: commit `59a9602` вызывает `check_checkpoint`,
  но не записывает checkpoint в `ObservationStore`; success test подтверждает
  только trigger event и intent. Карточка требует сохранить checkpoint и intent
  до dispatch, поэтому критерий не выполнен.
- ACCEPTED 2026-09-10 после независимой remediation: commit `74d2928` сохраняет
  idempotent checkpoint до intent и dispatch, а failure checkpoint блокирует intent
  и side effect. Полный suite прошёл.

## EXP-013 — adversarial binding policy decision к actuator boundary

Статус: REVIEW
Цель: доказать тестом, что подмена request после allow decision не достигает mock actuator.
Гипотеза: actuator сверяет allow decision с точным request перед side effect.
Зависит от: EXP-003
Среда исполнения: local
Внешняя цель: none
Вне scope: реальный GitHub API, Broker key, Docker и testdev.
Разрешённые пути:
- src/app_contracts/actuator.py
- src/app_contracts/github_actuator.py
- src/app_contracts/authority.py
- tests/test_adversarial.py
- tests/test_actuator.py
- tests/test_authority.py
- tests/test_broker.py
- tests/test_github_app.py
Критерии приёмки:
- негативные случаи меняют repository, branch, digest или idempotency key после allow;
- каждый случай отклоняется до mock boundary;
- matching request по-прежнему достигает mock boundary.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не является доказательством внешней GitHub транзакции.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-10: commit `b99e77f` защищает branch/key лишь когда
  вызывающий передал optional `intent`. Реальный `BrokeredGitHubActuator` intent
  не передаёт, поэтому согласованная подмена branch и idempotency key обходит
  новую проверку. Нужен fail-closed binding на фактическом brokered path.
- SCOPE EXPANDED 2026-09-10: reviewer-remediator подтвердил bypass и теперь может
  обновить все затронутые brokered callers/tests. Приёмка требует regression с
  согласованной подменой branch+key+grant, которая не достигает mock boundary.
- CHANGES REQUESTED 2026-09-10 (post-remediation review): commit `ce6c0b0`
  делает `intent` обязательным и сравнивает его с request, но не связывает intent
  с approval. Поэтому новый согласованный `request + intent + grant` с тем же
  staged digest всё ещё может пройти policy и boundary. Не принимать до выбора и
  реализации approval-bound intent representation (например, digest полного
  approved intent либо branch/key в approval contract) с end-to-end regression.

## EXP-014 — multi-file regression для verified manifest

Статус: CLOSED
Цель: расширить manifest binding на несколько файлов и порядок путей.
Гипотеза: manifest включает только полный verified set независимо от порядка input mapping.
Зависит от: EXP-002
Среда исполнения: local
Внешняя цель: none
Вне scope: file deletion publication, GitHub API, Docker и testdev.
Разрешённые пути:
- tests/test_repository_process.py
- fixtures/repository/project/test_calculator.py
- src/app_contracts/repository_process.py
Критерии приёмки:
- multi-file happy path детерминирован по path order;
- missing или extra path отклоняется;
- подмена одного файла после verification отклоняет весь manifest.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- удаление файлов отдельная publication semantics и не включено.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `6a0ffe5` покрывает canonical path order,
  missing/extra paths и подмену одного verified файла.

## EXP-015 — reconciliation regression для частичной публикации

Статус: CLOSED
Цель: добавить deterministic local tests для retry/reconciliation частичной GitHub publication.
Гипотеза: повтор с тем же idempotency key не создаёт второй PR receipt после известного результата.
Зависит от: EXP-013
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub App, credentials, push, Docker и testdev.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- имитированы failure после branch/create-file/PR response;
- reconciliation возвращает существующий receipt или явный unknown outcome;
- retry не выполняет слепой duplicate side effect.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- mock HTTP не подтверждает поведение реального GitHub API.
Результат Control Plane:
- ACCEPTED 2026-09-10: commit `2f3f5f9` fail-closed обрабатывает неизвестное
  состояние ветки и покрывает reconciliation branch/PR локальными tests.

## EXP-016 — Docker sandbox opt-in smoke evidence

Статус: CLOSED
Цель: воспроизводимо запустить существующий opt-in Docker sandbox test локально.
Гипотеза: подготовленный image/profile выполняет test без host fallback.
Зависит от: none
Среда исполнения: docker
Внешняя цель: none
Вне scope: изменение Dockerfile/image, testdev, GitHub и deployment.
Разрешённые пути:
- tests/test_sandbox.py
Критерии приёмки:
- выполнена только команда с `RUN_DOCKER_SANDBOX_TESTS=1` из task evidence;
- зафиксированы Docker availability, result и skipped/failure reason;
- файловые изменения и commit запрещены.
Проверки:
- RUN_DOCKER_SANDBOX_TESTS=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- docker info
Commit: DENIED
Ограничения и риски:
- Docker daemon может быть недоступен; в этом случае вернуть evidence и остановить batch.
Результат Control Plane:
- ACCEPTED AS ENVIRONMENT EVIDENCE 2026-09-10: Docker daemon доступен, но
  образ `python:3.12-alpine` отсутствует. Opt-in suite ожидаемо остановился до
  `docker run`; образ не скачивался и файлов/commit не создано.

## EXP-017 — Docker sandbox negative resource evidence

Статус: BLOCKED
Цель: воспроизводимо выполнить существующую adversarial Docker проверку ресурсов.
Гипотеза: Docker profile ограничивает процесс в пределах тестируемого сценария.
Зависит от: EXP-016
Среда исполнения: docker
Внешняя цель: none
Вне scope: изменение image/profile, testdev, GitHub и deployment.
Разрешённые пути:
- tests/test_sandbox.py
Критерии приёмки:
- выполнен opt-in Docker test с фиксированным evidence;
- результат отделён от утверждений о полной host isolation;
- файловые изменения и commit запрещены.
Проверки:
- RUN_DOCKER_SANDBOX_TESTS=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- docker info
Commit: DENIED
Ограничения и риски:
- failure среды не исправлять в рамках этой карточки.
Результат Control Plane:
- BLOCKED 2026-09-10: prerequisite image `python:3.12-alpine` отсутствует.
  Отдельное решение Control Plane о pull/подготовке образа требуется до READY.

## EXP-018 — подготовить testdev preflight read-only card

Статус: CLOSED
Цель: определить безопасную read-only команду проверки broker preflight на testdev без её выполнения.
Гипотеза: Control Plane может сформировать последующую remote card без передачи secret path или service mutation.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: SSH, testdev access, `.env`, key, systemctl, restart, deployment и GitHub.
Разрешённые пути:
- deploy/agent00x-broker-preflight.service
- deploy/agent00x-broker-preflight.user.service
- docs/27-implementation-status.md
- .opencode/tasks/WORK_QUEUE.md
Критерии приёмки:
- executor предлагает в evidence одну read-only remote команду и её ожидаемый безопасный output contract;
- не изменяет очередь, deploy files или remote state;
- не выполняет remote command.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: DENIED
Ограничения и риски:
- предложение не является разрешением на testdev access; Control Plane создаёт отдельную card.
Результат Control Plane:
- ACCEPTED 2026-09-10: executor не менял локальные/remote файлы и предложил одну
  безопасную read-only `systemctl show` команду без EnvironmentFile/secret output.

## EXP-019 — testdev broker preflight observation

Статус: DRAFT
Цель: read-only проверить статус broker preflight на testdev.
Зависит от: EXP-018
Среда исполнения: testdev
Внешняя цель: none
Вне scope: `.env`, keys, restart, deploy, publish и GitHub.
Разрешённые пути:
- (none; remote read-only action)
Критерии приёмки:
- точная SSH/systemctl command и expected output утверждены Control Plane.
Проверки:
- определяется перед READY
Разрешённые внешние команды:
- определяется перед READY
Commit: DENIED
Ограничения и риски:
- никогда не выполнять без отдельного подтверждения в OpenCode.

## EXP-020 — Agent00X-sandbox snapshot read-only spike

Статус: DRAFT
Цель: подтвердить base commit и allowlist sandbox repository без side effects.
Зависит от: EXP-015
Среда исполнения: local
Внешняя цель: Agent00X-sandbox
Вне scope: branch, PR, push, credential access, publication и testdev.
Разрешённые пути:
- (none; external read-only action)
Критерии приёмки:
- точная read-only git command и expected evidence утверждены Control Plane.
Проверки:
- определяется перед READY
Разрешённые внешние команды:
- определяется перед READY
Commit: DENIED
Ограничения и риски:
- historical spike не доказывает безопасную publication chain.

## Batch B — локальное укрепление контрактов

`executor` исполняет только `READY` карточки `EXP-021`—`EXP-040` строго по
возрастанию ID. Каждая карточка: scope → проверки → `git status`/diff → один
локальный commit → следующая карточка. `REVIEW`, `BLOCKED`, `DRAFT` и `CLOSED`
не выполнять. При красной проверке, конфликте предсуществующих правок или
неясном scope остановить Batch B и вернуть evidence Control Plane.

## EXP-021 — валидировать структуру JSON Schema subset

Статус: CLOSED
Цель: fail-closed отвергать malformed schema declarations до валидации instance.
Гипотеза: validator не пропускает неправильные `required`, `properties` и
`additionalProperties` как неявно ослабленную schema.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: новые schema keywords, внешние validators, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- malformed `required`/`properties`/`additionalProperties` дают детерминированную
  ошибку validator до обработки instance;
- существующие project schemas и fixtures остаются валидными;
- test доказывает, что malformed schema не расширяет accepted payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять поддержку новых JSON Schema keywords.
Результат Control Plane:
- ACCEPTED 2026-09-10: `f21d605` валидирует declarations fail-closed; 20 текущих
  schema files и полный suite подтверждены.

## EXP-022 — зафиксировать canonical digest edge cases

Статус: CLOSED
Цель: покрыть детерминированность digest для unicode, порядка ключей и NaN.
Гипотеза: canonical digest одинаков для семантически одинаковых JSON mappings и
fail-closed отклоняет не-JSON numeric values.
Зависит от: EXP-021
Среда исполнения: local
Внешняя цель: none
Вне scope: смена hash algorithm, schema format, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/digests.py
- tests/test_contracts.py
Критерии приёмки:
- tests фиксируют equality digest для разного порядка ключей и UTF-8 текста;
- `NaN`/infinity не дают digest и не сериализуются молча;
- существующие digest chain checks не ослаблены.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- hash algorithm и формат префикса `sha256:` не менять.
Результат Control Plane:
- ACCEPTED 2026-09-10: `5ada8cc` добавляет deterministic edge-case regressions
  без изменения алгоритма или production surface.

## EXP-023 — усилить terminal transitions state machine

Статус: CLOSED
Цель: доказать, что terminal process state нельзя повторно открыть переходом.
Гипотеза: state machine fail-closed отвергает transition из terminal state, в том
числе при повторном command/request.
Зависит от: EXP-022
Среда исполнения: local
Внешняя цель: none
Вне scope: SQLite runtime, recovery policy, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/state_machine.py
- tests/test_state_machine.py
Критерии приёмки:
- negative tests покрывают переходы из каждого terminal state;
- допустимые существующие transition остаются рабочими;
- error не раскрывает payload процесса.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не менять перечень бизнес-состояний без необходимости теста.
Результат Control Plane:
- ACCEPTED 2026-09-10: `df603fa` покрывает все terminal states и targets.

## EXP-024 — проверить optimistic concurrency SQLite runtime

Статус: CLOSED
Цель: добавить adversarial regression для stale expected version в durable store.
Гипотеза: второй writer с устаревшей версией не меняет state и audit history.
Зависит от: EXP-023
Среда исполнения: local
Внешняя цель: none
Вне scope: schema migration, threaded load test, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- stale update отклоняется без частичной state/audit записи;
- успешная update сохраняет последовательность version/audit;
- regression воспроизводим в temporary SQLite database.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять distributed locking или менять storage engine.
Результат Control Plane:
- ACCEPTED 2026-09-10: `78aeb88` доказывает отсутствие частичной state/audit
  записи от stale writer.

## EXP-025 — защитить audit history от mutable caller payload

Статус: CLOSED
Цель: проверить, что последующая мутация caller mapping не меняет сохранённое audit event.
Гипотеза: runtime store сохраняет detached canonical event, а не ссылку на объект вызывающего.
Зависит от: EXP-024
Среда исполнения: local
Внешняя цель: none
Вне scope: новые audit fields, encryption, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- test меняет nested caller payload после записи и подтверждает неизменность readback;
- digest/order existing audit checks остаются зелёными;
- при необходимости patch минимален и не меняет public API без test.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не обещать tamper-proof storage от администратора host.
Результат Control Plane:
- ACCEPTED 2026-09-10: `08b3909` закрепляет detached audit read/write behavior.

## EXP-026 — закрыть unsafe repository path variants

Статус: CLOSED
Цель: отклонять path normalization variants до подготовки repository change.
Гипотеза: `./`, empty segment, backslash и traversal-like path не достигают workspace write.
Зависит от: EXP-025
Среда исполнения: local
Внешняя цель: none
Вне scope: symlink policy вне fixture workspace, GitHub API, Docker, testdev.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- negative cases покрывают `./file`, `dir//file`, `dir\\file`, `../file`;
- нормальные nested relative paths продолжают работать;
- rejected input не оставляет файл в ephemeral workspace.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не вводить поддержку удаления файлов или symlink publication semantics.
Результат Control Plane:
- ACCEPTED 2026-09-10: `7fed78e` отклоняет normalization/traversal variants до
  workspace write и сохраняет nested relative paths.

## EXP-027 — доказать целостность publish manifest content digest

Статус: CLOSED
Цель: добавить negative test подмены `PublishableFile.content_digest` после manifest construction.
Гипотеза: publisher повторно сверяет digest bytes и не отправляет подменённый файл.
Зависит от: EXP-026
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, credentials, branch/PR/push, Docker, testdev.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- tampered content или digest отклоняется до HTTP PUT/POST;
- matching verified file сохраняет текущий happy path;
- test явно подтверждает отсутствие provider-call mock при reject.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- это local mock boundary, не live GitHub proof.
Результат Control Plane:
- ACCEPTED 2026-09-10: `2ef8b79` валидирует весь manifest до reconciliation и
  любого provider call.

## EXP-028 — fail-closed для malformed GitHub reconciliation response

Статус: CLOSED
Цель: покрыть malformed response branch/PR reconciliation.
Гипотеза: нераспознаваемый ответ провайдера даёт unknown/error, а не absent и не retry.
Зависит от: EXP-027
Среда исполнения: local
Внешняя цель: none
Вне scope: live API, retry scheduler, credentials, Docker, testdev.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed branch/PR payload не вызывает POST/PUT side effect;
- valid known receipt остаётся возвращаемым;
- test различает absent и malformed/unknown по безопасному результату или error.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять network retries в этой карточке.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-10: `1f7c238` считает `None` признаком absent branch,
  хотя production `_get_json` не возвращает `None` для подтверждённого 404. Нужен
  явный безопасный absent-result или отдельная обработка HTTP 404; `None` и любой
  malformed/transport outcome должны оставаться unknown без POST/PUT.
- ACCEPTED 2026-09-10 после remediation `2680b64`: production `_get_json`
  преобразует только HTTP 404 в explicit absent signal; 500, `None` и malformed
  payload блокируют publication без side effect. Полный suite прошёл.

## EXP-029 — проверить encoding GitHub content path

Статус: CLOSED
Цель: доказать безопасное URL-encoding вложенного пути при публикации файла.
Гипотеза: path с пробелом/`#` кодируется как один repository content resource и не меняет branch.
Зависит от: EXP-028
Среда исполнения: local
Внешняя цель: none
Вне scope: live API, расширение allowlist, Docker, testdev, GitHub credentials.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- mock test проверяет endpoint path и branch payload для special characters;
- traversal и absolute paths остаются запрещены;
- existing normal-file publication tests остаются зелёными.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять новые provider operations.
Результат Control Plane:
- ACCEPTED 2026-09-10: `20014c4` фиксирует encoding и rejection unsafe paths.

## EXP-030 — зафиксировать policy decision expiry boundary

Статус: CLOSED
Цель: проверить точную границу expiry разрешения policy decision.
Гипотеза: decision, истёкший на текущем instant, не может быть использован как allow.
Зависит от: EXP-029
Среда исполнения: local
Внешняя цель: none
Вне scope: clock service, distributed time, GitHub, Docker, testdev.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- tests покрывают before/at/after expiry с timezone-aware time;
- deny/exception не раскрывает approval contents;
- existing valid approval flow остаётся working.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не менять decision TTL default без явного основания.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-10: `95013a3` добавил helper и unit test, но ни один
  actuator boundary его не вызывает. Карточка требует enforcement при use time,
  поэтому нужен actual-call regression до mock/provider boundary.
- CHANGES REQUESTED 2026-09-10 (повторное ревью `067dc7e`): `DecisionUseBoundary`
  — локальный тестовый surrogate, а `publish_authorized_request` всё ещё не
  вызывает `check_decision_usable`. Вызови gate в реальной actuator boundary до
  `endpoint.publish`/broker-provider boundary, передай timezone-aware `now`
  явно либо через узко ограниченный clock seam, и добавь regression на
  before/at/after expiry, доказывающий отсутствие mock side effect. Не меняй TTL.
- ACCEPTED 2026-09-10: `d5fc7bb` проводит `check_decision_usable` через
  `publish_authorized_request` до side effect и через brokered boundary до
  открытия provider channel; actual-call before/at/after регрессии зелёные.
  Независимый полный прогон: 187 tests, OK (skipped=1). Local only, без push.

## EXP-031 — gateway rejects unknown write-like operation

Статус: CLOSED
Цель: добавить regression для неизвестной операции с write-like envelope traits.
Гипотеза: Gateway не классифицирует неизвестное действие как Fast Path.
Зависит от: EXP-030
Среда исполнения: local
Внешняя цель: none
Вне scope: новые Gateway policies, external classifier, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- неизвестная операция не получает Fast allow;
- known internal read-only flow не регрессирует;
- evidence фиксирует deterministic reason code без payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не подключать внешнюю policy service.
Результат Control Plane:
- ACCEPTED 2026-09-10: `ced36a3` закрепляет fail-closed route unknown operation.

## EXP-032 — broker replay после provider failure

Статус: CLOSED
Цель: подтвердить single-use Credential Use Grant при ошибке открытия channel.
Гипотеза: повтор grant не становится разрешённым после failure и не minting второй token.
Зависит от: EXP-031
Среда исполнения: local
Внешняя цель: none
Вне scope: реальные credentials, GitHub App, Docker, testdev, network.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- injected provider/channel failure и повтор того же grant детерминированно отклоняются;
- successful single-use flow не регрессирует;
- tests не содержат token values.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не менять minting protocol или добавлять persistent broker state.
Результат Control Plane:
- ACCEPTED 2026-09-10: `a41c96c` подтверждает single-use grant после failure.

## EXP-033 — mock GitHub idempotency conflict regression

Статус: CLOSED
Цель: отклонять reuse idempotency key с отличающимся request payload.
Гипотеза: idempotency key нельзя использовать для маскировки другого side effect.
Зависит от: EXP-032
Среда исполнения: local
Внешняя цель: none
Вне scope: реальный GitHub API, publication journal, Docker, testdev.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- same key + identical request возвращает исходный receipt;
- same key + changed branch/digest/repository отклоняется до receipt;
- tests не меняют external state.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- mock behaviour не доказывает semantics реального провайдера.
Результат Control Plane:
- ACCEPTED 2026-09-10: `f5f3587` закрепляет reject for same key/different effect.

## EXP-034 — journal unknown outcome blocks blind retry

Статус: CLOSED
Цель: покрыть recovery journal при неизвестном исходе external side effect.
Гипотеза: recovery требует reconciliation и не вызывает publisher повторно.
Зависит от: EXP-033
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, SQLite migration, Docker, testdev.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- simulated unknown outcome не создаёт второй mock side effect;
- known receipt корректно завершает reconciliation;
- error/reason code не содержит credential или raw provider response.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не реализовывать real provider polling.
Результат Control Plane:
- ACCEPTED 2026-09-10: `14f89ff` доказывает stable reconciliation-required state.

## EXP-035 — расширить canary scan agent-facing surfaces

Статус: CLOSED
Цель: проверить scanner на вложенные agent-facing structures и safe false-negative boundary.
Гипотеза: sentinel обнаруживается в nested mapping/list, а redacted reference не считается secret value.
Зависит от: EXP-034
Среда исполнения: local
Внешняя цель: none
Вне scope: OS process list, filesystem-wide scan, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- nested canary даёт finding с безопасным location, но без вывода самого value;
- допустимый artifact reference не даёт finding;
- scanner не получает доступ к `.env` или credential files.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- scanner не доказывает отсутствие секрета во всех surface host.
Результат Control Plane:
- ACCEPTED 2026-09-10: `df3086f` покрывает nested surfaces/redacted reference.

## EXP-036 — добавить observer cases в machine-readable threat corpus

Статус: CLOSED
Цель: зафиксировать инъекции secret-like поля и raw prompt-like path как исполняемые threat cases.
Гипотеза: threat corpus сохраняет security regression ObservationEvent без включения реальных secrets.
Зависит от: EXP-035
Среда исполнения: local
Внешняя цель: none
Вне scope: новые production controls, external corpus, Docker, testdev, GitHub.
Разрешённые пути:
- fixtures/threats/mvp-security-cases.json
- tests/test_threat_corpus.py
- tests/test_observer_contracts.py
Критерии приёмки:
- corpus содержит минимум два synthetic observer cases с expected deny;
- test связывает case с contract validation, не копируя sensitive value в output;
- существующие corpus cases сохраняются и остаются валидными.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- threat corpus не является полным security audit.
Результат Control Plane:
- ACCEPTED 2026-09-10: `37e7642` добавляет два synthetic observer threat case.

## EXP-037 — проверить causal references ObservationEvent

Статус: CLOSED
Цель: усилить schema/tests причинных ссылок event без добавления runtime graph.
Гипотеза: causal reference не может быть пустой, malformed или secret-like payload.
Зависит от: EXP-036
Среда исполнения: local
Внешняя цель: none
Вне scope: graph traversal, SQLite causal index, Docker, testdev, GitHub.
Разрешённые пути:
- schemas/observation-event.schema.json
- tests/test_observer_contracts.py
Критерии приёмки:
- valid event с event-id references остаётся schema-valid;
- empty/malformed causal ref и unknown nested field отклоняются;
- никаких raw prompts, tokens или свободных payload objects не добавлено.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- schema не доказывает существование referenced event в store.
Результат Control Plane:
- ACCEPTED 2026-09-10: `fa53eae` подтверждает действующую строгую schema testами.

## EXP-038 — связать ObservationStore event identity с process context

Статус: CLOSED
Цель: fail-closed отвергать Checkpoint, чей trigger принадлежит другому process/run/branch.
Гипотеза: cursor и trigger недостаточны без identity binding к checkpoint context.
Зависит от: EXP-037
Среда исполнения: local
Внешняя цель: none
Вне scope: durable store, multi-process locking, dispatch gate, Docker, testdev.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- cross-process, cross-run и cross-branch trigger cases отклоняются;
- matching identity checkpoint остаётся accepted;
- reject не возвращает stored event payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не превращать in-memory store в durable journal.
Результат Control Plane:
- ACCEPTED 2026-09-10: `691fa69` проверяет process/run/branch identity без payload leak.

## EXP-039 — проверить MemorySummary time interval semantics

Статус: CLOSED
Цель: добавить deterministic validation, что `period_end` не раньше `period_start`.
Гипотеза: schema-valid format сам по себе недостаточен для корректного interval summary.
Зависит от: EXP-038
Среда исполнения: local
Внешняя цель: none
Вне scope: retention scheduler, legal hold, deletion, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_observer_contracts.py
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- pure semantic validator для MemorySummary детерминированно отклоняет reversed interval;
- equal/forward valid interval принимается согласно принятой семантике, явно зафиксированной test;
- не добавлять secret-bearing fields или free-form policy mutation.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не реализовывать реальную retention policy.
Результат Control Plane:
- ACCEPTED 2026-09-10: `b681194` добавляет pure interval validator с explicit
  zero-length semantics и tests.

## EXP-040 — contract catalog regression против лишней R0 schema

Статус: CLOSED
Цель: сделать R0 catalog явным allowlist, чтобы неподтверждённый schema file не выглядел частью R0.
Гипотеза: catalog test сообщает расхождение между declared R0 set и обнаруженными R0-named files.
Зависит от: EXP-039
Среда исполнения: local
Внешняя цель: none
Вне scope: auto-discovery всех schemas, изменение contract versioning, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_observer_contracts.py
Критерии приёмки:
- test фиксирует ровно утверждённый R0 catalog и понятный drift failure;
- существующие 4 R0 schemas и fixtures остаются accepted;
- не удалять, не переименовывать и не менять schema files ради прохождения test.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- catalog не является runtime registry всех project schemas.
Результат Control Plane:
- ACCEPTED 2026-09-10: `900a825` закрепляет exact R0 allowlist/drift regression.

## Batch C — история, контрольные точки и локальная устойчивость

`executor` исполняет только `READY` карточки `EXP-041`—`EXP-050` строго по
возрастанию. Для каждой: только scope → проверки → `git status`/diff → один
локальный commit. При первой красной проверке или неясном scope остановить batch.

## EXP-041 — связать checkpoint cursor с trigger position

Статус: CLOSED
Цель: запретить checkpoint с существующим trigger event, но cursor другой записи.
Гипотеза: trigger identity и cursor должны указывать на одну и ту же append-only запись.
Зависит от: EXP-038
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, dispatch gate, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- checkpoint с cursor не своего trigger отклоняется без payload leak;
- matching trigger/cursor принимается;
- existing identity checks остаются зелёными.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять persistent storage.

## EXP-042 — проверить idempotency checkpoint snapshot

Статус: CLOSED
Цель: закрепить detached-copy и conflict semantics для checkpoint records.
Гипотеза: повтор идентичного checkpoint идемпотентен, mutation caller/read snapshot не меняет store.
Зависит от: EXP-041
Среда исполнения: local
Внешняя цель: none
Вне scope: transaction rollback, durable storage, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- same ID/content не создаёт вторую checkpoint запись;
- same ID/different content даёт conflict;
- caller/readback mutation не меняет stored record.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- in-memory semantics не равны durable atomicity.

## EXP-043 — наблюдение intent/result causality regression

Статус: CLOSED
Цель: проверить schema-valid correlation intent и result через invocation reference.
Гипотеза: result event без корректной invocation reference не проходит deterministic local validation.
Зависит от: EXP-042
Среда исполнения: local
Внешняя цель: none
Вне scope: runtime graph, tool execution, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
- tests/test_observer_contracts.py
Критерии приёмки:
- missing/foreign invocation reference у result отклоняется;
- matching intent/result reference принимается;
- rejection не возвращает stored payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не реализовывать общий causal graph.

## EXP-044 — MemorySummary source-ref uniqueness

Статус: CLOSED
Цель: исключить дублирование source references в MemorySummary semantic validation.
Гипотеза: summary с повторной ссылкой не представляет полный набор источников честно.
Зависит от: EXP-043
Среда исполнения: local
Внешняя цель: none
Вне scope: retention scheduler, deletion, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- duplicate source ref отклоняется;
- distinct references и source digest остаются accepted;
- error не выводит summary content.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не вычислять source digest и не читать referenced artifacts.

## EXP-045 — LearningCorrection immutable version semantics

Статус: CLOSED
Цель: добавить pure validation связи supersedes/version у LearningCorrection.
Гипотеза: correction не может supersede itself и не может иметь некорректную immutable version.
Зависит от: EXP-044
Среда исполнения: local
Внешняя цель: none
Вне scope: application correction, policy mutation, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- self-supersede/invalid version отклоняются;
- valid correction не мутируется validator;
- нет capability/approval/credential fields.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не создавать workflow применения correction.

## EXP-046 — audit reason-code shape hardening

Статус: CLOSED
Цель: fail-closed валидировать type и размер audit reason codes до SQLite write.
Гипотеза: audit не принимает arbitrary nested payload под видом reason code.
Зависит от: EXP-045
Среда исполнения: local
Внешняя цель: none
Вне scope: encryption, migration, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- non-string/oversized reason code отклоняется без audit write;
- normal reason-code list остаётся accepted;
- error не повторяет caller value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не менять existing audit schema без необходимости.

## EXP-047 — repository patch empty-change regression

Статус: CLOSED
Цель: доказать, что empty/no-op repository change не выпускает publishable staged change.
Гипотеза: отсутствие patch является deny condition, а не пустой публикацией.
Зависит от: EXP-046
Среда исполнения: local
Внешняя цель: none
Вне scope: deletion semantics, live GitHub, Docker, testdev.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- no-op mapping не строит publish manifest/staged change;
- meaningful existing change remains valid;
- workspace fixture не загрязняется.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять file deletion publication.

## EXP-048 — strict canonical schema ID validation

Статус: CLOSED
Цель: проверить uniqueness/format `$id` across project schemas before validation use.
Гипотеза: duplicate or malformed schema ID не может silently confuse contract provenance.
Зависит от: EXP-047
Среда исполнения: local
Внешняя цель: none
Вне scope: schema ID migration, external registry, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_contracts.py
Критерии приёмки:
- test enumerates project schemas and asserts non-empty unique `$id` matching existing project convention;
- synthetic duplicate/malformed cases demonstrate failure;
- no schema file is changed merely to satisfy the test.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- test is not a remote schema registry.

## EXP-049 — secret scanner cyclic data boundary

Статус: CLOSED
Цель: fail-closed обработать cyclic in-memory surface без recursion crash или leak.
Гипотеза: scanner reports a safe failure/finding instead of traversing indefinitely.
Зависит от: EXP-048
Среда исполнения: local
Внешняя цель: none
Вне scope: filesystem scans, process telemetry, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- cyclic mapping/list не вызывает unbounded recursion;
- canary в reachable cyclic surface не печатается;
- normal nested scan remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- scanner остаётся ограниченным переданными caller surfaces.

## EXP-050 — threat corpus required field regression

Статус: CLOSED
Цель: структурно fail-closed валидировать каждый threat corpus case до test execution.
Гипотеза: неполная case record не пропускается и не уменьшает coverage незаметно.
Зависит от: EXP-049
Среда исполнения: local
Внешняя цель: none
Вне scope: external corpus, production threat service, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_threat_corpus.py
- fixtures/threats/mvp-security-cases.json
Критерии приёмки:
- missing ID/category/expected outcome case даёт понятный test failure;
- существующий corpus полностью проходит structural validation;
- test не выводит injected payload values.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- corpus coverage остаётся конечной выборкой, не full audit.
Результат Control Plane:
- ACCEPTED 2026-09-10: Batch C commits `ae39df4`, `01dfd1f`, `3e6bcf4`,
  `5c7e18f`, `6e7c9ae`, `0888e28`, `d411e4e`, `5ef982e`, `4801e34`,
  `d3ea522` проверены по отдельным commit boundaries; независимый штатный suite
  прошёл: 209 tests OK, 1 skipped. Внешних действий и push не было.

## EXP-051 — approval-bound full intent digest remediation

Статус: CLOSED
Цель: исключить coordinated swap `request + intent + credential grant` после approval.
Гипотеза: approval хранит digest полного canonical approved intent, policy и
actuator fail-closed сверяют его до открытия broker/provider boundary.
Зависит от: EXP-013
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, real credentials, remote publication, Docker, testdev.
Разрешённые пути:
- schemas/approval.schema.json
- fixtures/valid/mvp-chain.json
- src/app_contracts/authority.py
- src/app_contracts/actuator.py
- src/app_contracts/github_actuator.py
- tests/test_authority.py
- tests/test_adversarial.py
- tests/test_actuator.py
- tests/test_broker.py
- tests/test_contracts.py
- tests/test_github_app.py
Критерии приёмки:
- approval содержит versioned `approved_intent_digest`, равный canonical digest
  полного approved intent; fixture/schema/chain validation согласованы;
- coordinated swap branch/key в request, intent и grant при том же staged digest
  отклоняется policy и не достигает mock broker/provider boundary;
- matching chain по-прежнему достигает boundary; messages не раскрывают content
  intent, grant или credential;
- full suite зелёный и remediation создаёт отдельный local commit.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- это local contract chain; real GitHub transaction не выполняется и не доказывается.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-10: `ce6c0b0` связывает request с supplied intent,
  но approval intent не одобряет. Данная карточка утверждает representation:
  canonical digest полного intent внутри approval.
- CHANGES REQUESTED 2026-09-11: `27670e9` добавляет верный digest в schema,
  policy и покрытые вызовы, но оставляет `approval` optional в обеих реальных
  actuator boundaries. Вызов без `approval` обходит full-intent проверку и
  может достигнуть endpoint/broker; это противоречит fail-closed критерию.
  Сделать approval обязательным в этих boundaries, обновить все разрешённые
  вызывающие тесты и добавить regression: omission approval → отказ до endpoint
  и до broker channel. Один отдельный local remediation commit, без push.
- SCOPE EXTENDED 2026-09-11: штатный suite выявил единственный legacy
  approval-less brokered happy-path в `tests/test_github_app.py`. Разрешено
  изменить только этот test call site/fixture, чтобы передавать валидный
  approval и сохранить доказательство приватности token/single-use grant.
  Не расширять production scope; после этого обязателен полный зелёный suite.
- ACCEPTED 2026-09-11: `27670e9` вводит versioned full canonical intent digest;
  `077c17e` делает approval mandatory до endpoint и broker channel. Независимый
  штатный suite: 230 tests OK, 1 skipped. Внешних действий и push не было.

## Batch D — последовательное исполнение

Исполнитель выполняет только `READY` карточки `EXP-052`—`EXP-061` строго по
возрастанию: одна карточка → штатный suite → diff/status → отдельный local commit.
При первой красной проверке, неясном scope или чужих незакоммиченных правках —
остановиться и вернуть evidence. `REVIEW`/`DRAFT`/`BLOCKED`/`CLOSED` не выполнять.

## EXP-052 — state-machine evidence detachment regression

Статус: CLOSED
Цель: доказать, что transition history не меняется после mutation caller evidence.
Гипотеза: state machine хранит detached canonical evidence snapshot.
Зависит от: EXP-050
Среда исполнения: local
Внешняя цель: none
Вне scope: durable storage, workflow changes, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_state_machine.py
Критерии приёмки:
- mutation исходного и прочитанного evidence не меняет сохранённую history;
- valid transition остаётся рабочим; ошибка не раскрывает payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не доказывает tamper-proof persistence.

## EXP-053 — publication journal request-digest conflict

Статус: CLOSED
Цель: закрепить fail-closed conflict при повторной подготовке process с иным digest.
Гипотеза: один process ID не может сменить publication payload до side effect.
Зависит от: EXP-052
Среда исполнения: local
Внешняя цель: none
Вне scope: recovery protocol, real provider, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- same process + different request digest отклоняется без второй записи/side effect;
- identical replay и existing happy path остаются рабочими.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- только локальная SQLite семантика.

## EXP-054 — broker grant malformed-boundary regression

Статус: CLOSED
Цель: отвергать malformed grant до открытия publication channel.
Гипотеза: broker не вызывает factory при отсутствующем или невалидном binding field.
Зависит от: EXP-053
Среда исполнения: local
Внешняя цель: none
Вне scope: credentials, live provider, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- malformed grant блокируется до factory/channel; сообщение без token/payload;
- valid single-use grant остаётся working.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять реальное credential storage.

## EXP-055 — gateway reason-code payload redaction

Статус: CLOSED
Цель: закрепить, что gateway reason codes не содержат request-controlled payload.
Гипотеза: deny/degraded result сообщает только stable classification.
Зависит от: EXP-054
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign, external classifier, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- adversarial operation/data strings не попадают в reason codes/error;
- known safe and unknown write-like classifications сохраняются.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не меняет список capabilities.

## EXP-056 — validator boolean-versus-number regression

Статус: CLOSED
Цель: fail-closed различить JSON boolean и numeric contract fields.
Гипотеза: `true`/`false` не принимаются там, где schema требует number/integer.
Зависит от: EXP-055
Среда исполнения: local
Внешняя цель: none
Вне scope: new schema dialect, production schema migration, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- boolean для numeric/integer schema field отклонён до business logic;
- ordinary numeric validation и schemas остаются зелёными.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавлять schema keywords.

## EXP-057 — mock GitHub repository-isolation replay

Статус: CLOSED
Цель: исключить receipt replay между различными repository IDs.
Гипотеза: idempotency lookup не возвращает receipt другой repository.
Зависит от: EXP-056
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, remote publication, Docker, testdev.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- same key across repositories не возвращает прежний receipt и не создаёт side effect;
- matching same-repository replay остаётся idempotent.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- mock не доказывает provider semantics.

## EXP-058 — runtime audit tuple detachment regression

Статус: CLOSED
Цель: проверить audit input как tuple и detached readback.
Гипотеза: accepted immutable sequence сериализуется безопасно, mutable output не влияет на store.
Зависит от: EXP-057
Среда исполнения: local
Внешняя цель: none
Вне scope: audit retention, distributed concurrency, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- valid tuple reason codes accepted; returned list mutation не меняет stored audit;
- invalid sequence remains denied before write.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не расширять audit event schema.

## EXP-059 — repository duplicate-path patch regression

Статус: CLOSED
Цель: отклонить patch mapping с нормализованно конфликтующими paths до write.
Гипотеза: один logical workspace path не получает два conflicting contents.
Зависит от: EXP-058
Среда исполнения: local
Внешняя цель: none
Вне scope: symlink support, deletion semantics, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- conflicting duplicate/unsafe path attempt leaves workspace unchanged;
- valid multi-file patch remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не менять filesystem outside temporary test workspace.

## EXP-060 — observer result invocation identity regression

Статус: CLOSED
Цель: запретить result causality link к result event вместо intent event.
Гипотеза: `check_result_causality` признаёт только корректный preceding intent reference.
Зависит от: EXP-059
Среда исполнения: local
Внешняя цель: none
Вне scope: graph database, durable journal, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- result-to-result/self reference denied without stored payload leak;
- matching intent-to-result path remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не реализовывать общий causal graph.

## EXP-061 — secret scanner duplicate-surface reporting

Статус: CLOSED
Цель: закрепить deterministic de-duplication finding surface names.
Гипотеза: repeated canaries в одной surface не создают repeated findings и не раскрывают value.
Зависит от: EXP-060
Среда исполнения: local
Внешняя цель: none
Вне scope: filesystem scan, telemetry, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- repeated/nested sentinel produces one stable surface finding without value;
- independent surfaces are reported separately; cyclic handling remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- scanner remains limited to caller-provided surfaces.
Результат Control Plane:
- ACCEPTED 2026-09-10: Batch D commits `8afc587`, `a3318df`, `1b62667`,
  `8e95f37`, `e34f1a4`, `cd05688`, `3911635`, `d313873`, `4f21539`,
  `9a570f6` проверены по отдельным commit boundaries; независимый штатный suite
  прошёл: 223 tests OK, 1 skipped. Внешних действий и push не было.

## Batch E — локальные contract-regressions

Исполнитель выполняет только `READY` карточки `EXP-062`—`EXP-071` строго по
возрастанию: одна карточка → штатный suite → diff/status → отдельный local commit.
При первой красной проверке, неясном scope или чужих незакоммиченных правках —
остановиться и вернуть evidence. `REVIEW`/`DRAFT`/`BLOCKED`/`CLOSED` не выполнять.

## EXP-062 — publication state-transition precondition regression

Статус: CLOSED
Цель: доказать, что journal не перепрыгивает статус publication process.
Гипотеза: completion/reconciliation допустимы лишь из documented preceding state.
Зависит от: EXP-061
Среда исполнения: local
Внешняя цель: none
Вне scope: recovery redesign, provider interaction, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- invalid status transition отклоняется и не меняет journal record;
- documented happy-path transition остаётся accepted;
- error не раскрывает request payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- только local SQLite journal.

## EXP-063 — broker request-grant type boundary regression

Статус: CLOSED
Цель: fail-closed отвергать malformed actuator request до broker factory.
Гипотеза: grant validation не обращается к request keys, пока request не прошёл structural gate.
Зависит от: EXP-062
Среда исполнения: local
Внешняя цель: none
Вне scope: credentials, live provider, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- non-mapping/missing required request binding blocked before factory/channel;
- errors do not contain request/grant content;
- valid single-use path remains working.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no credential persistence.

## EXP-064 — mock GitHub receipt detachment regression

Статус: CLOSED
Цель: проверить, что caller mutation receipt не влияет на endpoint state.
Гипотеза: mock boundary returns detached immutable-equivalent receipt snapshots.
Зависит от: EXP-063
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, remote publication, Docker, testdev.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- mutation caller request/read receipt cannot alter stored reconciliation result;
- idempotent same-repository replay remains stable;
- no secret-like data is emitted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- mock does not prove provider semantics.

## EXP-065 — runtime-store timestamp-awareness regression

Статус: CLOSED
Цель: reject naive timestamps before runtime-store state or audit write.
Гипотеза: mixed naive/aware time cannot silently corrupt ordering/expiry semantics.
Зависит от: EXP-064
Среда исполнения: local
Внешняя цель: none
Вне scope: migrations, clock service, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- naive supplied timestamps are rejected before persistence;
- aware existing happy path remains accepted;
- error does not echo caller value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no timezone normalization policy beyond fail-closed validation.

## EXP-066 — repository source-path canonicalization regression

Статус: CLOSED
Цель: reject equivalent unsafe relative paths before workspace write.
Гипотеза: dot segments and separator variants cannot create an alternate logical path.
Зависит от: EXP-065
Среда исполнения: local
Внешняя цель: none
Вне scope: symlink support, deletions, filesystem outside test workspace, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- unsafe/equivalent paths are denied with no workspace mutation;
- canonical valid multi-file patch remains accepted;
- no host filesystem path appears in error.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- only temporary test workspace may be written.

## EXP-067 — observation duplicate invocation ambiguity regression

Статус: CLOSED
Цель: reject result causality when more than one recorded intent claims an invocation ID.
Гипотеза: ambiguous invocation identity cannot select an arbitrary intent cursor.
Зависит от: EXP-066
Среда исполнения: local
Внешняя цель: none
Вне scope: graph database, durable journal, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- duplicate matching intents fail closed without stored payload leak;
- one preceding matching intent remains accepted;
- result-to-result denial remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no general causal graph.

## EXP-068 — secret scanner unsupported-value boundary

Статус: CLOSED
Цель: ensure unsupported/cyclic caller value fails closed without serialization leak.
Гипотеза: scanner reports only stable surface identity when it cannot safely inspect a value.
Зависит от: EXP-067
Среда исполнения: local
Внешняя цель: none
Вне scope: filesystem scan, telemetry, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- unserializable surface produces safe deterministic finding/error without repr/value;
- ordinary nested scan remains accepted;
- existing cyclic behaviour remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- scanner remains limited to caller-provided surfaces.

## EXP-069 — gateway audit-event stable-shape regression

Статус: CLOSED
Цель: prove gateway audit emission contains only canonical allowed fields.
Гипотеза: adversarial operation/data cannot expand audit record shape or leak into reason codes.
Зависит от: EXP-068
Среда исполнения: local
Внешняя цель: none
Вне scope: audit schema expansion, policy redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- deny/degraded audit record uses stable permitted keys and classifications only;
- request-controlled content is absent;
- existing safe classification remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external audit sink.

## EXP-070 — validator enum boolean identity regression

Статус: CLOSED
Цель: reject bool values that compare equal to numeric enum members.
Гипотеза: Python equality cannot make `True` valid for numeric contract enum `[1]`.
Зависит от: EXP-069
Среда исполнения: local
Внешняя цель: none
Вне scope: new schema dialect/keywords, schema migrations, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- bool is denied for numeric enum and number/integer combinations;
- normal numeric and explicit boolean enum validation remain accepted;
- error does not reflect injected value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no new schema keyword.

## EXP-071 — approval schema unknown-property regression

Статус: CLOSED
Цель: demonstrate approval contract rejects unrecognised top-level control fields.
Гипотеза: injected approval capability/credential fields cannot pass generic validation.
Зависит от: EXP-070
Среда исполнения: local
Внешняя цель: none
Вне scope: authority redesign, approval digest remediation, Docker, testdev, GitHub.
Разрешённые пути:
- tests/test_contracts.py
- schemas/approval.schema.json
Критерии приёмки:
- synthetic unknown top-level approval control field is denied;
- current valid approval fixture remains accepted;
- no schema is loosened or new capability introduced.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- does not replace EXP-051 full-intent remediation.
Результат Control Plane:
- ACCEPTED 2026-09-11: Batch E commits `e02b333`, `4d4863f`, `998a63e`,
  `f172081`, `a45147c`, `78346c6`, `57e2cee`, `3a06984`, `40e5e23`,
  `79f5639` проверены по отдельным commit boundaries; независимый штатный suite
  прошёл: 241 tests OK, 1 skipped. Внешних действий и push не было.

## Batch F — boundary-state and input-shape regressions

Исполнитель выполняет только `READY` карточки `EXP-072`—`EXP-081` строго по
возрастанию: одна карточка → штатный suite → diff/status → отдельный local commit.
При первой красной проверке, неясном scope или чужих незакоммиченных правках —
остановиться и вернуть evidence. `REVIEW`/`DRAFT`/`BLOCKED`/`CLOSED` не выполнять.

## EXP-072 — publication ID conflict redaction regression
Статус: CLOSED
Цель: не раскрывать caller-controlled process/idempotency values при journal conflict.
Гипотеза: stable error classification достаточна для local recovery boundary.
Зависит от: EXP-071
Среда исполнения: local
Внешняя цель: none
Вне scope: provider, recovery redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- conflicting process/key is rejected without echo of injected values;
- identical replay and happy path remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local SQLite journal only.

## EXP-073 — publication boundary shape-before-state regression
Статус: CLOSED
Цель: reject malformed publication request before journal state changes or mock side effect.
Гипотеза: missing boundary field cannot leave an `attempting` record.
Зависит от: EXP-072
Среда исполнения: local
Внешняя цель: none
Вне scope: real provider, recovery protocol, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed request is denied before transition/endpoint call;
- valid prepared request remains published exactly once;
- error has no request payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no new provider integration.

## EXP-074 — mock GitHub scalar-type boundary regression
Статус: CLOSED
Цель: reject malformed scalar boundary fields before receipt allocation.
Гипотеза: non-string identifiers/digests cannot exploit Python coercion or create receipts.
Зависит от: EXP-073
Среда исполнения: local
Внешняя цель: none
Вне scope: live GitHub, remote publication, Docker, testdev.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed scalar fields are denied with zero receipt/side effect;
- valid request and idempotent replay remain accepted;
- error does not stringify injected value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- mock does not model provider validation.

## EXP-075 — runtime event readback detachment regression
Статус: CLOSED
Цель: prove mutation of returned runtime event evidence cannot alter stored history.
Гипотеза: `events()` returns detached records at every nesting level.
Зависит от: EXP-074
Среда исполнения: local
Внешняя цель: none
Вне scope: durable tamper proofing, migrations, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- mutation readback evidence does not alter later readback;
- valid transition history remains accepted;
- no stored payload appears in error.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no persistence-encryption claim.

## EXP-076 — repository non-string content prewrite regression
Статус: CLOSED
Цель: reject non-string patch content before any temporary workspace write.
Гипотеза: mapping type cannot cause partial write or raw TypeError.
Зависит от: EXP-075
Среда исполнения: local
Внешняя цель: none
Вне scope: binary patches, symlinks, deletion semantics, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- invalid content values leave workspace unchanged and yield ContractValidationError;
- valid text patch remains accepted;
- error omits caller value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- only temporary test workspace may be written.

## EXP-077 — observation append readback detachment regression
Статус: CLOSED
Цель: prove event append and `events()` preserve detached snapshots.
Гипотеза: caller/readback mutation cannot alter causal validation inputs.
Зависит от: EXP-076
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, graph database, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- nested caller/readback mutation leaves stored event unchanged;
- causality/checkpoint happy paths remain green;
- no payload leak in rejection.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no durable tamper-proof storage.

## EXP-078 — secret scanner surface-name type regression
Статус: CLOSED
Цель: reject/contain malformed non-string surface keys without value leak.
Гипотеза: finding output never serializes arbitrary key objects.
Зависит от: EXP-077
Среда исполнения: local
Внешняя цель: none
Вне scope: filesystem scan, telemetry, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- hostile key/value cannot crash scanner or leak repr;
- regular named surfaces and cyclic handling remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- scanner stays caller-surface only.

## EXP-079 — gateway audit sink failure containment regression
Статус: CLOSED
Цель: ensure sink failure does not turn a denied gateway decision into an unclassified exception leak.
Гипотеза: gateway returns/raises only stable boundary classification on audit failure.
Зависит от: EXP-078
Среда исполнения: local
Внешняя цель: none
Вне scope: external audit sink, retry protocol, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- hostile sink exception is contained without envelope content in output;
- normal sink and safe classifications stay green;
- no capability expansion.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external delivery guarantee.

## EXP-080 — validator object-key type regression
Статус: CLOSED
Цель: fail-closed reject non-string mapping keys before schema property traversal.
Гипотеза: Python mappings with exotic keys cannot bypass additional-property checks.
Зависит от: EXP-079
Среда исполнения: local
Внешняя цель: none
Вне scope: schema dialect changes, migrations, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- non-string/exotic key is denied with stable message and no key repr;
- ordinary object validation remains accepted;
- no new schema keyword.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local validator only.

## EXP-081 — approval digest canonical-order regression
Статус: CLOSED
Цель: prove approved intent digest is invariant to mapping insertion order but sensitive to semantic mutation.
Гипотеза: canonical hashing binds content, not incidental object construction order.
Зависит от: EXP-080
Среда исполнения: local
Внешняя цель: none
Вне scope: approval signing, authority redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
- tests/test_contracts.py
Критерии приёмки:
- reordered equivalent intent is accepted against existing approval digest;
- one semantic field mutation is rejected;
- error contains no intent/approval payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no cryptographic signing claim.
Результат Control Plane:
- ACCEPTED 2026-09-11: Batch F commits `c31dd4d`, `92a67f1`, `d599e0c`,
  `dffbd02`, `9ccc7bd`, `4fe574e`, `ca20536`, `ea34e58`, `267f2f0`,
  `153672a` проверены по отдельным boundaries; независимый suite: 253 tests OK,
  1 skipped. Внешних действий и push не было.

## Batch G — local fail-closed continuation

Исполнитель выполняет только `READY` карточки `EXP-082`—`EXP-086` строго по
возрастанию: одна карточка → штатный suite → diff/status → отдельный local commit.
При первой красной проверке или неясном scope остановиться. Внешние среды и push запрещены.

## EXP-082 — publication completed receipt identity regression
Статус: CLOSED
Цель: reject completion receipt inconsistent with prepared publication record.
Гипотеза: journal cannot record a receipt for another repository/branch/digest.
Зависит от: EXP-081
Среда исполнения: local
Внешняя цель: none
Вне scope: provider, recovery redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- inconsistent receipt is denied with record still attempting and no payload leak;
- matching completion remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local mock journal only.

## EXP-083 — broker request value-shape regression
Статус: CLOSED
Цель: reject malformed required request values before factory/channel.
Гипотеза: field presence alone is insufficient at credential boundary.
Зависит от: EXP-082
Среда исполнения: local
Внешняя цель: none
Вне scope: credentials, provider, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- empty/non-string required binding is denied with zero factory calls;
- valid flow remains accepted; error does not echo value.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no credential persistence.

## EXP-084 — runtime process-id audit isolation regression
Статус: CLOSED
Цель: prove audit records cannot be read across process IDs.
Гипотеза: process filter is enforced before detached readback.
Зависит от: EXP-083
Среда исполнения: local
Внешняя цель: none
Вне scope: multi-node concurrency, migrations, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- foreign/unknown process yields no audit payload;
- own process audit remains ordered and detached.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local SQLite only.

## EXP-085 — gateway malformed envelope no-audit regression
Статус: CLOSED
Цель: malformed gateway input is denied without emitting a partially controlled audit event.
Гипотеза: audit sink sees only validated canonical classification.
Зависит от: EXP-084
Среда исполнения: local
Внешняя цель: none
Вне scope: external sinks, policy redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed envelope has stable denial and zero sink calls;
- normal deny/degraded audit paths remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external delivery guarantee.

## EXP-086 — validator nested unknown-field regression
Статус: CLOSED
Цель: fail-closed reject nested unknown object fields without key/value representation.
Гипотеза: additionalProperties is applied consistently below the root.
Зависит от: EXP-085
Среда исполнения: local
Внешняя цель: none
Вне scope: schema migration/dialect, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- nested injected field is rejected with stable message;
- valid nested object remains accepted; no injected content leak.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local validator only.
Результат Control Plane:
- ACCEPTED 2026-09-11: Batch G commits `4518fd1`, `7968dc3`, `a7ef248`,
  `1523557`, `885cf53` проверены по отдельным commit boundaries; независимый
  штатный suite: 258 tests OK, 1 skipped. EXP-082 не является миграцией старых
  SQLite journals. Внешних действий и push не было.

## Batch H — causality and publication integrity

Исполнитель выполняет только `READY` карточки `EXP-087`—`EXP-089` строго по
возрастанию: одна карточка → штатный suite → diff/status → отдельный local commit.
При первой красной проверке или неясном scope остановиться. Внешние среды и push запрещены.

## EXP-087 — observation causal ordering regression
Статус: CLOSED
Цель: result может ссылаться только на ранее записанный intent того же invocation.
Гипотеза: future intent или result-before-intent не могут легализовать causal link.
Зависит от: EXP-086
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, graph database, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- future/reversed reference denied without payload leak;
- one preceding intent remains accepted; ambiguous/result references remain denied.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no general causal graph.

## EXP-088 — approval digest type boundary regression
Статус: CLOSED
Цель: malformed approval digest is rejected as a contract error before policy/actuator use.
Гипотеза: non-string/invalid digest cannot create comparison ambiguity.
Зависит от: EXP-087
Среда исполнения: local
Внешняя цель: none
Вне scope: signing, authority redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
- tests/test_contracts.py
Критерии приёмки:
- malformed digest types/patterns denied with no value leak;
- canonical valid approval and full-intent binding remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no cryptographic signing claim.

## EXP-089 — publication receipt ID type regression
Статус: CLOSED
Цель: reject non-positive/non-integer mock receipt IDs before journal completion.
Гипотеза: malformed receipt cannot corrupt publication record state.
Зависит от: EXP-088
Среда исполнения: local
Внешняя цель: none
Вне scope: provider, migration, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- invalid receipt ID leaves record attempting with null PR ID;
- valid matching completion remains accepted; error contains no receipt payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local mock journal only.
Результат Control Plane:
- ACCEPTED 2026-09-11: `e201857`, `212c185`, `8f9aa1f` проверены по отдельным
  commit boundaries; независимый штатный suite: 261 tests OK, 1 skipped.
  Внешних действий и push не было.

## Batch I — causality hardening

Исполнитель выполняет только `READY` карточку `EXP-090`. После: штатный suite,
diff/status, один local commit и evidence. При ошибке или неясном scope остановиться.

## EXP-090 — causal event-type allowlist regression
Статус: CLOSED
Цель: result признаёт только явные intent-type events как causal predecessors.
Гипотеза: произвольный non-result event с совпадающим invocation_id не должен легализовать result.
Зависит от: EXP-089
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, graph database, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- unknown/non-intent predecessor is denied without payload leak;
- preceding recognised intent remains accepted; future/ambiguous/result paths remain denied.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no general causal graph or external observation store.
Результат Control Plane:
- ACCEPTED 2026-09-11: `13a0a80` проверен в разрешённом scope; независимый
  штатный suite: 263 tests OK, 1 skipped. Внешних действий и push не было.

## Batch J — causal contract tightening

Исполнитель выполняет только `READY` карточку `EXP-091`. После: штатный suite,
diff/status, один local commit и evidence. При ошибке или неясном scope остановиться.

## EXP-091 — causal unknown-event-type regression
Статус: CLOSED
Цель: schema-valid, но неallowlisted event type не может быть causal intent predecessor.
Гипотеза: extensibility event schema не расширяет implicit authority in causality check.
Зависит от: EXP-090
Среда исполнения: local
Внешняя цель: none
Вне scope: schema redesign, durable journal, graph database, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- unknown event type with matching invocation is denied without payload leak;
- recognised preceding intent still works and existing causal denials remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no claim that event schema itself is closed-world.

Результат Control Plane:
- ACCEPTED 2026-09-11: `09ce2dc` проверен в разрешённом scope; независимый
  штатный suite: 264 tests OK, 1 skipped. Внешних действий в рамках EXP-091 не
  было; последующая публикация репозитория выполняется отдельным решением Control
  Plane.

## Формат task card

Добавляйте карточки в порядке выполнения. Исполнитель работает только с `READY`
карточками, сверху вниз, и возвращает отдельное evidence для каждой в конце запуска.
`BLOCKED`, `DRAFT`, `REVIEW` и `CLOSED` карточки не исполняются.

```text
## EXP-### — краткое название
Статус: READY
Цель: <одно проверяемое предложение>
Гипотеза: <что именно проверяется>
Зависит от: <ID предыдущей задачи или none>
Среда исполнения: local | docker | testdev
Внешняя цель: none | Agent00X-sandbox
Вне scope: <что явно не делать>
Разрешённые пути:
- src/app_contracts/example.py
- tests/test_example.py
Критерии приёмки:
- <наблюдаемый результат>
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- <только для docker/testdev/Agent00X-sandbox; иначе none>
Commit: ALLOWED
Ограничения и риски:
- <конкретные ограничения>
```

Control Plane создаёт, меняет статусы и закрывает карточки. Если задачи зависимы,
следующая получает `READY` только после приёмки evidence и ревью предыдущей;
независимые задачи можно пометить `READY` одновременно.

Для `testdev` укажите точный host action и команды; для Docker — образ и
`RUN_DOCKER_SANDBOX_TESTS=1`; для `Agent00X-sandbox` — цель эксперимента и
допустимую read/test-операцию. Ни одна карточка не может разрешить push, создание
PR, чтение secrets, изменение unit-файлов или перезапуск сервиса.
Историю завершённых работ храните вне `.opencode/`, если она нужна проекту.
