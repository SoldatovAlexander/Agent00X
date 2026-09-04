# Agent Process Platform

Проект безопасной мультиагентной платформы, в которой работа организована как
исполняемые процессы, задачи маршрутизируются между моделями, а секреты и
критические действия изолированы от LLM-контуров.

Концепция и ключевые архитектурные решения зафиксированы. Проект перешёл к
исполняемой валидации: технологии выбираются по результатам узких экспериментов,
начиная с контрактов и trust boundaries вертикального MVP.

## Текущий статус реализации

Подготовка концептуальной документации завершена. Milestone M0 и контрактный
инкремент M0.5 выполнены: добавлены шестнадцать машинных JSON Schema, fixtures, канонический digest, сквозные
инварианты, state machine, fixture repository и mock GitHub boundary. Начат M1:
реализованы `SandboxBackend`, development-only process backend и Docker
container backend. Docker smoke test подтвердил default-deny network, read-only
snapshot и writable ephemeral workspace; escape/kernel-hardening остаются gate M1.

Reference M1 flow уже создаёт ограниченное изменение в ephemeral workspace,
строит patch, запускает allowlisted tests и выпускает schema-valid Evidence
Bundle, Verification Report и Staged Change. Это детерминированная реализация;
подключение LLM-worker будет отдельным адаптером после закрепления границ.

M0.5 добавляет Identity, Capability Grant, Delegation Receipt, Trust Profile,
typed Actuator Request и Credential Use Grant. Делегирование проверяется на
монотонное сужение, а credential-use связан с digest одного actuator request и
не содержит значения credential.

Durable Process Runtime использует SQLite: состояние и переходы сохраняются
атомарно, конкурентные записи защищены версией, а audit-события append-only.

Минимальная deterministic policy допускает публикацию только для allowlisted
repository и actuator при действующем approval, привязанном к точному digest,
operation и версии policy. Недоступная policy даёт fail-closed результат.

Gateway classifier выбирает Fast, Slow или Degraded Path и не допускает write,
secret или privilege transition на Fast Path. Typed mock actuator принимает
только согласованную связку request, policy decision и approval.

Gateway enforcement сохраняет в durable append-only audit только actor,
operation digest, результат и reason codes; Fast Path не может достичь
публикующего actuator.

Publication journal хранит durable состояние внешнего side effect: recovery
сверяет idempotency key с boundary и переводит неизвестный исход в
`reconciliation_required`, не выполняя слепой retry.

Сквозные adversarial tests подтверждают: tainted publish не авторизуется,
policy outage блокирует publication path, а replay не создаёт второй PR.

Broker предоставляет Actuator только одноразовый opaque channel, привязанный к
digest request; агентам и контрактам credential value недоступно.

Canary scanner проверяет отсутствие тестового credential во всех контролируемых
agent-facing и persisted surfaces и сигнализирует о найденной утечке.

Machine-readable threat corpus фиксирует security-регрессии Gateway и contract
injection как исполняемые сценарии, а не только как текстовый backlog.

Docker backend подготовлен без host fallback: он требует доступный daemon и
локально доступный image, после чего применяет container security profile.

Официальный baseline, ограничения среды и следующий gate:
[Статус реализации MVP](docs/27-implementation-status.md).

Запуск тестов:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## Документы

- [Видение и границы](docs/00-vision-and-scope.md)
- [Архитектура](docs/01-architecture.md)
- [Модель процессов](docs/02-process-model.md)
- [Безопасность и модель угроз](docs/03-security-and-threat-model.md)
- [Протоколы и Agent I/O Gateway](docs/04-protocol-gateway.md)
- [Модели, агенты и skills](docs/05-agents-models-and-skills.md)
- [Реестр решений](docs/06-decision-register.md)
- [Гипотезы и вопросы для валидации](docs/07-validation-backlog.md)
- [Референсы и кандидаты для исследования](docs/08-references.md)
- [Процессная парадигма из книги](docs/09-book-process-paradigm.md)
- [Эталонный процесс](docs/10-reference-process.md)
- [Контроли эталонного процесса](docs/11-reference-process-controls.md)
- [Validation Plan v1](docs/12-validation-plan-v1.md)
- [Матрица трассируемости](docs/13-traceability-matrix.md)
- [Модель относительных затрат](docs/14-effort-model.md)
- [Контуры управления и доверия](docs/15-governance-and-trust.md)
- [Dormant Specialists и Function Packs](docs/16-dormant-specialists.md)
- [Модель адаптации агента и Process Patterns](docs/17-agent-adaptation-and-patterns.md)
- [Рекурсивные команды и делегирование](docs/18-recursive-agent-teams.md)
- [Параллельное локальное исполнение](docs/19-local-agent-host.md)
- [Identity, capabilities и mandates](docs/20-identity-and-authorization.md)
- [Жизненный цикл и улучшение связок](docs/21-agent-lifecycle-and-learning.md)
- [Карта комплекта и статусы](docs/22-documentation-map.md)
- [Полный бриф проекта](docs/23-project-brief.md)
- [Итоговый план MVP](docs/24-mvp-final-plan.md)
- [Разбор внешней оценки](docs/25-external-review-disposition.md)
- [Каталог контрактов MVP](docs/26-mvp-contract-catalog.md)
- [Статус реализации MVP](docs/27-implementation-status.md)
- [Глоссарий](docs/glossary.md)

## Статусы утверждений

- **Принято** — базовое архитектурное решение. Меняется через новый ADR.
- **Гипотеза** — требует проверки прототипом, исследованием или экспериментом.
- **Открыто** — решение ещё не принято.
