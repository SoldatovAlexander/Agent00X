# Модель адаптации агента и Process Patterns

Статус: целевая модель; Pattern Compiler и полная agent assembly не реализованы.
Версия: 0.1

## Полная конфигурация Agent Instance

Реальный агент — не только модель. Исполняемый экземпляр определяется полной
сборкой:

```text
model
+ process pattern
+ role profile
+ skills
+ tools
+ policy
+ context package
+ process state
+ governed memory
+ identity and delegation
+ capabilities
+ effort profile
+ runtime and sandbox
+ protocol adapters
= Agent Instance
```

Каждый существенный компонент имеет версию или digest. Результат оценивается как
работа всей сборки, а не только конкретной модели.

## Уровни адаптации

| Уровень | Главный вопрос | Пример |
|---|---|---|
| Process Pattern | Как организована длительная работа? | research, development |
| Role Profile | За что отвечает участник? | verifier, implementer |
| Skill | Как выполнить конкретную операцию? | проверить источники |
| Tool | Что можно попросить выполнить? | `workspace.read` |
| Policy | Что разрешено сейчас? | read-only в данном проекте |
| Task Contract | Что требуется в этом запуске? | проверить patch |
| Context Package | Какие данные нужны сейчас? | diff, правила, состояние |
| Effort Profile | Сколько ресурсов допустимо? | 40 EU + резерв 20 EU |

## Pattern Registry

Process Pattern — versioned описание жизненного цикла, ролей, артефактов,
контрольных точек, эскалаций и критериев завершения. Он не предоставляет права и
не хранит фактическое состояние процесса.

```yaml
pattern:
  id: software-development
  version: 1.0
  lifecycle:
    - intake
    - specification
    - planning
    - implementation
    - testing
    - independent-review
    - staging
    - approval
    - application
  required_roles: [implementer, verifier]
  optional_roles: [architect, security-reviewer]
  required_artifacts: [specification, patch, test-report, review-report]
  checkpoints: [before-implementation, before-apply]
  completion: acceptance-criteria-satisfied
```

## Первые семейства patterns

### Development

Постановка, исследование проекта, спецификация, план, реализация, тестирование,
review, staging и применение. Подпаттерны: bugfix, feature, refactoring,
dependency update, migration и security remediation.

### Research

Вопрос, границы, карта утверждений, поиск, проверка источников, поиск
опровержений, синтез и независимое рецензирование.

### Experimentation

Гипотеза, дизайн, критерии успеха, preregistration, подготовка среды, dry-run,
выполнение, анализ и воспроизведение. Для MHS добавляются reservation,
telemetry, interlocks и emergency stop.

### Management

Цель, декомпозиция, владельцы, обязательства, зависимости, контроль отклонений,
эскалация, решение и ретроспектива. Агент координирует, но не становится
владельцем организационной ответственности.

## Pattern Compiler

Compiler получает Task Contract, Process Pattern, Role Profile, Capability
Cards, policy decision, доступные модели и текущее состояние. На выходе:

- Agent Manifest;
- Context Assembly Plan;
- Capability Request;
- Effort Profile;
- tool visibility set;
- required artifacts;
- completion и escalation rules;
- runtime/sandbox profile.

Compiler детерминированно проверяет совместимость версий и не может самостоятельно
активировать права, отсутствующие в Process Contract.

## Идентификатор сборки

```text
agent_build_id = hash(
  model_version,
  pattern_version,
  role_version,
  skills_lock,
  tool_schema_digests,
  policy_version,
  context_manifest_digest,
  state_version,
  memory_refs,
  capability_grant_digest,
  effort_profile_version,
  runtime_image_digest,
  adapter_versions
)
```

Динамические payload и фактическое потребление ресурсов сохраняются в run trace,
а не подменяют идентификатор конфигурации.

## Правило простоты

Pattern применяется для длительной, повторяемой или рискованной работы. Узкая
задача остаётся обычным workflow step, AI-функцией или Task Contract со skill.
Нельзя создавать сложный pattern только ради единообразия каталога.
