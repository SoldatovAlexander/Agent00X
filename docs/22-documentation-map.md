# Карта комплекта и статусы

Статус: актуальный индекс  
Дата: 2026-09-04

## Концептуальное ядро

| Документ | Назначение | Статус |
|---|---|---|
| `00-vision-and-scope.md` | Видение, цели и границы | Рабочая концепция |
| `09-book-process-paradigm.md` | Методическая основа из книги | Принято |
| `01-architecture.md` | Контуры платформы | Принято как направление |
| `02-process-model.md` | Процесс, состояния и evidence | Принято концептуально |
| `23-project-brief.md` | Единый продуктово-архитектурный бриф и сравнение | Рабочая версия 0.1 |

## Агенты и адаптация

| Документ | Назначение | Статус |
|---|---|---|
| `05-agents-models-and-skills.md` | Роли, routing и skills | Принято, алгоритмы открыты |
| `17-agent-adaptation-and-patterns.md` | Полная сборка и Process Patterns | Принято |
| `18-recursive-agent-teams.md` | Agent Factory и рекурсивное делегирование | Принято |
| `16-dormant-specialists.md` | Сон, повторное использование и Function Packs | Принято |
| `14-effort-model.md` | Относительные затраты | Принято |

## Инфраструктура и безопасность

| Документ | Назначение | Статус |
|---|---|---|
| `03-security-and-threat-model.md` | Угрозы и контроли | Требует adversarial validation |
| `04-protocol-gateway.md` | A2A, MCP, AG-UI/A2UI, ACP, MHS | Стек принят |
| `19-local-agent-host.md` | Несколько агентов на одном компьютере | Принято |
| `20-identity-and-authorization.md` | Identity, grants, trust и mandates | Направление принято |
| `15-governance-and-trust.md` | Runtime verification и governance | Backlog принят |
| `21-agent-lifecycle-and-learning.md` | Evals, shadow, drift и process mining | Направление принято |

## Валидация

| Документ | Назначение | Статус |
|---|---|---|
| `10-reference-process.md` | Эталонный сквозной процесс | Гипотеза |
| `11-reference-process-controls.md` | Роли, правила и tools | Гипотеза |
| `12-validation-plan-v1.md` | Эксперименты VP-01…VP-19 | Выполняется |
| `13-traceability-matrix.md` | Связи ADR, правил и проверок | Рабочая версия |
| `07-validation-backlog.md` | Гипотезы и открытые вопросы | Актуальный backlog |
| `24-mvp-final-plan.md` | Thin vertical slice, milestones и Definition of Done | Итоговый план 1.0 |
| `25-external-review-disposition.md` | Решения по замечаниям внешней оценки | Рассмотрено |
| `26-mvp-contract-catalog.md` | Семантика реализованных M0-контрактов | Реализовано частично, 0.1 |
| `27-implementation-status.md` | Baseline реализации, тестов, ограничений и gates | Актуальный статус 1.0 |

## Управление решениями

| Документ | Назначение |
|---|---|
| `06-decision-register.md` | Принятые архитектурные решения |
| `08-references.md` | Источники и технологические кандидаты |
| `glossary.md` | Единая терминология |

## Созданные исполняемые артефакты

- Draft 2020-12 schemas десяти ключевых MVP-контрактов в `schemas/`;
- позитивная сквозная и негативные fixtures в `fixtures/`;
- dependency-free schema-subset validator;
- канонический SHA-256 digest и cross-contract chain validation;
- детерминированная state machine `PROC-001`;
- 29 unit tests контрактов, инвариантов, workflow, sandbox lifecycle и M1 flow;
- fixture repository и идемпотентная mock GitHub boundary;
- `SandboxBackend` и development-only process backend для начала M1.
- reference M1 flow: scoped change, patch, tests, evidence, verification и stage.

## Следующие исполняемые артефакты

- schemas Capability Card, Trust Profile и Transaction Mandate;
- форматы Process Pattern, Role Profile и Function Pack;
- исполняемая minimal policy и Gateway profiles;
- protocol conformance profiles;
- threat-case corpus;
- eval datasets;
- proof-of-concept Local Agent Host;
- security spike Gateway/Broker.

Эти элементы относятся к активной стадии исполняемой валидации.

Текущий доказанный статус фиксируется в `27-implementation-status.md`. При
расхождении оперативного статуса он имеет приоритет над более ранними
описательными формулировками.
