# Жизненный цикл и улучшение агентных связок

Статус: архитектурное направление принято  
Версия: 0.1

## Объект улучшения

Система улучшает не абстрактную модель, а версионированную связку:

```text
model + pattern + role + skills + tools + policy + context compiler
+ governed memory + capabilities + runtime + adapters + effort profile
```

Каждый run связывается с `agent_build_id`, Process Contract, входными digest,
результатами, evidence, Effort Record и security events.

## Lifecycle конфигурации

```text
draft
-> candidate
-> shadow
-> limited
-> approved
-> dormant/active
-> monitored
-> re-evaluated
-> upgraded / quarantined / deprecated / retired
```

Новая конфигурация не заменяет старую задним числом. Уже завершённые процессы
остаются воспроизводимыми по своим версиям.

## Накопительное улучшение

На повторяемых задачах собираются:

- verification pass rate;
- качество и полнота evidence;
- Effort Units на принятый результат;
- число повторов и эскалаций;
- latency и resource contention;
- policy denials;
- security incidents и near misses;
- доля корректных `cannot_proceed_safely`;
- применимость skills;
- причины human override.

Данные используются для предложения новой версии role, pattern, skill set,
router rule или Function Pack. Автоматическая активация изменений запрещена.

## Continuous Evals

Обязательные классы:

- функциональные сценарии и acceptance criteria;
- edge cases и negative tests;
- prompt injection и data poisoning;
- tool misuse и capability escalation;
- рекурсивное делегирование и fork bomb;
- privacy/DLP;
- crash recovery и idempotency;
- протокольные conformance/fuzz tests;
- MHS safety simulations;
- cost-quality routing в Effort Units.

## Shadow Mode

Candidate выполняет задачу параллельно рабочей конфигурации без критических
side effects. Результаты сравниваются по заранее заданным метрикам. Shadow Mode
не получает production credentials и не создаёт реальных approvals.

## Process Mining

Анализ audit traces может выявлять повторяемые ветви, bottlenecks, лишних
субагентов, нестабильные tools и кандидаты на Dormant Specialist или Function
Pack. Любой вывод является предложением с evidence, а не автоматическим
изменением процесса.

## Контроль дрейфа

Re-evaluation запускается при изменении:

- модели или provider behavior;
- pattern/role/skill;
- tool schema или protocol adapter;
- policy;
- source knowledge;
- runtime image;
- data distribution;
- security advisory.

До завершения проверки профиль может работать в ограниченном режиме или
перейти в quarantine.

## Safe refusal

`cannot_proceed_safely` является нормальным типизированным результатом. Он
используется при конфликте источников, отсутствии владельца, невозможности
проверить состояние, исчерпании безопасного бюджета, недоступности policy или
отсутствии безопасной операции восстановления.

