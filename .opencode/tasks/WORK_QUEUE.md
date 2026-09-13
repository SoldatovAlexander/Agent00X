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

## Batch P — authority and boundary hardening

Результат Control Plane:
- ACCEPTED 2026-09-12: независимое review commits `2e76f42`—`45035de`
  подтвердило соответствие разрешённым путям и fail-closed negative paths для
  authority, actuator, brokered actuator, mock/publication/repository boundaries,
  schema declarations и GitHub App adapter. Проверка
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`:
  360 tests passed, 1 opt-in Docker test skipped. Нет внешних вызовов,
  публикаций или изменений конфигурации.

## EXP-165 — validate authority clock type
Статус: ACCEPTED
Цель: Authority rejects a non-datetime or naive use clock through a stable contract error.
Гипотеза: approval and decision expiry checks cannot rely on unchecked caller clocks.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: policy semantics and external publication.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed now values are denied without raw attribute errors or side effects.
- valid aware clocks preserve expiry behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-166 — gate approval root mappings
Статус: ACCEPTED
Цель: Authority rejects malformed approval, intent, and staged-change roots deterministically.
Гипотеза: direct approval validation must validate mapping boundaries before field access and hashing.
Зависит от: EXP-165
Среда исполнения: local
Внешняя цель: none
Вне scope: approval schema format or policy decisions.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed roots yield stable ContractValidationError messages without payload leakage.
- valid approval binding remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-167 — validate policy configuration identity sets
Статус: ACCEPTED
Цель: malformed PolicyConfig version and allowlist members fail at construction.
Гипотеза: policy cannot operate with empty/non-string identity constraints or arbitrary iterable inputs.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: allowlist contents for valid configuration.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed config fails without raw errors.
- valid config preserves decisions.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-168 — require boolean policy availability
Статус: ACCEPTED
Цель: DeterministicPolicy does not treat truthy non-booleans as availability.
Гипотеза: invalid availability configuration cannot yield an allow decision.
Зависит от: EXP-167
Среда исполнения: local
Внешняя цель: none
Вне scope: Gateway availability behavior.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed availability is denied or rejected deterministically.
- valid True/False behavior is unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-169 — gate policy decision request shape
Статус: ACCEPTED
Цель: direct policy evaluation rejects malformed actuator requests before decision construction.
Гипотеза: missing or malformed request identity fields cannot cause raw key errors or be echoed in reasons.
Зависит от: EXP-168
Среда исполнения: local
Внешняя цель: none
Вне scope: changing valid allow/deny policy rules.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed requests have a stable fail-closed outcome without side effects.
- valid bound request behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-170 — gate usable-decision root and clock
Статус: ACCEPTED
Цель: decision-use checks validate decision mapping and now before expiry field access.
Гипотеза: malformed decisions and clocks fail through the authority boundary without raw exceptions.
Зависит от: EXP-165
Среда исполнения: local
Внешняя цель: none
Вне scope: decision schema or decision lifetime for valid data.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed decision roots and clocks raise stable ContractValidationError.
- valid allow decision remains usable only before expiry.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-171 — gate actuator gateway-decision shape
Статус: ACCEPTED
Цель: the mock actuator rejects malformed gateway decisions before endpoint access.
Гипотеза: only a typed slow-path allow can cross the action boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: Gateway classifier or mock endpoint behavior for valid decisions.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- malformed gateway decision causes zero endpoint calls and no raw errors.
- valid slow-path allow remains publishable.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-172 — reject false actuator approval proof early
Статус: ACCEPTED
Цель: false or non-boolean approval_valid is denied before the mock endpoint.
Гипотеза: authority proof must be validated by the actuator boundary, not delegated to the provider double.
Зависит от: EXP-171
Среда исполнения: local
Внешняя цель: none
Вне scope: approval digest validation or endpoint implementation.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- invalid approval proof makes zero endpoint calls.
- true proof with existing valid inputs still publishes.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-173 — gate actuator policy-decision shape
Статус: ACCEPTED
Цель: malformed policy-decision roots are denied before action publication.
Гипотеза: an actuator must not access unchecked decision fields or leak caller values.
Зависит от: EXP-172
Среда исполнения: local
Внешняя цель: none
Вне scope: policy engine decision generation.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- malformed decision inputs cause zero endpoint calls and stable errors.
- valid allow decisions retain binding checks.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-174 — gate brokered actuator broker shape
Статус: ACCEPTED
Цель: BrokeredGitHubActuator rejects an invalid broker before any action path.
Гипотеза: a non-conforming broker cannot be invoked through an unchecked method access.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: GitHub App minting and provider calls.
Разрешённые пути:
- src/app_contracts/github_actuator.py
- tests/test_github_app.py
Критерии приёмки:
- invalid broker causes a stable boundary error and zero provider calls.
- valid broker path preserves current behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-175 — validate mock reconciliation lookup inputs
Статус: ACCEPTED
Цель: MockGitHub reconciliation rejects malformed lookup identifiers without exposing them.
Гипотеза: read-only reconciliation has the same typed boundary as publication.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: publication idempotency semantics for valid identifiers.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed key/repository inputs fail deterministically and do not alter receipts.
- valid same- and cross-repository lookup behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-176 — constrain mock publication branch shape
Статус: ACCEPTED
Цель: MockGitHub rejects branches outside the agent process namespace.
Гипотеза: the mock action boundary must not accept a content-bound key for an arbitrary branch.
Зависит от: EXP-175
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub branches or namespace design changes.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed/out-of-namespace branches make no receipt.
- existing valid agent/process branches remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-177 — gate publication journal read identifiers
Статус: ACCEPTED
Цель: PublicationJournal read and transition paths reject malformed process IDs before SQLite operations.
Гипотеза: journal methods share a stable process identity boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: database schema and valid recovery semantics.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed IDs fail without raw errors or journal mutation.
- valid not-found and lifecycle behavior remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-178 — gate repository test-command shape before writes
Статус: ACCEPTED
Цель: prepare_change rejects malformed test commands before workspace mutation.
Гипотеза: an invalid verification command cannot leave an altered ephemeral workspace or partial artifacts.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid allowlisted command execution and Docker.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed command shapes fail before workspace writes and staged artifacts.
- valid preparation remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-179 — validate repository preparation metadata
Статус: ACCEPTED
Цель: prepare_change rejects malformed process/task/repository/base-commit metadata before writes.
Гипотеза: artifact identifiers must be typed and non-empty before they enter evidence or digests.
Зависит от: EXP-178
Среда исполнения: local
Внешняя цель: none
Вне scope: artifact schema redesign or publication.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed metadata leaves workspace and artifacts untouched.
- valid preparation retains existing evidence bindings.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-180 — validate canonical schema enum declarations
Статус: ACCEPTED
Цель: malformed enum declarations fail schema validation before instance validation.
Гипотеза: scalar or malformed enum definitions cannot silently change contract acceptance.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: supported valid schema semantics.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- malformed enum declarations raise deterministic RuntimeError.
- existing schemas and valid enum behavior remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-181 — validate schema type declarations
Статус: ACCEPTED
Цель: malformed type declarations fail at schema validation instead of during instance processing.
Гипотеза: schema structure errors have a stable fail-closed boundary.
Зависит от: EXP-180
Среда исполнения: local
Внешняя цель: none
Вне scope: adding new JSON Schema types.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- unsupported or non-string type declarations raise deterministic RuntimeError before payload inspection.
- valid project schemas remain structurally valid.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-182 — validate GitHub minter expiry response
Статус: ACCEPTED
Цель: GitHub App minter rejects malformed token expiry timestamps without exposing token material.
Гипотеза: a nonempty string is insufficient proof of a usable short-lived installation token.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub requests, private-key access, and testdev.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed expiry response fails before a token object is returned and leaks no token.
- a valid timestamp response remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-183 — validate GitHub permission duplication
Статус: ACCEPTED
Цель: duplicate GitHub permission entries are rejected before token exchange.
Гипотеза: ambiguous grant permissions cannot be silently collapsed into a provider payload.
Зависит от: EXP-182
Среда исполнения: local
Внешняя цель: none
Вне scope: permission allowlist expansion or real GitHub calls.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- duplicate/ambiguous permissions make zero token-exchange calls.
- valid distinct allowed permissions retain current payload.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-184 — sanitize GitHub reconciliation identifiers
Статус: ACCEPTED
Цель: direct GitHub reconciliation rejects malformed branch and idempotency identifiers before GET.
Гипотеза: read-only provider calls require the same typed namespace boundary as publication.
Зависит от: EXP-183
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub calls, token minting, and pull-request creation.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed direct reconciliation inputs make zero GET calls and yield stable errors.
- valid reconciliation behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## Batch Q — fail-closed integration boundaries

Исполнитель выполняет только `READY` карточки `EXP-185`—`EXP-191` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. Карточки независимы по контракту, но изменения в
одном модуле не смешиваются между commit. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: независимое review commits `962c854`, `490770c`,
  `3d58b7f`, `4b567e1`, `6b99e81` и `76832f3` подтвердило разрешённый scope,
  fail-closed negative paths и сохранение valid behaviour для EXP-185—188,
  EXP-190 и EXP-191. Проверка
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`:
  368 tests passed, 1 opt-in Docker test skipped. Внешних вызовов,
  публикаций или изменений конфигурации нет.
- CHANGES REQUESTED 2026-09-13 for EXP-189 / commit `5401173`: проверка
  collaborator ограничена `mark_attempting`; partial journal с этим методом,
  но без `get`, проходит gate и даёт raw `AttributeError` до mutation. Нужен
  полный fail-closed journal boundary и regression test до принятия.

