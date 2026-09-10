# Agent Process Platform / Агент 00Х

Исследовательский прототип для проверки гипотезы: поможет ли явное представление
целей, данных, состояния, процедур, полномочий и результатов агенту исполнять
проработанную бизнес-функцию. Первый сценарий — `repository-change`.

Наблюдатель, контрольные точки каждого решения и вызова инструмента, а также
обучение через ветвление исполнения входят в замысел прототипа. Они **ещё не
реализованы**. Материал для коллег: [объяснение проекта](docs/29-agent-explained.md).
Память будет слоистой и ограниченной: после шести месяцев — месячные, после года
— годовые сводки; [полная политика](docs/30-memory-model.md).

## Состояние

Есть 16 JSON Schema, fixtures, детерминированный reference flow подготовки
изменений, SQLite runtime, mock publication boundary, sandbox-профили и отдельные
GitHub App spikes. Это не равнозначно готовому агенту или доказанной сквозной
безопасности: найдены нарушения привязки проверенного изменения к manifest и
approval к запросу публикации; они ещё не исправлены.

Единственный актуальный статус реализации и границ доказательств:
[документ 27](docs/27-implementation-status.md). Порядок работ R0—R5:
[план исследовательского прототипа](docs/24-mvp-final-plan.md).

Проверка существующего кода:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Обычный прогон на 2026-09-07: 83 теста, 82 прошли, один opt-in Docker test
пропущен. Подробнее — в документе 27.

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
