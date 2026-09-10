# Контуры управления и доверия

Статус: архитектурный backlog; не относится к реализованным гарантиям первого
среза. Фактический статус — в документе 27.
Версия: 0.1

## Назначение

Этот документ фиксирует перспективные контуры, которые должны быть заложены в
модель данных и интерфейсы уже сейчас, но реализуются поэтапно после security
foundation MVP.

## Identity Fabric

Система различает и криптографически связывает identity пользователя,
организации, процесса, агента, субагента, сервиса, внешнего A2A-агента и
устройства. Любое действие хранит проверяемую цепочку:

```text
Human / Organization -> Process -> Agent -> Subagent -> Tool / Device
```

Delegation Receipt фиксирует issuer, subject, scope, audience, TTL, возможность
дальнейшего делегирования, отзыв и исходный principal.

## Runtime Verification

Критические инварианты исполняются вне LLM и проверяются на каждом переходе:

- approval соответствует точному digest;
- capability не шире делегированного grant;
- действие допустимо в текущем состоянии;
- данные не выходят за аудиторию;
- MHS-команда проходит limits и interlocks;
- depth, budget и deadline не превышены.

## Policy Lifecycle и Simulator

Политика имеет версию и проходит путь:

```text
draft -> tests -> simulation/replay -> review -> limited rollout -> active
```

Policy Simulator прогоняет новую версию через обезличенные или разрешённые audit
traces, показывает изменения разрешений, блокировок и blast radius. Агент не
может самостоятельно активировать новую политику.

## Capability Cards

Агенты, skills, patterns, tools и hardware adapters публикуют versioned карточки
возможностей: назначение, требуемые права, запрещённые операции, риск, входы,
выходы, evidence и совместимые patterns. Pattern Compiler использует карточки
вместо подбора компонентов по свободному тексту.

## Continuous Red Team и Evals

Security evals запускаются при изменении модели, pattern, skill, policy, tool,
adapter, context compiler или runtime image. Набор включает injection, data
exfiltration, privilege escalation, confused deputy, replay, agent fork bomb и
MHS safety cases.

## Agent SLO

Наблюдаемость измеряет не только latency, но и:

- Effort Units на принятый результат;
- долю успешных verification;
- долю корректных безопасных отказов;
- число и пользу эскалаций;
- глубину и стоимость делегирования;
- policy denials и ложные срабатывания;
- время reconciliation;
- воспроизводимость результатов.

## Внешние агенты и Transaction Mandates

Для внешнего A2A-агента задаются trust profile, разрешённые классы данных,
максимальная глубина делегирования, обязательные проверки и scope операций.

Для покупок, платежей, публикаций и иных транзакций используется ограниченный
Mandate: конкретный principal, действие, лимит, получатель/класс получателей,
TTL, approval policy и idempotency. Mandate не раскрывает платёжные реквизиты и
не заменяет Credential Broker.

## Process Mining и Digital Twin

По audit traces система может предлагать повторяющиеся ветви, bottlenecks,
неэффективные skills и кандидаты на новый pattern. Предложения проходят тот же
lifecycle, что и другие изменения.

Digital Twin моделирует процессы, policies, ресурсы, агенты и, для MHS, состояние
устройства. Реальное действие не выполняется, пока симуляция не завершена в
допустимых границах.