## EXP-185 — gate chain contract roots before field access
Статус: ACCEPTED
Цель: `validate_chain` отвергает неполные или shape-invalid contract members через стабильную ошибку границы.
Гипотеза: mapping-root проверка сама по себе недостаточна; до cross-contract field access нужно детерминированно отсечь missing и malformed required members.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: изменение JSON Schema, valid chain semantics, Docker, testdev, Agent00X-sandbox и внешние вызовы.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- malformed or incomplete member contracts fail with a stable `ContractValidationError`, without raw `KeyError`, `TypeError` or attacker value leakage.
- existing valid chain fixtures and their integrity checks preserve behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- проверяет только локальные cross-contract boundaries; не доказывает сквозную публикацию.

## EXP-186 — reject unhashable chain binding values safely
Статус: ACCEPTED
Цель: `validate_chain` отклоняет non-scalar binding identifiers до set/digest comparisons.
Гипотеза: caller-controlled lists or mappings in linked identity fields cannot cause raw hashing/type exceptions or be treated as comparable identifiers.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: разрешённые значения valid identifiers, JSON Schema и external publication.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- unhashable or non-string binding values fail closed with a stable payload-free `ContractValidationError`.
- valid cross-contract equality and digest bindings remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не расширяет и не переопределяет business semantics valid contracts.

## EXP-187 — make broker channel opening atomic on factory failure
Статус: ACCEPTED
Цель: failed or malformed in-memory channel factory result does not consume a credential grant.
Гипотеза: a transient internal factory failure must not turn a grant into used state before a conforming private channel exists.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: credential minting, GitHub connectivity, broker permission policy and real credential material.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- a raising or malformed factory result yields a stable boundary failure and leaves `opened_grants`/single-use state unchanged.
- a later valid opening for the same valid grant succeeds once; a completed opening remains single-use.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- относится только к local test broker and does not assert provider-token recovery semantics.

## EXP-188 — validate dispatch boundary before observation writes
Статус: ACCEPTED
Цель: `run_gated_dispatch` rejects a non-callable dispatch target before checkpoint or intent persistence.
Гипотеза: malformed dispatch wiring cannot leave a durable-looking pre-dispatch trace for an action that was never callable.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: dispatch execution semantics for valid callables, observer durability and external side effects.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- non-callable dispatch produces a stable `PreDispatchError` and leaves event/checkpoint state unchanged.
- a valid callable still runs only after both validated records are written and returns the existing cursor/result shape.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не добавляет rollback для exceptions inside a valid dispatch callable.

## EXP-189 — gate publication collaborators before journal mutation
Статус: ACCEPTED
Цель: `execute_publication` rejects malformed journal or endpoint collaborators before changing publication status.
Гипотеза: unchecked collaborator method access must not transition a prepared record to attempting before failing with a raw attribute error.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: SQLite schema, MockGitHub valid publication behavior, real GitHub calls and recovery policy.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed collaborators fail through a stable boundary error with no journal status mutation and no endpoint call.
- valid prepared publication keeps its existing exactly-once and crash behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не меняет provider interface or external-effect guarantees.
Результат Control Plane:
- CHANGES REQUESTED 2026-09-13: partial journal with callable `mark_attempting`
  but no `get` reaches raw `AttributeError`; require every journal operation
  used before the first state mutation to be gated and cover it by regression.
- CHANGES REQUESTED 2026-09-13 after remediation commit `25aace1`: `get` is
  now gated, but a partial journal with callable `get` and `mark_attempting`
  and no `mark_completed` still performs one endpoint call, changes status to
  `attempting`, then raises raw `AttributeError`. Gate `mark_completed` before
  any mutation/external call and add the corresponding no-call regression.
- ACCEPTED 2026-09-13: remediation commit `34c1a59` gates callable `get`,
  `mark_attempting` and `mark_completed` before the first mutation or endpoint
  call. The added regression confirms a partial journal without
  `mark_completed` yields the stable boundary error, zero endpoint calls and a
  prepared record. Full suite: 384 tests passed, 1 opt-in Docker test skipped.

## EXP-190 — validate recovery endpoint boundary before lookup
Статус: ACCEPTED
Цель: `recover_publication` rejects a malformed recovery endpoint without mutating an attempting journal record.
Гипотеза: reconciliation must validate the lookup collaborator before the uncertain-effect branch is classified.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: automatic retry policy, SQLite schema, real GitHub reconciliation and external calls.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed endpoint fails with a stable boundary error while an attempting record remains attempting.
- valid endpoint preserves completed, prepared and reconciliation-required outcomes.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- сохраняет правило never-retry-uncertain-effect automatically.

## EXP-191 — sanitize observation conflict identifiers
Статус: ACCEPTED
Цель: conflicting event and checkpoint identifiers are rejected without echoing caller-supplied IDs.
Гипотеза: idempotency conflict reporting is a contract boundary and must not leak arbitrary identifiers in error text.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: event/checkpoint schema, successful idempotent replay and observer persistence.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- differing duplicate event/checkpoint content raises a stable payload-free conflict error and leaves stored history unchanged.
- identical replay retains its original cursor/index behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не меняет identifier format or conflict detection semantics.

## Batch R — canonical binding and digest boundaries

Исполнитель выполняет только `READY` карточки `EXP-192`—`EXP-194` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `a3c51e8`, `1c406b2` and
  `229dd5a` confirmed scope, stable fail-closed boundaries and preserved valid
  digest/chain behavior. Full suite: 374 tests passed, 1 opt-in Docker test
  skipped; no external calls, publication or configuration changes.

## EXP-192 — require non-empty chain binding values
Статус: ACCEPTED
Цель: `validate_chain` rejects empty strings in cross-contract binding fields before equality and digest comparisons.
Гипотеза: an empty identifier must not satisfy a single-value set or equality check merely because every linked contract carries the same empty string.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: JSON Schema, valid identifier values, external publication and Docker.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- empty process, repository and staged-change bindings fail with stable payload-free `ContractValidationError`.
- existing valid chain binding and mismatch behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не меняет допустимый формат non-empty IDs or digests.

## EXP-193 — require boolean chain taint marker
Статус: ACCEPTED
Цель: a non-boolean canonical-envelope `security.tainted` value cannot authorize the chain.
Гипотеза: truthy and falsy arbitrary values must not be interpreted as a security decision at the publication authorization boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: envelope schema redesign, valid tainted/untainted semantics and external calls.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- non-boolean taint markers fail closed with stable errors, without raw value leakage.
- `True` remains denied and `False` remains eligible for the existing valid-chain checks.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не утверждает, что valid envelope is trusted beyond local contract checks.

## EXP-194 — gate raw-byte digest inputs
Статус: ACCEPTED
Цель: `sha256_bytes` rejects non-bytes-like inputs through a stable digest boundary error.
Гипотеза: direct callers cannot trigger a raw hashing `TypeError` by supplying text, mappings or arbitrary objects instead of content bytes.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: canonical JSON representation, digest algorithm and valid repository preparation.
Разрешённые пути:
- src/app_contracts/digests.py
- tests/test_contracts.py
Критерии приёмки:
- malformed byte inputs fail deterministically without their representation in error text.
- `bytes` and explicitly supported bytes-like valid inputs retain their existing digest values.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не вводит новый canonicalization profile.

## Batch S — local error-surface containment

Исполнитель выполняет только `READY` карточки `EXP-195`—`EXP-197` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `8bc2c6b`, `eeaf56e` and
  `6d044f2` confirmed scope, payload-free runtime/publication/scanner errors
  and preserved valid behavior. Full suite: 374 tests passed, 1 opt-in Docker
  test skipped; no external calls, publication or configuration changes.

## EXP-195 — sanitize runtime process lookup and conflict errors
Статус: ACCEPTED
Цель: runtime store does not echo caller-supplied process IDs or versions in not-found, duplicate and optimistic-conflict errors.
Гипотеза: persistence error boundaries must remain useful without copying untrusted process identifiers into logs or caller-visible messages.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: SQLite schema, process lifecycle, version comparison semantics and external persistence.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- duplicate, missing and version-conflict cases raise stable payload-free project errors.
- valid create/get/advance and conflict classification remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не скрывает SQLite operational failures outside these contract errors.

## EXP-196 — sanitize uncertain-publication recovery identifier
Статус: ACCEPTED
Цель: `recover_publication` reports an unresolved external effect without echoing its caller-supplied process identifier.
Гипотеза: an uncertain-effect status is important, but the error boundary must not leak arbitrary request identity into evidence or logs.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: retry policy, journal schema, MockGitHub behavior and real provider calls.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- recovery-required errors are stable and payload-free while preserving journal reconciliation-required state.
- valid completed and prepared recovery outcomes remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не changes the policy that uncertain effects must not be retried automatically.

## EXP-197 — contain canary finding names in raised errors
Статус: ACCEPTED
Цель: `assert_canary_absent` signals a finding without reproducing caller-supplied surface names in its exception text.
Гипотеза: a scanner may return safe diagnostics to its direct caller, but a raised security error must not relay untrusted labels into broad error surfaces.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: canary matching, `find_canary_surfaces` return value, serialization behavior and secret scanning of real host surfaces.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- raised leak errors are stable and contain neither canary nor caller-controlled surface names.
- direct findings for valid scan inputs preserve their current names and ordering.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не доказывает отсутствие secrets in host telemetry, process lists or crash dumps.

## Batch T — endpoint and clock boundary follow-up

Исполнитель выполняет только `READY` карточки `EXP-198`—`EXP-201` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `8b25a09`, `9fa59d1`,
  `e23566b` and `039719b` confirmed allowed scope, stable fail-closed boundary
  handling and preserved valid behavior. Full suite: 378 tests passed, 1
  opt-in Docker test skipped; no external calls, publication or configuration
  changes.

