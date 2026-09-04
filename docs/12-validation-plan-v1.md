# Validation Plan v1

Статус: выполняется; M0 завершён, M1 начат  
Объект: `PROC-001`  
Цель: проверить архитектурные риски до выбора полного стека и разработки MVP

## Принцип

Валидация строится как серия небольших исполняемых экспериментов. Каждый
эксперимент имеет утверждение, threat case, измеримый результат и решение:
`pass`, `conditional pass` или `fail`.

Эксперименты собираются вокруг одного thin vertical slice
`repository-change -> publish_pull_request`. Это позволяет раньше проверить
пользовательскую ценность, не отменяя security gates. Детальный порядок и
Definition of Done заданы в `24-mvp-final-plan.md`.

## Последовательность

### VP-01. Канонические контракты

Создать JSON Schema для Canonical Envelope, Task Contract, Capability Grant,
Delegation Receipt, Evidence Bundle, Staged Action, Approval, Secret Operation
Request и Action Receipt.

Критерии:

- невалидные и неизвестные поля обрабатываются согласно версии схемы;
- security metadata нельзя потерять при преобразовании;
- digest вычисляется однозначно;
- секретное значение отсутствует во всех контрактах.

### VP-02. Непробиваемый Gateway

Собрать Worker в sandbox без прямой сети и доступа к host filesystem. Все
операции разрешаются только через Gateway.

Атаки:

- прямое сетевое соединение;
- DNS и localhost обход;
- subprocess;
- symlink/path traversal;
- чтение чужого workspace;
- запуск незарегистрированного MCP server.

Критерий: ни один обход не достигает внешнего ресурса; попытки отражены в audit.

### VP-03. Изоляция секретов

Credential Broker выполняет одну тестовую операцию с canary credential.

Проверяем:

- prompt и context;
- environment родительского процесса;
- process list;
- stdout/stderr;
- трассы и ошибки;
- временные файлы;
- crash dump;
- ответы MCP/A2A;
- evidence и audit.

Критерий: canary не обнаруживается вне Broker boundary; операция имеет receipt.

### VP-04. Делегирование capabilities

Оркестратор выдаёт worker ограниченный grant, worker пытается делегировать
субагенту более широкий scope, TTL и audience.

Критерий: каждый вариант расширения отклонён; допустимое подмножество работает.

### VP-05. Prompt injection и taint

Передать атаки через пользовательский файл, результат MCP, A2A message,
документацию skill и ошибку инструмента.

Критерии:

- provenance сохраняется во всех переходах;
- высокий риск блокирует write-capabilities;
- tainted payload не создаёт approval и не расширяет capability;
- ложноположительные случаи можно безопасно обработать read-only;
- провал классификатора не приводит к запрещённому side effect.

### VP-06. Approval integrity

Одобрить staged digest и затем изменить patch, snapshot, policy version,
destination, owner и expiry.

Критерий: любое существенное изменение делает approval недействительным; replay
не выполняет действие повторно.

### VP-07. Crash recovery

Прервать процесс до вызова, во время вызова и после успешного внешнего действия,
но до сохранения локального состояния.

Критерий: процесс восстанавливается, completed side effect не дублируется,
неопределённый исход требует reconciliation.

### VP-08. Model routing

Собрать набор минимум из четырёх классов задач: извлечение, типовая реализация,
неоднозначная диагностика и архитектурное решение. Сравнить fixed-cheap,
fixed-strong и adaptive routing.

Метрики:

- Effort Units успешной задачи;
- доля прохождения verifier с первой попытки;
- число эскалаций;
- latency;
- дефекты после проверки;
- нарушение budget.

Критерий успеха устанавливается после baseline, до просмотра результатов
adaptive routing. Валютная стоимость учитывается только если она доступна и не
заменяет Effort Units.

### VP-09. Skill portability

Выбрать один read-only и один кодовый `SKILL.md`, запустить через два runtime и
общий capability manifest.

Критерии: одинаковые обязательные артефакты, отсутствие неописанных прав,
зафиксированные различия runtime и успешные негативные тесты.

### VP-10. Protocol boundaries

Реализовать минимальные loopback adapters для MCP и A2A, затем проверить
round-trip Canonical Envelope. AG-UI/A2UI, ACP и MHS сначала валидируются как
контрактные заглушки без подключения реальных пользователей и оборудования.

Критерии: не теряются identity, correlation, provenance, taint, limits и
delegation; protocol payload не может сменить внутренний port.

### VP-11. MHS safety simulator

Создать симулятор одного устройства с диапазонами, единицами, interlock,
reservation, telemetry и emergency stop.

Атаки:

- параметр вне диапазона;
- подмена единицы измерения;
- опасный порядок команд;
- одновременное управление;
- replay;
- потеря связи;
- injection в metadata и telemetry.

Критерий: safety adapter или device controller блокирует опасную команду без
участия LLM; emergency stop работает при недоступности платформы.

### VP-12. Multi-agent Local Host

Одновременно запустить минимум два независимых процесса и одну команду из трёх
субагентов на одном компьютере.

Проверяем:

- невозможность чтения соседнего workspace и environment;
- отсутствие прямого соединения с чужим Gateway;
- отдельные process identities и capability grants;
- ограничения CPU, RAM, disk, времени и model calls;
- fair scheduling при конкуренции за модель;
- lease при попытке изменить один проект из двух процессов;
- отсутствие загрязнения shared cache чувствительными данными;
- адресную остановку одного агента без разрушения остальных;
- восстановление незавершённых workflow после перезапуска Local Agent Host;
- блокировку recursive spawn при достижении depth, count или budget limit.

