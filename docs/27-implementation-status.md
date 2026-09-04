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
M1 Safe local preparation    IN PROGRESS
M2 Controlled publication    PLANNED
M3 Adversarial validation    PLANNED
M4 Dual UX                   PLANNED
```

## 2. Milestone status

| Milestone | Статус | Доказанный результат | Следующий gate |
|---|---|---|---|
| Documentation baseline | Выполнен | Видение, ADR, threat model, process model, бриф и план связаны | Изменять только по результатам реализации |
| M0 Executable contracts | Выполнен | Schemas, fixtures, digest chain, state machine, invariants и mock boundary работают | Контракты используются в M1/M2 |
| M1 Safe local preparation | В работе | Reference change готовится в ephemeral workspace, тестируется и становится Staged Change | Container network/kernel isolation и process persistence |
| M2 Controlled publication | Не начат | Есть mock GitHub boundary и логические контракты | Gateway, policy, approval, actuator и Broker |
| M3 Adversarial validation | Не начат | Есть первые negative unit tests | Threat corpus, bypass, replay, crash и canary tests |
| M4 Dual UX | Не начат | Personal/Organization требования описаны | Общий runtime API и два представления |

## 3. Реализованные артефакты

### Контракты

В `schemas/` находятся десять Draft 2020-12 schemas:

1. Process Contract;
2. Canonical Envelope;
3. Task Contract;
4. Evidence Bundle;
5. Verification Report;
6. Staged Change;
7. Approval;
8. Publish Pull Request Intent;
9. Policy Decision;
10. Action Receipt.

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

Зафиксированный результат: **29 из 29 платформенных тестов проходят**.
Дополнительно проходит один тест fixture repository.

Проверены schema validation, отсутствие credential-поля, зарегистрированная
operation, связи process/repository/task/evidence/verification/approval/receipt,
канонические digests, content-bound idempotency, workflow transitions, mock
publication replay, command allowlist, минимальный environment, разделение
snapshot/workspace, path traversal и запрет staging после failed tests.

## 5. Что ещё не доказано

- kernel/process isolation от враждебного кода;
- запрет прямого network egress и обхода Gateway;
- настоящий policy decision и capability verification;
- cryptographic identity/delegation chain;
- применение реального short-lived GitHub credential;
- отсутствие секрета в crash dump и системной телеметрии;
- реальная публикация GitHub PR;
- durable recovery во время side effect;
- Fast/Slow/Degraded Gateway routing;
- LLM Worker, Model Router и параллельный Local Agent Host;
- Personal и Organization UX.

## 6. Известные ограничения среды

### Docker

Docker CLI установлен, но daemon недоступен. Текущий
`LocalProcessSandboxBackend` — development fallback: он не заявляет network или
kernel isolation и не снимает блокер VP-02.

### Node.js

Системный Node.js не запускается из-за отсутствующей версии Homebrew-библиотеки
`llhttp`. Python MVP от Node.js не зависит.

### Repository state

Рабочая директория не является Git-репозиторием. История изменений, branching и
CI отсутствуют. Инициализация Git и remote требует отдельного решения владельца.

## 7. Блокеры и ограничения

| ID | Тип | Состояние | Влияние |
|---|---|---|---|
| ENV-001 | Среда | Docker daemon недоступен | Блокирует доказательство container isolation, не блокирует Gateway/policy code |
| ENV-002 | Среда | Node.js повреждён | Не блокирует Python MVP |
| ENV-003 | Организационное | Git не инициализирован | Не блокирует тесты, блокирует history/CI flow |
| MVP-001 | Работа | Нет container backend | M1 не завершён |
| MVP-002 | Работа | Нет durable Process Runtime | Recovery не доказан |
| MVP-003 | Работа | Нет Gateway/policy/approval | M2 не начат |
| MVP-004 | Работа | Нет Broker/real actuator | Secretless publication не доказана |

Ни одно ограничение не требует возвращения к общей подготовке документов.

## 8. Следующий исполняемый инкремент

Пока container daemon недоступен:

1. minimal deterministic policy;
2. Gateway path classifier и canonical request handling;
3. approval validation по digest и expiry;
4. typed actuator request;
5. append-only audit events;
6. durable process state на локальном хранилище;
7. negative tests для policy unavailable, taint и replay.

После появления daemon добавляется Docker/Podman backend и выполняются network,
mount, environment, process и escape tests.

## 9. Правило обновления статуса

Milestone меняет статус только при наличии исполняемого результата,
автоматических позитивных и негативных тестов, списка снятых и оставшихся
блокеров и явно зафиксированных свойств, которые ещё не доказаны. Число
документов, строк кода или happy-path демонстрация не означают завершения.