## EXP-198 — gate in-memory broker factory callability
Статус: ACCEPTED
Цель: a non-callable in-memory broker factory is rejected through a stable boundary error before grant state changes.
Гипотеза: constructor-injected collaborators must be checked before invocation, so malformed test wiring cannot yield a raw `TypeError` or consume a valid single-use grant.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: GitHub App minting, real credential material, provider calls and permission policy.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- non-callable factories fail with a stable `ContractValidationError` and leave `opened_grants`/used-grant state unchanged.
- valid factories and the existing factory-result validation retain their behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- покрывает только local in-memory broker seam.

## EXP-199 — gate mock actuator endpoint shape
Статус: ACCEPTED
Цель: `publish_authorized_request` rejects a malformed endpoint before provider method access.
Гипотеза: a policy-valid request must not end in a raw attribute error because the final mock action collaborator lacks a callable publication method.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: Authority/Policy semantics, valid MockGitHub behavior, GitHub App and external calls.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- malformed endpoint yields a stable payload-free `ContractValidationError` and no publication side effect.
- a conforming endpoint preserves existing approval, decision and slow-path checks before publication.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не проверяет production provider availability or external-effect recovery.

## EXP-200 — require a non-empty mock agent branch suffix
Статус: ACCEPTED
Цель: `MockGitHubEndpoint` rejects the bare `agent/` namespace as an invalid publication branch.
Гипотеза: namespace membership alone cannot authorize an empty branch identity or its content-bound idempotency key.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: branch naming policy for valid suffixes, real GitHub branches and namespace redesign.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- a bare namespace branch is denied before a receipt is recorded.
- existing non-empty agent/process branches retain their idempotency and repository isolation behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не expands valid branch namespaces or makes real provider calls.

## EXP-201 — reject malformed runtime clock values explicitly
Статус: ACCEPTED
Цель: SQLite runtime APIs reject falsy, non-datetime and naive explicit `now` values instead of silently defaulting or raising raw attribute errors.
Гипотеза: caller-supplied timestamps must cross the same deterministic boundary whether they are truthy or falsy, before any database mutation.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: timestamp format for valid aware datetimes, SQLite schema and process lifecycle semantics.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- explicit malformed `now` values on create, advance and audit append fail with a stable `ContractValidationError` and leave state/audit unchanged.
- omitted `now` and valid timezone-aware datetimes preserve existing persistence behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не makes runtime store a distributed clock or transaction service.

## Batch U — preparation and gateway shape hardening

Исполнитель выполняет только `READY` карточки `EXP-202`—`EXP-205` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `622b865`, `b0d1ec4`,
  `a2235af` and `f081140` confirmed allowed scope, fail-closed negative paths
  and preserved valid preparation/gateway/GitHub adapter behavior. Full suite:
  384 tests passed, 1 opt-in Docker test skipped; no external calls,
  publication or configuration changes.

## EXP-202 — reject malformed preparation clocks explicitly
Статус: ACCEPTED
Цель: `prepare_change` rejects explicit falsy, non-datetime and naive `now` values before workspace writes.
Гипотеза: caller-supplied timestamps cannot silently fall back to the local clock or cause raw time errors while creating evidence and staged artifacts.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: artifact timestamp format for valid aware datetimes, test command semantics, Docker and external publication.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- explicit invalid clocks fail with stable `ContractValidationError` before workspace mutation or staged artifacts.
- omitted `now` and valid aware values preserve existing preparation behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не adds a trusted time source or changes artifact lifetime.

## EXP-203 — validate gateway sensitivity scalar
Статус: ACCEPTED
Цель: gateway classification rejects non-string or empty `security.sensitivity` before selecting a path.
Гипотеза: malformed sensitivity cannot be silently treated as low-risk because it happens not to equal a protected label.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: sensitivity taxonomy, valid routing semantics, audit persistence and external calls.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed sensitivity values produce the existing stable malformed-envelope deny path and do not reach an audit sink.
- valid sensitivity values preserve current fast/slow/degraded decisions.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не declares any new sensitivity level trusted or permitted.

## EXP-204 — reject duplicate verified-file paths before GitHub calls
Статус: ACCEPTED
Цель: `publish_verified_files` rejects duplicate manifest paths before branch or content requests.
Гипотеза: a manifest must denote one deterministic final content per path; duplicate entries cannot produce order-dependent writes on a scoped branch.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub calls, token minting, branch creation policy and file content semantics for unique paths.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- duplicate paths fail with a stable boundary error and make zero mocked POST/PUT calls.
- a unique verified manifest preserves current branch reconciliation and content-digest checks.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- local mock transport tests do not prove GitHub atomicity.

## EXP-205 — require a non-empty GitHub process branch suffix
Статус: ACCEPTED
Цель: GitHub App channel rejects the bare `agent/process-` prefix for reconciliation and publication paths.
Гипотеза: the production adapter must not accept an empty process branch identity merely because it matches a prefix check.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid process branch naming, GitHub API calls, token handling and pull-request creation.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- bare prefix is rejected before mocked GET/POST/PUT calls in every direct branch entrypoint.
- existing non-empty agent/process branches retain reconciliation and publication behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не expands GitHub App permissions or performs real provider activity.

## Batch V — audit and collaborator boundary hardening

Исполнитель выполняет только `READY` карточки `EXP-206`—`EXP-208` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `e51320c`, `f43f521` and
  `287ecb0` confirmed allowed scope, fail-closed paths and preserved valid
  behavior. Full suite: 387 tests passed, 1 opt-in Docker test skipped; no
  external calls, publication or configuration changes.

## EXP-206 — validate gateway audit scalar fields before sink access
Статус: ACCEPTED
Цель: gateway enforcement rejects malformed audit correlation, principal and input-digest scalars before invoking any audit sink.
Гипотеза: presence-only checks must not forward arbitrary values to a custom sink that may persist or expose them as trusted audit fields.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: audit schema, valid gateway routing, SQLite persistence and external calls.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- non-string or empty audit scalars take the stable malformed-envelope deny path and make zero sink calls.
- valid audit envelopes preserve current decisions and minimal audit records.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не declares an audit sink trusted beyond its local protocol boundary.

## EXP-207 — gate observation-store collaborator shape before dispatch
Статус: ACCEPTED
Цель: `run_gated_dispatch` rejects a malformed store collaborator before any record call or dispatch execution.
Гипотеза: a caller cannot bypass the stable pre-dispatch error boundary through a missing/non-callable `record_checkpoint` or `append` method.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: durable observer storage, valid ObservationStore semantics and external side effects.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- malformed stores yield a stable `PreDispatchError`, make no dispatch call and do not leak raw attribute/type errors.
- a conforming store retains checkpoint-before-intent-before-dispatch ordering.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не adds persistence or rollback semantics to valid dispatch failures.

## EXP-208 — validate injected GitHub transport callability
Статус: ACCEPTED
Цель: GitHub App channel rejects non-callable injected POST/GET/PUT transports before any provider-path method access.
Гипотеза: test or adapter wiring cannot produce raw `TypeError` in publication/reconciliation paths merely because an injected collaborator is truthy but not callable.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub calls, token minting, API response semantics and private-key handling.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed injected transports fail with stable broker/boundary errors before mocked network activity.
- valid injected transports preserve existing local reconciliation and publication tests.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- covers constructor-injected local collaborators, not network availability.

## Batch W — broad local contract sweep

Исполнитель выполняет только `READY` карточки `EXP-209`—`EXP-220` строго по
возрастанию ID: одна карточка → её проверки → `git status`/diff → один локальный
commit → следующая карточка. При ошибке проверки, неясном scope или
предсуществующих правках останови весь batch и верни evidence Control Plane.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `3aec9c3`—`b6a96ad`
  confirmed allowed scope, stable negative paths and preserved valid behavior
  for EXP-209—220. Full suite: 399 tests passed, 1 opt-in Docker test skipped;
  no external calls, publication or configuration changes.

## EXP-209 — gate publication process ID request scalar
Статус: ACCEPTED
Цель: `execute_publication` validates a non-empty string process ID before journal access.
Гипотеза: malformed request identities cannot escape through journal-specific errors or reach a state transition.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: journal schema, valid publication and external calls.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed process IDs yield stable `ContractValidationError`, no mutation and no endpoint call.
- valid prepared publication behavior is unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no recovery-policy change.

## EXP-210 — gate recovery journal collaborator shape
Статус: ACCEPTED
Цель: `recover_publication` validates every journal method required by each recovery transition before journal access.
Гипотеза: malformed recovery collaborators cannot create raw attribute errors or partial status changes.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: retry policy, journal schema and provider calls.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed journal paths fail stably with zero endpoint calls and unchanged records.
- valid completed, prepared and uncertain recovery behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- never retry uncertain effects automatically.

## EXP-211 — validate delegation collection members
Статус: ACCEPTED
Цель: chain delegation rejects non-string or empty action/resource members before set containment.
Гипотеза: unhashable or malformed delegated capabilities cannot cause raw errors or evade subset checks.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid delegation policy and JSON Schema.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- malformed member values fail with payload-free `ContractValidationError`.
- valid subset and expansion-denial behavior is preserved.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no capability expansion.

## EXP-212 — gate observation invocation reference scalar
Статус: ACCEPTED
Цель: result causality rejects non-string or empty invocation references deterministically.
Гипотеза: malformed references cannot enter causal scans as arbitrary equality values.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: event schema, ordering semantics and persistence.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- malformed references yield stable errors without stored payload leakage.
- valid causal references retain their cursor result.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no observer durability claim.

