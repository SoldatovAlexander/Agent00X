# Наблюдатель, контрольные точки и обучение через корректировку

Статус: концепция принята; observer contracts и локальный SQLite journal
реализованы частично; structural report может разрешать content-addressed
event и checkpoint artifacts из отдельного local SQLite store, но полный runtime collector,
checkpoint/workspace restore, replay и учебные ветки отсутствуют

Дата: 2026-09-07

Основание: ADR-028—ADR-030

## 1. Назначение

Наблюдатель помогает исследовать, как организация данных, состояния и правил
влияет на исполнение агентом проработанной бизнес-функции. Он предоставляет
отчёт о текущем состоянии, состоянии на выбранный момент и причинных связях
между задачами, решениями, вызовами инструментов и результатами.

Наблюдатель не читает скрытые внутренние рассуждения модели. Он использует
зафиксированные основания решений и наблюдаемые события. Основание, заявленное
агентом, не считается автоматически истинной причиной или доказательством
правильности решения. При отсутствии основания отчёт сообщает об этом.

## 2. Архитектура и доверие

Две части выполняют разные роли:

1. Детерминированный сборщик в Runtime/Gateway сохраняет события исполнения
   агента и всех субагентов, включая запросы инструментов, отказы и результаты.
   Worker не может выключить его или переписать историю.
2. LLM-наблюдатель читает разрешённую историю и составляет отчёты со ссылками на
   события. Для непрерывной записи постоянно работающая LLM не нужна.

Журнал логически независим от рабочих агентов, append-only и имеет контроль
доступа. Для прототипа допустим общий доверенный Runtime с отдельными
интерфейсами записи и чтения; отдельная машина не обязательна. Это не обещание
защиты от администратора хоста. Артефакты хранятся отдельно по версии и digest;
digest без доступного содержимого недостаточен для восстановления.

## 2.1 Граница replayable trajectory

Для каждого запуска журнал должен позволять восстановить разрешённую
траекторию: границы шагов, конфигурационную сборку, инъекции контекста с их
источником, запросы инструментов, решения Gateway и неизменяемые результаты.
Это делает возможными поиск, fork и воспроизводимую проверку процессного следа;
это не означает запись скрытых рассуждений модели, полного prompt или секретов.

Replay не воспроизводит внешний мир и не получает прежние credentials,
capabilities или approvals. Внешние эффекты сверяются по receipt и текущей
политике; недостающие, удалённые или redacted представления должны быть явно
отмечены как пробелы, а не заменены догадкой. Полная session-log реализация,
fork и replay пока отсутствуют.

Наблюдатель не получает секреты, не выдаёт полномочия, не изменяет конфигурацию
агента и не останавливает выполнение. Остановка и применение корректировки —
отдельные авторизованные действия человека/Control Plane.

История, вывод инструментов и комментарии человека могут содержать недоверенный
текст. Для наблюдателя это данные, а не инструкции. Чувствительные данные
доступны только в рамках его полномочий; сырые prompts не записываются по
умолчанию. Редактирование перед записью не должно разрушать ссылки на версии:
сохраняются отдельные разрешённые представления и признак неполноты.

## 3. Правило контрольных точек

Каждое принятое агентом решение, влияющее на процесс, и каждый вызов инструмента
создают отдельную контрольную точку **до исполнения**. Это включает выбор
следующего шага, делегирование, повтор, отказ, уточнение и завершение. Скрытые
токены рассуждений не являются событиями процесса.

Для решения фиксируется ситуация выбора и предложенное решение до применения
перехода. Для инструмента — запрос до отправки. Если решение вызывает инструмент,
точки связаны причинно, но не сливаются. Завершение, ошибка, отказ или неизвестный
исход записываются отдельным событием, связанным с запросом.

Checkpoint и соответствующее событие намерения должны быть надёжно записаны до
диспетчеризации действия. При отказе записи очередное решение не применяется и
инструмент не вызывается; Runtime переходит в контролируемое ожидание/ошибку.
Уже начатое внешнее действие может продолжиться: его исход после восстановления
требует сверки, а не выдуманного результата или слепого повтора.

Контрольная точка не требует остановки и не является approval. Она сохраняет
логическое состояние и ссылки на данные, а не полный образ ОС или состояние
внутренних вычислений LLM. В прототипе каждый запуск получает устойчивый порядок
событий; причинные ссылки учитывают параллельные действия субагентов.

## 4. Минимальные форматы

Это нормативный проект полей; базовые ObservationEvent и Checkpoint schemas и
валидаторы реализованы. SQLiteObservationStore сохраняет их локально и
проверяет reopen/recovery сценарии, но это не collector, access-control
механизм, защищённый audit backend или production migration system. Значения
секретов запрещены.

