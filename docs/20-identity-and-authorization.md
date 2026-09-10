# Identity, capabilities и mandates

Статус: целевое направление; криптографическая identity/delegation chain не
реализована и не подтверждена.
Версия: 0.1

## Identity Fabric

Поддерживаются разные типы principals:

- human user;
- organization и team;
- process instance;
- orchestrator, agent и subagent instance;
- service/workload;
- external A2A agent;
- tool/MCP server;
- MHS device и controller.

Identity подтверждает, кто действует. Capability определяет, что разрешено.
Process state определяет, допустимо ли действие сейчас. Эти проверки не
взаимозаменяемы.

## Capability Grant

```yaml
capability_grant:
  id: cap-42
  issuer: policy-service
  subject: worker-7
  original_principal: user-12
  process_id: process-42
  actions: [repository.read, workspace.patch]
  resources: [repo:project-x@sha256:...]
  audience: [gateway-worker-7]
  delegable_actions: [repository.read]
  max_delegation_depth: 1
  expires_at: 2026-09-04T12:30:00Z
  policy_version: policy-18
  nonce: unique-value
```

Grant является короткоживущим, отзывным, связанным с процессом и непригодным для
другой аудитории.

## Delegation Receipt

Каждое делегирование создаёт подписанную запись с parent grant, child subject,
суженным scope, TTL, Effort Units и разрешением на следующую глубину. Полная
цепочка проверяется на Gateway и Action Gateway.

Отсутствие или разрыв цепочки означает deny, даже если непосредственный агент
успешно аутентифицирован.

## Trust Profile внешнего агента

```yaml
trust_profile:
  principal: a2a:partner.example/risk-agent
  level: verified-partner
  permitted_data: [public, partner-shared]
  prohibited_data: [secret, personal-sensitive]
  allowed_capabilities: [risk.assess]
  max_delegation_depth: 0
  required_verification: independent
  max_effort_units: 30
```

Стандартный протокол взаимодействия не повышает trust level автоматически.

## Transaction Mandate

Для финансовых, юридических, коммуникационных и иных значимых транзакций
используется отдельный Mandate:

```yaml
mandate:
  id: mandate-7
  principal: user-12
  process_id: process-42
  action_class: cloud-service-purchase
  recipient_class: approved-vendors
  limit:
    relative_units: 100
    monetary_limit: null
  expires_at: 2026-09-10T00:00:00Z
  approval_policy: explicit-before-commit
  delegation: forbidden
```

Mandate разрешает ограниченный класс намерений, но не раскрывает credentials и
не заменяет backend validation, approval или idempotency.

## Revocation и lifecycle

Identity, grants, delegation receipts, trust profiles и mandates имеют статус,
версию, issuer, TTL и механизм отзыва. Gateway проверяет актуальное состояние
для критических операций и не полагается только на кэшированный документ.

## Неизменяемые ограничения

- текст сообщения не создаёт identity или capability;
- Agent Card не является доказательством доверия;
- агент не подписывает собственное расширение прав;
- approval не переносится между principals или processes;
- dormant profile не хранит активный grant;
- секрет не является доказательством полномочия агента;
- fail-open запрещён для write, secret, transaction и MHS operations.
