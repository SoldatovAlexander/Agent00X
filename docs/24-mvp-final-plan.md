# Итоговый план MVP: Thin Vertical Slice

Статус: исследовательский прототип; план уточнён, реализация не завершена

Версия: 1.1

Дата: 2026-09-07

## 1. Цель

Проверить, позволяет ли предложенное представление целей, данных, состояния,
правил и полномочий исполнять агентом проработанную бизнес-функцию. Подтверждение
этой возможности является самостоятельным результатом; коммерческая экономия
не служит предварительным условием продолжения эксперимента.

Первый сквозной сценарий:

> агент подготавливает и проверяет изменение программного проекта, после чего
> инициирует публикацию Pull Request, не имея прямого доступа к GitHub и не
> получая credential ни в prompt, context, environment, workspace, trace или
> artifact.

MVP не является универсальной агентной платформой. Это минимальный вертикальный
срез Process, Execution и Authority Plane, достаточный для проверки главных
trust boundaries. Наблюдатель и обучение через контролируемое ветвление входят
в исследовательское ядро. Полная спецификация: [документ 28](28-observer-and-learning.md).

### Актуальная последовательность после переоценки

Этот порядок имеет приоритет над исторической последовательностью M0—M4 ниже.
Названия старых milestones сохраняются для связи с уже выполненной работой.

1. **R0 — постановка и контракты наблюдения.** Зафиксировать исследовательскую
   гипотезу, сценарии, формат события, checkpoint, LearningCorrection и memory
   summary. Концептуальная часть выполнена документами 28 и 30; машинные схемы
   и тесты ещё нужны.
2. **R1 — целостность и фиксация действий.** Закрыть подмену manifest после
   verification и рассогласование digest actuator request с approval. Сохранять
   checkpoint каждого решения и вызова до исполнения, в том числе для субагентов.
   При отказе журнала блокировать очередное действие. Добавить негативные тесты.
3. **R2 — реальный сквозной исполнитель.** Remote snapshot конкретного commit,
   один LLM Worker, независимая проверка, минимальный CLI и контролируемая
   публикация. Все проверки до внешнего write; реальные границы секретов и
   durable reconciliation. Основные пути R2 инструментированы наблюдением R1.
4. **R3 — наблюдатель и исторический отчёт.** Отчёты сейчас/на момент T,
   причинные ссылки, отделение фактов от оснований и интерпретаций; проверки
   неполной истории, поздних ответов и отказов. Детерминированный отчёт допустим
   первым, LLM-объяснение не заменяет доказательства.
5. **R4 — учебная ветка.** Корректировка человека, восстановление из checkpoint
   в симуляции, новый branch и candidate-конфигурация без старых полномочий.
   Исходная история сохраняется, внешние действия автоматически не повторяются.
6. **R5 — эксперимент.** Штатные случаи, исключения и новые похожие задачи;
   сравнение полной и упрощённой организации данных. Проверить перенос
   корректировки и отсутствие регрессий, записать ограничения и отрицательные
   результаты. VP-20—VP-23 обязательны для завершения исследовательского среза.

Безопасность проверяется внутри каждого этапа, а не только после сборки.
Оптимизация Router, несколько протоколов, рекурсивные команды, оборудование и
полноценный Organization UI не блокируют исследовательский прототип.

## 2. Демонстрационный сценарий

```text
User goal
  -> Process Contract
  -> repository snapshot
  -> Worker in sandbox
  -> patch + tests + evidence
  -> independent verification
  -> immutable Staged Change
  -> user approval of digest
  -> publish_pull_request Intent
  -> Agent I/O Gateway
  -> deterministic Policy Decision
  -> GitHub Actuator
  -> Credential Broker obtains short-lived GitHub App token
  -> branch + commit + push + Pull Request
  -> sanitized Action Receipt
```

Worker получает read-only snapshot исходного репозитория и отдельный writable
ephemeral workspace. Он может сформировать patch, но не имеет GitHub credential,
прямого сетевого egress и права публикации.