## EXP-213 — gate preparation sandbox collaborator shape
Статус: ACCEPTED
Цель: `prepare_change` validates required sandbox members before workspace access.
Гипотеза: malformed sandbox collaborators cannot cause raw attribute errors or writes outside a valid session boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: sandbox backend implementation, Docker and valid command execution.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed sandbox collaborators fail stably before writes or command execution.
- valid local preparation remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no broader filesystem authority.

## EXP-214 — validate preparation command result shape
Статус: ACCEPTED
Цель: `prepare_change` rejects malformed sandbox command results before evidence construction.
Гипотеза: a backend cannot inject a raw attribute error or untrusted report fields into staged artifacts.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid test result semantics, Docker and artifact schema redesign.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed result shape fails with stable boundary error and no staged result.
- valid command results preserve verification outcome and report digest.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- does not make local execution hostile-code safe.

## EXP-215 — gate manifest sandbox collaborator shape
Статус: ACCEPTED
Цель: `build_publish_manifest` rejects malformed sandbox workspace collaborators before file access.
Гипотеза: a publish boundary cannot trust arbitrary objects exposing partial workspace attributes.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: manifest content binding and repository publication.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed sandboxes fail with stable `ContractValidationError` and no output manifest.
- a valid verified manifest retains current behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no real repository access.

## EXP-216 — gate GitHub channel config and token shapes
Статус: ACCEPTED
Цель: GitHub publication channel rejects malformed config/token collaborators before request construction.
Гипотеза: direct adapter calls cannot raise raw attribute errors or expose token material through malformed injected dependencies.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: private-key reads, real GitHub calls and token minting semantics.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed config/token inputs fail stably before mocked transport calls and leak no token value.
- valid channel paths remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no provider activity.

## EXP-217 — validate GitHub minter injected clock and transport
Статус: ACCEPTED
Цель: installation token minter validates injected clock and POST collaborator callability and time shape.
Гипотеза: test seams cannot silently default falsy inputs or produce raw type errors before token boundary checks.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: openssl signing, private keys, real token exchange and permissions.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed injected seams fail through stable broker errors before token exchange calls.
- valid injected seams preserve current local minter behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no credential values in tests or evidence.

## EXP-218 — bind direct GitHub pull-request idempotency key
Статус: ACCEPTED
Цель: direct GitHub channel publication validates that idempotency key matches scoped branch and staged digest.
Гипотеза: bypassing the higher actuator adapter cannot reuse an arbitrary marker for a different publication content binding.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: GitHub API calls, branch policy and upstream approval semantics.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- mismatched keys fail before mocked GET/POST calls.
- matching existing and new publication requests preserve reconciliation behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no real pull-request creation.

## EXP-219 — restrict mock reconciliation key namespace
Статус: ACCEPTED
Цель: MockGitHub reconciliation rejects lookup keys outside the publication namespace.
Гипотеза: read-only lookup must not become an unrestricted index over arbitrary caller identifiers.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid idempotency semantics and real provider reconciliation.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed/out-of-namespace keys fail stably and do not disclose receipts.
- content-bound valid keys retain repository-isolated lookup behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no change to publication writes.

## EXP-220 — validate runtime store database path boundary
Статус: ACCEPTED
Цель: SQLite process store rejects malformed database path input before connection setup.
Гипотеза: public persistence construction cannot expose raw sqlite/path errors for invalid collaborator values.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: schema, valid path behavior and external persistence.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- invalid path shapes fail through stable project errors without files or connections.
- valid temporary database behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no filesystem permission expansion.

## Batch X — state, journal and GitHub response hardening

Исполнитель выполняет только `READY` карточки `EXP-221`—`EXP-230` строго по
возрастанию ID: одна карточка → проверки → отдельный local commit → следующая.
При ошибке, неясном scope или предсуществующих правках останови batch и верни evidence.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `2747ed3`—`a6a3f80`
  confirmed allowed scope, stable fail-closed boundaries and preserved valid
  behavior for EXP-221—230. Full suite: 409 tests passed, 1 opt-in Docker test
  skipped; no external calls, publication or configuration changes.

## EXP-221 — require boolean transition evidence flags
Статус: ACCEPTED
Цель: transition rejects truthy/falsy non-boolean evidence flags.
Гипотеза: malformed evidence cannot satisfy state gates by Python truthiness.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: transition graph and valid evidence semantics.
Разрешённые пути:
- src/app_contracts/state_machine.py
- tests/test_state_machine.py
Критерии приёмки:
- non-booleans fail stably; valid booleans preserve outcomes.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no new states.

## EXP-222 — validate publication recovery process identifier
Статус: ACCEPTED
Цель: `recover_publication` validates process ID before journal access.
Гипотеза: malformed IDs cannot yield raw journal errors or mutations.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: recovery policy and journal schema.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed IDs fail stably with no endpoint call; valid recovery is unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no automatic retry.

## EXP-223 — require canonical journal idempotency-key shape
Статус: ACCEPTED
Цель: journal preparation rejects malformed idempotency-key namespace before persistence.
Гипотеза: arbitrary strings cannot denote durable publication bindings.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid key algorithm and publication.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed keys leave no record; valid keys retain idempotency.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no schema migration.

## EXP-224 — require canonical journal request-digest shape
Статус: ACCEPTED
Цель: journal preparation rejects malformed request digests before persistence.
Гипотеза: arbitrary non-empty values cannot stand for request binding.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: digest algorithm and valid lifecycle.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed digests leave no record; valid SHA-256 digests preserve behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external calls.

## EXP-225 — validate GitHub token expiry is future-dated
Статус: ACCEPTED
Цель: minter rejects past or equal expiry timestamps.
Гипотеза: syntactically valid expired tokens cannot cross broker boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: real exchange, private keys and clock design.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- expired/equal responses are rejected without token return; future expiry remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no real GitHub calls.

## EXP-226 — reject unsafe GitHub verified-file whitespace paths
Статус: ACCEPTED
Цель: verified-file publication rejects leading/trailing-whitespace paths.
Гипотеза: path-normalization ambiguity cannot reach a scoped write.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid content and branch policy.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- unsafe paths make zero mocked calls; valid paths retain digest checks.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no provider activity.

## EXP-227 — reject boolean GitHub pull-request numbers
Статус: ACCEPTED
Цель: adapter rejects boolean PR-number responses.
Гипотеза: bool cannot satisfy integer provider receipt boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid responses and provider calls.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- boolean/malformed numbers fail stably; positive integers remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no PR creation.

## EXP-228 — validate reconciled GitHub receipt number type
Статус: ACCEPTED
Цель: reconciliation rejects malformed existing PR numbers.
Гипотеза: malformed GET response cannot manufacture a usable receipt.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: network behavior and valid reconciliation.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed receipt is safely denied/unknown; valid receipt behavior persists.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external calls.

## EXP-229 — validate mock publication idempotency-key grammar
Статус: ACCEPTED
Цель: mock publication rejects empty/malformed key segments before receipt creation.
Гипотеза: prefix-only matching cannot authorize malformed bindings.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: valid receipts and real GitHub.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed grammar yields no receipt; canonical keys retain idempotency.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no provider calls.

## EXP-230 — sanitize runtime persisted-JSON corruption errors
Статус: ACCEPTED
Цель: runtime event/audit read APIs contain malformed persisted JSON errors.
Гипотеза: corrupted local rows cannot expose raw decoder messages.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: schema migration, repair tooling and valid reads.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- malformed stored JSON yields stable project errors without content leakage; valid reads remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no database repair.

## Batch Y — remaining local boundary sweep

Исполнитель выполняет `READY` EXP-231—240 строго по ID, по одному commit и с
полным suite; при ошибке или неясном scope останови batch и верни evidence.

Результат Control Plane:
- ACCEPTED 2026-09-13: independent review commits `4cb7b41`—`a1b9132`; full suite: 420 tests passed, 1 opt-in Docker test skipped.

## EXP-231 — validate audit sink callability
Статус: READY
Цель: gateway rejects malformed audit sink before audit invocation.
Гипотеза: absent/non-callable sink cannot yield raw errors or an allow outcome.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: gateway routing and valid audit persistence.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed sinks give stable degraded deny; valid sinks preserve audit behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no external calls.

## EXP-232 — validate credential grant expiry time zone
Статус: READY
Цель: broker rejects expiry strings with invalid offsets deterministically.
Гипотеза: non-UTC-comparable grant expiry cannot open a channel.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: grant policy and GitHub connectivity.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- malformed expiry fails before factory; valid aware expiry remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no token material.

## EXP-233 — validate local sandbox snapshot shape
Статус: READY
Цель: local sandbox rejects malformed snapshot paths before copy.
Гипотеза: arbitrary objects cannot cross filesystem boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: Docker and valid sandbox execution.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- invalid snapshots fail stably without workspace creation; valid snapshots persist.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no Docker.

## EXP-234 — validate local sandbox close idempotence
Статус: READY
Цель: repeated local sandbox close is harmless.
Гипотеза: cleanup retries cannot raise raw filesystem errors.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: execution and Docker.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- double close is stable; normal cleanup behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no isolation claim.

## EXP-235 — validate memory summary source-reference uniqueness types
Статус: READY
Цель: source-reference duplicate checking rejects unhashable members safely.
Гипотеза: malformed values cannot trigger raw set errors.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: summary schema and persistence.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- malformed refs yield stable error; valid uniqueness remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no storage change.

## EXP-236 — validate correction root required identity
Статус: READY
Цель: correction validation rejects malformed identity whenever supersession is present.
Гипотеза: no arbitrary root can bypass self-reference validation.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: correction schema and storage.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- malformed roots fail stably; valid correction behavior persists.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no learning workflow.

