# Референсы и кандидаты для исследования

Статус: исследовательский список; упоминание не означает технологический выбор

## Архитектурные референсы

### «Процессы для человека и ИИ»

Локальная рукопись:
`/Volumes/DATA/Проекты/Книга про процессы/manuscript/processes_for_people_and_ai_manuscript.md`

Основной методический источник проекта. Из книги приняты первичность процесса,
внешнее хранение состояния, разделение workflow/агента/backend, контракты,
связность процессных артефактов, минимальные права, проверяемые правила и
обоснованность мультиагентной архитектуры.

### Anthropic Commerce Agents

Репозиторий: <https://github.com/anthropics/commerce-agents>

Интересующие паттерны:

- единое определение агента через prompt, skills, tool contracts и gates;
- staged changes и отдельный apply;
- повторная проверка guardrails при применении;
- host approval вне текста чата;
- provenance для идентификаторов, участвующих в write-операциях;
- fenced untrusted content;
- read-only аналитический делегат;
- фильтрация памяти.

Документ безопасности:
<https://github.com/anthropics/commerce-agents/blob/main/docs/safety.md>

### Agent Skills

Спецификация: <https://agentskills.io/specification>  
Примеры Anthropic: <https://github.com/anthropics/skills>

Используется как кандидат на канонический переносимый формат skills. Поле
`allowed-tools` не рассматривается как достаточный механизм безопасности.

## Кандидаты process runtime

### LangGraph

<https://github.com/langchain-ai/langgraph>

Кандидат для stateful agent graph, human-in-the-loop и сохранения состояния.

### Temporal

<https://github.com/temporalio/sdk-python>

Кандидат для долговечного исполнения, retry, timers, восстановления и
компенсирующих действий.

Гипотеза для проверки: Temporal как внешний process runtime, LangGraph как
вариативный агентный участок внутри activity.

## Кандидаты безопасности и авторизации

### Open Policy Agent

<https://github.com/open-policy-agent/opa>

Кандидат для policy-as-code и детерминированных решений на Gateway.

### OpenFGA

<https://github.com/openfga/openfga>

Кандидат для отношений пользователь — организация — проект — агент — ресурс.

### Secretless AI

<https://github.com/opena2a-org/secretless-ai>

Референс для broker-based secret operations, внедрения credentials в дочерний
процесс и identity-bound policy. Требуется отдельный security review перед
возможным использованием.

## Кандидаты маршрутизации моделей

### RouteLLM

<https://github.com/lm-sys/RouteLLM>

Референс для обучения и калибровки маршрутизации между дешёвой и сильной
моделью. В проекте потребуется более широкая функция решения, включающая риск,
приватность, capabilities и стоимость ошибки.

## Протоколы

- A2A: <https://a2a-protocol.org/latest/>
- MCP: <https://modelcontextprotocol.io/>
- AG-UI: <https://docs.ag-ui.com/>
- A2UI: <https://github.com/a2ui-project/a2ui>
- ACP: в книге рассматривается как Agent Client Protocol для границы
  «редактор или агентный клиент — агент разработки»; актуальную спецификацию
  нужно проверить на стадии protocol validation.
- MHS: <https://www.anthropic.com/news/model-hardware-standard-research-preview>
  — принят как граница подключения физического оборудования; на момент фиксации
  находится в research preview и требует отдельной проверки зрелости.

Протокольный стек зафиксирован, но версии, SDK и conformance profiles выбираются
только после отдельной валидации каждой интеграции.

## Правило использования референсов

Перед включением зависимости в план реализации необходимо проверить:

- актуальную спецификацию и зрелость;
- лицензию;
- security history;
- модель развёртывания и доверительные границы;
- возможность автономного или локального режима;
- стоимость эксплуатации;
- совместимость с принятыми ADR;
- наличие conformance и adversarial tests.

## Стандарты identity и runtime governance

- NIST AI Agent Standards Initiative:
  <https://www.nist.gov/artificial-intelligence/ai-agent-standards-initiative>
- NIST Agent Identity and Authorization:
  <https://www.nist.gov/blogs/cybersecurity-insights/back-future-why-agentic-ai-needs-strong-identity-foundation>
- CNCF Cloud Native Agentic Standards:
  <https://www.cncf.io/blog/2026/03/23/cloud-native-agentic-standards/>
- AWS Dogwood Runtime Verification:
  <https://aws.amazon.com/blogs/opensource/introducing-dogwood-runtime-verification-for-ai-agents/>
- Microsoft Agent Governance Toolkit:
  <https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/>
- Agent Gateway:
  <https://github.com/agentgateway/agentgateway>

Эти источники подтверждают актуальность identity, delegated authorization,
gateway governance и runtime verification. Конкретные реализации остаются
кандидатами и не заменяют собственные принятые trust boundaries.