## 3. Границы MVP

### Входит

- один Process Pattern `repository-change`;
- один Orchestrator, один Worker и независимый Verifier;
- durable process state и checkpoint до каждого решения и вызова инструмента;
- сборщик событий агента/субагентов, read-only Observer и исторические отчёты;
- версионируемая корректировка и учебная ветка без внешних writes;
- sandbox backend на базе готового механизма изоляции;
- персональный Gateway для Worker;
- минимальные canonical contracts;
- детерминированная policy с deny-by-default;
- staging и approval по digest;
- GitHub Actuator с одной операцией `publish_pull_request`;
- Credential Broker и короткоживущий GitHub App installation token;
- Action Receipt, audit и secret-leak test;
- минимальный CLI для задачи, approval, отчёта и разбора ошибки.

### Не входит

- универсальный marketplace;
- production-grade multi-tenant control plane;
- рекурсивная глубина более одного уровня;
- динамическое обучение Router;
- полный импорт skills нескольких экосистем;
- все протоколы одновременно;
- семантический injection detector на каждом сообщении;
- MHS и реальное оборудование;
- автоматическое слияние PR или deployment;
- долгоживущие PAT и общие `.env`;
- два полноценных пользовательских режима и дообучение весов модели.

## 4. Компоненты

| Компонент | Минимальная ответственность | Не делает |
|---|---|---|
| Process Runtime | Состояния, переходы, retry, checkpoint | Не интерпретирует credential |
| Orchestrator | Декомпозиция и выбор следующего шага | Не применяет изменения |
| Worker | Анализ snapshot, patch и evidence | Не имеет внешней сети и GitHub identity |
| Verifier | Тесты и acceptance criteria | Не публикует результат |
| Sandbox Manager | Workspace, mounts, quotas, network default-deny | Не принимает бизнес-решения |
| Gateway | Identity, schema, provenance, policy call, audit | Не хранит секреты |
| Policy Engine | Allow/deny по typed attributes | Не принимает свободный prompt как правило |
| Approval Service | Подтверждение точного digest | Не изменяет staged action |
| GitHub Actuator | Зарегистрированная операция публикации | Не исполняет произвольный shell/API request |
| Credential Broker | Получение и использование scoped credential channel | Не возвращает token агенту |
| Audit Sink | Метаданные, digests и receipts | Не пишет секрет или полный prompt по умолчанию |
| Observation Collector | События и checkpoint до действия, причинные ссылки | Не зависит от добровольного отчёта Worker |
| Observer | Отчёты по разрешённой истории, пробелы и основания решений | Не читает скрытые рассуждения, не управляет агентами |
| Learning Branch Runtime | Новая ветка, candidate-конфигурация и eval | Не переписывает прошлое и не переносит старые grants |

## 5. Sandbox profile

Sandbox реализуется готовыми backend, а не собственным гипервизором. Интерфейс
`SandboxBackend` отделяет платформу от конкретной технологии.

Минимальный профиль:

- отдельный process/container boundary;
- read-only mount repository snapshot;
- writable ephemeral workspace;
- no host credential mounts;
- empty/minimal environment allowlist;
- default-deny egress;
- отдельный Gateway socket/endpoint;
- CPU, RAM, disk, process count и timeout limits;
- cleanup после завершения;
- artifact export только через Gateway.

Первый backend выбирается экспериментом между Docker и Podman. gVisor или
Firecracker рассматриваются как усиленные Linux-профили после измерения угроз и
накладных расходов. Personal Mode на macOS/Windows может использовать иной
backend при сохранении одного security contract.

## 6. Adaptive Gateway

Gateway выбирает профиль проверки по источнику, trust domain, taint, порту,
capability, чувствительности и потенциальному side effect.

### Fast Path

Допустим, если одновременно выполнены условия:

