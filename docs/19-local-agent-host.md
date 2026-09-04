# Параллельное локальное исполнение

Статус: архитектурное решение принято  
Версия: 0.1

## Назначение

Local Agent Host запускает несколько независимых процессов, команд и агентов на
одном компьютере. Он является системным runtime, а не LLM-агентом.

## Компоненты

```text
Local Agent Host
├── Host Supervisor
├── Resource Scheduler
├── Agent Factory
├── Sandbox Manager
├── Workspace/Snapshot Manager
├── Gateway Supervisor
├── Model Endpoint Pool
├── Lease and Lock Manager
├── Artifact Cache
├── Audit Sink
└── Recovery Manager
```

## Изоляция экземпляра

Каждый Agent Instance получает:

- уникальную execution identity;
- собственный process/workload boundary;
- отдельный workspace и temporary storage;
- персональный I/O Gateway endpoint;
- default-deny network policy;
- Capability Grant и Effort Profile;
- CPU/RAM/GPU/disk/time quotas;
- список разрешённых model endpoints;
- lifecycle и kill handle.

Host не помещает credentials в общий environment. Secret operations проходят
только через Authority Plane.

## Sandbox backend strategy

Local Agent Host не реализует собственный гипервизор. `SandboxBackend`
предоставляет единый контракт запуска, mount, network policy, quotas, artifact
export, stop и cleanup поверх существующих механизмов.

Для MVP сравниваются Docker и Podman. Базовый профиль использует container/process
boundary, read-only snapshot, отдельный writable workspace, минимальный
environment, default-deny egress и cgroups/namespaces там, где они доступны.
gVisor и Firecracker остаются кандидатами усиленного Linux-профиля после
измерения угроз, совместимости и overhead.

Конкретный backend может различаться между Linux, macOS и Windows, но обязан
проходить одинаковый conformance suite. Факт запуска в контейнере сам по себе не
считается доказательством изоляции.

## Планирование ресурсов

Scheduler учитывает приоритет процесса, deadline, risk, Effort Units, резерв под
verification, доступность моделей и fair-share между владельцами. Он должен
предотвращать монопольное потребление CPU/GPU, очереди моделей и диска одной
ветвью.

Допустимые реакции при дефиците:

- поставить задачу в очередь;
- уменьшить параллелизм;
- выбрать разрешённый более лёгкий model tier;
- приостановить низкоприоритетную ветвь;
- запросить изменение бюджета;
- безопасно завершить процесс.

## Workspaces и общие ресурсы

Входом является immutable snapshot или явно разрешённый mount. Записываемый
workspace принадлежит одному Agent Instance. Результат публикуется как artifact
с digest.

Изменяемые проекты, базы и MHS-устройства защищаются lease/lock. Shared cache
допустим только для immutable, проверенных и корректно классифицированных данных;
cache key включает trust domain и security-relevant versions.

## Несколько процессов одного проекта

Параллельное чтение snapshot разрешено. Параллельные изменения выполняются в
разных workspaces и не применяются напрямую. Перед apply проверяются base digest,
конфликт, актуальная policy и approval.

## Recovery

После перезапуска Host восстанавливает Process Runtime из durable state, но не
восстанавливает старые bearer tokens или неограниченные сетевые соединения.
Capabilities и leases проходят повторную проверку; неопределённые side effects
переходят в reconciliation.

## Управление

Должны поддерживаться адресные операции:

- stop отдельного агента;
- stop ветви;
- pause/resume процесса;
- revoke capability;
- quarantine profile или skill;
- global emergency stop.

Остановка одного instance не должна повреждать остальные процессы.
