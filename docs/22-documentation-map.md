# Карта комплекта и статусы

Статус: актуальный индекс  
Дата: 2026-09-07

Для первого знакомства и обсуждения с коллегами:
[Агент 00Х простым языком](29-agent-explained.md).
Последние дополнения концепции: [наблюдатель и обучение](28-observer-and-learning.md)
и [модель памяти](30-memory-model.md).
Актуальный порядок работ — R0—R5 в плане MVP версии 1.1. Новые форматы пока
спроектированы на уровне документа, а не реализованы в коде.

## Концептуальное ядро

| Документ | Назначение | Статус |
|---|---|---|
| `00-vision-and-scope.md` | Видение, цели и границы | Рабочая концепция |
| `09-book-process-paradigm.md` | Методическая основа из книги | Принято |
| `01-architecture.md` | Контуры целевой платформы | Принято как направление; не текущий deployment |
| `02-process-model.md` | Процесс, состояния и evidence | Принято концептуально |
| `23-project-brief.md` | Бриф широкой платформы и сравнение | Рабочая версия; не критерий первого среза |

## Агенты и адаптация

| Документ | Назначение | Статус |
|---|---|---|
| `05-agents-models-and-skills.md` | Роли, routing и skills | Целевое направление; LLM Worker/Router не реализованы |
| `17-agent-adaptation-and-patterns.md` | Полная сборка и Process Patterns | Концепция; не реализовано |
| `18-recursive-agent-teams.md` | Agent Factory и рекурсивное делегирование | Концепция; отложено |
| `16-dormant-specialists.md` | Сон, повторное использование и Function Packs | Концепция; отложено |
| `14-effort-model.md` | Относительные затраты | Модель для будущего измерения |

## Инфраструктура и безопасность

| Документ | Назначение | Статус |
|---|---|---|
| `03-security-and-threat-model.md` | Угрозы и контроли | Требует adversarial validation |
| `04-protocol-gateway.md` | A2A, MCP, AG-UI/A2UI, ACP, MHS | Целевой стек; adapters не реализованы |
| `19-local-agent-host.md` | Несколько агентов на одном компьютере | Целевая модель; Host не реализован |
| `20-identity-and-authorization.md` | Identity, grants, trust и mandates | Направление принято |
| `15-governance-and-trust.md` | Runtime verification и governance | Backlog принят |
| `21-agent-lifecycle-and-learning.md` | Evals, shadow, drift и process mining | Направление принято; learning branch не реализован |

## Валидация

| Документ | Назначение | Статус |
|---|---|---|
| `10-reference-process.md` | Эталонный сквозной процесс | Гипотеза |
| `11-reference-process-controls.md` | Роли, правила и tools | Гипотеза |
| `12-validation-plan-v1.md` | Эксперименты VP-01…VP-23 | Выполняется; VP-20…23 запланированы |
| `13-traceability-matrix.md` | Связи ADR, правил и проверок | Рабочая версия |
| `07-validation-backlog.md` | Гипотезы и открытые вопросы | Актуальный backlog |
| `24-mvp-final-plan.md` | Исследовательский срез, R0—R5 и Definition of Done | План 1.1 |
| `28-observer-and-learning.md` | Наблюдатель, checkpoint, ветвление и корректировка | Концепция принята, форматы спроектированы |
| `29-agent-explained.md` | Назначение, цели и архитектура простым языком | Материал для коллег |
| `30-memory-model.md` | Слои памяти, ретенция и суммаризация | Концепция принята, не реализовано |
| `25-external-review-disposition.md` | Решения по замечаниям внешней оценки | Рассмотрено |
| `26-mvp-contract-catalog.md` | Семантика реализованных M0-контрактов | Реализовано частично, 0.1 |
| `27-implementation-status.md` | Реализация, тесты, ограничения и gates | Единственный оперативный статус 1.1 |

## Управление решениями

| Документ | Назначение |
|---|---|
| `06-decision-register.md` | Принятые архитектурные решения |
| `08-references.md` | Источники и технологические кандидаты |
| `glossary.md` | Единая терминология |

## Созданные исполняемые артефакты

- Draft 2020-12 schemas шестнадцати ключевых MVP-контрактов в `schemas/`;
- позитивная сквозная и негативные fixtures в `fixtures/`;
- dependency-free schema-subset validator;
- канонический SHA-256 digest и cross-contract chain validation;
- детерминированная state machine `PROC-001`;
- тесты контрактов, Gateway/policy, Broker, recovery, canary/adversarial controls, threat corpus, durable workflow, sandbox lifecycle и M1 flow (актуальный прогон — в документе 27; Docker integration opt-in);
- fixture repository и идемпотентная mock GitHub boundary;
- `SandboxBackend` и development-only process backend для начала M1.
- reference M1 flow: scoped change, patch, tests, evidence, verification и stage.
- SQLite Process Runtime с атомарными versioned transitions и append-only events.
- deterministic policy и approval validation с fail-closed policy-unavailable path.
- Gateway Fast/Slow/Degraded classifier и typed mock actuator integration.
- Gateway enforcement, append-only sanitized audit и запрет Fast Path для actuator.
- Durable publication journal и recovery/reconciliation вокруг mock side effect.
- Сквозные adversarial tests: taint, policy outage и replay.
- Broker interface и одноразовый opaque actuator channel без credential value.
- Canary credential scanner для agent и persisted surfaces.
- Машиночитаемый threat corpus для Gateway и contract injection.
- Подготовленный Docker sandbox profile без host fallback.

## Следующие исполняемые артефакты

Очередность фиксирована планом R0—R5:

1. ObservationEvent, Checkpoint, LearningCorrection и MemorySummary schemas с
   валидаторами и негативными тестами.
2. Исправление привязки проверенного manifest и approval к публикации, плюс
   checkpoint до действия.
3. Затем — LLM Worker, исторический Observer, учебная ветка и эксперимент.

Capability Card, Transaction Mandate, protocol adapters, Router, Local Agent
Host и Function Packs остаются последующими исследовательскими направлениями.

Текущий доказанный статус фиксируется в `27-implementation-status.md`. При
расхождении оперативного статуса он имеет приоритет над более ранними
описательными формулировками.