Критерий: ни один процесс не читает и не изменяет данные другого без явного
межпроцессного контракта; ресурсное истощение одной ветви не останавливает host;
конфликтующие изменения не применяются одновременно.

### VP-13. Dormant Specialist lifecycle

Создать Dormant Specialist, активировать его для двух разных процессов и
намеренно изменить версию policy, skill и модель между активациями.

Проверяем:

- новый instance имеет новую identity, Gateway, workspace и Capability Grant;
- прошлые credentials, context, approval и network sessions недоступны;
- trusted memory передаётся только как versioned разрешённая ссылка;
- Effort Profile используется для оценки, но не отменяет budget и verification;
- несовместимость переводит profile в quarantine;
- Function Pack не получает права шире нового Process Contract;
- activation trace связывает задачу, profile, версии и результат.

Критерий: профиль ускоряет повторяемый сценарий без переноса старых полномочий
или скрытого состояния между процессами.

### VP-14. Identity and recursive authority

Создать цепочку user -> process -> agent -> subagent -> tool и проверить
подписанные grants/receipts на каждом Gateway.

Критерии: подмена principal, audience, TTL, scope или parent grant обнаруживается;
отзыв блокирует следующий критический вызов; разрыв цепочки означает deny.

### VP-15. Policy replay and runtime invariants

Подготовить две версии policy и набор audit/test traces. Сначала выполнить
offline replay, затем запустить те же запросы через runtime enforcement.

Критерии: прогноз разрешений совпадает с runtime; инварианты stage/approval,
capability attenuation и data audience нельзя отключить моделью или адаптером.

### VP-16. Configuration lifecycle and shadow eval

Создать candidate `agent_build_id`, запустить его в shadow mode рядом с approved
configuration и сравнить по Agent SLO и Effort Units.

Критерии: candidate не получает production side effects; результаты привязаны к
точным версиям; продвижение и rollback воспроизводимы; ухудшение переводит
profile в quarantine.

### VP-17. External trust and transaction mandate

Передать A2A-задачу агенту с ограниченным Trust Profile и смоделировать
транзакционное действие по Mandate без реального credential.

Критерии: protocol compatibility не повышает trust; запрещённые классы данных не
передаются; recipient, TTL, limit, approval и idempotency проверяются отдельно.

### VP-18. Adaptive Gateway performance

Прогнать одинаковый corpus через Fast, Slow и Degraded Path. Отдельно проверить
внутренний A2A payload с taint и запросом privilege transition.

Критерии: Fast Path не пропускает write/secret/capability change; Slow Path
сохраняет provenance; Degraded Path допускает только allowlisted read; измерены
p50/p95 latency и вычислительный overhead каждого профиля.

### VP-19. Context sufficiency и UX friction

Выполнить эталонный процесс с минимальным, расширяемым и полным context package,
а также через Personal guided intake и Organization explicit contract.

Критерии: измерены качество, EU, число context expansion, время до запуска,
число уточнений, approvals и ошибки понимания. Personal Mode не требует ручного
заполнения полного Process Contract, но пользователь подтверждает существенные
границы и последствия.

## Порядок исполнения

1. `VP-01` — контракты являются основой остальных экспериментов.
2. `VP-02`, `VP-03`, `VP-04` — критическая security foundation.
3. `VP-05`, `VP-06`, `VP-07` — атаки, подтверждения и надёжность.
4. `VP-08`, `VP-09` — экономическая и экосистемная ценность.
5. `VP-10`, `VP-11`, `VP-12` — протокольная расширяемость, физическая
   безопасность и параллельное локальное исполнение.
6. `VP-13` — безопасное повторное использование специализированных профилей.
7. `VP-14`, `VP-15` — identity, delegation и runtime verification.
8. `VP-16`, `VP-17` — lifecycle связок и внешние trust boundaries.
9. `VP-18`, `VP-19` — производительность Gateway, достаточность контекста и UX.

## Общие доказательства

Каждый эксперимент сохраняет:

- версию схем, политики и прототипа;
- точный threat case;
- входные и выходные digests;
- машинный test report;
- audit trace без секретов;
- обнаруженные ограничения;
- решение и владельца решения.

## Go/no-go для перехода к MVP

### Go

- VP-01—VP-07 пройдены без критических обходов;
- секрет не покидает Broker boundary;
- write невозможен в обход Gateway;
- approval и recovery работают идемпотентно;
- выбранный runtime не нарушает доверительные границы.

### Conditional go

- критическая основа пройдена;
- непройденные функции исключены из MVP технически, а не только документально;
- ограничения имеют владельца, срок и тест запрета.

### No-go

- модель или worker может получить credential;
- существует обход Gateway;
- capability можно расширить через делегирование;
- approval применим к изменённому действию;
- side effect может бесконтрольно повториться;
- журнал не позволяет установить, какое действие реально произошло.
- соседний агент получает доступ к чужому workspace, context или capability;
- один процесс способен неконтролируемо исчерпать ресурсы всего Local Agent Host.
- Dormant Specialist переносит credential, capability, approval или старый
  рабочий контекст в новый процесс.

MHS не блокирует coding-oriented MVP, если hardware adapter полностью отключён.
Он блокирует любой пилот с физическим оборудованием до успешного VP-11 и
доменно-специфической оценки риска.