### ObservationEvent — что произошло

| Поля | Значение |
|---|---|
| `schema_version`, `event_id`, `event_type` | Версия, уникальный ID и тип события |
| `process_id`, `run_id`, `branch_id`, `task_id` | Функция, конкретный запуск, ветка и задача |
| `agent_id`, `parent_agent_id` | Исполнитель и родитель; для сервисов — service identity |
| `sequence`, `occurred_at`, `recorded_at` | Порядок записи, время возникновения и приёма |
| `causal_event_ids`, `checkpoint_id`, `invocation_id` | Причинность, точка и корреляция запроса с исходом |
| `state_version`, `agent_build_id`, `procedure_version` | Какая конфигурация и состояние действовали |
| `input_refs`, `output_refs` | Разрешённые ссылки на версионированные артефакты с digest |
| `decision_or_tool`, `safe_parameters`, `rationale`, `expected_result` | Решение/инструмент, безопасные параметры, заявленное основание и ожидание |
| `authority_refs`, `status`, `error_code` | Ссылки на проверки полномочий и фактический исход |
| `classification`, `redaction_status` | Ограничения чтения и полнота сохранённых данных |

Поля, неприменимые к типу события, отсутствуют по схеме. Типы первого среза:
`decision_proposed`, `decision_applied`, `tool_requested`, `tool_completed`,
`tool_failed`, `tool_denied`, `outcome_unknown`, `agent_started`, `agent_finished`,
`correction_proposed`, `branch_created`. Повторное получение одного `event_id`
не создаёт вторую запись; конфликт содержимого с тем же ID отклоняется.

### Checkpoint — откуда можно продолжить исследование

| Поля | Значение |
|---|---|
| `schema_version`, `checkpoint_id`, `kind` | Версия, ID, `decision` или `tool_call` |
| `process_id`, `run_id`, `branch_id`, `agent_id` | Принадлежность точки |
| `trigger_event_id`, `parent_checkpoint_id`, `event_cursor` | Событие, предыдущая точка и граница истории |
| `state_ref`, `context_manifest_ref`, `workspace_manifest_ref` | Логическое состояние, доступный контекст и файлы с версиями/digest |
| `configuration_refs`, `authority_refs` | Версии модели, процедур и политик; исторические ссылки на права |
| `pending_action_ref`, `in_flight_invocation_ids` | Предложенное действие и уже исполняемые операции |
| `external_effect_refs`, `restore_mode`, `completeness` | Известные внешние эффекты, допустимый режим и полнота восстановления |

Состояние включает задачи и статусы дочерних агентов. Исторические ссылки на
полномочия не восстанавливают сами права. Недоступные артефакты, незавершённые
вызовы и неизвестный исход явно ограничивают возможность продолжения.

### LearningCorrection — чему и в каких условиях учим

| Поля | Значение |
|---|---|
| `schema_version`, `correction_id`, `version` | Неизменяемая версия корректировки |
| `checkpoint_id`, `target_event_id`, `author_id`, `created_at` | Точка ошибки и автор замечания |
| `error_description`, `explanation`, `expected_action` | Что неверно, почему и как следовало действовать |
| `applicability`, `counterexamples` | Условия применимости и случаи, где правило неверно |
| `proposed_configuration_change`, `evidence_refs` | Изменение примера/процедуры/контекста и основания |
| `evaluation_case_refs`, `baseline_build_id`, `candidate_build_id` | Проверки и сравниваемые конфигурации |
| `review_status`, `approval_ref`, `supersedes` | Отдельный review, разрешение применения и предыдущая версия |

Замечание само по себе не предоставляет права, не меняет policy и не становится
универсальным правилом. Статусы: proposed → evaluated → approved/rejected.
При применении создаётся новая конфигурация; исходная не переписывается.

## 5. Исторические отчёты

Отчёт содержит вопрос, время среза, границу записанных событий, факты со ссылками,
заявленные основания, результаты и пробелы. Интерпретации наблюдателя помечены
отдельно. Запрос «что было известно в момент T» использует только данные,
доступные тогда. Запрос «что теперь известно о моменте T» может включать поздние
результаты, но обязан их обозначать. Нет события завершения — исход неизвестен,
а не автоматически успешен или ошибочен.

Если история неполная, система выдаёт частичный отчёт. Обещание «на любой момент»
ограничено периодом наблюдения и сроком хранения разрешённых данных. Нельзя
восстановить незаписанное или уже удалённое содержимое по одному хешу.
Сроки, слои памяти и форматы сводок определены в [документе 30](30-memory-model.md).

