# Рекурсивные команды и делегирование

Статус: архитектурное решение принято  
Версия: 0.1

## Принцип

Любой агент с делегируемой capability может запросить одного или нескольких
субагентов. Субагент может сделать то же самое, пока сохраняются пределы
глубины, прав, бюджета, времени и ожидаемой пользы.

Агент не создаёт процесс самостоятельно. Он формирует `AgentSpawnRequest`, а
Workflow, Policy Engine и Agent Factory принимают решение и создают экземпляр.

## AgentSpawnRequest

```yaml
spawn_request:
  process_id: process-42
  parent_agent_id: development-agent-3
  parent_task_id: task-7
  purpose: "Проверить первичные источники по выбранному API"
  requested_pattern: research/1.0
  requested_role: source-verifier
  required_skills: [documentation-search, source-evaluation]
  task_contract_ref: task-contract-7.2
  requested_capabilities: [repository.read, web.read]
  forbidden_capabilities: [repository.write, secret.use, action.apply]
  effort_request: 30
  delegation:
    may_spawn_children: false
    requested_depth: 0
```

## Монотонное сужение

```text
child.capabilities subset-of parent.delegable_capabilities
child.data_scope   subset-of parent.data_scope
child.audience     subset-of parent.audience
child.ttl          <= parent.ttl
child.effort       <= parent.remaining_effort
child.max_depth     = parent.max_depth - 1
```

Учитываются делегируемые права, а не все собственные права родителя.

## Delegation Value Gate

Новая ветвь допускается, если есть хотя бы одна процессная причина:

- отдельная компетенция;
- отдельный контекст или источник;
- независимая проверка;
- полезный параллелизм;
- иной risk или privacy boundary;
- необходимость другой модели или runtime.

Оценка:

```text
delegation_value =
  expected_quality_gain
  + parallelism_gain
  + verification_independence
  - effort_units
  - latency
  - coordination_complexity
  - added_security_risk
```

Если порог не достигнут, Factory предлагает текущему агенту tool call, skill или
обычный workflow step вместо нового субагента.

## Ограничения рекурсии

- `max_spawn_depth`;
- `max_children_per_agent`;
- `max_total_agents`;
- `max_parallel_agents`;
- Effort Units процесса и ветви;
- резерв для verification и безопасного завершения;
- deadline и max retries;
- разрешённые patterns и model tiers;
- запрет циклического delegation graph;
- лимит межагентных сообщений и размера artifacts.

## Team Manifest

```yaml
team:
  id: team-42
  process_id: process-42
  owner: user-12
  members:
    - {agent: architect-1, role: architect}
    - {agent: implementer-2, role: implementer}
    - {agent: verifier-3, role: verifier}
  communication:
    through_gateway: true
    direct_messages: false
    shared_raw_context: false
    artifact_exchange: true
  limits:
    max_agents: 5
    max_depth: 2
    max_parallel: 3
    effort_units: 240
  decisions:
    quality_verdict: verifier-3
    final_approval: user-12
```

## Изоляция и handoff

Каждый субагент получает отдельные identity, Gateway, workspace, context и
Capability Grant. Родителю возвращается типизированный `SubtaskResult` с
artifact/evidence refs, assumptions, risks и Effort Record. Полная переписка и
внутренний рабочий контекст автоматически не наследуются.

## Защита от agent fork bomb

Agent Factory атомарно резервирует Effort Units и concurrency slot до запуска.
При превышении лимитов, цикле, отсутствии результата или низкой ожидаемой пользе
запрос отклоняется. Один parent не может обойти лимит несколькими конкурирующими
spawn requests.

