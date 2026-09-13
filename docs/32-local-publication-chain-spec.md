# Local publication-chain specification (contract level)

Дата: 2026-09-13. Основа Batch AA. Производна от [документа 27](27-implementation-status.md)
и [матрицы границ](31-proof-boundary-traceability.md): локальные assertions ниже
покрыты unit-тестами (`420 passed, 1 skipped` от 2026-09-13), external proof
отсутствует и требует отдельных карточек. Спецификация не разрешает external
publication и не меняет реализацию.

## 1. Positive path (порядок обязателен, обход Authority Plane запрещён)

| Шаг | Вход (ownership) | Операция и digest binding | Переход состояния | Evidence |
|---|---|---|---|---|
| 1. Prepare | worker: `changes`, `test_command`, aware `now` | `prepare_change`: workspace → patch/evidence/verification/staged; `verified_contents` фиксированы | — (артефакты immutable) | patch, evidence/verification/staged digests |
| 2. Approve | человек/Control Plane | approval фиксирует `staged_change_digest` и `approved_intent_digest` (canonical digest полного intent) | — | approval contract |
| 3. Decide | policy: request + approval + staged + intent | `DeterministicPolicy.decide`: allow только при digest-bound approval; TTL 300s | — | policy decision (`evaluated_at`/`expires_at`) |
| 4. Classify | gateway: envelope | `enforce`: SLOW allow; чувствительность/audit-gates до sink | audit event (sanitized) | `GatewayDecision`, audit record |
| 5. Open channel | broker: credential grant | grant↔request digest, обязательный expiry (`now`), single-use, approval-bound intent — всё до открытия канала | grant → used (только после conforming channel) | channel handle (opaque, без credential value) |
| 6. Publish | actuator: decision + approval + intent + `now` | `publish_authorized_request`: expiry → approval → intent digest → decision/request match → branch/key → idempotency | journal: prepared → attempting → publish → completed | receipt (`MockPullRequest`) |
| 7. Recover | journal + reconciliation lookup | `recover_publication`: completed/prepared возвращаются; attempting требует сверки; uncertain — никогда не retry автоматически | attempting → completed / reconciliation_required | record, recovery outcome |

## 2. Обязательные negative paths (все — fail-closed до side effect)

| Нарушение | Где отклоняется | Ожидаемый результат |
|---|---|---|
| Подмена staged digest / intent / branch / key / grant при том же digest | policy (`deny`), затем actuator/broker boundaries | `deny` + отказ до endpoint/channel; сообщения без содержимого |
| Просроченные decision или grant (включая at-expiry) | actuator gate и broker open до канала | Отказ; grant не расходуется при failure фабрики |
| Omission approval / intent / `now` | actuator и broker boundaries | Детерминированный отказ до endpoint/channel |
| Повтор (replay) с тем же idempotency key | endpoint idempotency + journal prepared/existing | Исходный receipt, без второго side effect |
| Malformed collaborators (journal без `get`/`mark_*`, endpoint без `publish`, не-callable transports) | boundary gates до мутации/вызова | Стабильная ошибка границы, статус `prepared`, ноль вызовов |
| Неизвестный исход external effect | `recover_publication` | `reconciliation_required`, `PublicationRecoveryRequired`, без автоматического retry |
| Crash до/после external effect | журнал + recovery | Явный retryable (`prepared`) либо сверка существующего receipt |

## 3. Stop conditions

Остановка с отказом (без записи receipt и без повтора): deny policy/gateway,
просрочка, mismatch привязок, malformed collaborators, неизвестный исход,
 crash после external effect. Продолжение только явным разрешённым вызовом
после reconciliation — никогда автоматически.

## 4. Local assertions против external proof

Локально утверждено unit-тестами: все строки разделов 1–2 на mock-транспорте,
in-memory broker и SQLite/ephemeral journal. Отдельных external proof card
требуют: настоящий mint/revoke токенов, семантика и атомарность GitHub API,
изоляция backend, durability при crash, выдача approval как доверенный вход,
поведение при рассинхронизации часов. Число тестов — мера покрытия, а не
доказательство границ доверия.