## 6. Ветвление и обучение

1. Человек выбирает checkpoint и создаёт корректировку.
2. Runtime проверяет доступность артефактов и создаёт новый `branch_id` с ссылкой
   на исходную точку; оригинальные события и файлы сохраняются.
3. Восстанавливается изолированное логическое состояние. По умолчанию используется
   `simulation`: записанные ответы или явно обозначенный mock, без внешних writes.
4. Агент выполняет альтернативный шаг с candidate-конфигурацией. Это новый запуск,
   а не обещание бит-в-бит воспроизведения недетерминированной модели.
5. Сравниваются исходный и исправленный случаи, похожие ранее не показанные
   задачи и регрессионный набор. Объяснение наблюдателя не заменяет verifier.
   Для repository-change ячейки, transfer cases и пороги заранее зафиксированы
   в [протоколе R5](33-r5-experimental-protocol.md); это не доказывает, что
   модельный эксперимент выполнен.
6. Человек отдельно разрешает применение новой конфигурации.

Для реального продолжения нужны актуальные данные, новая проверка policy и новые
grants/approval. Отправленное письмо, опубликованный PR или платёж не исчезают
при восстановлении. Их компенсация — отдельная разрешённая операция. При
неизвестном исходе сначала выполняется reconciliation. Автоматический перенос
credentials, действующих сессий и старых разрешений в новую ветку запрещён.

## 7. Проверки прототипа

- Каждое решение и вызов имеют сохранённую checkpoint до применения/отправки;
  отказ хранилища блокирует диспетчеризацию, включая путь субагента.
- По журналу можно восстановить состояние до/после вызова, причинность,
  незавершённые операции и доступные на тот момент данные.
- Повтор события, конкурентная запись, crash и поздний ответ не искажают историю.
- Worker не может переписать журнал; наблюдатель не получает секреты и не следует
  инструкциям, внедрённым в tool output.
- Учебная ветка сохраняет оригинал и не повторяет внешний side effect.
- Корректировка помогает на новых похожих случаях и проходит старые проверки;
  при отсутствии улучшения гипотеза обучения остаётся неподтверждённой.

Первый пример: агент предлагает опубликовать изменённый после проверки файл.
Наблюдатель показывает связанные события; человек объясняет необходимость новой
проверки и approval. Учебная ветка должна выбрать повторную проверку, но даже
ошибающийся агент не может обойти детерминированный запрет публикации.

## 8. Граница текущего инкремента