## EXP-237 — validate publication receipt branch and digest scalars
Статус: READY
Цель: journal receipt completion rejects empty/malformed branch and digest before transition.
Гипотеза: malformed receipts cannot bind an attempted action.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: provider behavior and recovery policy.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed receipt leaves attempting state; valid receipt completes.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no provider call.

## EXP-238 — validate process-record SQLite enum boundary
Статус: READY
Цель: corrupted persisted state values yield stable runtime errors.
Гипотеза: invalid database enum cannot leak raw ValueError.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: database repair and valid lifecycle.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- corrupt state fails stably without row content; valid get persists.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no schema migration.

## EXP-239 — validate validator numeric constraint declarations
Статус: READY
Цель: malformed minimum/minLength/minItems schema declarations fail before instance validation.
Гипотеза: malformed schema cannot cause raw comparison errors.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: supported valid schema semantics.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- malformed declarations yield deterministic schema errors; valid schemas pass.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no new schema types.

## EXP-240 — validate secret scanner surface-name emptiness
Статус: READY
Цель: scanner rejects empty surface names before diagnostics.
Гипотеза: empty labels cannot create ambiguous leak findings.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: canary matching and host scanning.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- empty/non-string names fail stably; valid findings preserve names/order.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- no real-host claim.

## Batch Z — factual consolidation and local-chain planning

Этот batch подготавливает фактическую базу перед интеграционными работами.
Карточки зависимы: Control Plane переводит следующую в `READY` только после
приёмки evidence предыдущей. Внешние среды, credentials, публикации, Docker и
изменения production-конфигурации запрещены.

## EXP-241 — inventory implemented evidence and unresolved boundaries
Статус: ACCEPTED
Цель: собрать проверяемый локальный inventory реализованных компонентов, commit evidence, команд suite и оставшихся границ.
Гипотеза: дальнейшее планирование можно обосновать текущими фактами, а не устаревшим числом тестов или целевой архитектурой.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: изменения Python-кода, схем, testdev, Agent00X-sandbox, Docker, сеть, commit и публикация.
Разрешённые пути:
- docs/27-implementation-status.md
- docs/24-mvp-final-plan.md
- .opencode/tasks/WORK_QUEUE.md
Критерии приёмки:
- inventory отличает реализованное/unit-tested от spike, спроектированного и непроверенного;
- содержит актуальную локальную команду suite и результат, не преувеличивая его доказательную силу;
- перечисляет открытые границы сквозной цепи и следующее проверяемое свойство.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- inventory не является security certification или доказательством external publication.
Результат Control Plane:
- ACCEPTED 2026-09-13: commit `592ac44` adds evidence inventory scoped to the
  allowed status document; 20 schemas and 19 test files were independently
  counted. Full suite: 420 tests passed, 1 opt-in Docker test skipped.

## EXP-242 — reconcile operational implementation status
Статус: ACCEPTED
Цель: обновить единственный оперативный статус проекта по принятому evidence EXP-241.
Гипотеза: документ 27 должен отражать фактический local contract coverage и сохранять явные ограничения R0—R5.
Зависит от: EXP-241
Среда исполнения: local
Внешняя цель: none
Вне scope: изменение реализации, объявление production-ready, изменение roadmap без evidence, внешние среды и сеть.
Разрешённые пути:
- docs/27-implementation-status.md
Критерии приёмки:
- устаревшие test count/date заменены проверенными текущими фактами;
- статус чётко отделяет локальные unit/integration assertions от end-to-end и external proof;
- открытые ограничения и ближайший этап соответствуют inventory.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не изменяет документы, не входящие в allowed paths.
Результат Control Plane:
- ACCEPTED 2026-09-13: commit `4f79453` reconciles operational status to the
  accepted inventory without overstating local regressions as end-to-end proof.
  Full suite: 420 tests passed, 1 opt-in Docker test skipped.

## EXP-243 — reconcile README operational claims
Статус: ACCEPTED
Цель: привести README к принятому operational status без переноса устаревших утверждений о тестах и нарушениях.
Гипотеза: entrypoint проекта обязан ссылаться на документ 27 как на единственный source of truth и не обещать более сильную гарантию.
Зависит от: EXP-242
Среда исполнения: local
Внешняя цель: none
Вне scope: код, GitHub App setup, secrets, deployment и external publication.
Разрешённые пути:
- README.md
Критерии приёмки:
- README указывает актуальную команду проверки и корректно описывает её пределы;
- ссылки на текущий статус, roadmap и ограничения согласованы с документом 27;
- отсутствуют production-ready или end-to-end claims без evidence.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- не меняет инструкцию использования реальных credentials.
Результат Control Plane:
- ACCEPTED 2026-09-13: commit `6b490eb` aligns README with accepted document 27
  without production or end-to-end claims. Full suite: 420 tests passed, 1 skipped.

## EXP-244 — create proof-boundary traceability map
Статус: ACCEPTED
Цель: создать компактную матрицу «property → component → local evidence → remaining proof boundary → next experiment».
Гипотеза: явная карта предотвращает подмену local regression coverage доказательством cross-plane security.
Зависит от: EXP-242
Среда исполнения: local
Внешняя цель: none
Вне scope: код, schemas, policy semantics, testdev, Docker, сеть и external actions.
Разрешённые пути:
- docs/31-proof-boundary-traceability.md
- docs/22-documentation-map.md
Критерии приёмки:
- охватывает минимум authority/policy, gateway, broker, preparation/manifest, journal/recovery, GitHub adapter и observation;
- каждая строка различает реализовано, локально проверено и всё ещё непроверено;
- для каждой непроверенной boundary указан следующий минимальный эксперимент без неявного external доступа.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- матрица — planning artifact, не acceptance certificate.
Результат Control Plane:
- ACCEPTED 2026-09-13: commits `8fcfeb3` and `ef33283` create the traceability
  map and correct broker reuse semantics. Full suite: 420 tests passed, 1 skipped.

## EXP-245 — specify integrated local publication chain
Статус: ACCEPTED
Цель: зафиксировать contract-level сценарий одной local publication chain и её обязательные negative paths как основу Batch AA.
Гипотеза: до реализации интеграционного harness должны быть определены inputs, ownership, digest bindings, state transitions, expected evidence и stop conditions.
Зависит от: EXP-241
Среда исполнения: local
Внешняя цель: none
Вне scope: реализация harness, GitHub API, credential minting, external writes, Docker и testdev.
Разрешённые пути:
- docs/32-local-publication-chain-spec.md
- docs/22-documentation-map.md
Критерии приёмки:
- scenario связывает prepared change, approval, policy decision, gateway, broker, actuator, journal и receipt без обхода Authority Plane;
- определены минимум positive path, digest/approval swap deny, expired decision/grant deny, replay/idempotency и uncertain-effect recovery;
- документ явно называет, какие assertions локальны и что требует отдельной external proof card.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
Ограничения и риски:
- спецификация не делает external publication разрешённой.
Результат Control Plane:
- ACCEPTED 2026-09-13: commits `ae863fc` and `5fabb94` create the chain spec
  and separate component assertions from the unimplemented Batch AA harness.
  Full suite: 420 tests passed, 1 skipped.

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

Статус: CLOSED
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
- ACCEPTED 2026-09-11: независимое review подтверждает remediation `27670e9`:
  approval содержит digest полного canonical intent, а policy и brokered actuator
  проверяют его до provider channel. Regression покрывает согласованную подмену
  request + intent + grant (включая branch/idempotency key) и подтверждает zero
  provider calls; matching request по-прежнему достигает mock boundary.

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

## Batch K — contract-boundary regression sweep

Исполнитель выполняет только карточки `EXP-092`—`EXP-111`, строго сверху вниз и
по одной. Для каждой: минимальный scope, штатный suite, diff/status, один local
commit и отдельный evidence. При первой ошибке, неясном контракте или выходе за
scope — остановиться; не переходить к следующей карточке. Никаких внешних систем.

Результат Control Plane:
- ACCEPTED 2026-09-11: EXP-092—EXP-099 и EXP-101—EXP-111 проверены по
  разрешённым путям; `git diff --check` чист, независимый штатный suite —
  285 tests OK, 1 skipped. Внешних действий и push не было.
- EXP-100 переведена в `REVIEW`: требуется обязательная expiry-проверка на
  boundary открытия канала.

## EXP-092 — causal precedence priority regression
Статус: CLOSED
Цель: закрепить приоритет denial для позднего allowlisted intent над чужими non-intent событиями.
Гипотеза: mixed history не превращает future intent в валидную причину.
Зависит от: EXP-091
Среда исполнения: local
Внешняя цель: none
Вне scope: schema redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- result перед allowlisted intent с тем же invocation остаётся denied without payload leak даже при preceding non-intent;
- existing causal outcomes stay green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-093 — checkpoint cursor type boundary
Статус: CLOSED
Цель: malformed checkpoint cursor fails closed before journal comparison.
Гипотеза: bool, float and non-integer cursor values cannot alias valid cursors.
Зависит от: EXP-092
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, schema redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- invalid cursor types are rejected with stable non-payload error;
- valid cursor and existing checkpoint cases remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-094 — checkpoint trigger identity regression
Статус: CLOSED
Цель: checkpoint trigger ID comparison cannot be confused by malformed identifier types.
Гипотеза: only schema-valid trigger references reach journal lookup.
Зависит от: EXP-093
Среда исполнения: local
Внешняя цель: none
Вне scope: schema redesign, durable journal, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- malformed trigger identity is denied without stored event payload;
- recognised checkpoint remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-095 — pre-dispatch atomic refusal regression
Статус: CLOSED
Цель: dispatch is never invoked when either pre-dispatch journal write fails.
Гипотеза: failure of checkpoint or intent recording has no side effect.
Зависит от: EXP-094
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, external dispatch, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- each injected write failure raises PreDispatchError and leaves dispatch call count zero;
- successful path stays green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние commands:
- none
Commit: ALLOWED

