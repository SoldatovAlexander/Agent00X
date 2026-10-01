# Agent Process Platform / Агент 00Х

Исследовательский прототип для проверки гипотезы: поможет ли явное представление
целей, данных, состояния, процедур, полномочий и результатов агенту исполнять
проработанную бизнес-функцию. Первый сценарий — `repository-change`.

Наблюдатель, контрольные точки каждого решения и вызова инструмента, а также
обучение через ветвление исполнения входят в замысел прототипа. Контракты
наблюдателя и локальный file-backed SQLite journal покрыты unit-тестами;
collector, отчёты и учебные ветки отсутствуют. Материал для коллег:
[объяснение проекта](docs/29-agent-explained.md).
Память будет слоистой и ограниченной: после шести месяцев — месячные, после года
— годовые сводки; [полная политика](docs/30-memory-model.md).

## Состояние

Есть 20 JSON Schema (16 базовых и 4 контракта наблюдателя), fixtures,
детерминированный reference flow подготовки изменений, SQLite runtime, mock
publication boundary, sandbox-профили и отдельные GitHub App spikes. Это не
равнозначно готовому агенту или доказанной сквозной безопасности: нарушения
привязки проверенного изменения к manifest и approval к запросу публикации
закрыты локальными fail-closed regression. Batch AA добавил composed local
harness для approval → policy → manifest → Broker → journal → recovery на
mock/in-memory/ephemeral doubles, а Batch AB закрепил gateway-before-broker
порядок в компоненте. Batch AD добавил deterministic twin-workspace и
same-workspace interleaving проверки подготовки. Это не production
orchestrator, доказательство реальной параллельной записи, filesystem locking,
сквозной безопасности или external publication. Batch AE добавил локальную
SQLite persistence/reopen и fail-closed проверки ObservationEvent/Checkpoint;
они не доказывают power-loss durability, защиту от привилегированного изменения,
collector completeness, access control или многопроцессную конкурентность.
Batch AF добавил локальный детерминированный executor shell с injected Worker,
Verifier и sandbox backend. Это не реальный LLM Worker, проверенный remote
snapshot, production sandbox или publication chain; детали и открытые границы —
в документе 27. Batch AG добавил экспорт дерева точного commit из локальной
Git object database и повторный запуск allowlisted-команды в отдельной локальной
sandbox-сессии. Batch AH (R2, локальный батч 3/3, 20 карточек) проверил
controlled publication и reconciliation только на локальном mock endpoint,
in-memory broker и SQLite journal. Это не remote provenance и не independently
trusted verifier: backend/verifier остаются injected doubles, а process backend
 — development fallback; real provider/credentials, production isolation и
durability остаются вне подтверждённого scope. Batch AI — отдельный локальный
R2 follow-up (20 карточек): bounded subprocess JSON handoff ограниченного
`VerifierInput` в дочерний процесс и приём только bound `VerifierResult`
(AI-1—AI-4 — wire contract, AI-5—AI-12 — процессный адаптер и fail-closed
поведение, AI-13—AI-19 — интеграция и отказная матрица). На 2026-10-01 принято
17/20 карточек Batch AI, карточки EXP-365—367 выполнены локально и ожидают
приёмки Control Plane. Это process-boundary prototype на текущем host, а не
independently trusted verifier: process separation не является security
isolation, remote provenance, production sandbox, реальная модель и external
providers остаются открытыми.

Единственный актуальный статус реализации и границ доказательств:
[документ 27](docs/27-implementation-status.md). Порядок работ R0—R5:
[план исследовательского прототипа](docs/24-mvp-final-plan.md).

Проверка существующего кода:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Обычный прогон на 2026-10-01: 709 тестов, 708 прошли, один opt-in Docker test
пропущен. Это подтверждает только покрытые тестами локальные свойства на
текущей машине, не безопасность всей цепочки. Подробнее — в документе 27.

## GitHub App: локальная подготовка

`.env.github-app.example` содержит только metadata отдельного allowlisted
тестового репозитория. Private key и `.env.github-app` не должны попадать в Git.
Preflight проверяет конфигурацию без сетевого вызова и без чтения ключа:

```bash
set -a; source .env.github-app; set +a
python3 scripts/github_app_preflight.py
```

Broker preflight service на `testdev` проверяет metadata при boot. Он не создаёт
token и не выполняет публикацию. Наличие App и успешные тестовые PR не означают,
что сквозной Authority Plane завершён: см. документ 27.

## Документы

- [Описание для коллег: назначение, цели, принципы и архитектура](docs/29-agent-explained.md)
- [Наблюдатель, контрольные точки и обучение](docs/28-observer-and-learning.md)
- [Модель памяти и сроков хранения](docs/30-memory-model.md)
- [План исследовательского прототипа](docs/24-mvp-final-plan.md)
- [Статус реализации и доказательств](docs/27-implementation-status.md)
- [Карта всего комплекта](docs/22-documentation-map.md)
- [Видение и границы](docs/00-vision-and-scope.md)
- [Архитектура](docs/01-architecture.md)
- [Модель процессов](docs/02-process-model.md)
- [Реестр архитектурных решений](docs/06-decision-register.md)
- [Гипотезы и backlog проверок](docs/07-validation-backlog.md)
- [План валидации](docs/12-validation-plan-v1.md)
- [Матрица трассируемости](docs/13-traceability-matrix.md)
- [Полный бриф широкого продукта](docs/23-project-brief.md)

Остальные специализированные документы перечислены в карте комплекта.