В этом инкременте приняты концепция, проект форматов и критерии VP-20—VP-22.
Контракты, in-memory store и локальный versioned SQLite journal покрыты
unit-тестами, включая reopen, pre-dispatch transaction и fail-closed отказ на
некорректной базе. Batch IF / EXP-643 добавляет opt-in atomic checkpoint+intent
gate только для `ProposalWorker.propose`: Worker вызывается после успешной
записи, а незаписанный исход блокирует повтор той же задачи в том же journal.
Batch IG / EXP-644 позволяет операторскому pinned runner явно передать новый
SQLite observer journal параметром `--observation-database`; он открыт только
на время запуска и закрывается после него. Synthetic remote pipeline сохраняет
bounded Worker-call события, которые затем читаются структурным report. Это
не обязательное журналирование и не полный collector: readiness, snapshot
fetch, sandbox, verifier, stage, Gateway и publication decisions/calls не все
инструментированы. Batch IE /
EXP-642 добавляет deterministic read-only CLI
для structural history report: проверяет schema/digests/cursor links,
показывает безопасные метаданные и явные sequence/causal/invocation/redaction/
artifact gaps. Отчёт всегда помечен partial и local_unattested. Это только
поведение загруженных строк, не полный collector, event-source truth, artifact
resolver или replay. Не заявляются power-loss/storage guarantees, защита от
администратора, многопроцессная конкурентность или полнота истории.
Batch IH / EXP-645 extends the same optional run through
`IndependentVerifier.verify`: its pre-dispatch checkpoint references the
preceding Worker terminal event and both calls share one run ID and monotonic
sequence. The journal stores only fixed verifier success/failure metadata, not
the verifier result payload or exception text. This still omits sandbox
creation/commands, readiness/snapshot intake, stage, Gateway and publication;
the report remains partial and local-unattested.
Batch II / EXP-646 additionally wraps the target-test and pinned/remote
verifier-replay `SandboxSession.run` calls in that same run. The journal records
fixed tool labels, pre-dispatch checkpoints/intents and bounded terminal
success/failure only; command arguments, stdout/stderr and exception text are
not persisted. A missing terminal event is explicitly unknown and blocks retry
through the one-shot adapter. Sandbox creation/cleanup, readiness/snapshot
checks, stage, Gateway and publication are still outside the collector, so the
history report remains partial and local-unattested.
Batch IJ / EXP-647 extends the run through `StagedArtifactStore.save` and the
exact-digest `load` readback. It records fixed operation labels and bounded
terminal status only; artifact content and exception details remain outside the
journal. Existing artifact/digest equality checks remain the authority for
successful stage verification. The stage store is local test infrastructure;
this adds no production durability claim. Sandbox lifecycle, readiness/snapshot,
Gateway and publication remain outside the collector.
Batch IL / EXP-649 starts the optional run before pinned snapshot intake. Each
allowlisted anonymous REST GET and the one raw commit-object source call gets a
checkpoint and intent before dispatch, then fixed terminal metadata; URLs,
repository/path/OID, headers, response bodies and exception text are excluded.
The resulting run is handed to the executor through the same journaled Worker
wrapper. Batch IM / EXP-650 records one fixed `PinnedSnapshot.validate-fixed-pin`
decision using a decision checkpoint and bounded applied/denied outcome before
executor handoff. It stores no pin values and a failed/unknown journal result
stops execution. This records only the local comparison result: it does not
establish snapshot authenticity or provenance. Readiness decisions remain
outside the collector; the overall evidence is partial, local and opt-in.
Batch IN / EXP-651 adds fixed lifecycle intents/outcomes for target and optional
verifier-replay sandbox creation and close to that same run. Snapshot/workspace
paths, image names, session identifiers, commands, output and backend results
are omitted. Commands remain single-layered. If journaling a close is refused,
the wrapper still attempts cleanup and marks its outcome unknown; if create
terminal evidence is lost, it best-effort closes the returned lease and forbids
reuse. Fake tests establish adapter behavior only, not Docker isolation or
trusted cleanup on a real host.
Batch IO / EXP-652 starts the observer run before consuming the fixed
`RemoteExecutionPermit`. It checkpoints a bounded authorization decision;
accepted or rejected status is recorded without permit/card fields, readiness
counters/timestamps, pin values or exception text. Pre-dispatch journal refusal
does not consume the permit or access snapshot sources; unknown terminal
evidence stops before snapshot intake. An accepted permit continues with the
same `JournaledProposalWorker` run through snapshot intake. The readiness
evidence itself is supplied externally and is not journaled here; no readiness
GET or live Worker was performed.
Batch IP / EXP-653 adds an opt-in `observer` locator to fixed pinned-run
evidence: run ID, inclusive as-of journal cursor and `partial` completeness.
It also attaches that safe locator to sanitized post-authorization errors,
including a recorded denial. The values can be passed to the existing
read-only history report filters; the report itself is not embedded. With no
observer store the previous output shape is unchanged. This is a navigation
hint into local-unattested evidence, not proof of collector completeness.
Batch IQ / EXP-654 adds one opt-in `ControlledPublication.local-mock` call
boundary around the existing typed-digest approval composition. It records a
fixed intent/checkpoint before entering the unchanged approval, deterministic
Policy Engine, Gateway, broker and in-memory mock publication path, then a
fixed success/failure result. A refused pre-dispatch checkpoint blocks that
path; missing terminal evidence is reported as unknown and never retried. The
journal excludes approval/signature, intent, digest, grant, credential, staged
payload, exception and receipt values. This is one coarse composition boundary:
Batch IR / EXP-655—659 adds separate fixed decision/tool events for exact
approval validation, the fresh Policy Engine evaluation, bound Gateway
authorization, one-shot broker channel acquisition and publication dispatch.
The journal records only `ok`, `denied`, fixed failure, or unknown outcomes;
pre-dispatch refusal prevents that gate's callable from running, and the
publication checkpoint precedes the existing publication-journal transition
and endpoint call. These hooks do not alter gate authority and currently run
only in the synthetic local-mock composition; they are not evidence of
authenticated approval, complete collection, live CLI wiring or real
publication. Readiness collection, broader Runtime/Gateway coverage, full
replay and learning branches remain incomplete. Model-weight training is not
required. Batch IS / EXP-660 exposes the local-mock approval CLI's opt-in
`--observer-db`; successful receipts and sanitized post-run errors carry only
the run ID, inclusive event cursor and `partial` marker. The separate SQLite
journal path is never printed, and default no-observer CLI output is unchanged.
This remains local-only CLI evidence, not a full pinned-run-to-publication
collector or real PR.
Batch IT / EXP-661 adds `--observer-run-id` continuation to that CLI. The
resume factory validates the exact process/run, recorded task, branch, start,
contiguous sequence, completed invocations and one-shot flags before appending;
foreign, pending, unknown or already-published runs are refused. A deterministic
publication intent is inserted once in an atomic SQLite transaction before
the mock publication path, preventing a second local process from winning the
same run claim. Synthetic tests prove the receipt continues the original run
with an advanced cursor and that duplicate claims do not dispatch twice. This
is still local SQLite/mock evidence, not independently hosted audit or a real
provider idempotency guarantee.
Batch IU / EXP-662 extends that exact-run continuation to the signed-mock CLI.
The CLI reads the process binding from the exact staged artifact, validates the
selected existing observer run, and claims the deterministic coarse mock
publication intent atomically before signature verification or any publication
gate. It then records a fixed `SignedApproval.verify` event plus the existing
Approval→Policy→Gateway→Broker→Publication events in the same run. The
one-shot claim closes a sequence-ordering gap: nested publication events now
start after the persisted coarse intent, not at its sequence number. Event
metadata excludes signature, request/profile content, digest, credential,
stage bytes and receipt values. Synthetic end-to-end coverage confirms an
exact-digest local mock receipt, unchanged inputs, a continuous event sequence,
and refusal of a repeated run without adding history. Trust profiles remain
operator-supplied/unverified, the signer is synthetic, and the endpoint is
in-memory; this is not a real Worker call, human authentication, real PR,
production collector or provider-level idempotency proof.
Batch IV / EXP-663 starts the observer run only after the existing operator
confirmation and credential-source availability checks, but before the single
anonymous readiness request. It records bounded pre-dispatch/terminal events
for readiness fetch and readiness eligibility/permit issuance, without storing
rate counters, reset time, response body, permit or exception text. The exact
same `JournaledProposalWorker` instance is passed to the pinned runtime, so
permit consumption and snapshot intake continue its sequence. A readiness
transport failure or insufficient remaining quota leaves a partial, selectable
run and stops before runtime; cancellation and missing process-injected
credential create no observer database/run. Fake-only tests verified this
control flow. No readiness request or live Worker was performed, and the
observer remains local/unattested with incomplete collector coverage.
Batch IW / EXP-664 composes the actual pinned operator CLI, fake readiness and
runtime, synthetic remote snapshot, Worker/verifier, exact SQLite stage,
approval-request CLI, synthetic signature and signed-mock CLI. The resulting
readiness→permit→snapshot→Worker→verifier→stage→approval→controlled-gates→mock
receipt history stays in one observer run with contiguous sequence and exact
stage digest; stage and approval inputs are unchanged, and a repeated mock
continuation is rejected without journal mutation. This remains synthetic
local evidence: no live readiness, credential, model, Docker, provider write or
production audit guarantee was exercised.
Batch IX / EXP-665 adds a metadata-only simulation-branch declaration. It
accepts only a schema-valid correction targeting the selected source history
and a complete checkpoint marked `simulation` with no in-flight invocation,
pending action or known external effects. The journal receives one
causally-linked `branch_created` event under a distinct run and branch ID; the
source events/checkpoints are not rewritten. This API does not resolve or
restore artifacts, execute an alternative step, or expose a replay/dispatch
callback. It is only the first no-replay boundary: simulation checkpoint
resolution, execution and learning evaluation remain unimplemented.

Batch LK / EXP-730 adds an append-only local SQLite artifact prototype. It
accepts only bounded canonical JSON bytes, requires caller-declared
`public`/`internal` classification and complete redaction, rejects selected
credential-shaped patterns, and derives immutable references as
`artifact://sha256/<digest>`. The history report can optionally resolve event
input/output references in read-only mode and emits only reference, digest and
byte-count metadata; classification/redaction metadata is persisted immutably,
and a same-reference metadata change is rejected. Payload bytes are never included. Missing, malformed or
tampered references remain explicit gaps. This is a bounded heuristic and
local-unattested storage prototype, not proof of secret absence, checkpoint or
workspace restore, replay, a complete collector, or durable external audit.

Batch LL / EXP-731 extends the same read-only resolution to all declared
checkpoint refs: state, context/workspace manifests, configuration, authority,
pending action, and known external effects. Report checkpoint records associate
safe references with the checkpoint and expose only the resolved artifact
digests and byte counts. The 10,000-reference limit covers both events and
checkpoints. Resolution confirms only content-addressed availability; it does
not deserialize state, restore a workspace, replay a step, or prove that the
checkpoint is complete or trustworthy.
