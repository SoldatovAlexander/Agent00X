# Dormant Specialists и Function Packs

Статус: архитектурное решение принято  
Версия: 0.1

## Идея

Для повторяемой работы не всегда нужно заново собирать временную команду из
общих компонентов. Платформа поддерживает Dormant Specialist — подготовленный
и проверенный профиль субагента, ожидающий подходящей задачи.

Это не живой агент, который продолжает думать в фоне, и не долгоживущий bearer
credential. Это управляемая конфигурация, которую Agent Factory может быстро
активировать для нового процесса.

## Что сохраняется во сне

```yaml
dormant_specialist:
  id: source-verifier-v3
  pattern: research/1.2
  role: source-verifier
  skills_lock: skills.lock@sha256:...
  allowed_model_tiers: [cheap, medium]
  capability_card: capability-card@2.0
  trusted_memory_refs:
    - decision-policy-summary@v7
  eval_profile: eval-suite-source-verifier@5
  effort_profile: source-verification@3
  owner: research-function
  activation_policy: approved-recurring-task
```

Сохраняются только versioned profile, approved skills, допустимые tiers,
проверенная предметная память, результаты evals и калибровка Effort Units.

## Что никогда не переживает сон

- capability grants;
- credentials и секреты;
- access token и session cookies;
- необработанный контекст прошлой задачи;
- временный workspace;
- активные сетевые соединения;
- approval;
- незавершённый side effect;
- права на дальнейшее делегирование без нового grant.

## Пробуждение

```text
dormant
  -> eligibility_check
  -> activation_authorized
  -> fresh_identity
  -> fresh_capabilities
  -> fresh_context
  -> active
  -> cooldown
  -> dormant / quarantined / retired
```

При активации Factory всегда создаёт новый Agent Instance. Он получает новый
process ID, execution identity, Gateway, Task Contract, budget, TTL, workspace и
capability subset. Старые рабочие контексты не подмешиваются автоматически.

## Когда пробуждать

Trigger может быть:

- явным выбором пользователя;
- совпадением Task Contract с Capability Card;
- событием процесса;
- расписанием, если это разрешённый monitor-процесс;
- рекомендацией Pattern Selector с подтверждением policy.

Автоматическое пробуждение не означает автоматическое предоставление write или
secret capabilities. Любая опасная capability выдаётся отдельно для нового
запуска.

## Function Pack

Function Pack — версионированный комплект Dormant Specialists, patterns, skills,
контрактов, правил, evals и интерфейсов для автоматизации устойчивой функции.

```text
function-packs/
  research-operations/
    pack.yaml
    process-patterns/
    specialists/
      source-verifier/
      evidence-synthesizer/
      research-reviewer/
    skills-lock/
    policies/
    evals/
    adapters/
```

Примеры будущих packs:

- `development-operations` — архитектор, implementer, test и security reviewer;
- `research-operations` — поиск, проверка источников, synthesis и reviewer;
- `experiment-operations` — hypothesis, design, execution, analysis и
  reproducibility reviewer;
- `management-operations` — цели, обязательства, риски, статусы и эскалации.

Function Pack не является автономным отделом: владелец процесса, approvals,
policies и ответственность остаются вне него.

## Защита от деградации

Dormant Specialist может устареть из-за новой модели, skill, policy, источника,
уязвимости или изменения предметной области. Перед пробуждением проводится
compatibility check. При несовместимости профиль получает статус `quarantined` и
не запускается до повторной проверки.

Каждый профиль имеет:

- owner;
- срок пересмотра;
- minimum eval score;
- версию policy и skills;
- допустимые данные и аудиторию;
- history активаций и инцидентов;
- условия retirement.

## Экономический эффект

Повторное использование профиля снижает Effort Units на сборку контекста,
выбор skills, настройку ролей и первичный review. Это не даёт право пропускать
verification: результат каждого нового запуска проверяется по его собственному
Task Contract.

