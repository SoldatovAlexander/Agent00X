# Статус реализации и доказательств

Статус: единственный оперативный статус проекта

Версия: 1.1

Дата сверки: 2026-09-07

Этот документ отвечает на вопрос «что существует и что подтверждено сейчас».
План работ находится в [документе 24](24-mvp-final-plan.md); замысел широкого
продукта — в документах 00 и 23. При расхождении этот документ имеет приоритет
для утверждений о реализации и проверках.

## 1. Итог

Проект находится на стадии исследовательского прототипа. Основная гипотеза:
явное представление целей, данных, состояния, процедур и правил поможет агенту
исполнять проработанную бизнес-функцию. Первый пример функции — `repository-change`.

Есть контрактная и sandbox-основа, детерминированный reference flow, mock boundary
и отдельные GitHub App spikes. Полный агент, remote snapshot как вход Worker,
наблюдатель, исторические отчёты, учебные ветки и сквозная защищённая публикация
ещё не реализованы. Нельзя заявлять production-ready, отсутствие всех утечек
секретов или доказанную неуязвимость Gateway.

## 2. Каноническая шкала доказательств

| Уровень | Значение |
|---|---|
| Реализовано и unit-tested | Код и автоматические тесты в этом репозитории; это не сквозное доказательство границы доверия |
| Spike | Узкая демонстрация конкретной интеграции или свойства; она не распространяется на соседние компоненты |
| Спроектировано | Решение принято в документах, но нет схем/кода/проверок либо они неполны |
| Не проверено | Свойство не может считаться установленным |

## 3. Что реализовано

| Область | Статус | Точная граница утверждения |
|---|---|---|
| Базовые контракты | Реализовано и unit-tested | 16 JSON Schema, fixtures, digest chain, subset validator и state machine |
| Local reference preparation | Реализовано и unit-tested | Ephemeral workspace, ограниченные изменения, patch, allowlisted tests, evidence, verification и staged change на fixture snapshot |
| Durable state и mock publication | Реализовано и unit-tested | SQLite transitions/audit и journal/reconciliation вокруг mock boundary |
| Policy/Gateway/Broker контракты | Реализовано и unit-tested | Детерминированные классы и негативные сценарии; это не связанный production Authority Plane |
| Docker profile | Частично проверено | Профиль и opt-in integration test существуют; обычный прогон не запускает Docker integration |
| GitHub App | Spike | App создал тестовые branch/PR; это не доказывает полную авторизацию, atomic publication или recovery |
| Наблюдатель и обучение | Спроектировано | ADR-029/030 и документ 28; нет схем, collector, отчётов или учебных веток |
| LLM Worker и субагенты | Не реализовано | Reference flow детерминированный, не является исполнением функции моделью |

## 4. Последняя локальная проверка

Команда:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Результат сверки 2026-09-07: **83 теста, 82 прошли, 1 пропущен**. Пропущен
opt-in Docker integration test; его запуск требует `RUN_DOCKER_SANDBOX_TESTS=1`,
доступный Docker daemon и образ. Этот результат подтверждает только указанные
тестами свойства кода на текущей машине.

Проверки покрывают схемы, digests, состояние, sandbox lifecycle, fixtures,
negative contract paths, mock publication recovery, часть Gateway/policy/Broker,
canary scanner и threat corpus. Canary scanner ищет контрольное значение в
переданных ему поверхностях; он не доказывает отсутствие секрета в реальных
process list, crash dump, системной телеметрии или всех логах.

## 5. Исторические GitHub App spikes

На allowlisted репозитории `Agent00X-sandbox` были созданы тестовые branch/PR,
включая PR #1 и #2. Второй spike использовал fixture snapshot, а не snapshot
фактического удалённого репозитория. Эти результаты подтверждают ограниченную
возможность GitHub App получить installation token и выполнить конкретный путь
GitHub API. Они не подтверждают, что опубликованные файлы, approval, policy,
manifest, Broker, journal и recovery образуют единую безопасную цепочку.

## 6. Известные нарушения и открытые границы

1. `build_publish_manifest` сопоставляет workspace с вновь переданным mapping,
   но не фиксирует его как единственное проверенное содержимое. Локальный
   негативный сценарий принял подменённый после проверки файл.
2. `DeterministicPolicy.decide` проверяет approval относительно `staged_change`,
   но возвращает digest из `actuator_request`. Локальный негативный сценарий
   получил `allow` для иного digest.
3. GitHub publication path не является атомарной транзакцией и нуждается в
   корректной обработке обновления существующих файлов, частичных сбоев и
   reconciliation.
4. Local process backend — development fallback, а Docker smoke/profile не
   доказывают защиту от враждебного кода или полного обхода Gateway.
5. Наблюдение «на любой момент» возможно только в пределах записанной и
   разрешённой к хранению истории; незаписанное содержание нельзя восстановить.

До устранения пунктов 1–3 нельзя считать выполненными gate approval integrity,
сквозную публикацию и её recovery. До проверок пунктов 4–5 нельзя обещать
непробиваемую изоляцию или полный исторический отчёт.