- transport identity подтверждена;
- schema и подпись корректны;
- сообщение не запрашивает новую capability;
- нет secret operation или внешнего side effect;
- provenance и taint не потеряны;
- payload остаётся внутри разрешённого trust domain;
- размер, rate и TTL допустимы.

Fast Path выполняет дешёвые детерминированные проверки. Он не означает, что
внутренний A2A-трафик считается доверенным.

### Slow Path

Включается для внешнего/tainted контента, protocol boundary, tool request,
write, secret operation, privilege transition, чувствительного вывода или
аномалии. Дополнительно применяются content inspection, injection screening,
DLP, расширенная policy evaluation, verifier и/или human approval.

### Degraded Path

При недоступности policy или неоднозначной классификации допускаются только
явно разрешённые read-only операции. Write, publish и secret operations
блокируются.

## 7. Authority flow для GitHub

### Intent Contract

`publish_pull_request` содержит repository ID, base commit, patch/artifact
digest, branch proposal, title, body artifact reference, owner, audience,
idempotency key и expiry. Произвольные URL, shell command и credential fields
запрещены схемой.

### Policy Decision

Проверяются:

- identity и непрерывная delegation chain;
- repository и installation allowlist;
- approved staged digest;
- base commit и отсутствие конфликта;
- разрешённая branch namespace;
- пройденные тесты и verdict Verifier;
- owner, audience, TTL, budget и idempotency;
- актуальная policy version.

### Credential и actuator

Предпочтителен GitHub App. Broker получает короткоживущий installation token с
минимальными repository permissions и предоставляет его только доверенному
GitHub Actuator через закрытый канал внутри Authority Plane. Actuator создаёт
branch/commit/push/PR или использует эквивалентную ограниченную API-последовательность.
Token не возвращается вызывающей стороне и уничтожается после операции.

### Receipt

Receipt содержит process ID, intent digest, staged digest, policy decision ID,
approval ID, repository, branch, commit SHA, PR ID/URL, idempotency key,
timestamps, sanitized status и postcondition result. Token и чувствительные
заголовки отсутствуют.

## 8. Рабочие потоки

### Поток A. Canonical contracts

Результат: JSON Schema/Pydantic-модели Process Contract, Intent Contract,
Staged Change, Policy Decision, Approval и Action Receipt.

### Поток B. Sandbox и Gateway

Результат: Worker без прямой сети; все внешние операции проходят через Gateway;
Fast/Slow/Degraded profiles наблюдаемы в audit.

### Поток C. Repository process

Результат: воспроизводимый patch, allowlisted tests, Evidence Bundle и независимый
verdict.

### Поток D. Authority Plane

Результат: policy, approval, GitHub Actuator, Broker и idempotent publication.

### Поток E. Security validation

Результат: canary credential не найден вне Broker boundary; попытки network,
schema, digest, replay и injection bypass заблокированы.

### Поток F. Product shell

Результат первого прототипа: CLI «цель → preview → approval → PR» с отчётом
наблюдателя и учебной веткой. Organization view — следующий этап, не gate прототипа.

## 9. Историческая основа

Этот раздел описывает уже созданные компоненты по прежней шкале M0—M4. Он не
задаёт порядок текущей работы: тот определён этапами R0—R5 в разделе 1.

### Milestone M0. Executable contracts — выполнен

- схемы и примеры сообщений;
- state machine;
- invariant tests;
- fixture repository и mock GitHub endpoint.

Выход: контракты проходят позитивные и негативные tests.

Результат: реализованы шестнадцать schemas, валидная цепочка, негативные fixtures,
canonical digest, cross-contract invariants, state machine, machine-readable
invariant catalog, fixture repository и mock GitHub boundary.

### Milestone M1. Safe local preparation — частично реализован

`SandboxBackend` и development-only process backend реализованы. Последний проверяет
workspace lifecycle, command allowlist и минимальный environment, но честно не
заявляет network/kernel isolation. Docker backend и smoke-проверки уже добавлены;
они не доказывают все заявленные границы изоляции.

