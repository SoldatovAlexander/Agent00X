# Статус реализации MVP

Статус документа: официальный baseline  
Версия: 1.0  
Дата фиксации: 2026-09-04  
Стадия проекта: реализация и исполняемая валидация

## 1. Итоговый статус

Подготовка концептуального комплекта завершена. Проект перешёл к созданию MVP.
Архитектура не считается окончательно доказанной: принятые решения проверяются
исполняемыми контрактами, тестами и security experiments.

```text
Documentation baseline       DONE
M0 Executable contracts      DONE
M0.5 Authority contracts     DONE
M1 Safe local preparation    IN PROGRESS
M2 Controlled publication    IN PROGRESS
M3 Adversarial validation    IN PROGRESS
M4 Dual UX                   PLANNED
```

## 2. Milestone status

| Milestone | Статус | Доказанный результат | Следующий gate |
|---|---|---|---|
| Documentation baseline | Выполнен | Видение, ADR, threat model, process model, бриф и план связаны | Изменять только по результатам реализации |
| M0 Executable contracts | Выполнен | Schemas, fixtures, digest chain, state machine, invariants и mock boundary работают | Контракты используются в M1/M2 |
| M0.5 Authority contracts | Выполнен | Identity, grants, delegation, trust и typed Authority Plane requests связаны в digest chain | Durable runtime и policy enforcement |
| M1 Safe local preparation | В работе | Docker smoke test и GitHub Actions подтверждают network deny, read-only snapshot и writable ephemeral workspace | Escape/kernel-hardening tests |
| M2 Controlled publication | В работе | Verified manifest создал реальный branch/commit и PR через scoped GitHub App | Использовать remote repository snapshot вместо fixture snapshot |
| M3 Adversarial validation | В работе | Сквозные taint, policy outage, replay, crash, canary, threat corpus и Docker network/resource checks проходят | Real-boundary tests и escape/kernel-hardening |
| M4 Dual UX | Не начат | Personal/Organization требования описаны | Общий runtime API и два представления |

## 3. Реализованные артефакты

### Контракты

В `schemas/` находятся шестнадцать Draft 2020-12 schemas:

1. Process Contract;
2. Canonical Envelope;
3. Task Contract;
4. Evidence Bundle;
5. Verification Report;
6. Staged Change;
7. Approval;
8. Publish Pull Request Intent;
9. Policy Decision;
10. Action Receipt;
11. Identity;
12. Capability Grant;
13. Delegation Receipt;
14. Trust Profile;
15. Actuator Request;
16. Credential Use Grant.

Agent-facing schemas используют `additionalProperties: false`; поле credential
не является частью допустимого контракта.

### Исполняемое ядро

