# Каталог контрактов MVP

Статус: каталог реализованных базовых контрактов; не включает проектируемые
контракты наблюдения

Версия: 1.1

## Общие правила

Дополнение 2026-09-09: ObservationEvent, Checkpoint и LearningCorrection
спроектированы в [документе 28](28-observer-and-learning.md), а MemorySummary и
его retention semantics — в [документе 30](30-memory-model.md). Эти форматы пока
не входят в реализованные шестнадцать JSON Schema. Машинные схемы и проверка их
инвариантов составляют следующий контрактный инкремент R0/R1.

- контракты versioned и reject unknown security-critical fields;
- все идентификаторы ресурсов канонизируются до policy evaluation;
- mutable payload не передаётся по ссылке без digest/version;
- credential fields запрещены во всех agent-facing schemas;
- timestamp, TTL, audience и idempotency обязательны для side effects;
- строки из недоверенного контента не становятся operation, destination или
  capability без allowlisted mapping.

## ProcessContract

Содержит `process_id`, owner, goal, repository scope, acceptance criteria, data
classification, budget, approval profile и expiry.

## RepositorySnapshot

Содержит canonical repository ID, base commit SHA, snapshot digest,
classification и разрешённые read paths. Не содержит remote credential.

## TaskContract

Содержит task ID, parent process, role, input artifact references, expected
output schema, capability subset, Effort Profile и completion criteria.

## EvidenceBundle

Содержит patch digest, test definitions/results, relevant source digests,
assumptions, known limitations, Worker build ID и timestamps.

## VerificationReport

Содержит verifier identity/build, acceptance checks, independent test results,
verdict (`pass`, `conditional`, `fail`) и blocker list.

## StagedChange

Содержит process ID, snapshot/base SHA, patch artifact digest, Evidence Bundle
digest, Verification Report digest, proposed publication metadata и expiry.
После создания immutable.

## Approval

Содержит approver identity, staged digest, repository, operation,
policy-version-at-preview, expiry и optional conditions. Изменение любого
security-relevant поля требует нового approval.

## IntentContract: publish_pull_request

Обязательные поля:

```yaml
schema_version: 1
operation: publish_pull_request
process_id: process-001
repository_id: github-installation/repository-id
base_commit: sha
staged_change_digest: sha256:...
approval_id: approval-001
branch_namespace: agent/process-001
title_artifact_ref: artifact://...
body_artifact_ref: artifact://...
idempotency_key: publish/process-001/digest
audience: github-installation-id
expires_at: timestamp
```

Запрещены `token`, `authorization`, arbitrary endpoint, raw shell command и
неограниченный API payload.

## PolicyDecision

Содержит decision ID, effect, reason codes, evaluated identity/delegation,
resource, operation, staged digest, policy version, obligations и expiry.
`allow` без совпадения всех обязательных атрибутов считается невалидным.

## ActuatorRequest

Формируется после policy и approval. Содержит только зарегистрированную
операцию, нормализованные параметры, artifact references, decision/approval
references и idempotency key.

## CredentialUseGrant

Внутренний контракт Authority Plane: credential class, GitHub installation,
repository audience, permission subset, actuator identity, operation, TTL и
single-use binding. Значение token не является полем контракта.

## ActionReceipt

```yaml
schema_version: 1
receipt_id: receipt-001
process_id: process-001
operation: publish_pull_request
intent_digest: sha256:...
staged_change_digest: sha256:...
policy_decision_id: decision-001
approval_id: approval-001
repository_id: github-installation/repository-id
branch: agent/process-001
commit_sha: sha
pull_request_id: 123
pull_request_url: canonical-url
idempotency_key: publish/process-001/digest
status: succeeded
postcondition: verified
started_at: timestamp
completed_at: timestamp
```

Receipt не содержит credential, request headers, unredacted API error или
полный приватный payload.

## Structured errors

- `invalid_schema`;
- `identity_invalid`;
- `delegation_invalid`;
- `capability_required`;
- `policy_denied`;
- `policy_unavailable`;
- `approval_required`;
- `approval_stale`;
- `digest_mismatch`;
- `base_changed`;
- `artifact_unavailable`;
- `verification_failed`;
- `credential_unavailable`;
- `actuator_failed`;
- `side_effect_unknown`;
- `idempotency_conflict`;
- `budget_exceeded`.

## Следующий артефакт

Базовые машинные JSON Schema, negative fixtures и conformance tests созданы.
Каталог продолжает описывать семантику и не заменяет исполняемую валидацию;
новые поля принимаются только вместе со schema version и тестами.