Reference flow уже применяет declared changes только в ephemeral workspace,
строит unified patch, запускает allowlisted tests и создаёт связанные digest
Evidence Bundle, Verification Report и Staged Change. Path traversal, провал
тестов и изменение исходного snapshot покрыты негативными тестами.

- Process Runtime;
- Worker sandbox;
- snapshot/workspace;
- patch, test и evidence;
- Verifier.

Выход: проверенное staged change создаётся без сети и секретов.

### Milestone M2. Controlled publication — частично реализован, не закрыт

- Gateway;
- minimal policy;
- approval по digest;
- GitHub Actuator;
- Credential Broker;
- Action Receipt.

Исторический результат: GitHub App spike создал тестовый PR. Выход этапа не
достигнут: нет сквозной доказанной связи staged change → approval → publication.

### Milestone M3. Adversarial validation — частично реализован, не закрыт

- network bypass;
- token canary scan;
- changed digest/replay;
- tainted input;
- policy unavailable;
- crash before/during/after publication;
- duplicate request.

Есть component-level негативные тесты. Выход этапа не достигнут: отсутствует
проверка реальной сквозной публикации и известны нарушения целостности.

### Milestone M4. Dual UX — отложен после исследовательского прототипа

- Personal guided flow;
- Organization audit/policy view;
- EU, latency и approval metrics.

Выход: два пользовательских режима работают на одной модели контрактов.

## 10. Критерии завершения исследовательского среза

Инженерный срез завершён только если:

1. PR создаётся из одобренного staged digest;
2. Worker не имеет GitHub network path и credential;
3. canary credential отсутствует во всех проверяемых поверхностях;
4. изменение digest отзывает approval;
5. повтор intent не создаёт второй side effect;
6. недоступность policy запрещает публикацию;
7. audit восстанавливает полную цепочку без сохранения секрета;
8. crash recovery не приводит к слепому повтору;
9. Personal пользователь понимает действие до approval;
10. эксперт через CLI видит identity, policy, evidence и receipt;
11. ограничение MVP технически отключает неготовые возможности;
12. записаны время выполнения и затраты; оптимизация Gateway/Router не является gate;
13. checkpoint каждого решения и вызова записан до исполнения;
14. наблюдатель восстанавливает историю в пределах сохранённых данных и явно
    указывает пробелы, неизвестные исходы и источники объяснения;
15. учебная ветка не изменяет исходную историю и не повторяет внешние действия;
16. на заранее заданных критериях оценены исполнение функции, вклад организации
    данных и перенос корректировки на новые случаи, включая регрессии.

Завершённый эксперимент может дать отрицательный результат по пункту 16:
это не подтверждение гипотезы, но основание для её корректировки. Завершение
инженерного среза и подтверждение исследовательской гипотезы отмечаются отдельно.

## 11. Решение после исследовательского среза

### Подтверждение гипотезы

Все критерии раздела 10 выполнены, функция исполняется на заранее определённом
наборе случаев, а полная организация данных показывает проверяемый вклад против
упрощённого варианта. Ограничения и residual risks документированы.

### Частичное подтверждение

Контракты и отдельные части функции работают, но вклад организации данных,
перенос корректировки или одна из границ остаются неопределёнными. Результат
фиксируется как частичный, следующий эксперимент сужается до конкретного пробела.

### Неподтверждение или остановка среза

- token появляется у агента или в журнале;
- Worker может обойти Gateway;
- произвольный URL/command достигает Actuator;
- approval применим к другому digest;
- повтор запроса создаёт дубликат;
- внутренний A2A Fast Path позволяет privilege transition;
- невозможно установить итог внешнего side effect.

## 12. Решения после среза

По результатам принимаются отдельные решения о process runtime, sandbox backend,
policy engine, protocol SDK, Router, skill portability и Function Packs. Ни одна
из этих технологий не выбирается заранее только ради полноты архитектуры.
