# Матрица границ доказательств (proof-boundary traceability)

Дата: 2026-09-13. Производна от [документа 27](27-implementation-status.md),
который остаётся единственным оперативным статусом. Шкала уровней — раздел 2
документа 27.

Правило чтения: local regression coverage **не является** доказательством
cross-plane security. В каждой строке явно разделены три состояния:
реализовано, локально проверено (unit-тесты, `420 passed, 1 skipped`
от 2026-09-13) и всё ещё непроверено. Для каждой непроверенной границы указан
следующий минимальный эксперимент — только локально, без неявного внешнего
доступа (без сети, секретов, testdev, Docker, живых GitHub-вызовов).

| Свойство | Компонент | Реализовано и локально проверено | Непроверенная граница | Следующий минимальный эксперимент (local only) |
|---|---|---|---|---|
| Привязка approval к полному intent | `authority.py` (`approved_intent_digest`, `validate_approval`) | Deny при подмене intent/branch/key/grant с тем же staged digest; digest равенства fixture; mock broker/provider boundary не достигается | Выдача approval — доверенный вход; сквозная связка «выдача → проверка» как единое целое | Один локальный прогон issuance→policy→actuator→brokered boundary с выданным и подменённым intent, без сети |
| Целостность policy decision | `authority.py` (`DeterministicPolicy`, digest-bound deny, TTL/expiry в точке использования) | Deny при подмене digest; before/at/after expiry; решения schema-valid | Распространение/повтор решений между процессами; поведение при рассинхронизации часов | Локальный two-process replay-harness: устаревшее решение отклоняется на обеих границах |
| Классификация и маршрутизация Gateway | `gateway.py` (Fast/Slow/Degraded, sensitivity scalar, audit gate) | Adversarial unit-тесты: taint, outage, replay, malformed sensitivity/audit без доступа к sink | Поведение на реальном трафике; долговечность аудита | Replay записанных локальных envelope-fixture со сверкой решений, без сети |
| Привязка/expiry/single-use broker grant | `broker.py`, `github_actuator.py` | Digest-привязка, обязательный expiry на каждом открытии канала, single-use после failure; approval обязателен | Настоящий mint/revoke токенов; отзыв и propagation expiry | Тест с controllable clock seam и fake-minter: отзыв/истечение до открытия канала, локально |
| Подготовка и manifest binding | `repository_process.py` (`verified_contents`, gates путей/дублей/clock) | Подмена workspace/mapping, traversal-варианты, дубли, невалидные часы отклоняются до записей | Гонки файловой системы, конкурентные писатели, crash между write и verify | Локальный two-writer тест на ephemeral workspace с детерминированным порядком |
| Журнал и recovery (exactly-once) | `publication.py` (состояния journal, crash/reconciliation) | Crash-инъекции, unknown-outcome без слепого retry, collaborator-gates до мутации | Неатомарные эффекты провайдера; сверка неизвестного исхода end-to-end | Локальная матрица частичных сбоев (branch создан / файл не записан / PR неизвестен) с запретом blind retry |
| GitHub-адаптер | `github_app.py` (reconcile absent/unknown, перепроверка digest, encoding, namespace ветки, transport gates) | Mock-transport unit-тесты: malformed → unknown без POST/PUT; дубли путей; bare-префикс | Семантика и атомарность реального API | Контрактный тест по зачекиненным транскриптам API, без живых вызовов |
| Наблюдение (события/checkpoint/dispatch gate) | `observation_store.py` + R0-схемы | Append-only, привязка cursor/trigger, idempotency/conflict, pre-dispatch gate до записи | Durability при crash; инструментирование runtime (сборщик вне тестовых doubles) | Crash-restart тест на file-backed journal double, без новой инфраструктуры |

Что карта не утверждает: production Authority Plane, сквозную публикацию,
изоляцию backend, полноту истории, отсутствие утечек вне покрытых поверхностей.
Число тестов (420) — мера покрытия, а не доказательство границ доверия.
