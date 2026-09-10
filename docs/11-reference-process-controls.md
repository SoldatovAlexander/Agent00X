# Контроли процесса PROC-001

Статус: гипотеза для валидации; controls описывают требуемое поведение, а не
реализованные гарантии. Фактический статус — в документе 27.
Версия: 0.1

## Роли и ответственность

| Роль | Ответственность | Не имеет права |
|---|---|---|
| Process Owner | Цель, область, принятие риска и финальное approval | Делегировать неограниченные права через текст |
| Workflow Runtime | Состояние, переходы, таймеры, retry и журнал | Интерпретировать свободный текст как policy |
| Observation Collector | Неизменяемые события и checkpoint до действия | Принимать бизнес-решения, выдавать права или раскрывать секреты |
| Observer | Отчёт по разрешённой истории, пробелам и причинам | Управлять процессом, изменять историю или читать скрытые рассуждения |
| Orchestrator | Декомпозиция, маршрутизация и сбор результатов | Читать секреты, применять критические изменения |
| Worker | Подготовка ограниченного результата | Расширять scope, получать credential, обходить Gateway |
| Verifier | Независимая проверка acceptance criteria | Применять результат или подтверждать от имени владельца |
| Security Investigator | Анализ подозрительного payload | Получать write-capabilities или секреты |
| Secret Guardian | Проверка необходимости секретной операции по метаданным | Читать значение credential или исполнять произвольные команды |
| Credential Broker | Использование credential для именованной операции | Возвращать credential или принимать свободный shell |
| Action Gateway | Финальная policy-проверка и допуск к применению | Изменять staged payload после approval |
| GitHub Actuator | Публикация зарегистрированного staged change | Выполнять произвольный shell или API payload |

## Состояния ChangeRequest

```text
received
  -> specified
  -> authorized
  -> executing
  -> verifying
  -> staged
  -> waiting_approval
  -> applying
  -> completed
```

Дополнительные состояния:

- `waiting_input`;
- `quarantined`;
- `escalated`;
- `rejected`;
- `failed`;
- `reconciliation_required`;
- `cancelled`.

## Правила переходов

| ID | Правило |
|---|---|
| BR-001 | `received -> specified` только при наличии цели, владельца, scope и критериев приёмки |
| BR-002 | `specified -> authorized` только после policy decision для конкретного TaskContract |
| BR-003 | Worker получает capabilities не шире родительского grant и с меньшим либо равным TTL |
| BR-004 | `executing -> verifying` требует artifact digest и Evidence Bundle |
| BR-005 | Worker и Verifier не должны быть одним execution identity для независимой проверки высокого риска |
| BR-006 | `verifying -> staged` требует прохождения обязательных тестов и отсутствия unresolved blocker |
| BR-007 | Текст в чате не создаёт approval |
| BR-008 | Approval связывается с process ID, action digest, owner, policy version и expiry |
| BR-009 | Любое изменение связанного поля после approval аннулирует его |
| BR-010 | `applying -> completed` требует Action Receipt и postcondition check |
| BR-011 | Неопределённый side effect переводит процесс в `reconciliation_required` |
| BR-012 | Tainted content не может использоваться для authorization или capability expansion |
| BR-013 | Secret operation принимает только зарегистрированный operation type и фиксированный destination class |
| BR-014 | Потеря policy service запрещает write и secret operations |
| BR-015 | Решение или вызов инструмента не применяется/не отправляется, пока не сохранены его checkpoint и event intention |
| BR-016 | Наблюдатель отделяет факт, заявленное основание и интерпретацию; отсутствие основания явно отмечается |
| BR-017 | Учебная ветка создаётся из checkpoint в simulation mode, не переносит старые grants/approval и не повторяет внешний side effect |

## Матрица автономности

| Действие | Риск | Worker | Orchestrator | Автоматически | Approval |
|---|---:|---:|---:|---:|---:|
| Читать разрешённый snapshot | Low | Да | Да | Да | Нет |
| Искать внутри snapshot | Low | Да | Да | Да | Нет |
| Создавать patch в sandbox | Medium | Да | Нет | Да | Нет |
| Запускать allowlisted тест | Medium | Запрос | Координирует | Да | Нет |
| Сетевой поиск | Medium | Через Gateway | Через Gateway | По политике | Иногда |
| Выполнять secret operation | High | Только запрос | Только запрос | Нет | По политике |
| Применять patch | High | Нет | Нет | Нет | Да |
| Публиковать/деплоить | Critical | Нет | Нет | Нет | Да, отдельный процесс |
| Менять policy | Critical | Нет | Нет | Нет | Административный контур |

## Реестр инструментов

| ID | Инструмент | Видит Worker | Исполнитель | Основные проверки |
|---|---|---:|---|---|
| TOOL-001 | `workspace.read` | Да | Sandbox | path scope, size, classification |
| TOOL-002 | `workspace.patch` | Да | Sandbox | writable scope, symlinks, quota |
| TOOL-003 | `test.run` | Да | Test Runner | allowlist, timeout, network off |
| TOOL-004 | `evidence.submit` | Да | Workflow | schema, digest, refs |
| TOOL-005 | `security.escalate` | Да | Gateway | correlation, taint preservation |
| TOOL-006 | `secret_operation.request` | Да | Authority Plane | operation registry, delegation, purpose |
| TOOL-007 | `change.stage` | Нет | Workflow | verifier result, digest, policy |
| TOOL-008 | `change.apply` | Нет | Action Gateway | approval, digest, state, idempotency |
| TOOL-009 | `github.publish_pull_request` | Нет | GitHub Actuator | policy, approval, base SHA, scoped credential, idempotency |
| TOOL-010 | `observation.report` | Нет | Observer | read scope, event refs, redaction, факт/основание/интерпретация |

## Типы структурированных ошибок

- `invalid_input`;
- `forbidden`;
- `invalid_state`;
- `capability_required`;
- `approval_required`;
- `approval_stale`;
- `tainted_input`;
- `conflict`;
- `budget_exceeded`;
- `rate_limited`;
- `side_effect_unknown`;
- `policy_unavailable`.

## Минимальный audit event

```yaml
event_id: evt-01
process_id: process-42
task_id: task-7
actor: worker-3
event_type: tool.requested
timestamp: 2026-09-03T12:00:00Z
input_digest: sha256:...
policy_decision_id: pd-19
capability_grant_id: cap-4
result: allowed
output_digest: sha256:...
```

Payload, prompt, credential и чувствительные данные не записываются в audit по
умолчанию. Для расследования используются ссылки на классифицированные
артефакты с отдельным контролем доступа. Это компактная проекция audit, а не
полный формат ObservationEvent/Checkpoint; последний определён в документе 28.