- dependency-free validator поддерживаемого schema subset;
- canonical JSON и SHA-256 digest;
- cross-contract validation;
- workflow state machine;
- machine-readable invariant catalog;
- mock GitHub boundary с идемпотентностью;
- `SandboxBackend` abstraction;
- development-only local process backend;
- reference repository-change preparation pipeline.
- durable SQLite process state, optimistic versioning и append-only transition events.
- deterministic policy, repository/actuator allowlist и approval validation.
- Gateway Fast/Slow/Degraded classifier и typed mock actuator integration.
- Gateway enforcement, sanitized append-only audit и Slow Path requirement для publication.
- durable publication journal; recovery по idempotency key или reconciliation_required.
- Docker sandbox backend с default-deny network profile, без automatic pull/fallback.
- Docker smoke test: network deny, read-only snapshot и writable ephemeral workspace.
- GitHub Actions workflow запускает contract- и Docker integration-тесты на каждом push и pull request.
- GitHub App preflight принимает только безопасные metadata и ссылку на private-key file с правами `0600`; trusted Broker подписывает RS256 JWT и запрашивает scoped short-lived token без передачи его worker.
- Trusted GitHub PR channel разрешает только связанный installation/repository и `agent/process-*` branch, формируя фиксированный `POST /pulls` payload без произвольного endpoint или credential поля.
- Перед созданием PR trusted channel выполняет reconciliation по idempotency marker и возвращает уже созданный PR без второго external side effect.
- Локальная preflight-команда проверяет GitHub App metadata без сетевого вызова и без чтения key content; локальные `.env.github-app`, `.github-app/`, `*.pem` и `*.key` исключены из Git.
- GitHub installation-token request передаёт GitHub только короткое имя allowlisted repository, как требует API; full `owner/repository` остаётся для endpoint binding и audit context.
- Live spike на `testdev` подтвердил GitHub App installation `159119281`: scoped token создал fixture branch и PR [Agent00X-sandbox#1](https://github.com/SoldatovAlexander/Agent00X-sandbox/pull/1). Token и key content не сохранялись в repository, output или audit.
- Второй live spike на `testdev` связал verified `Staged Change` с GitHub Contents API: manifest создал commit `645ccc6bd4e8cfed4fdab434f15cdeff22d834ee` и [Agent00X-sandbox#2](https://github.com/SoldatovAlexander/Agent00X-sandbox/pull/2). В этом spike использован изолированный fixture snapshot; remote snapshot ещё не является входом verifier.

### Reference preparation pipeline

```text
authorized fixture snapshot
  -> isolated temporary copy
  -> declared path changes
  -> unified patch
  -> allowlisted tests
  -> Evidence Bundle
  -> Verification Report
  -> immutable Staged Change
```

При path traversal, неизменном payload или провале тестов staged change не
создаётся. Исходный fixture snapshot не изменяется.

## 4. Результаты проверки

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Зафиксированный результат: **71 из 71 платформенных тестов проходят** при `RUN_DOCKER_SANDBOX_TESTS=1`.
Дополнительно проходит один тест fixture repository.

Проверены schema validation, отсутствие credential-поля, зарегистрированная
operation, связи process/repository/task/evidence/verification/approval/receipt,
канонические digests, content-bound idempotency, сужение делегирования,
привязка credential-use к typed actuator request, durable workflow transitions,
защита от stale writer, append-only audit, approval expiry/version/destination,
policy unavailable, mock
publication replay, Gateway path classification, typed actuator boundary,
enforced Slow Path, sanitized append-only audit, command allowlist, минимальный environment, разделение
snapshot/workspace, path traversal и запрет staging после failed tests.
Recovery после mock side effect проверяет сбой до вызова, сбой после успешного
внешнего действия и неизвестный исход без слепого повтора.
Сквозные adversarial tests проверяют taint, недоступность policy и replay.
Broker interface открывает только одноразовый opaque channel, связанный с digest
typed actuator request; значение credential не присутствует в контракте.
Canary scan доказывает отсутствие test credential во всех контролируемых
agent-facing и persisted surfaces; искусственные утечки в evidence/audit ловятся.
Threat corpus исполняет ожидаемые результаты Gateway для taint, внешнего
протокола, policy outage, privilege transition и read-only path.
Docker smoke test выполнен на Docker Desktop 28.3.3 с образом `python:3.12-alpine`.
Network deny, read-only snapshot и isolated workspace подтверждены; устойчивость
к container escape и полноценная kernel isolation ещё не доказаны.
Тот же профиль успешно прошёл на чистом GitHub runner. Контейнер запускается от
непривилегированного UID/GID владельца workspace, поэтому writable workspace
проверяется одинаково локально и в CI.
Интеграционный тест дополнительно подтверждает deny для DNS и TCP-egress,
нулевые effective capabilities, фактические CPU/RAM/PID limits из Docker inspect
и реальное блокирование создания процессов сверх PID limit.

## 5. Что ещё не доказано

- kernel/process isolation от враждебного кода;
- запрет прямого network egress и обхода Gateway;
- настоящий policy decision и capability verification;
- cryptographic identity/delegation chain;
- применение реального short-lived GitHub credential;
- отсутствие секрета в crash dump и системной телеметрии;
- получение и verification remote repository snapshot до подготовки staged change;
- durable recovery во время side effect;
- Fast/Slow/Degraded Gateway routing;
- LLM Worker, Model Router и параллельный Local Agent Host;
- Personal и Organization UX.

## 6. Известные ограничения среды

### Docker

Docker Desktop 28.3.3 доступен. `DockerSandboxBackend` протестирован с образом
`python:3.12-alpine`: default-deny network, read-only snapshot и writable
ephemeral workspace подтверждены. `LocalProcessSandboxBackend` сохраняется как
development fallback и не заявляет network/kernel isolation.

### Node.js

Системный Node.js не запускается из-за отсутствующей версии Homebrew-библиотеки
`llhttp`. Python MVP от Node.js не зависит.

### Repository state

Рабочая директория является Git-репозиторием на ветке `main`; remote
`origin` настроен на GitHub. CI подтверждён: workflow `MVP verification`
выполняет 71 платформенный тест, включая Docker integration profile.

## 7. Блокеры и ограничения

| ID | Тип | Состояние | Влияние |
|---|---|---|---|
| ENV-002 | Среда | Node.js повреждён | Не блокирует Python MVP |
| MVP-001 | Частично снят | Docker backend и smoke isolation доказаны | Escape/kernel-hardening tests не пройдены |
| MVP-002 | Частично снят | Recovery/reconciliation доказан на mock boundary | Real external publication recovery не доказан |
| MVP-003 | Работа | Нет integrated Gateway enforcement и real Broker/actuator | M2 не завершён |
| MVP-004 | Частично снят | Broker interface и grant binding работают на mock boundary | Real GitHub App credential flow не доказан |

Ни одно ограничение не требует возвращения к общей подготовке документов.

## 8. Следующий исполняемый инкремент

1. GitHub App Broker и ограниченный real actuator spike — требует GitHub App и allowlisted test repository;
2. container escape/process-limit tests и расширенный network-bypass corpus;
3. расширить canary scan на реальный Broker и системную телеметрию после их появления.

## 9. Правило обновления статуса

Milestone меняет статус только при наличии исполняемого результата,
автоматических позитивных и негативных тестов, списка снятых и оставшихся
блокеров и явно зафиксированных свойств, которые ещё не доказаны. Число
документов, строк кода или happy-path демонстрация не означают завершения.