## EXP-096 — approval identifier type boundary
Статус: CLOSED
Цель: malformed approval identifiers are rejected as contract errors, not raw lookup failures.
Гипотеза: invalid identity fields cannot enter authorization comparison.
Зависит от: EXP-095
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign, signatures, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed required approval/intent identifier produces stable non-secret denial;
- valid approval path remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-097 — decision expiry parsing regression
Статус: CLOSED
Цель: malformed decision expiry fails closed as ContractValidationError.
Гипотеза: expiry parsing never exposes raw parser exception at an actuator boundary.
Зависит от: EXP-096
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign, clock service, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed, non-string and naive expiry values deny with stable message;
- valid future and expired decision cases remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-098 — policy TTL configuration boundary
Статус: CLOSED
Цель: non-positive policy decision TTL cannot create immediately invalid allow decisions.
Гипотеза: invalid policy configuration is rejected deterministically.
Зависит от: EXP-097
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign, config framework, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- zero, negative and invalid TTL values fail closed without decision issuance;
- positive configured TTL behaviour remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-099 — credential grant identifier boundary
Статус: CLOSED
Цель: malformed credential grant binding cannot open a publication channel.
Гипотеза: broker validates grant identity before channel factory access.
Зависит от: EXP-098
Среда исполнения: local
Внешняя цель: none
Вне scope: real credentials, GitHub App, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- malformed grant/request binding is denied and channel factory call count stays zero;
- valid grant path remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-100 — credential grant expiry regression
Статус: CLOSED
Цель: invalid or expired credential grant cannot be used to obtain a publication channel.
Гипотеза: broker enforces grant lifetime before external channel access.
Зависит от: EXP-099
Среда исполнения: local
Внешняя цель: none
Вне scope: real credentials, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/broker.py
- src/app_contracts/github_app.py
- src/app_contracts/github_actuator.py
- tests/test_broker.py
- tests/test_github_app.py
Критерии приёмки:
- malformed and expired grant deny without channel creation or secret exposure on every broker opening path;
- valid unexpired grant path remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

Результат Control Plane:
- CHANGES REQUESTED 2026-09-11: `3731e5b` проверен, но expiry проверяется
  только при необязательном аргументе `now`; production broker paths могут
  открыть канал без проверки срока. Исправить в разрешённом scope так, чтобы
  expiry был обязательной границей до channel factory; без реального GitHub,
  secret или push.
- ACCEPTED 2026-09-11: remediation `b40efa1` делает timezone-aware `now`
  обязательным на всех broker opening paths и проверяет expiry до mint/factory.
  Независимый штатный suite: 288 tests OK, 1 skipped. Внешних действий и push
  не было.

## EXP-101 — actuator request identity regression
Статус: CLOSED
Цель: malformed actuator request identity is denied before publish invocation.
Гипотеза: request contract boundary prevents raw errors and channel side effects.
Зависит от: EXP-100
Среда исполнения: local
Внешняя цель: none
Вне scope: real publish, GitHub App, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- malformed request identity fails closed with publisher call count zero;
- existing authorized path remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-102 — publication process ID boundary
Статус: CLOSED
Цель: invalid publication process ID cannot create or mutate journal state.
Гипотеза: journal rejects malformed identity before SQLite persistence.
Зависит от: EXP-101
Среда исполнения: local
Внешняя цель: none
Вне scope: schema migration, real GitHub, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- invalid process ID fails deterministically and creates no record;
- valid prepare/recovery cases remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-103 — publication state transition regression
Статус: CLOSED
Цель: journal cannot mark completion from an unprepared or wrong state.
Гипотеза: receipt insertion remains bound to the expected transition.
Зависит от: EXP-102
Среда исполнения: local
Внешняя цель: none
Вне scope: schema migration, real GitHub, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- invalid transition leaves record unchanged and no receipt is stored;
- ordinary publication flow remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-104 — runtime audit reason-code boundary
Статус: CLOSED
Цель: malformed audit reason codes cannot be persisted or masquerade as valid audit evidence.
Гипотеза: runtime store validates shape and scalar type before insert.
Зависит от: EXP-103
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration, production store, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- malformed reason codes fail closed and audit history is unchanged;
- valid audit event remains readable.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-105 — runtime optimistic-version boundary
Статус: CLOSED
Цель: bool and malformed expected versions cannot alias an integer record version.
Гипотеза: version conflict protection remains type-safe.
Зависит от: EXP-104
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration, production store, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- invalid expected version rejects without state mutation;
- correct version still advances exactly once.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-106 — repository manifest duplicate-path regression
Статус: CLOSED
Цель: manifest cannot contain duplicate canonical target paths.
Гипотеза: two input spellings cannot create ambiguous publication content.
Зависит от: EXP-105
Среда исполнения: local
Внешняя цель: none
Вне scope: real repository, GitHub, Docker, testdev.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- duplicate canonical path is denied before manifest output;
- distinct safe paths retain deterministic manifest behaviour.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-107 — repository content type boundary
Статус: CLOSED
Цель: non-text publishable file content is rejected before hashing or manifest creation.
Гипотеза: manifest digest has one explicit content representation.
Зависит от: EXP-106
Среда исполнения: local
Внешняя цель: none
Вне scope: real repository, GitHub, Docker, testdev.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- bytes, null and non-string content fail without file output;
- valid text content remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-108 — secret scan nested serialization regression
Статус: CLOSED
Цель: canary detection covers nested mapping/list surfaces without leaking the canary in errors.
Гипотеза: recursive diagnostic serialization cannot hide nested credential material.
Зависит от: EXP-107
Среда исполнения: local
Внешняя цель: none
Вне scope: real secrets, external scanner, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- nested canary is detected and exception reports only surface names;
- clean nested values remain accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-109 — state transition evidence type regression
Статус: CLOSED
Цель: malformed transition evidence cannot authorize a state change.
Гипотеза: transition enforces evidence contract before evaluating target state.
Зависит от: EXP-108
Среда исполнения: local
Внешняя цель: none
Вне scope: workflow redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/state_machine.py
- tests/test_state_machine.py
Критерии приёмки:
- malformed evidence denies without transition;
- legitimate existing transitions remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-110 — memory summary interval timezone regression
Статус: CLOSED
Цель: naive or malformed summary timestamps fail closed.
Гипотеза: summary interval ordering compares only timezone-aware parsed timestamps.
Зависит от: EXP-109
Среда исполнения: local
Внешняя цель: none
Вне scope: memory backend, schema redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- malformed/naive timestamps deny without source payload leak;
- valid ordered interval remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-111 — learning correction version type boundary
Статус: CLOSED
Цель: correction version cannot be aliased by bool, float or invalid scalar types.
Гипотеза: version gate accepts only the supported explicit integer version.
Зависит от: EXP-110
Среда исполнения: local
Внешняя цель: none
Вне scope: learning backend, schema redesign, Docker, testdev, GitHub.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- malformed versions fail with stable non-payload validation error;
- current valid correction remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## Batch L — boundary follow-up

Выполнять только EXP-112—EXP-116 строго по порядку: local, штатный suite,
diff/status, один local commit и evidence на карточку. При первой ошибке — стоп.
Docker, testdev, Agent00X-sandbox, внешние системы и push запрещены.

## EXP-112 — authority identifier scalar boundary
Статус: CLOSED
Цель: typed approval/intent identifiers fail closed before equality checks.
Гипотеза: malformed scalar identity cannot alias authorization binding.
Зависит от: EXP-100
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign, GitHub.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- non-string required identifiers deny without payload leak; valid approval stays green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-113 — gateway malformed-envelope regression
Статус: CLOSED
Цель: malformed gateway envelope fails closed without raw lookup error.
Гипотеза: classification has deterministic mapping/type boundary.
Зависит от: EXP-112
Среда исполнения: local
Внешняя цель: none
Вне scope: gateway redesign, GitHub.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed envelope denied and existing routing remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-114 — publication idempotency-key boundary
Статус: CLOSED
Цель: malformed idempotency key cannot create journal state.
Гипотеза: journal prepare validates identity scalars before persistence.
Зависит от: EXP-113
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration, real GitHub.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed key denies with no record mutation; valid replay remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-115 — sandbox symlink containment regression
Статус: CLOSED
Цель: sandbox rejects symlink escape from working root.
Гипотеза: containment check resolves links before file access.
Зависит от: EXP-114
Среда исполнения: local
Внешняя цель: none
Вне scope: Docker, real repository, GitHub.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- crafted symlink escape is denied without outside read; normal file remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-116 — GitHub token response boundary
Статус: CLOSED
Цель: malformed token-mint response cannot create a usable channel.
Гипотеза: adapter validates opaque token response fields before use.
Зависит от: EXP-115
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub, secrets.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed response denies without token leak; valid mock response remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## Batch M — next boundary sweep

Исполнитель выполняет только EXP-117—EXP-119 по порядку: local, штатный suite,
diff/status, один local commit и evidence; при первой ошибке — стоп. Без push и
внешних систем.