## 7. Текущие этапы

| Этап из плана 1.1 | Статус | Ближайший проверяемый результат |
|---|---|---|
| R0: наблюдение и память | Концепция готова | JSON Schema, валидаторы и негативные тесты ObservationEvent/Checkpoint/LearningCorrection/MemorySummary |
| R1: целостность и фиксация действий | Не начат | Устранить два известных нарушения и сохранять checkpoint до действия |
| R2: сквозной исполнитель | Не начат | Один LLM Worker с remote snapshot и controlled publication |
| R3: исторический Observer | Не начат | Отчёты по сохранённой истории, причинности и пробелам |
| R4: учебная ветка | Не начат | Simulation branch без переноса старых прав и external writes |
| R5: эксперимент | Не начат | Сравнение полной и упрощённой организации данных по заранее заданному набору задач |

Исторические M0/M0.5/M1/M2/M3/M4 больше не являются шкалой текущего плана.
Они обозначают происхождение имеющихся компонентов: базовые контракты и часть
local preparation существуют; M2/M3 не завершены; M4 отложен.

## 8. Правило изменения статуса

Этап меняет статус только при наличии кода, позитивных и негативных тестов,
воспроизводимой команды запуска, списка оставшихся ограничений и ссылки на
соответствующую гипотезу/ADR. Happy-path демонстрация, число документов или
одна успешная внешняя операция не превращаются в доказательство соседних свойств.

## 9. Evidence inventory (EXP-241, сверка 2026-09-13)

Инвентаризация собрана исполнителем по карточке EXP-241 и не меняет выводы
разделов 1–8: сверка статуса — предмет EXP-242. Уровни — по шкале раздела 2.

Штатная проверка, выполненная при сборе:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Результат 2026-09-13: **420 тестов, все прошли, 1 пропущен**. Пропущен
штатный opt-in Docker integration test (требует `RUN_DOCKER_SANDBOX_TESTS=1`,
доступный Docker daemon и образ). Результат подтверждает только свойства,
покрытые тестами, на текущей машине; число тестов не является доказательством
изоляции, сквозной публикации или end-to-end безопасности.

| Область | Артефакты | Evidence (commit) | Уровень |
|---|---|---|---|
| Базовые контракты | 16 исходных JSON Schema в `schemas/`, fixtures, `digests.py`, `validator.py`, `state_machine.py` | История `git log`, chain/contract-тесты | Реализовано и unit-tested |
| Observer R0-контракты | `observation-event`, `checkpoint`, `learning-correction`, `memory-summary` schemas + `test_observer_contracts.py` (итого 20 схем, 19 test-файлов) | `ea4fd5a` (EXP-004) и follow-up commits, включая `f734226` (EXP-008) | Реализовано и unit-tested на уровне контрактов; collector, отчёты и учебные ветки отсутствуют |
| Reference preparation и manifest binding | `repository_process.py`, `PreparedChange.verified_contents`, regression-тесты подмены | `e98cce3` (EXP-002), принят Control Plane | Unit-tested; нарушение п.1 раздела 6 имеет remediation evidence, сверка статуса — EXP-242 |
| Policy/authority gate | `authority.py` (`DeterministicPolicy`, привязка digest), regression-тесты подмены | `274fbdc` (EXP-003), принят Control Plane | Unit-tested; нарушение п.2 раздела 6 имеет remediation evidence, сверка статуса — EXP-242 |
| Durable state и mock publication | `runtime_store.py` (SQLite transitions/audit), `publication.py` (journal/reconciliation), mock boundary, recovery-тесты | Batch-коммиты EXP-010—EXP-015 и далее (см. `git log`) | Реализовано и unit-tested, включая негативные и recovery-сценарии |
| Gateway/Broker/Actuator boundary hardening | Fail-closed проверки типов, digest, expiry, idempotency и привязок в `gateway.py`, `broker.py`, `actuator.py`, `github_actuator.py`, `mock_github.py`, `github_app.py` + regression-тесты | Batch-коммиты EXP-021—EXP-230 (см. `git log`; EXP-231 и новее на 2026-09-13 не приняты Control Plane) | Реализовано и unit-tested локально; production Authority Plane не связан |
| GitHub App | Исторические branch/PR spikes на allowlisted репозитории | Без изменений с раздела 5 | Spike |
| Observer runtime, обучение, LLM Worker | Отсутствуют как код | Без изменений | Спроектировано / Не реализовано |

Открытые границы сквозной цепи (без изменений по существу, см. раздел 6):
п.1–2 имеют remediation evidence (сверка — EXP-242); п.3 (неатомарная GitHub-публикация), п.4 (изоляция local backend/Docker) и п.5 (неполнота истории) остаются открытыми; сквозная цепочка approval → policy → manifest → Broker → journal → recovery не доказана как единое целое; Docker-интеграция — только opt-in.

Ближайшее проверяемое свойство: соответствие разделов 1–8 настоящего inventory
(предмет EXP-242). Настоящий inventory не является security certification
и не доказывает external publication.
