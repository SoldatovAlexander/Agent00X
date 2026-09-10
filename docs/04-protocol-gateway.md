# Протоколы и Agent I/O Gateway

Статус: целевое архитектурное решение; protocol adapters и сквозной Gateway не
реализованы. Фактический статус — в документе 27.

## Решение

Каждый агент взаимодействует с внешним миром только через персональный Agent
I/O Gateway. A2A, MCP, AG-UI/A2UI, ACP, MHS и будущие стандарты
подключаются через сменные protocol adapters.

```text
A2A ----\
MCP -----+--> Protocol Adapter --> Agent I/O Gateway --> Agent Runtime
AG-UI ---+
MHS ------/
```

## Ответственность Protocol Adapter

- handshake и версия протокола;
- transport authentication;
- streaming и protocol-specific lifecycle;
- преобразование формата;
- conformance errors.

Адаптер не принимает бизнес-решения и не выдаёт полномочия.

## Ответственность Agent I/O Gateway

- проверка principal и delegation chain;
- schema validation, quotas и replay protection;
- provenance, classification и taint propagation;
- prompt-injection screening;
- capability и policy enforcement;
- маршрутизация по внутренним портам;
- исходящий DLP;
- подписание, трассировка и аудит.

Дополнение 2026-09-07: Gateway/Runtime должны передавать в Observation Collector
безопасные события намерения и результата каждого решения или tool call. Этот
поток не превращает payload в инструкцию для Observer и не передаёт credentials.
Конкретные контракты пока не реализованы; см. документ 28.

## Risk-based execution paths

Gateway не запускает максимальный набор проверок для каждого сообщения. Профиль
определяется источником, trust domain, портом, taint, sensitivity, capability и
потенциальным side effect.

### Fast Path

Выполняет authentication, schema/signature validation, TTL, limits, provenance,
taint preservation и дешёвую policy-проверку. Допустим только без privilege
transition, secret operation и внешнего side effect. Внутренний A2A-трафик не
становится доверенным автоматически: скомпрометированный агент остаётся
недоверенным источником содержания.

### Slow Path

Обязателен для внешнего или tainted payload, tool/write request, protocol trust
boundary, secret operation, capability change, чувствительного вывода и
аномалии. Может включать content inspection, prompt-injection classifier, DLP,
расширенную policy evaluation, независимую проверку и human approval.

### Degraded Path

Если policy service или обязательный security component недоступен, разрешаются
только заранее определённые read-only операции. Write, publish, privilege
transition и secret operation получают deny.

Выбранный path, причины и фактическая latency записываются в audit для
последующей калибровки. Fast Path означает меньшую стоимость проверки, а не
ослабление базовых инвариантов.

## Внутренние порты

- Task Port — постановка и делегирование задач;
- Data Port — недоверенные и доверенные данные;
- Tool Port — запрос операций;
- Artifact Port — результаты и файлы;
- Event Port — статусы и streaming;
- Approval Port — подтверждения вне обычного чата;
- Credential Operation Port — строго типизированные секретные операции.

Данные, поступившие через Data Port, не могут трактоваться как approval или
capability grant.

## Канонический envelope

```yaml
message_id: msg-01
correlation_id: process-42
source:
  principal_id: external-agent-7
  protocol: a2a
  trust_domain: partner
destination:
  agent_id: worker-3
  port: task
intent:
  operation: code.review
payload:
  type: artifact-reference
provenance:
  origin: user
  delegation_chain: [user-12, orchestrator, external-agent-7]
  content_hash: sha256:...
security:
  trust: untrusted
  sensitivity: internal
  tainted: true
  permitted_uses: [analysis]
  forbidden_uses: [authorization, secret-access]
limits:
  expires_at: 2026-09-03T12:10:00Z
  max_response_bytes: 50000
```

## Поддерживаемые направления

- A2A — agent discovery, delegation, task status и artifacts;
- MCP — tools, resources и context;
- AG-UI/A2UI — пользовательские события, approvals и декларативный UI;
- ACP — соединение редактора или агентного клиента с агентом разработки;
- MHS — обнаружение, описание и безопасное управление физическим оборудованием
  через доменные hardware adapters;
- новые протоколы — через versioned plugin и conformance suite.

ACP из книги означает Agent Client Protocol и не является протоколом управления
физическими устройствами. Для этой границы принят MHS — Model Hardware Standard.
Его интеграция рассматривается отдельно от MCP: MCP может предоставить агенту
доступ к MHS, но аппаратные ограничения и жизненный цикл устройства остаются в
MHS-адаптере и нижележащем контроллере.

## Особые требования MHS

- описание возможностей устройства отделяется от разрешения их использовать;
- физические диапазоны, единицы измерения и safety limits валидируются вне LLM;
- опасные команды поддерживают dry-run или симуляцию, если это технически
  возможно;
- устройство или контроллер имеют независимый emergency stop;
- сессия управления имеет владельца, TTL и правила эксклюзивности;
- повтор команды защищён idempotency key или доменной защитой от дублей;
- телеметрия, команда, оператор, модель, policy decision и результат связаны
  общим trace ID;
- потеря связи переводит оборудование в заранее определённое безопасное
  состояние;
- prompt injection из телеметрии, метаданных и документации устройства не может
  расширить capability агента.

## Требования к новому адаптеру

- versioned manifest;
- явное соответствие внутренним портам;
- authentication и identity mapping;
- лимиты сообщений и вложений;
- threat profile;
- fail-closed для неизвестных write-операций;
- conformance, fuzz и adversarial tests;
- отсутствие прямого доступа к runtime агента.

## Доступность

Gateway не должен становиться небезопасной единой точкой отказа. При потере
центрального policy-сервиса допускается заранее определённый degraded mode:
безопасные чтения могут продолжаться, изменения блокируются.