## EXP-117 — runtime process identity boundary
Статус: CLOSED
Цель: invalid process identity cannot create a runtime record.
Гипотеза: SQLite boundary does not coerce malformed IDs.
Зависит от: EXP-116
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration, GitHub.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- malformed ID denies without row/event; valid create remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-118 — delegation mapping boundary
Статус: CLOSED
Цель: malformed delegation chain entries fail closed.
Гипотеза: chain validation rejects non-mapping parent/child before comparison.
Зависит от: EXP-117
Среда исполнения: local
Внешняя цель: none
Вне scope: delegation redesign, GitHub.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- malformed chain denies without details; valid chain remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-119 — repository absolute-path regression
Статус: CLOSED
Цель: absolute paths cannot enter publish manifest.
Гипотеза: path normalisation remains repository-contained.
Зависит от: EXP-118
Среда исполнения: local
Внешняя цель: none
Вне scope: real repository, GitHub.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- unsafe paths deny before output; safe paths remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-120 — validator root mapping regression
Статус: CLOSED
Цель: non-mapping root fails as contract validation.
Гипотеза: validator leaks no raw attribute error.
Зависит от: EXP-119
Среда исполнения: local
Внешняя цель: none
Вне scope: schema redesign, GitHub.
Разрешённые пути:
- src/app_contracts/validator.py
- tests/test_contracts.py
Критерии приёмки:
- malformed roots deny deterministically; valid corpus remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-121 — memory source reference boundary
Статус: CLOSED
Цель: malformed memory sources cannot satisfy provenance.
Гипотеза: source validation rejects invalid references before comparison.
Зависит от: EXP-120
Среда исполнения: local
Внешняя цель: none
Вне scope: memory backend, GitHub.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- malformed sources deny without payload leak; valid sources remain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-122 — correction reference boundary
Статус: CLOSED
Цель: malformed supersedes reference cannot pass correction gate.
Гипотеза: correction graph accepts explicit valid references only.
Зависит от: EXP-121
Среда исполнения: local
Внешняя цель: none
Вне scope: learning backend, GitHub.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- malformed reference denies; valid correction remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-123 — observation self-reference regression
Статус: CLOSED
Цель: result cannot use itself as predecessor.
Гипотеза: causality excludes self before classification.
Зависит от: EXP-122
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal, GitHub.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- self-reference denies without payload; valid predecessor stays green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-124 — mock provider identity boundary
Статус: CLOSED
Цель: malformed mock request cannot store a receipt.
Гипотеза: test provider cannot mask identity defects.
Зависит от: EXP-123
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub.
Разрешённые пути:
- src/app_contracts/mock_github.py
- tests/test_mock_github.py
Критерии приёмки:
- malformed identity denies without receipt; normal replay remains green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## Batch N — broad contract regression sweep

Исполнитель выполняет EXP-125—EXP-144 строго сверху вниз: local, штатный suite,
diff/status, один local commit и evidence. При первой ошибке остановиться. Без
push, Docker, testdev, Agent00X-sandbox и внешних систем.

## EXP-125 — authority expiry input boundary
Статус: ACCEPTED
Цель: malformed approval expiry fails closed.
Гипотеза: datetime parsing leaks no raw error.
Зависит от: EXP-124
Среда исполнения: local
Внешняя цель: none
Вне scope: policy redesign.
Разрешённые пути:
- src/app_contracts/authority.py
- tests/test_authority.py
Критерии приёмки:
- malformed expiry denies; valid approval stays green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-126 — broker grant class boundary
Статус: ACCEPTED
Цель: malformed grant class cannot open channel.
Гипотеза: broker binding rejects invalid grant shape before factory.
Зависит от: EXP-125
Среда исполнения: local
Внешняя цель: none
Вне scope: real credentials.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- invalid grant denies with zero factory calls.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-127 — actuator operation boundary
Статус: ACCEPTED
Цель: malformed operation cannot publish.
Гипотеза: actuator rejects before provider call.
Зависит от: EXP-126
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- invalid operation denies with zero side effect.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-128 — gateway audit event boundary
Статус: ACCEPTED
Цель: malformed audit event fails closed.
Гипотеза: gateway preserves deny semantics without raw error.
Зависит от: EXP-127
Среда исполнения: local
Внешняя цель: none
Вне scope: gateway redesign.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed audit input denies safely; known routing green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-129 — publication repository boundary
Статус: ACCEPTED
Цель: malformed repository cannot journal publication.
Гипотеза: journal validates before persistence.
Зависит от: EXP-128
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration.
Разрешённые paths:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- invalid repository denies without record mutation.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-130 — runtime audit mapping boundary
Статус: ACCEPTED
Цель: malformed audit mapping cannot persist.
Гипотеза: store keeps history unchanged on denial.
Зависит от: EXP-129
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- invalid audit mapping denied without mutation.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-131 — repository path whitespace boundary
Статус: ACCEPTED
Цель: unsafe path spellings cannot enter manifest.
Гипотеза: canonical path check remains contained.
Зависит от: EXP-130
Среда исполнения: local
Внешняя цель: none
Вне scope: real repository.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- unsafe spelling denied; safe manifest green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-132 — sandbox directory boundary
Статус: ACCEPTED
Цель: malformed sandbox root fails closed.
Гипотеза: local sandbox never escapes root.
Зависит от: EXP-131
Среда исполнения: local
Внешняя цель: none
Вне scope: Docker.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- invalid root denied; valid sandbox green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-133 — secret scan empty-canary boundary
Статус: ACCEPTED
Цель: invalid canary fails deterministically.
Гипотеза: scanner cannot silently accept unusable search token.
Зависит от: EXP-132
Среда исполнения: local
Внешняя цель: none
Вне scope: real secrets.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- invalid canary safe outcome; ordinary scan green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-134 — state target boundary
Статус: ACCEPTED
Цель: malformed state target cannot transition.
Гипотеза: transition contract rejects before mutation.
Зависит от: EXP-133
Среда исполнения: local
Внешняя цель: none
Вне scope: workflow redesign.
Разрешённые пути:
- src/app_contracts/state_machine.py
- tests/test_state_machine.py
Критерии приёмки:
- invalid target denied; valid transition green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-135 — observation checkpoint mapping boundary
Статус: ACCEPTED
Цель: malformed checkpoint fails closed.
Гипотеза: journal read cannot leak raw lookup error.
Зависит от: EXP-134
Среда исполнения: local
Внешняя цель: none
Вне scope: durable journal.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- malformed checkpoint denied; valid checkpoint green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-136 — learning correction mapping boundary
Статус: ACCEPTED
Цель: malformed correction is rejected.
Гипотеза: correction checker has deterministic root boundary.
Зависит от: EXP-135
Среда исполнения: local
Внешняя цель: none
Вне scope: learning backend.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- malformed correction denies; valid correction green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-137 — memory interval mapping boundary
Статус: ACCEPTED
Цель: malformed summary fails closed.
Гипотеза: memory validation has deterministic root boundary.
Зависит от: EXP-136
Среда исполнения: local
Внешняя цель: none
Вне scope: memory backend.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- malformed summary denies; valid summary green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-138 — chain root boundary
Статус: ACCEPTED
Цель: malformed chain root is rejected.
Гипотеза: chain checker leaks no raw type error.
Зависит от: EXP-137
Среда исполнения: local
Внешняя цель: none
Вне scope: delegation redesign.
Разрешённые пути:
- src/app_contracts/chain.py
- tests/test_contracts.py
Критерии приёмки:
- malformed root denied; valid chain green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-139 — GitHub broker grant mapping boundary
Статус: ACCEPTED
Цель: malformed adapter grant cannot mint token.
Гипотеза: adapter fails before secret-bearing call.
Зависит от: EXP-138
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub, secrets.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed grant denies with zero mint calls.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-140 — actuator request mapping boundary
Статус: ACCEPTED
Цель: malformed request fails before publication.
Гипотеза: actuator has explicit root contract.
Зависит от: EXP-139
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub.
Разрешённые пути:
- src/app_contracts/actuator.py
- tests/test_actuator.py
Критерии приёмки:
- malformed request denied with zero side effect.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-141 — broker request digest boundary
Статус: ACCEPTED
Цель: malformed digest cannot open channel.
Гипотеза: binding digest is strict before factory.
Зависит от: EXP-140
Среда исполнения: local
Внешняя цель: none
Вне scope: real credentials.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- malformed digest denied with zero factory calls.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-142 — publication digest boundary
Статус: ACCEPTED
Цель: malformed journal digest cannot persist.
Гипотеза: prepare validates scalar binding before storage.
Зависит от: EXP-141
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed digest denied with no record mutation.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-143 — runtime reason-code boundary
Статус: ACCEPTED
Цель: malformed audit reason fails closed.
Гипотеза: store rejects non-string codes before persistence.
Зависит от: EXP-142
Среда исполнения: local
Внешняя цель: none
Вне scope: database migration.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- malformed reason denied with history unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-144 — repository content mapping boundary
Статус: ACCEPTED
Цель: malformed change mapping cannot build manifest.
Гипотеза: repository process rejects invalid content before hashing.
Зависит от: EXP-143
Среда исполнения: local
Внешняя цель: none
Вне scope: real repository.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed mapping denied; valid manifest green.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## Формат task card

Добавляйте карточки в порядке выполнения. Исполнитель работает только с `READY`
карточками, сверху вниз, и возвращает отдельное evidence для каждой в конце запуска.
`BLOCKED`, `DRAFT`, `REVIEW` и `CLOSED` карточки не исполняются.

