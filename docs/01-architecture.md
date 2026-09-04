# Целевая архитектура

Статус: концептуальная, принята как направление

## Контуры

```text
Users / External Agents / Tools / Devices
                  |
          Protocol Adapters
                  |
          Agent I/O Gateways
                  |
    +-------------+--------------+
    |                            |
Control Plane                Execution Plane
identity, policy,            orchestrator, workers,
registry, routing,           verifiers, sandboxes,
budgets, audit               process runtime
    |                            |
    +---------- Action Gateway--+
                    |
          Authority Plane
    credential broker, approvals,
      scoped identities, vaults
```

## Control Plane

Хранит конфигурацию и принимает детерминированные решения:

- идентичности пользователей, агентов и сервисов;
- реестр агентов, моделей, skills, инструментов и протоколов;
- политики доступа и классификацию данных;
- бюджеты, квоты и правила маршрутизации;
- журнал событий и метаданные provenance;
- версии процессов и конфигураций.

Оркестратор обращается к Control Plane, но не является его администратором.

## Execution Plane

Исполняет ограниченные контракты задач:

- процессный оркестратор;
- временные рабочие агенты;
- независимые верификаторы;
- sandbox-среды;
- хранилище артефактов;
- долговечный runtime процессов.

Каждый агент получает минимальный контекст, отдельную идентичность, ограниченный
набор capabilities и одноразовое рабочее пространство.

## Local Agent Host

Один компьютер может одновременно исполнять несколько независимых процессов,
команд и агентов. Для этого используется Local Agent Host — системный runtime,
который не является агентом и не принимает содержательных решений.

Он отвечает за:

- запуск и завершение agent instances;
- sandbox и отдельный workspace каждого экземпляра;
- process, filesystem и network isolation;
- CPU, RAM, GPU, disk, token и time quotas;
- распределение локальных моделей и внешних model endpoints;
- персональный I/O Gateway для каждого агента;
- блокировки общих проектов, устройств и других ресурсов;
- сбор событий без смешивания контекстов;
- восстановление процессов после перезапуска компьютера;
- принудительную остановку отдельного агента, ветви или всего host.

Control Plane и Credential Broker могут быть общими сервисами компьютера, но
решения, credentials, workspaces и журналы доступа логически изолируются по
process ID, principal и trust domain.

```text
Local Agent Host
├── Process A
│   ├── Orchestrator A
│   ├── Worker A1
│   └── Verifier A2
├── Process B
│   ├── Orchestrator B
│   └── Researcher B1
└── Shared infrastructure
    ├── Scheduler
    ├── Policy client
    ├── Credential Broker client
    ├── Artifact store
    └── Audit sink
```

Shared infrastructure не означает общий LLM-контекст или общую файловую
область. Совместное использование возможно только для явно опубликованных
immutable artifacts и проверенных read-only caches.

## Authority Plane

Единственный контур, способный применять привилегированные операции:

- проверяет principal, владельца, цель, ресурс, аудиторию и срок действия;
- использует credential внутри доверенного процесса;
- предпочитает короткоживущие scoped tokens;
- возвращает результат и квитанцию, но не значение секрета;
- поддерживает отзыв полномочий и аварийную блокировку.

Secret Guardian может использовать LLM для классификации намерения, но решение
policy engine и применение credential выполняются детерминированно.

## Основные потоки

### Выполнение задачи

1. Пользователь создаёт цель.
2. Оркестратор выбирает или создаёт версию процесса.
3. Процесс формирует типизированный task contract.
4. Router выбирает модель и среду исполнения.
5. Worker создаёт результат и evidence bundle.
6. Verifier независимо проверяет критерии приёмки.
7. Изменение сохраняется как staged action.
8. Policy engine и при необходимости человек одобряют точный digest.
9. Action Gateway применяет изменение идемпотентно.
10. Процесс сохраняет receipt и переходит в завершённое состояние.

### Секретная операция

1. Агент запрашивает именованную операцию, а не credential.
2. Gateway проверяет цепочку делегирования и provenance запроса.
3. Policy engine проверяет цель, владельца, ресурс, окружение и аудиторию.
4. Credential Broker получает credential из vault и выполняет операцию.
5. Агенту возвращается очищенный результат и action receipt.

## Запрещённые обходные пути

- прямой сетевой интерфейс агента в обход I/O Gateway;
- общий `.env` для нескольких агентов;
- передача секретов через prompt, tool result, лог или артефакт;
- выдача произвольной shell-команды Secret Guardian;
- применение staged action без повторной проверки актуальной политики;
- увеличение capabilities на основании текста из документа или ответа агента.

## Связанные детальные спецификации

- [адаптация и Process Patterns](17-agent-adaptation-and-patterns.md);
- [рекурсивные команды](18-recursive-agent-teams.md);
- [Local Agent Host](19-local-agent-host.md);
- [identity и authorization](20-identity-and-authorization.md);
- [lifecycle и улучшение связок](21-agent-lifecycle-and-learning.md);
- [Dormant Specialists и Function Packs](16-dormant-specialists.md);
- [Effort Units](14-effort-model.md).