```text
## EXP-### — краткое название
Статус: DRAFT
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

## Batch O — contract boundaries, local-only

## EXP-145 — type-check gateway envelope fields
Статус: ACCEPTED
Цель: malformed values in required gateway envelope fields are denied before classification.
Гипотеза: presence alone must not let non-string operation/protocol/port or non-boolean security fields enter routing logic.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: policy semantics, audit sink implementation, external calls.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- malformed scalar field values return the stable malformed-envelope deny path and do not reach an audit sink.
- valid envelopes retain their current routing decision.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-146 — require boolean gateway policy availability
Статус: ACCEPTED
Цель: a non-boolean policy availability signal cannot authorize a request.
Гипотеза: truthy strings and integers must not be treated as a healthy Policy Engine.
Зависит от: EXP-145
Среда исполнения: local
Внешняя цель: none
Вне scope: changing fast/slow/degraded policy semantics for valid booleans.
Разрешённые пути:
- src/app_contracts/gateway.py
- tests/test_gateway.py
Критерии приёмки:
- non-boolean policy availability is denied deterministically without a raw exception or audit call.
- True and False preserve existing behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-147 — gate broker clock shape
Статус: ACCEPTED
Цель: credential validation rejects missing, non-datetime, and naive clock values before any channel action.
Гипотеза: grant expiry checks must not rely on an unchecked caller-supplied clock.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: credential minting and GitHub connectivity.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- invalid now values raise a stable ContractValidationError and leave the channel factory unopened.
- a valid aware datetime remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-148 — validate broker channel factory result
Статус: ACCEPTED
Цель: a malformed broker factory result is rejected before it can be exposed to an actuator.
Гипотеза: opening a credential channel must fail closed when the private provider interface is absent.
Зависит от: EXP-147
Среда исполнения: local
Внешняя цель: none
Вне scope: provider API implementation or credential material.
Разрешённые пути:
- src/app_contracts/broker.py
- tests/test_broker.py
Критерии приёмки:
- non-channel factory results fail with a stable boundary error and are not returned.
- valid test channels continue to open once per valid grant.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-149 — validate local sandbox allowlist shape
Статус: ACCEPTED
Цель: malformed local command allowlists cannot create a sandbox.
Гипотеза: allowlist members must be non-empty command names, not arbitrary iterable values.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: Docker backend and network isolation claims.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- malformed allowlist roots and members are denied before filesystem copy or process execution.
- a valid allowlist preserves existing local test execution.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-150 — validate local sandbox command invocation shape
Статус: ACCEPTED
Результат Control Plane: ACCEPTED — remediation commit ac9b59f удалил дублирующее определение теста; штатный suite зелёный.
Цель: malformed argv and timeout values are denied before subprocess invocation.
Гипотеза: strings, non-string argv members, booleans, and invalid timeout values must not cross the local process boundary.
Зависит от: EXP-149
Среда исполнения: local
Внешняя цель: none
Вне scope: Docker backend and command execution semantics for valid argv.
Разрешённые пути:
- src/app_contracts/sandbox.py
- tests/test_sandbox.py
Критерии приёмки:
- invalid invocation shapes raise SandboxError without starting a command.
- a valid allowlisted command continues to run in the ephemeral workspace.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-151 — gate secret-scan surface container
Статус: ACCEPTED
Цель: non-mapping scan surfaces fail deterministically without representation leakage.
Гипотеза: the canary scanner must validate its root boundary before iterating names or values.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: scanning credential files or changing canary matching semantics.
Разрешённые пути:
- src/app_contracts/secret_scan.py
- tests/test_secret_scan.py
Критерии приёмки:
- malformed surface roots raise a stable error that contains neither attacker values nor repr output.
- valid mappings retain their current findings.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-152 — pin correction identity boundary
Статус: ACCEPTED
Цель: a LearningCorrection self-reference check validates correction_id type before comparison.
Гипотеза: malformed correction identity cannot bypass or destabilize supersession validation.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: schema changes and correction storage.
Разрешённые пути:
- src/app_contracts/learning_correction.py
- tests/test_learning_correction.py
Критерии приёмки:
- malformed correction_id values are rejected without raw errors or payload leakage.
- valid correction and true self-supersession behavior remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-153 — validate MemorySummary source references
Статус: ACCEPTED
Цель: source_refs accepts only non-empty string references before duplicate comparison.
Гипотеза: malformed source members cannot be silently accepted or trigger a raw set/hash exception.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: summary schema and persistence.
Разрешённые пути:
- src/app_contracts/memory_summary.py
- tests/test_memory_summary.py
Критерии приёмки:
- malformed source members yield the stable source-refs boundary error without revealing values.
- valid distinct references and duplicate rejection preserve current behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-154 — gate state-machine current state type
Статус: ACCEPTED
Цель: malformed current state values are rejected deterministically.
Гипотеза: only ProcessState values may index the transition graph.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: transition graph changes or new states.
Разрешённые пути:
- src/app_contracts/state_machine.py
- tests/test_state_machine.py
Критерии приёмки:
- malformed current values raise InvalidTransition without raw type details.
- valid legal and illegal transitions retain existing outcomes.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-155 — sanitize unknown observation trigger errors
Статус: ACCEPTED
Цель: an unknown checkpoint trigger is denied without echoing its caller-supplied identifier.
Гипотеза: causality failures must not place untrusted event identifiers into error text.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: event schema, journal persistence, and dispatch execution.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- unknown trigger rejection has a stable payload-free error and does not alter journal/checkpoint state.
- a valid checkpoint remains accepted.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-156 — sanitize unknown invocation errors
Статус: ACCEPTED
Цель: an unknown result invocation reference is denied without echoing caller content.
Гипотеза: result causality errors must not disclose an untrusted invocation identifier.
Зависит от: EXP-155
Среда исполнения: local
Внешняя цель: none
Вне scope: intent type allowlist and event ordering semantics.
Разрешённые пути:
- src/app_contracts/observation_store.py
- tests/test_observation_store.py
Критерии приёмки:
- unknown invocation rejection has a stable payload-free error and returns no stored payload.
- valid causality references preserve their current cursor result.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-157 — validate publication request values before attempt
Статус: ACCEPTED
Цель: malformed required publication request values cannot transition a prepared record to attempting.
Гипотеза: type and emptiness checks must occur before the external-effect state boundary.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: MockGitHub behavior, GitHub connectivity, and recovery semantics for valid requests.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed required request values are rejected before journal mutation and endpoint invocation.
- a valid request remains published exactly once.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-158 — gate publication receipt object shape
Статус: ACCEPTED
Цель: malformed completion receipts cannot cause raw errors or mutate an attempt.
Гипотеза: journal completion validates the receipt boundary before reading its fields.
Зависит от: EXP-157
Среда исполнения: local
Внешняя цель: none
Вне scope: endpoint implementation or changing valid receipt binding checks.
Разрешённые пути:
- src/app_contracts/publication.py
- tests/test_publication.py
Критерии приёмки:
- malformed receipt roots and fields are rejected with a stable error while status remains attempting.
- a matching valid receipt still completes the record.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-159 — gate runtime lookup process identifier
Статус: ACCEPTED
Цель: malformed process IDs are rejected before SQLite read queries.
Гипотеза: read APIs must apply the same process identity boundary as process creation.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: database schema and valid not-found behavior.
Разрешённые пути:
- src/app_contracts/runtime_store.py
- tests/test_runtime_store.py
Критерии приёмки:
- get, events, and audit_events reject malformed process IDs with a stable contract error.
- valid existing and absent string IDs retain their current results.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-160 — gate publish-manifest prepared change shape
Статус: ACCEPTED
Цель: malformed prepared-change roots are denied before digest or workspace access.
Гипотеза: manifest construction must not trust an object merely because it exposes similar attributes.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: prepared change serialization format or repository publication.
Разрешённые пути:
- src/app_contracts/repository_process.py
- tests/test_repository_process.py
Критерии приёмки:
- malformed prepared-change inputs yield a stable ContractValidationError without output files or raw attribute errors.
- a genuine prepared change still exports the verified manifest.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-161 — canonicalize invalid mapping keys safely
Статус: ACCEPTED
Цель: canonical digest helpers reject unsupported mapping keys with a deterministic value error.
Гипотеза: digest callers must not receive raw sort/type errors for malformed object keys.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: changing canonical encoding of valid JSON values.
Разрешённые пути:
- src/app_contracts/digests.py
- tests/test_contracts.py
Критерии приёмки:
- mixed or non-string mapping keys fail without exposing their repr or values.
- valid mapping ordering and Unicode digest behavior remain unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-162 — gate GitHub App environment value types
Статус: ACCEPTED
Цель: malformed GitHub App configuration value types fail through the configuration boundary.
Гипотеза: non-string environment mapping values cannot trigger raw attribute errors during preflight.
Зависит от: none
Среда исполнения: local
Внешняя цель: none
Вне scope: real environment access, private-key reading, testdev, and GitHub requests.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed configuration value types raise GitHubAppConfigurationError without path or value leakage.
- valid metadata preflight behavior remains unchanged.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-163 — gate GitHub publication request fields
Статус: ACCEPTED
Цель: malformed GitHub publication request field values are rejected before reconciliation or POST.
Гипотеза: the provider channel validates scalar request fields at its own boundary even when called directly.
Зависит от: EXP-162
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub calls, token minting, branch creation, and pull-request creation.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed direct requests make zero get/post calls and raise a stable ContractValidationError.
- valid allowlisted requests retain current reconciliation and publication behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED

## EXP-164 — gate GitHub verified-file request shape
Статус: ACCEPTED
Цель: malformed verified-file publication inputs are rejected before branch or content provider calls.
Гипотеза: branch, staged-change, and file input boundaries are independently enforced in the GitHub channel.
Зависит от: EXP-163
Среда исполнения: local
Внешняя цель: none
Вне scope: real GitHub calls, token minting, branch creation, and pull-request creation.
Разрешённые пути:
- src/app_contracts/github_app.py
- tests/test_github_app.py
Критерии приёмки:
- malformed direct verified-file requests make zero get/post/put calls and fail with a stable boundary error.
- a valid verified manifest preserves existing scoped branch and content payload behavior.
Проверки:
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
Разрешённые внешние команды:
- none
Commit: ALLOWED
