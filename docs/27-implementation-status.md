# Статус реализации и доказательств

Статус: единственный оперативный статус проекта

Версия: 1.1

Дата сверки: 2026-10-09

Этот документ отвечает на вопрос «что существует и что подтверждено сейчас».
План работ находится в [документе 24](24-mvp-final-plan.md); замысел широкого
продукта — в документах 00 и 23. При расхождении этот документ имеет приоритет
для утверждений о реализации и проверках.

## 1. Итог

Проект находится на стадии исследовательского прототипа. Основная гипотеза:
явное представление целей, данных, состояния, процедур и правил поможет агенту
исполнять проработанную бизнес-функцию. Первый пример функции — `repository-change`.

Есть контрактная и sandbox-основа, детерминированный reference flow, локальный
executor shell, ограниченный runtime composition, mock boundary и отдельные
GitHub App spikes. Последующее R2 evidence включает один live DeepSeek Worker
proposal для exact pinned public snapshot (EXP-520), replay того же сохранённого
candidate с HTTP/DB verifier PASS и SQLite exact readback (EXP-548), unsigned
approval-request CLI (EXP-552) и synthetic signer round-trip через policy и
controlled local mock PR chain (EXP-553/554). Batch EX / EXP-558 добавил
read-only CLI проверки внешнего подписанного approval request по точному stage
и операторскому, неаутентифицированному trust profile. Это всё ещё не подтверждённая
production end-to-end система: commit signature объявлена GitHub API как valid,
но ключ/авторство независимо не проверялись, а source transport доверяет GitHub/TLS;
verifier доверен только в same-host/container контуре, signer синтетический,
mock и fake-provider evidence не равны реальной publication, а текущий project
working tree не содержит persisted SQLite stage из EXP-520. При этом на
2026-10-08 записанная временная SQLite-стадия EXP-548 всё ещё существует на
текущем host: read-only `stage_preview` подтвердил её точный digest, PASS и
`backend/routes.py` patch. Байтово-идентичная копия сохранена вне Git в
локальном каталоге evidence для продолжения review; это не резервная копия и
не production durability guarantee. Approval на этой стадии не создавался.
Проверка EXP-599 подтвердила, что `AI_PROCESS_API` не инъецирован в текущий
runner. EXP-600 проверил только README назначенного проекта AI Process
Architect: он описывает настройку серверной переменной окружения, но не
документирует поддерживаемый нераскрывающий интерфейс передачи значения в
Agent00X. Это не доказывает, что ключ отсутствует в проекте; файлы секретов и
значение переменной не проверялись. До безопасной инъекции credential-source
live Worker остаётся закрыт.
Batch ID / EXP-641 added a limited lazy `NativeKeyringCredentialSource` for the
fixed `Agent00X/AI_PROCESS_API` item, explicitly selecting only allowlisted
macOS Keychain, Windows Credential Manager or Linux Secret Service backends.
It does not transfer a key from AI Process Architect. Synthetic tests passed;
the status CLI intentionally checks only backend availability and never looks
up the item. The current check runtime has no `keyring` package installed, so
backend status was `unavailable` (`credential_item_checked=false`,
`value_read=false`, exit 3). No real backend/item or OS-specific security
properties were tested. EXP-634 remains BLOCKED and does not authorize a run
through this new source.
At this point in the historical sequence, the user reported that no suitable
injector was available and the hidden `TerminalPromptCredentialSource` was
proposed as an MVP fallback. A later Control Plane amendment and fresh
confirmation authorized one EXP-634 attempt; that invocation stopped at the
hidden credential prompt before the DeepSeek channel opened HTTPS. EXP-634 is
spent and cannot be retried. EXP-725 later prepared the separate EXP-726
profile, which remains DRAFT. A subsequent terminal inspection showed the
operator command was not running and the credential value was entered as shell
input; treat it as compromised and revoke it before any new attempt. No
DeepSeek request is evidenced, and revocation has not been confirmed.
Batch IU / EXP-662 now exercises a synthetic remote-snapshot execution with a
persistent observer through the signed-approval CLI and the existing
approval→policy→gateway→broker→mock-publication gates, continuing the exact
process/run and staged digest. The signed-mock CLI's optional resume uses a
deterministic atomic one-shot claim; repeated use is refused. This is local
SQLite, fake Worker/verifier, synthetic signature and in-memory mock evidence
only. It does not consume EXP-634 authorization or establish real Worker,
authenticated approval, independent verifier trust, complete collection or a
real PR. EXP-634 remains BLOCKED pending a supported credential source or a
freshly approved source amendment.
Batch IV / EXP-663 moves observer-run creation ahead of the one-shot readiness
request and records bounded readiness-fetch and permit-eligibility decisions.
The same `JournaledProposalWorker` instance is handed into the pinned runtime,
which continues with permit consumption and snapshot intake; a readiness
transport failure or low quota leaves a redacted partial run and never starts
runtime. Only fake/offline tests exercised this path; no readiness request,
credential or live Worker was used.
Batch IW / EXP-664 adds one synthetic composition test that invokes the actual
pinned operator CLI with fake readiness/runtime, exercises the one-shot permit,
remote snapshot executor, exact SQLite stage, approval-request CLI, synthetic
signature and signed-mock CLI, and confirms a contiguous same-run history from
readiness through mock receipt. Approval/stage inputs remain unchanged, repeat
continuation is rejected, and the mock receipt has the exact staged digest.
This is local fake evidence only; it does not establish a live Worker,
authenticated signer, real provider effect or production collector completeness.
Batch IX / EXP-665 adds only a metadata declaration for a new simulation branch.
It requires a schema-valid correction targeting an event within the source
checkpoint history, a complete checkpoint explicitly marked `simulation`, and
no pending action, in-flight invocation or known external effect. It appends a
causally linked `branch_created` event under a distinct run/branch ID and does
not restore artifacts/workspace or expose any execution/dispatch API. Synthetic
memory and SQLite-reopen tests confirm the source history is unchanged and
refuse partial/unsafe/duplicate branch inputs. Criterion 15 remains partial:
no alternative step, replay isolation or learning evaluation is implemented.
Batch IY / EXP-666 carried the preserved exact EXP-614 stage from the accepted
live Worker result/replay through the actual approval-request CLI and
signed-mock CLI using only the deterministic synthetic test signer and
operator-supplied synthetic trust profile. The mock receipt binds the same
stage digest and synthetic provider ID; stage and same-volume backup hashes and
SQLite sidecar state were unchanged. The receipt explicitly reports
`external_write=false` and `identity_authenticated=false`: it is neither a
human approval nor a real PR, and the temporary approval/signature files were
deleted automatically.
Batch IZ / EXP-667 repeats that exact-digest local-mock continuation with a
persistent observer DB at `/Volumes/DATA/Agent00X-local-evidence/exp667-observer.sqlite3`.
It records the approval/publication gates in one 15-event, 7-checkpoint run;
the source Worker/verifier stage predates this run and is deliberately not
claimed as observed in it. Sequence and gate order were confirmed from the
read-only journal rows; the redacted structural report remains `partial`, with
an absent agent terminal event and unverified collector coverage. The exact
stage and same-volume copy remain byte-identical; the synthetic repeat was
refused without journal mutation. No provider effect occurred.
Production runtime,
independent verifier trust, signer enrollment, durable recovery и real PR
остаются открытыми; есть structural report загруженных journal rows (EXP-642)
и opt-in journal вызовов Worker/verifier (EXP-643—645), но полный runtime
collector, полнота истории, artifact resolution, replay и учебные ветки не
реализованы.
EXP-667 was accepted after read-only journal inspection confirmed the persisted
gate order. Its initial evidence harness exited after the successful CLI call
because it expected gate labels in the report's intentionally redacted facts;
no publication retry was made. The journal was inspected read-only and the
report remains explicitly partial.
Batch JA / EXP-668 strengthens the same structural report: self-referential or
forward causal event IDs now appear as `causal_reference_not_prior` gaps with
the referenced IDs. This improves detection of malformed ordering, but does
not authenticate local journal contents or establish collector completeness.
The full offline suite after EXP-671 passed: 1256 tests (1247 passed, 9
skipped). Python emitted existing `ResourceWarning`s for unclosed SQLite
connections in other tests; this batch did not alter those fixtures.
Batch JF / EXP-673 adds an explicit colorless `--format text` mode to the
read-only stage preview CLI while preserving JSON as its default. It displays
the exact staged-change, artifact and verified-content digests, repository/base,
declared paths, verifier identity/verdict/digest, approval/publication state and
patch. Terminal control and directional-format characters are escaped; the
text mode opens SQLite read-only and does not invoke approval/publication code.
Focused stage-preview tests: 7 passed; full offline suite: 1258 tests (1249
passed, 9 skipped), with existing SQLite `ResourceWarning`s; `git diff --check`
passed. Only synthetic stages were used. Criterion 9 advances locally, but no
usability study or authenticated human approval is established.
Batch JG / EXP-674 connects the terminal review output to the existing exact
synthetic-canary scanner: clean preview passes, while a marker injected only
into a synthetic patch is localized to `stage-preview`; the failure diagnostic
does not echo the marker. Focused preview tests: 8 passed; full offline suite:
1259 tests (1250 passed, 9 skipped), with existing SQLite `ResourceWarning`s;
`git diff --check` passed. This covers one synthetic output surface only; there
is no scan of all actual runtime/evidence surfaces. Criterion 3 remains open.
Batch JH / EXP-675 extends the canary regression through the fake pinned-CLI →
Worker → stage → approval-request → signed-mock composition. A synthetic
credential is resolved exactly once by the fake Worker callback, then checked
against stdout/stderr, stage and observer SQLite bytes, approval/signature/trust
files, observer report and mock receipt. No canary is present. Focused composed
test: 1 passed; full offline suite: 1259 tests (1250 passed, 9 skipped), with
existing SQLite `ResourceWarning`s; `git diff --check` passed. This remains
fake/synthetic evidence: criterion 3 still lacks a real Worker/verifier run and
a scan of every actual runtime surface.
Batch JI / EXP-676 removes unbounded `json.dumps(default=str)` from exact-canary
scanning. The scanner now traverses only supported JSON-like values under fixed
surface-count, per-surface byte, node and depth limits; cycles, unsupported
objects and limit overflows fail closed as findings without echoing values.
Focused scanner/preview/composition suite: 30 passed; full offline suite: 1261
tests (1252 passed, 9 skipped), with existing SQLite `ResourceWarning`s;
`git diff --check` passed. The heuristic remains synthetic and exact-canary
based; it is not a general secret detector or complete live-run scan.
Batch JJ / EXP-677 adds a subprocess regression with a newly constructed parent
environment containing only a synthetic `AI_PROCESS_API`; the actual local
sandbox child reports that variable absent. A mocked Docker exec command is
also asserted to carry exactly its three fixed environment entries, and the
existing `--network none` profile assertions remain intact. Focused sandbox
suite: 19 tests (18 passed, one Docker opt-in skipped); full offline suite:
1263 tests (1254 passed, 9 skipped), with existing SQLite `ResourceWarning`s;
`git diff --check` passed. The `python:3.12-alpine` image is absent locally; no
pull was attempted, so actual Docker network/env isolation was not revalidated.
Batch JK / EXP-678 then ran the opt-in integration exactly once using the
already-local pinned target image
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`
(`linux/arm64`). The parent test process had a synthetic `AI_PROCESS_API`; the
container environment and `docker inspect Config.Env` lacked that variable.
The test confirmed no network/DNS, `NetworkMode=none`, read-only root and source
snapshot, dropped capabilities, no-new-privileges, fixed memory/CPU/PID limits,
and a writable isolated workspace. The temporary container was removed; a
read-only Docker listing showed none running from that image. Opt-in test: 1
passed; standard full offline suite: 1263 tests (1254 passed, 9 skipped), with
existing SQLite `ResourceWarning`s; `git diff --check` passed. No image was
pulled and no public network, repository, credential or provider effect was
used. This is strong target-container evidence, not full Worker orchestration
or production host/daemon attestation.
Batch JB / EXP-669 adds an opt-in observer run to the stored-candidate replay
CLI. On synthetic tests, one run spans readiness/quota, snapshot source calls,
fixed pin decision, the stored proposal, sandbox, verifier and stage save/readback.
It does not call a live Worker/model; the output remains `partial` and
`local_unattested`, and the CLI has not been run against GitHub or Docker here.
Batch JC / EXP-670 then made one authorized read-only replay attempt using that
observer, but stopped at snapshot intake before the tree GET. Read-only journal
metadata and route-code inspection localized the cause to the observer's
incorrect tree/blob URL matcher. The source stage and same-volume copy remained
byte-identical; no target test or verifier ran. Batch JD / EXP-671 corrected
the exact commit/tree/blob route shapes and added allowlist regressions. The
replay has not yet been repeated under EXP-670; that card remains blocked and
its partial run has no target/verifier evidence. A distinct, separately-carded
EXP-672 run then passed snapshot intake and reached target tests but failed the
expanded SQLite signed-64 boundary case (`target-test-sqlite-range-status`). Its
partial journal recorded 67 events/33 checkpoints and sandbox close; verifier
and stage persistence were not reached. The candidate is stale against the
newer regression, while the source and backup remain unchanged. No second
attempt is authorized under EXP-672.
Нельзя заявлять production-ready, отсутствие всех утечек секретов или доказанную
неуязвимость Gateway.

### Сверка критериев Thin Vertical Slice из документа 24, раздел 10 (2026-10-09)

Статусы ниже относятся к требуемому сквозному evidence, а не к наличию
отдельного класса или unit-теста. `Частично` означает только локальные,
synthetic/fake или same-host доказательства; это не закрывает production gate.

| № | Критерий | Текущее evidence | Статус / что ещё требуется |
|---|---|---|---|
| 1 | PR из одобренного staged digest | EXP-520/548/614 дают сохранённый live Worker result/replay candidate и verifier PASS; EXP-648/664 compose synthetic execution through actual approval-request and signed-mock CLIs; EXP-666/667 carry the preserved EXP-614 exact stage through those CLIs to a same-digest mock receipt; EXP-686/687 compose enrolled synthetic approval through mock gates; EXP-693 carries the enrolled mock receipt from a Docker target/verifier stage; EXP-699/703 cover the actual snapshot reader/parser through enrolled mock receipt; EXP-723/745/748 cover public snapshot with fake Worker; EXP-781 passes the exact 23-file pinned snapshot through `ContainerProposalWorker`, target, pinned verifier, stage/readback, preview and same-digest local mock receipt, retaining the principal digests in fixed-schema evidence. | **Открыт:** receipt is local-mock-only (`external_write=false`, `identity_authenticated=false`); EXP-781 stage has not yet passed through operator-signed approval CLI, and no trusted human approval or real PR receipt exists. |
| 2 | Worker без GitHub network path и credential | EXP-678/693 cover the pinned target image's `network=none`, synthetic parent-environment exclusion, resource limits, target tests and verifier boundary; EXP-723 uses a fake Worker; EXP-781 uses reusable `ContainerProposalWorker` in the pinned target image after public read-only snapshot fetch, with one injected fake-channel response and no credential/provider call. | **Частично:** direct GitHub egress is blocked for the container Worker and local boundary passed; no live model credential or separate host/daemon trust boundary is proven; local Worker fallback has no network isolation. |
| 3 | Canary credential отсутствует на проверяемых поверхностях | Existing exact-canary tests cover synthetic nested agent/evidence/audit surfaces; EXP-674 scans terminal stage-review output; EXP-675 checks CLI, stage/observer DB, approval inputs, report and receipt across a fake composition; EXP-676 bounds scanner work and fails closed on unscannable surfaces. | **Открыт:** no reproducible scan of an actual live Worker/verifier run and all runtime/persisted surfaces; pattern checks remain heuristic. |
| 4 | Изменение digest отзывает approval | Approval и intent привязаны к digest; mutation/неверная подпись отклоняются локальными policy regressions (EXP-547, EXP-553/554, EXP-558). | **Частично закрыт локально:** повторить как gate реального staged approval и signer enrollment. |
| 5 | Повтор intent не создаёт второй side effect | Idempotency и lost-response reconciliation покрыты mock/fake provider тестами (EXP-537/538, EXP-550/551). | **Частично закрыт локально:** нет подтверждённого recovery после реального provider side effect. |
| 6 | Недоступная policy запрещает publication | Composed mock-chain и fast/slow/degraded policy paths имеют fail-closed regression coverage (EXP-247/248 и последующие gateway/broker suites). | **Частично закрыт локально:** нет production policy service/runtime evidence. |
| 7 | Audit восстанавливает цепочку без секрета | SQLite journal and observer store verify local event causality/reopen; EXP-667 persists 15 bounded approval/publication events; EXP-687/693 exercise same-run synthetic Worker/verifier through receipt; EXP-699/703 carry actual snapshot parser events through mock receipt; EXP-723/745/748 link public pinned snapshot intake to fake Worker, target/verifier, exact stage, enrolled mock approval and receipt in one observer run; EXP-748 retains the observer run ID and stage digest without source content. | **Открыт:** EXP-748's temporary observer DB was not retained; this is not a live Worker/trusted independent host; collector completeness and operational durability remain unproven. |
| 8 | Crash recovery не делает слепой повтор | Unknown/lost outcomes переходят в reconciliation; fake GitHub и SQLite reopen cases не повторяют подтверждённый side effect. | **Частично закрыт локально:** нет production crash/recovery evidence против provider. |
| 9 | Personal пользователь понимает действие до approval | EXP-629/630 дают bounded read-only preview точного stage и patch; EXP-673 adds a colorless terminal view with all three exact digests and escaped patch text while retaining JSON by default. | **Частично:** readable CLI evidence exists, but no usability study or authenticated human approval has validated the operator experience. |
| 10 | Эксперт через CLI видит identity, policy, evidence и receipt | CLI выдаёт bounded stage/verifier/approval/publication evidence (EXP-552/558/563/573); EXP-682/683 adds verifier-enrollment digest evidence; EXP-685–687 compose synthetic enrollment and local mock gates; EXP-723/745/748 assert same-digest enrolled mock receipt and observer-run linkage through the operator CLIs; EXP-781 adds fixed-schema stdout evidence with pinned snapshot, candidate, stage, verified-content, verifier and mock-receipt identities. | **Частично:** EXP-781 is test output, not the operator CLI; enrollment is synthetic and `identity_authenticated=false`; authority governance and a real provider receipt/identity remain unproven. |
| 11 | MVP технически отключает неготовые возможности | Fixed CLIs ограничивают target, operation, endpoint и повтор; unapproved write paths требуют отдельного permit/approval. | **Частично:** нет доказательства единого production deployment, где все незакрытые функции невозможно включить/обойти. |
| 12 | Записаны время и затраты | EXP-723's public-read-only fake-worker integration test took about 24 seconds; EXP-745 took 21.516 seconds and EXP-748 took 23.124 seconds; EXP-781 took 17.127 seconds for the pinned snapshot/Docker Worker/target/verifier/stage/mock composition. These runs made no model call or provider write. EXP-634's one-call USD 1 ceiling is user-set, not account-enforced. | **Открыт:** no live end-to-end model time/cost or provider-enforced spend cap. |
| 13 | Checkpoint каждого решения/вызова записан до исполнения | EXP-643—647 cover Worker/verifier/test/replay/stage gates; EXP-649—664 cover snapshot intake, permit, lifecycle and synthetic approval gates; EXP-687/693 cover ordered mock-publication events; EXP-699/703 carry synthetic snapshot events through mock receipt; EXP-723/745/748 assert the public-read-only snapshot path through fake Worker, target/verifier, stage and mock receipt in one observer run; EXP-748 retained exact call counts and a content-free stage/run evidence line. | **Частично:** no live Worker-to-publication trace, production collector completeness or real publication; the temporary observer DB was not retained and earlier replay reports remain partial/local-unattested. Cleanup evidence can still be absent if the journal is unavailable. |
| 14 | Observer восстанавливает сохранённую историю и показывает пробелы | EXP-642/653/668 provide bounded reports and explicit gap markers; EXP-687/693/699/703 prove synthetic same-run continuity; EXP-723 validates public snapshot-intake events linked through fake Worker, target/verifier, stage and mock receipt; EXP-730/731 resolve content-addressed event and declared checkpoint refs from an optional local SQLite store; EXP-740 validates a referenced workspace manifest and materializes bounded file bytes in memory for a complete simulation checkpoint. | **Частично:** the report still lists metadata rather than restoring state/workspace into an execution environment; artifact origin, external-state reconciliation and collector completeness remain unproven; output remains partial/local-unattested. |
| 15 | Учебная ветка не меняет историю и не повторяет effects | EXP-665 adds a metadata-only simulation-branch declaration; EXP-740 adds strict content-addressed in-memory workspace materialization for a complete simulation checkpoint. Tests preserve source event/checkpoint and artifact DB bytes; no dispatch API is exposed. | **Частично:** no alternative execution/replay isolation proof or learning evaluation; the restored bytes are not run and the API cannot perform external actions. |
| 16 | Оценены функция, вклад организации данных и перенос корректировки | Batch KM / EXP-706 preregistered дизайн, oracle и decision rules в docs/33; EXP-707 добавил versioned casebook и проверку 100-попыточного расписания. | **Подготовлен, не исполнен:** нет результатов Worker-run, повторов, baseline-vs-context сравнения или оценки переноса; гипотеза не оценена. |

**Итог:** из 16 критериев ни один пока не подтверждён как завершённый на
сквозном production-уровне. Локально частично доказаны пункты 4—6, 8—10 и
13—15; пункты 1—3, 7, 11—12 остаются открытыми, пункт 16 подготовлен, но не
исполнен. Отдельный
препятствующий этап R2 сохраняется: опубликованный signer key не проверил
подпись pinned commit (EXP-639 BLOCKED). EXP-634 получил свежее подтверждение
и был израсходован на одну попытку, остановившуюся до DeepSeek-запроса;
EXP-726 остаётся DRAFT. Терминальный ввод предыдущей попытки раскрыл
credential, поэтому его требуется отозвать; факт отзыва не подтверждён.
Критерий 14 дополнен разрешением event refs (EXP-730/731) и ограниченной
in-memory materialization workspace snapshot (EXP-740), но отчёт не восстанавливает
исполняемое состояние и полнота collector не доказана. Критерий 15 продвинут от
metadata-only declaration до валидации и in-memory materialization simulation
workspace; изолированное исполнение/replay и обучение не реализованы;
протокол и casebook критерия 16 подготовлены, эксперимент не проводился. Эта
сверка не меняет статусы
исторических карточек и не является закрытием MVP.

Batch AM закрыт: все 5 карточек EXP-400—404 приняты, причём EXP-404 — как
раскрытое локальное исключение. Карточки добавили pinned verifier snapshot
handoff, отдельный container runtime код, trusted image/code result identity и
один opt-in local Docker synthetic run для EXP-403. Runtime probe подтвердил UID
65532, read-only `/`, отсутствие Docker socket и ограниченное child environment;
фиксированный CLI profile принят без независимой kernel/daemon attestation.
EXP-404 добавил nonce-bound stale-response rejection и отказные тесты; второй
targeted прогон прошёл (21 тест), но команда была запущена дважды, по одному live
verifier invocation в каждом прогоне при лимите карточки в один. По явному
решению пользователя от 2026-10-06 Control Plane принял это как раскрытое локальное
исключение: оба запуска были synthetic/offline, без credentials и внешних writes.
Batch AM закрыт. Для Batch AN пользователь выбрал публичный
`SoldatovAlexander/brainbooster_full_v11` (`master`) и назначил себя approval
owner. Control Plane ограничил текущий scope публичным unauthenticated
read-only preflight и локальными fake/SQLite-reopen экспериментами; GitHub App
permissions/credentials не разрешены. Provider write остаётся отдельной
неразрешённой операцией, требующей точной карточки и свежего подтверждения.
EXP-405 Batch AN добавил bounded content-bearing GitHub snapshot record,
сохранив `github_rest_api_claim` и metadata-only compatibility API; fake-only
targeted suite прошёл 32 теста. EXP-406 связал synthetic remote snapshot через
injected local executor и verifier wire schema v3, с fail-closed binding и
сохранением claim identity при worker failure (44 + 83 targeted tests).
EXP-408 подтвердил file-backed SQLite reopen для unknown/conflicting fake
outcomes без повторного lookup/publish (55 targeted tests). Это не выполнение
выбранного репозитория, не live Worker и не production verifier. EXP-410
добавил synthetic-only lease-owned remote snapshot materializer; EXP-411 связал
его с `ExecutionRequest` и executor lifecycle (6 + 46 targeted tests). EXP-412
добавил fake-tested anonymous HTTPS transport. EXP-413 anonymous metadata-only
GET закрепил публичный `master` на commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` и tree
`2007066217aadafd9887fb3e3069220333b4fddb` (28 entries; `truncated=false`);
blob contents не читались. EXP-606 позднее зафиксировал ответ точечного GitHub
commit endpoint: `verified=true`, `reason=valid` для того же commit, author login
`SoldatovAlexander`, committer login `web-flow`. Это GitHub verification
assertion, не independent local signature verification или доказательство
человеческой личности. General caller-selected remote input не поддержан; фиксированный
pinned metadata CLI существует. EXP-407
заблокирован до конкретного полезного MVP change и отдельного подтверждения
provider write; произвольная публикация ради демонстрации исключена. EXP-409
сверил evidence и оставил R2 открытым. Batch AN: 4/5 принято, 1 BLOCKED; R2
не закрыт.

Актуальное уточнение R2 на 2026-10-07 (оно заменяет устаревшую строку R2 в
таблице раздела 7): continuation Batch AO—BI включает 21 батч: AO — 5/5,
AP — 4/5 (EXP-419 DRAFT), AQ/AR/AS/AT — по 5/5, AU — 1 ACCEPTED, 1 BLOCKED,
3 DRAFT, AV — 5/5 ACCEPTED. EXP-426 получил только metadata/digests для 12
выбранных файлов; EXP-427/428 создали redacted структурный обзор без запуска
target code. В Batch AT полный snapshot выбранного публичного pin подтверждён:
23/23 blobs прошли ограниченные SHA и byte-pattern preflight. Один candidate
change в `backend/routes.py` — no-write при malformed integer session input —
проверен как прямой вызов pinned route только в контейнере: `ValueError` до DB
execute/commit; 422 HTTP mapping остаётся непроверенным. EXP-440 был
BLOCKED из-за отсутствующего точного image; follow-up EXP-456 (2026-10-07)
получил тот же pinned digest и прошёл synthetic `DockerSandboxBackend` smoke
с `network_isolated=true`. Batch AZ/BA зафиксировали orchestration failure и
follow-up: EXP-457 BLOCKED до запуска target; EXP-458 ACCEPTED после выполнения
ровно pinned route blob в контейнере. Это не полное target app/API/runtime test.

EXP-429—432 связали synthetic remote claim с replay, subprocess verifier,
digest-only seed/intent, test approval и mock receipt; в EXP-432 stage object
захватывается только тестовой обёрткой. EXP-433 создал fixed
`--remote-fixture-preview`, который не читает удалённый repo и не публикует.
Metadata-only remote CLI есть. Один live anonymous GET 2026-10-06 получил HTTP
403; один новый вызов 2026-10-07 вернул `snapshot_ready` для точного pin,
23 файла и content digest `sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
Batch EW / EXP-557 теперь заново вычисляет Git SHA-1 каждого subtree и
полного root tree из recursive path/mode/object-ID listing. Это проверяет
Merkle-целостность представленного дерева, но не байты commit object,
авторство, подпись, remote provenance или TLS/API trust path; evidence origin
остаётся `github_rest_api_claim`.
Batch AV добавил отдельный DeepSeek Chat
Completions Worker contract с fake channel и strict JSON parser, затем провёл
synthetic snapshot через replay, subprocess verifier и digest-only seed/intent.
`--deepseek-remote-fixture-preview` локально возвращает фиксированные
metadata/digests и `publication=not_attempted`; это не live model call. Timeout
проверен только как ошибка, сообщённая channel: прерывание блокирующего вызова
не реализовано и не доказано. После Batch BG suite содержал 893 теста;
EXP-465 в Batch BH добавил remote composition с требованием durable stage.
Batch BK позднее добавил same-process watchdog для закрытия соединения при
зависании HTTPS request или body read. Batch BL добавил active-socket
`shutdown(SHUT_RDWR)` перед close и подтвердил прерывание заголовка/частичного
тела на loopback TCP с реальным stdlib HTTPConnection; Batch BM проверил те же
активные read phases на loopback HTTPS/SSLSocket с ephemeral SAN-matching
сертификатом; Batch BN подтвердил interrupt зависшего loopback TLS handshake
до ServerHello. Batch BO не смог заблокировать допустимый upload в loopback TCP
на текущей ОС и явно пропускает узкий тест с объяснением. Upload backpressure
остаётся без доказательства; EXP-603 ограничивает caller wait на source, но не
отменяет сам callback. EXP-602 отдельно ограничил
ожидание DNS общим deadline и доказал fail-closed поведение без late connect;
сам системный resolver отменить нельзя, поэтому зависший вызов удерживает один
daemon resolver slot до возврата и временно блокирует новые DNS-попытки.
Batch BP connected `DeepSeekProposalWorker` to the real channel and a loopback
verified HTTPS stub, producing only a fixed synthetic proposal. It verifies
adapter composition, not model inference or useful target work.
EXP-508 now starts the monotonic budget before credential lookup and rejects a
callback that returns after expiry before constructing the HTTP connection. A
synthetic slow-callback test proves no request is initiated. The synchronous
callback still cannot be interrupted if it never returns. EXP-603 bounds the
caller wait by the same deadline using one process-wide daemon callback slot;
late success/exception cannot initiate HTTP, and other calls fail closed while
the slot remains occupied. The callback itself continues if it is stuck; a late
source return may briefly retain source-owned memory and is not zeroized.
EXP-602 moved DNS
resolution into one process-wide bounded daemon slot, limits the caller wait by
the same deadline and connects only to timely numeric results. Tests prove that
a late/failed resolver cannot create the HTTP connection and that blocked
resolver threads cannot accumulate without bound. The OS resolver call itself
is not cancellable: one timed-out resolver may remain until it returns and
occupy the slot, denying later DNS attempts. This is not an end-to-end hard
deadline; callback cancellation and upload backpressure remain unproven.
Batch BQ defines the runtime-checkable, platform-neutral `CredentialSource`
callable protocol for one opaque credential and checks the existing synthetic
in-memory test provider against it. The DeepSeek channel remains injected and
does no environment/file/vault lookup. This is a portable interface contract,
not a macOS/Linux/Windows credential-store implementation or evidence that a
real secret source is secure. Batch BZ adds an atomic one-attempt guard per
`DeepSeekHTTPChannel` object before credential lookup; it is not an account-level
spend cap and constructing another instance resets the guard.
Batch BR retains only a bounded numeric HTTP status in sanitized anonymous
snapshot failures; it does not expose response content or enable a retry.
Batch BS carries a typed status code to the pinned metadata CLI as a stable
`remote-snapshot-http-NNN` failure code; raw errors and response content remain
suppressed.
Batch AW — девятый follow-up batch
(EXP-450—454 ACCEPTED; 5/5): validated stage artifact, SQLite
save/reopen по bound digest интегрированы с executor sink; VERIFIED возвращается
только после exact-digest save/readback. Read-only preview CLI показывает bound
digest, repository/base/process, verifier и patch; typed-digest CLI запускает
только mock gates и возвращает `external_write=false`. Это не authenticated
production approval и не real PR.
Batch AX — десятый continuation batch: EXP-455 accepted 1/1 после одного
anonymous CLI intake exact pin (`snapshot_ready`, 23 файла); per-file
path/size/digest сохранены в WORK_QUEUE. Это API claim, не independent
provenance. Batch AY — 11-й batch: EXP-456 accepted 1/1 после digest-pinned
synthetic Docker smoke. Batch AZ — 12-й: EXP-457 BLOCKED до target execution из-за
ошибки lifecycle harness. Batch BA — 13-й: EXP-458 accepted 1/1; точный
`backend/routes.py` blob впервые исполнен только внутри указанного Docker
профиля. Нечисловой session `level` вызывает `ValueError` до `cursor.execute` и
`commit`; валидный synthetic input сохраняет один execute/commit. Это не
подтверждает HTTP 422 и не тестирует FastAPI integration, production runtime,
полное приложение или adversarial isolation. Гипотеза о runtime-необходимости
422/no-write уточнена: no-write доказан для probe, HTTP mapping остаётся
непроверенным. Batch BB/BC/BD: EXP-459/460/461 остались исторически BLOCKED
до target HTTP run (соответственно bounded GitHub API response, затем повторный
API fail и `/tmp` `noexec` для native wheel). Batch BE: EXP-462 accepted 1/1.
Exact pinned Python 3.11.16 arm64 image, 4 files matched to EXP-455 digests and
15 offline wheels verified against PyPI JSON were used for a real local Uvicorn
HTTP run. Malformed `level` returned 500 / zero rows; valid request returned 200
/ exactly one expected SQLite row. Empty static/frontend directories were
synthetic; requirements in the target snapshot remain unpinned. This establishes
the existing baseline defect and no-write behavior, not a fix or full-image
rebuild. Batch BF: EXP-463 accepted 1/1. A fixed Control Plane candidate in the
disposable writable container copy maps invalid numeric session fields and
overflow to HTTP 422 before DB writes; all five fields plus overflow returned
422/zero rows, and valid input remained 200/one exact row. Candidate SHA-256 is
recorded in WORK_QUEUE. This is useful target behavior tested at actual HTTP
level, but it was not proposed by the Worker, independently reviewed,
persisted/committed or passed through the stage/verifier/approval/publication
chain. No GitHub writes occurred. Batch BG: EXP-464 accepted 1/1; a fixed
DeepSeek HTTPS channel now implements the existing fake-tested Chat Completions
contract with an injected opaque key provider, pinned host/path, verified TLS,
bounded bytes/timeout, no redirects/retries and sanitized errors. Eleven offline
tests pass. No API key/provider request was used; this is not adversarial process
isolation and does not prove live spend or response quality.
Batch BH: EXP-465 accepted 1/1. `run_remote_snapshot_execution` now fails closed
unless a stage sink is provided, defaults to required durable exact-digest
readback, and forwards the stage contract to the executor. The synthetic fixture
preview explicitly opts out. An offline integration test ran a fake DeepSeek
Worker through the bounded subprocess verifier and local sandbox, persisted and
reloaded the exact stage in temporary SQLite, rendered its digest-bound preview,
and obtained only a local mock-publication receipt for the same digest. Targeted
suite: 22 tests passed; the suite now contains 896 tests, 3 opt-in Docker tests
skipped;
`git diff --check` passed. This does not establish live Worker output,
independent verifier trust, production durability, authenticated approval, or
real provider publication.
Batch BI: EXP-466 заблокирован на единственной разрешённой попытке полного
read-only intake: GitHub вернул безопасно-сокращённую ошибку на commit request;
retry запрещён карточкой. Новый verifier image собран офлайн из pinned base
(`sha256:f44e93faf9c93e233a3789a392a8528f55f8e72589b11e7273d5b722b97125e8`,
context code digest `sha256:bdbbb7ce12135e43d9672bc2b4a61748786c185fb55ad28796a932c417bdcb41`),
но snapshot/blob content не получены, target code и verifier не запускались,
stage/approval не создавались; running containers отсутствуют. Candidate hash
из EXP-466 не сверялся с live snapshot и не является новым evidence.
Использована временная локальная БД.
Это не доказывает production crash durability, host-tamper resistance,
multi-process writer safety или authenticated user approval.
Внешних writes не было.

Открытые MVP gates: EXP-520 уже дал один live DeepSeek Worker proposal для
полезного изменения `backend/routes.py`; EXP-548 повторно прогнал его без модели
и получил verifier PASS с exact-stage readback. Это не доказывает повторяемую
production execution: fixed runner теперь поддерживает одноразовый
`TerminalPromptCredentialSource` с запретом небезопасного echo fallback, но
секрет не вводился и новый live run не выполнялся; account/provider-level spend
cap не подтверждён. Текущий checkout не содержит stage DB. Временные пути
EXP-520 и EXP-548 были повторно проверены 2026-10-08: EXP-548 stage присутствует
и его byte-identical copy сохранена вне Git в локальном evidence-каталоге;
EXP-520 source stage отдельно не перепроверялся. Эти host-local файлы не дают
backup/production durability guarantee. Поэтому approval CLI на фактическом
candidate stage пока не запускался. Остаются independently
trusted verifier и independently validated snapshot provenance/authorship;
hard transport/runtime
timeout для синхронного credential callback и upload interruption;
доверенный human signer enrollment и production approval точного digest;
production runtime composition, crash-safe recovery и controlled real PR
publication. CLI-гейт частично открыт:
`--remote-snapshot-execute` связывает fixed full-snapshot pin, injected Control
Plane profile, bounded execution и sanitized evidence, а
`run_remote_snapshot_with_runtime` собирает Worker, Docker sandbox, verifier и
SQLite stage из явно переданных зависимостей. Ни одна команда не предъявила
реальную approval/signature от человека или реальный PR. Provider write/PR
остаётся отдельной операцией, требующей точной task card и свежего подтверждения.
R2 остаётся OPEN; batch count или synthetic/mock receipt не закрывают ни один
недоказанный trust gate.

Batch FI / EXP-569 adds a strict signed-verifier-response envelope and local
Ed25519 verifier bound to the canonical process request digest, fresh 256-bit
challenge, caller-pinned verifier-profile digest and issue time. The adapter
rejects stale/future responses, wrong key/profile/request/challenge, altered
verifier results, noncanonical/duplicate/oversized JSON and excessive key
sets. It deliberately returns a receipt with
`independent_host_trust_established=false`: no separate verifier service,
private-key custody or independently pinned public key has been demonstrated.
EXP-569's synthetic focused suite passed 9 tests; its full offline suite passed
1046 tests (1037 passed, 9 skipped).

Batch FK / EXP-571 integrates that typed receipt into execution as audit-only
evidence. The executor revalidates the contained verifier result and exact
request digest, records only the attestation digest, bounded key ID, profile
digest and explicit `signature_valid=true` / `independent_host_trust_established=false`
markers, then fails before durable stage save/readback. Publication-seed
construction rejects receipt-bearing results even if relabeled VERIFIED. This
does not enroll verifier identity or host trust; a separate trust-enrollment
task card is required before a receipt can become stage evidence. Local
same-host verifier behavior is unchanged. No remote verifier, key, stage write
or provider effect was used. EXP-571 targeted suite passed 127 tests (2 skipped);
the full offline suite passed 1049 tests (1040 passed, 9 skipped), and
`git diff --check` was clean.

Batch FL / EXP-572 hardens the CLI projection against caller-constructed
`ExecutionResult(status=VERIFIED)` values carrying audit-only receipt metadata.
Those results must remain `failed`; neither verified digests nor an optional
stage locator may be emitted. Malformed receipt metadata gets a stable safe
failure without echoing its values. This is a projection-level defense in
depth, not verifier trust enrollment. The focused CLI suite passed 42 tests
(2 skipped); the full offline suite passed 1051 tests (1042 passed, 9 skipped).
`git diff --check` passed.

Batch FJ / EXP-570 is a DRAFT read-only testdev preflight with one exact
host-key-verified SSH command to inspect only OS/architecture, Docker version
and the two pinned image IDs. It requires fresh confirmation in OpenCode; no
SSH invocation or remote host change has occurred.

Batch DZ / EXP-535 (R2 batch 88/88) repaired one local GitHub Contents request
contract: for each existing file, the adapter reads blob metadata at the exact
staged base commit and sends that validated blob SHA with the update request;
missing, unknown, malformed, and non-file metadata fail before branch/file
writes. The fake-only targeted suite passed (56 tests), the full offline suite
passed (955 tests, 946 passed, 9 skipped), and `git diff --check` passed. No
GitHub request or provider write occurred. This does not establish real PR
publication, multi-file atomicity, or durable recovery; those gates remain open.

Batch EA / EXP-536 (R2 batch 89/89) adds fake-only candidate-branch state
reconciliation for content writes. A fresh channel after a lost successful PUT
recognizes the desired Git blob SHA and skips the duplicate write. A partial
two-file case writes only the file still matching its base blob SHA; an
unexpected third state blocks all file PUTs in that attempt. The target suite
passed (59 tests), the full offline suite passed (958 tests, 949 passed, 9
skipped), and `git diff --check` passed. No real GitHub request or provider
write occurred. This is remote-state reconciliation logic under fake transport,
not evidence of production durability, a local provider journal, multi-file
atomicity, or actual PR recovery.

Batch EB / EXP-537 (R2 batch 90/90) connects `PublicationJournal` to typed
`GitHubPullRequest` receipts. Startup adds a nullable URL column to legacy
SQLite journals without changing existing attempts. Fake-provider evidence
simulated a PR POST that took effect but lost its response; after close/reopen,
read-only idempotency lookup recovered the exact PR ID/URL without a second
POST. Empty reconciliation becomes terminal `reconciliation_required`. Targeted
suite: 96 tests; full offline suite: 963 tests (954 passed, 9 skipped); diff
check clean. No real GitHub request, credential or provider write occurred.
This verifies local journal/adapter behavior, not production filesystem
durability, live provider semantics, or a controlled end-to-end approval path.

Batch EC / EXP-538 (R2 batch 91/91) composes the typed GitHub App broker/channel
with the existing approval, deterministic policy, slow-gateway and SQLite
journal coordinator. A synthetic token minter and fake transports create a PR,
lose the POST response, then recover the exact typed receipt and HTTPS URL by
read-only lookup with exactly one POST. Existing mock composition remains
covered. This is local fake-transport integration evidence only: no real
credential, network or GitHub write was used; production approval, durability
and live publication remain unproven.

Batch ED / EXP-539 (R2 batch 92/92) adds integrated denial-path evidence for
the GitHub App composition. Missing approval stops before stage loading;
policy denial stops before gateway; gateway denial stops before broker. Across
all three cases the synthetic token minter and fake provider GET/POST transports
remain untouched and the SQLite publication journal has no row. Targeted suite:
117 tests; full offline suite: 965 tests (956 passed, 9 skipped); diff check
clean. This proves only local fake-transport ordering, not authenticated
approval, provider behavior, or production trust.

Batch EE / EXP-540 (R2 batch 93/93) replaces coordinator checks based on
caller-set Python `module/name` strings with exact registered class identities
for the trusted broker, channel and receipt types. Lookalike broker and channel
classes are rejected before stage loading or effects; the isolated gate module
still does not import the GitHub adapter directly. Targeted suite: 118 tests;
full offline suite: 966 tests (957 passed, 9 skipped); diff check clean. This
registry is trusted in-process wiring, not a boundary against arbitrary code in
the same process.

Batch EF / EXP-541 (R2 batch 94/94) now composes the exact approved staged
content with candidate-branch file publication and PR creation. The non-empty,
sorted, unique file manifest is checked against per-file digests and the seed's
verified contents digest. Fake transports prove branch → file PUT → PR order;
a lost PR response recovers the exact receipt without a second POST, while a
lost file-write response stops before PR creation and leaves the journal in
`reconciliation_required` after one read-only lookup. Targeted suite: 156 tests;
full offline suite: 968 tests (959 passed, 9 skipped); diff check clean. No live
credential, network or provider write was used; this is not atomic multi-file
publication or production recovery.

Batch EG / EXP-542 (R2 batch 95/95) adds one bounded read-only reconciliation
after an ambiguous Contents PUT. The controlled attempt continues to the PR
only if candidate-branch ref and every file's Git blob SHA prove the complete
verified manifest is present; no content or branch write is repeated. Fake
integration covers applied-but-lost PUT plus lost PR response, and a
not-applied response remains `reconciliation_required` without PR creation.
Targeted suite: 121 tests; full offline suite: 969 tests (960 passed, 9 skipped);
diff check clean. This is not cross-process resume, multi-file atomicity, or
live-provider evidence.

Batch EH / EXP-543 (R2 batch 96/96) persists restart-time reconciliation for
uncertain file publication. A reopened `attempting` row first checks for the
matching PR; if none is established, it remains terminal
`reconciliation_required` while exact candidate-branch file state is stored
as digest-only evidence (manifest digest, verified/unverified outcome, branch
commit SHA and UTC observation time). Expected manifest digest is journal-bound
at prepare before provider effects; mismatch stops before GET. It does not
resume writes or reuse approval. Targeted suite: 99 tests; full offline suite:
972 tests (963 passed, 9 skipped); diff check clean. This is local SQLite/fake
evidence, not cross-host or production durability.

Batch EJ / EXP-544 (R2 batch 97/97) repeats only the read-only PR lookup for a
terminal `reconciliation_required` attempt after restart, using the original
repository and idempotency key. A later exact typed receipt completes that
same journal and retains prior digest-only file evidence; absent or mismatched
receipts leave it terminal. Tests forbid POST/PUT on recovery. Targeted suite:
100 tests; full offline suite: 973 tests (964 passed, 9 skipped); diff check
clean. Local SQLite/fake evidence only, not live-provider recovery.

Batch EK / EXP-545 (R2 batch 98/98) makes the PR base branch explicit through
`PublicationIntent`, approval digest, actuator request, mock/GitHub adapter,
and idempotency key. The approved intent digest binds repository and source
commit; the key binds head branch, explicit base branch, and staged digest
within the configured repository. Exact base branch is retained in typed
receipts and checked when the journal completes or recovers an attempt. Fake
tests cover `master`, base substitution, and zero provider/token calls on
rejection. Focused suite: 369 tests (3 skipped); full standard unittest suite:
974 tests (965 passed, 9 skipped); `git diff --check` clean. No network,
credential, provider write, branch, PR, commit, or deployment was used. R2
remains OPEN; this does not establish live PR publication or production-grade
approval/recovery.

Batch EL / EXP-546 specified an explicit non-empty `allowed_approver_ids` set.
EXP-556 (Batch EV) made that documented set a required `PolicyConfig` field.
The deterministic policy rejects a missing, malformed, or unlisted
`approver_id` before the slow gateway/broker path; the existing local mock path
uses only the synthetic `local-mock-operator` claim.
This is an allowlist check on a supplied identity claim, not authentication,
signature verification, or evidence that a person approved anything. Provider
credentials and live calls are outside this batch. Focused suite: 180 tests
(1 skipped); full standard suite: 975 tests (966 passed, 9 skipped);
`git diff --check` clean. No credentials or external writes were used. R2 and
the MVP remain OPEN.

Batch EM / EXP-547 adds Ed25519 signature verification over the canonical
approval ID, approver claim, repository/operation, staged and intent digests,
policy version, approval time and expiry. Policy maps trusted approver IDs to
fixed public-key bytes; a mutated approval or signature from another key is
denied before downstream effects; the composed negative test observes no
Gateway, Broker, provider or journal effect for an altered signed approval.
Unknown unsigned fields are also rejected. The existing typed-digest CLI's mock-only
path signs with an ephemeral synthetic key; test-only private material is
deterministic and is not used by runtime. This proves signature/key possession
for the supplied public key, not the human identity behind it or safe key
enrollment, custody, revocation, independent policy trust, or production
approval. `cryptography==50.0.2` is the declared Ed25519 implementation.
Focused suite: 229 tests (1 skipped); full offline suite: 978 tests (969 passed,
9 skipped); `git diff --check` clean. No credential or external service was used.

Batch EN / EXP-548 replayed the exact persisted EXP-520 live Worker output
without constructing a Worker channel or reading a credential. Read-only source
stage digest `sha256:a68580b0acd241cb346f7fd225c9632c166ebedfe985d1fa656cd88d966198d7`
contained the pinned repository/commit and one verified `backend/routes.py`
candidate. One fresh anonymous readiness request met the `>=25` threshold;
the bounded public snapshot again matched commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, tree
`2007066217aadafd9887fb3e3069220333b4fddb`, 23 blobs and full content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
The exact target image
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`
and verifier image
`sha256:f343041a8b7353341bc933f9bcff48a5415f585e8e642b4d22c1d0d35e22705a`
were present as `linux/arm64`; verifier code identity remained
`sha256:b1336165e906e8bd2801ff61bcc6a3740c683639416f80caea40e3e8d22825a5`.
The stored candidate was rehydrated unchanged, the target ran network-none, the
HTTP/DB probe and exact Docker verifier passed, and new SQLite stage readback and
preview bound staged digest
`sha256:d9dab36eb53279b5707d05ddd3b73052a912366d613756cb2858b29d9eccf734`,
verified contents digest
`sha256:8a0cd5df060c82eeea111337fccf527d26f0a24618bc3b5dace19cb9ff7a982e`,
verification digest
`sha256:1930fd5f5224ceda7313053d06288db735ed1fa85700a361b1f686f340ce2e23` and
artifact digest
`sha256:c60036bd6740205a1e72c6c0e66f05756f1c13a176095d5e09eb8080d8687e8c`.
The new stage database is in the task temp directory
`/var/folders/ck/vsbcwwq12jb6y77nhglk61qc0000gn/T/agent00x-exp548-stage-jfcd5so9/stage.sqlite3`.
This is a deterministic replay, not another live model call; Docker is still
same-host evidence. At EXP-548 time no commit-signature metadata had been
queried; EXP-606 later recorded GitHub API `verified=true, reason=valid` for
this pinned commit. That is GitHub's assertion, not independent local
signature verification or proof of authorship.
Focused suite: 65 tests (3 skipped); full suite: 978 tests (969 passed, 9
skipped); `git diff --check` clean. No approval, credential, model call, provider
write, branch, PR, commit, push or deployment occurred. R2/MVP remain OPEN.

Batch EO / EXP-549 adds `scripts/replay_staged_candidate.py`, a fixed-target
operator CLI that accepts only a read-only source-stage database/digest and a
new output database path. It rehydrates only the stage's validated
`verified_contents`, makes one readiness check and bounded pinned public
snapshot intake, runs the shared executor with fixed target/verifier/test
contracts, commits output with an exclusive hard link (no overwrite), reopens
the output read-only and emits digest-only evidence. It has no Worker channel,
credential-source, approval, publication or GitHub App imports; the generic
already-read snapshot composition was moved to
`app_contracts.remote_snapshot_pipeline` and remains re-exported by `worker_cli`.
The exact pin/test/image configuration lives in the data-only
`app_contracts.brainbooster_target_profile` module. Offline fake tests prove
source DB immutability, distinct absent output, stored-content-only proposal,
early denial before sandbox on invalid stage/readiness/pin, and a clean import
without LLM, credential or publication adapters. The new CLI itself was not run
against external services in this batch. Focused suite: 76 tests (4 skipped);
full offline suite: 985 tests (976 passed, 9 skipped); `git diff --check` clean.
No credential or external service was used. R2/MVP remain OPEN.

Batch EP / EXP-550 introduces `RepositoryTargetBinding` between the verified
source slug and GitHub App's installation-scoped repository identity. The
binding is derived from validated target configuration; seed and publication
intent retain both identities, so the intent digest changes on either
substitution. The controlled-publication gate validates the stage's original
slug before policy/broker processing and supplies a copy with the provider ID
only to the GitHub App verified-file adapter. Focused suite: 246 tests passed;
full offline suite: 992 tests (983 passed, 9 skipped); `git diff --check` clean.
Synthetic configuration only; no credential, network, model, Docker, approval
or provider write was used. The production runtime does not yet construct and
carry this binding through an authenticated approval and real publication.
R2/MVP remain OPEN.

Batch FM / EXP-573 adds `scripts/publish_signed_stage_github.py` for one
fixed-target, exact-stage publication path. It reloads the durable stage and
signed approval, displays a bounded patch preview, requires a fresh interactive
`PUBLISH <digest>` confirmation, then composes the existing deterministic
Policy, slow Gateway, single-use GitHub App Broker/channel and persistent
digest-only journal. Fake-only tests prove mismatch/invalid approval/policy
denial stop before provider effects, the success receipt is bound to the
approved digest and target, and a lost PR response does not trigger a write
retry. The sanitized result marks `identity_authenticated=false` and confirms
the PR receipt without claiming that this invocation necessarily performed a
provider write. Focused suite: 5 tests passed; full offline suite: 1056 tests
(1047 passed, 9 skipped); `git diff --check` clean. The command has not been run:
no credential, network, GitHub write, branch, PR, Docker, SSH or deployment was
used. A live publication still requires a separate exact task card and fresh
confirmation; R2/MVP remain OPEN.

Batch EQ / EXP-551 exercises the bound identity through the complete local fake
approval→policy→gateway→broker→GitHub App file/PR adapter→SQLite journal chain.
The signed intent digest contains both the source slug and provider ID; the
source staged record remains unchanged, while the adapter sees only the
provider-scoped ID. Simulated applied PUT/PR response loss is reconciled by
read-only checks into one exact typed receipt, with no duplicate PR POST. A
wrong provider ID stops before policy, stage loading, broker, transport or
journal; target-slug mismatch stops at binding. Focused suite: 181 tests passed;
full offline suite: 994 tests (985 passed, 9 skipped); `git diff --check` clean.
This is fake/local evidence only: no credentials, network, model, Docker,
authenticated human approval, production runtime or real PR. R2/MVP remain OPEN.

Batch ER / EXP-552 adds `scripts/create_approval_request.py`, a bounded local
read-only export of one exact verified SQLite stage. It validates the fixed
source-slug/provider-ID binding and explicit branch/base, approver, policy and
approval ID, then emits the full patch review, digest-bound intent and exact
canonical Ed25519 signing bytes. The result is explicitly unsigned with no
approval created or provider write; the CLI imports no credential source,
broker, network, model or provider adapter and does not alter the stage DB.
Tests verify deterministic bytes, sensitivity to mutation of every intent and
signed approval field, malformed input rejection, target mismatch rejection,
and read-only CLI behavior. Focused suite: 19 tests passed; full offline suite:
1000 tests (991 passed, 9 skipped); `git diff --check` clean. This is a review
artifact only: actual human signing, trusted signer enrollment, production
runtime composition and publication remain unimplemented/unverified. No
credential or external service was used; R2/MVP remain OPEN.

Batch ES / EXP-553 closes the local export→signer→policy contract gap with an
offline regression: a freshly generated ephemeral Ed25519 test key signs the
exact bytes emitted by EXP-552, and the existing `DeterministicPolicy` accepts
the approval only for the matching staged change, intent and allowlisted public
key. Mutating the intent without a corresponding signature is denied on the
approved-intent digest. The test stops at the policy decision and does not run
Gateway, Broker, journal or provider code. Focused suite: 40 tests passed; full
offline suite: 1001 tests (992 passed, 9 skipped); `git diff --check` clean.
This proves format/policy interoperability only; the signer is synthetic, so
human identity, key enrollment, production runtime and publication remain open.
No credential or external service was used; R2/MVP remain OPEN.

Batch EV / EXP-556 makes the documented approver allowlist an explicit required
`PolicyConfig.allowed_approver_ids` set, separately from the public-key mapping.
Every allowlisted ID must have a configured 32-byte public key; a configured
key whose ID is not allowlisted cannot authorize a decision. All runtime and
test policy construction sites now supply the set. Regression tests confirm
that an otherwise valid, correctly signed but unlisted approver is denied
before Gateway, Broker, journal or mock endpoint effects. Focused suite: 108
tests passed; full offline suite: 1004 tests (995 passed, 9 skipped);
`git diff --check` clean. This is an explicit policy allowlist, not proof of
human identity or key enrollment; R2/MVP remain OPEN.

Batch ET / EXP-554 carries the externally formatted approval request through
the complete local controlled-mock path. A fresh ephemeral Ed25519 test key
signs the exported canonical bytes; the dual-identity stage/intent then passes
the actual approval and deterministic policy gates, a slow-allow test Gateway,
a single-use in-memory Broker and SQLite journal, producing exactly one
`MockGitHubEndpoint` receipt with the same provider ID, branch/base, stage
digest and idempotency key. A corrupted signature is denied before Gateway,
Broker or mock endpoint effects. Focused suite: 73 tests passed; full offline
suite: 1002 tests (993 passed, 9 skipped); `git diff --check` clean. No GitHub
App adapter, real credential, network, model, Docker, branch or PR was used.
The local chain is still not production runtime wiring; real human signer
enrollment/approval, independent verifier trust and real-provider publication
remain OPEN.

Batch DK / EXP-520 (R2 execution batch 73/73) completed one user-authorized live
DeepSeek proposal against `SoldatovAlexander/brainbooster_full_v11`, exact commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, tree
`2007066217aadafd9887fb3e3069220333b4fddb` and content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
One fresh anonymous readiness request passed; the model proposal changed only
`backend/routes.py`. Read-only preview confirmed all five numeric fields are
parsed before the insert and invalid/non-finite values are rejected; the pinned
HTTP/DB verifier returned PASS. Exact stage digest is
`sha256:a68580b0acd241cb346f7fd225c9632c166ebedfe985d1fa656cd88d966198d7`,
verification digest is
`sha256:07ca43adb230f9bd52cd8d9343440aaa8056053d80220b2dbc9497ac37367512`.
The user authorized one-time lazy in-memory use of `AI_PROCESS_API` from the
AI Process Architect project and set a USD 1 ceiling. The credential value was
not emitted or copied into Agent00X. One live call only; no retry, approval or
provider write. The USD 1 ceiling is user-set, not an account-enforced cap;
at EXP-520 time commit-signature metadata had not been checked. EXP-606 later
recorded GitHub's `verified=true, reason=valid` assertion for the pinned commit;
independent local verification/authorship and transport provenance remain open.
The same-host verifier is not independently trusted. Accepted as a live Worker-to-
stage experiment, not as R2 exit evidence.

### R2 exit matrix (remote metadata rechecked 2026-10-08; local suite updated 2026-10-08)

| Gate | What current evidence demonstrates | Evidence still required for R2 exit |
|---|---|---|
| Fixed remote repository snapshot | EXP-594 made one fresh anonymous header-only preflight (HTTP 200, 60 remaining), then one integrated REST intake: exactly 25 GETs, fixed commit/tree/content digest, 23/23 verified blobs (240290 bytes), plus matching depth-1 raw commit proof. EXP-606 records GitHub API `verification.verified=true`, `reason=valid`; EXP-614 replayed through raw-commit-gated intake with the same 23-file snapshot and matching raw object. Later EXP-784 made one anonymous codeload GET and reproduced the pinned 23-file content digest; EXP-788 completed the codeload snapshot intake through a pinned Worker/verifier, exact stage save/readback and local mock receipt. No file names or contents were emitted. | GitHub's verification assertion is not independent local signature/key verification or proof of authorship; both transports rely on GitHub/TLS. Codeload archive claims do not include a raw commit object. The exact request count for EXP-614 was not emitted. Provider writes and credentials remain outside snapshot evidence. |
| Worker change | Batch DK / EXP-520 made one expressly authorized live DeepSeek call against the exact pinned public snapshot and produced the `backend/routes.py` proposal/stage. EXP-548 replayed the stored output unchanged through pinned target/verifier; EXP-614 repeated after raw-commit proof enforcement without another model call. EXP-781/788 also exercised one synthetic `ContainerProposalWorker` proposal through exact pinned snapshot and verifier paths to local mock receipt, with no live model request. | The historical live call does not establish a verified account-level spend cap or host trust for the in-process credential callback. Recent composed evidence uses a synthetic Worker, not a new model call. Independent verifier trust, snapshot authorship and real publication remain open. |
| Bounded execution and test | Batch BA directly executed the exact pinned route blob; Batch BE exercised selected pinned modules with Uvicorn loopback HTTP in exact Python 3.11.16 image, `container-network-none`, `network_isolated=true`: malformed integer produced 500 / zero rows; valid produced 200 / one exact row. Batch BF tested the fixed patch in only the writable container copy: malformed values and overflow returned HTTP 422 / zero writes; valid remained 200 / one row. EXP-548/614 replayed the stored Worker candidate against the full 23-blob snapshot; EXP-781/788 repeated pinned target test, container verifier, exact stage save/readback and local mock receipt. | These runs establish bounded local/container behavior, not a separately governed verifier host or authenticated snapshot authorship; pin full app runtime/dependencies and production recovery. |
| Independent verification | Verifier input/result cross a bounded child-process JSON boundary and re-run the test. EXP-510 also completed a synthetic stage through the actual pinned Docker verifier image. EXP-609 adds a fixed one-shot stdin/stdout service CLI bound to `BRAINBOOSTER_VERIFIER_PROFILE`; it accepts no profile/image/test/endpoint overrides and lazily reads only `AGENT_VERIFIER_SIGNING_SEED` through `ProcessEnvironmentCredentialSource` at the final signing boundary. EXP-680—683 define and compose signed enrollment, exact HTTPS endpoint/host binding and a separate signed OOB host decision, but the recorded integration used a fake HTTPS connection and remained audit-only. EXP-791 carries synthetic signed verifier provenance through codeload-origin execution, approval request reconstruction and enrolled local-mock receipt. EXP-792 adds a real loopback HTTP exchange with the verifier service in a distinct same-host child process and verifies the signature; it still asserts `independent_host_trust_established=false`. | No separately governed verifier host, real authority key, remote key custody, authenticated host identity or OOB-reviewed host-separation evidence is established. EXP-791 and EXP-792 use synthetic verifier/authority fixtures and do not promote trust. Same-host process/container separation is insufficient; real endpoint deployment and review of host evidence are still required before any trust promotion. |
| Durable stage and human approval | Canonical stage artifacts are saved/reopened through SQLite and exact-digest readback precedes VERIFIED. EXP-548/614 stages and the EXP-624 byte-identical copy pass read-only preview. EXP-789 exercised request and signed-mock CLIs against the retained EXP-788 stage, but review found that stage lacked signed verifier proof; EXP-790 now rejects it before emitting a request and leaves its DB unchanged. EXP-791 separately proves a synthetic codeload stage with caller-pinned signed verifier provenance can reconstruct an approval request and reach only an enrolled in-memory mock receipt, with `identity_authenticated=false` and `external_write=false`. | All approval signs/enrollments used synthetic keys; they do not authenticate a human or establish real authority governance. The retained EXP-788 stage remains ineligible because verifier provenance is absent. No OOB signer identity or production durability/recovery proof exists. |
| Controlled Pull Request publication and recovery | Fake-only GitHub App composition binds verified manifest to seed, journals before branch/file effects, and covers response-loss recovery without duplicate POST (EXP-537—543, 545, 550/551). EXP-573 adds a fixed-target live-capable CLI but tests only fake transports/synthetic approvals. EXP-666/667 and EXP-687/791 reach only local enrolled-mock receipts; receipts explicitly report `external_write=false`. | No real PR receipt exists. All recent continuations terminate at a synthetic local mock, not GitHub. Missing: real/OOB signer enrollment, fresh exact authorization for provider use, approved provider identity, real PR evidence, independently trusted verifier, and durable recovery demonstrated against the approved provider without blind retry. No multi-file atomicity claim. |

EXP-577 performed one anonymous metadata-only GET for the fixed public source on
2026-10-08. GitHub reported numeric repository ID `1040264611`, default branch
`master`, `visibility=public` and `archived=false`. This confirms source-repository
metadata only; it does not identify an App installation, grant permissions or
change the pinned commit/tree.

**R2 decision: OPEN.** At the checkpoint before DI—DL, the execution continuation
had reached batch 70: 63 accepted and 7 blocked (CN, CO, CS, CT, CW, CZ and CX).
CX / EXP-507 stopped
before readiness after an initial image preflight miss; it was not retried.
DC / EXP-512 and DD / EXP-513 then restored and confirmed the exact image in
the active `desktop-linux` context. DE / EXP-514 completed one fresh readiness
gate and one exact-pin synthetic pipeline attempt: target 422/no-write and
200/one-write, Docker verifier PASS, exact-digest stage/readback, preview and
local mock receipt. Batch DF / EXP-515 added a `build_deepseek_remote_execution_profile`
helper that assembles the bounded channel/Worker from an injected credential
source without reading it during profile construction. DG / EXP-516 adds the
importable `run_remote_snapshot_with_runtime` entrypoint to assemble the fixed
Docker sandbox, configured verifier and context-managed SQLite stage, still
without secret/config lookup. DH / EXP-517 requires a fresh one-use permit from
the TLS-verified header-only readiness result, bound to exact task/pin and an
explicit Control Plane provider-call approval, before any remote snapshot
intake. Offline tests prove no body read/retry, TTL/threshold checks and atomic
single use; no live readiness request was made. Targeted CLI/transport tests:
42 passed. DI / EXP-518 now requires the runtime caller to pass an explicit
digest-pinned execution image (immutable `sha256:` image ID or `@sha256`
reference); invalid or mutable references fail before Docker adapter creation,
SQLite opening, permit consumption, credential lookup or GitHub access. Exact
image forwarding and fail-closed behavior have 35 targeted tests. Full offline
suite: 943 tests, 936 passed, 7 skipped. No Docker image was built or run, and
no readiness or Worker call occurred in DI. DJ / EXP-519 then built a dependency-only
Python 3.11.16 arm64 target image with immutable ID
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812` from
the exact 15 EXP-462 wheels. The digest-pinned base was pulled once when absent;
the multi-stage build used `--network=none`, and read-only non-root import smoke
confirmed FastAPI 0.142.2, Uvicorn 0.54.0 and multipart 0.0.32. Target source,
wheelhouse and DB are absent from the final image. Full offline suite remains
943 tests, 936 passed, 7 skipped. No target app or verifier run, readiness or
Worker call occurred. DL / EXP-521 then built a matching Python 3.11.16
`linux/arm64` verifier image from only the exact EXP-519 image's installed
dependencies and the accepted lock. Two separate builds from equivalent exact
contexts with `SOURCE_DATE_EPOCH=0` produced the same image ID
`sha256:f343041a8b7353341bc933f9bcff48a5415f585e8e642b4d22c1d0d35e22705a`
(`linux/arm64`); verifier code digest
`sha256:b1336165e906e8bd2801ff61bcc6a3740c683639416f80caea40e3e8d22825a5`.
The offline builds and one network-none, read-only, non-root import smoke passed
for Python 3.11.16 and FastAPI/Uvicorn/multipart `0.142.2/0.54.0/0.0.32`; target
source, DB and wheelhouse paths were absent. Full offline suite: 944 tests, 937
passed, 7 skipped. No target app/test, snapshot, readiness or Worker run
occurred. DM / EXP-522 then verified the fixed Uvicorn/SQLite command on the
exact four-file source slice: five malformed fields and one overflow returned
HTTP 422/zero rows, then valid input returned 200/one exact row. The fixed argv
and 30-second test / 60-second verifier timeout are recorded in the opt-in
pipeline test; full suite after EXP-522: 945 tests, 938 passed, 7 skipped.
This is not full-snapshot execution evidence. The numbered continuation was at
R2 execution batch 97: 86 accepted and 10 historically blocked, with one DRAFT
(DK / EXP-520). EXP-520 is now accepted after one authorized live Worker proposal
and successful pinned HTTP/DB verification; this does not close independent
verifier or trust gates. DN / EXP-523 passed the
one-shot anonymous readiness gate
(HTTP 200 / 60 remaining) and validated the exact 23-blob snapshot, but the
allowlisted target test command returned nonzero; `prepare_change` exposed only
`verification failed; staged change was not created`. The independent
container verifier was not reached. No stage, preview, approval or mock receipt
was produced; no retry occurred. The underlying HTTP/DB probe result is
unavailable, so no more specific failure is claimed. Batch DO / EXP-524 then
added a finite allowlist of fixed test-failure
markers; unrecognized child output remains hidden. Forty focused tests and the
embedded-probe syntax check passed; full offline suite: 947 tests, 940 passed,
7 skipped. This diagnostic change is not a replay and does not establish the
EXP-523 failure cause. DP / EXP-525 then fetched and digest-validated the same
full snapshot after a fresh readiness HTTP 200 / 35, but the exact Python base
image referenced by the test was absent. Docker daemon 28.3.3 was active; no
target command or verifier ran. DQ / EXP-526 anonymously fetched the pinned
Python base image into the Docker cache and verified image ID
`sha256:8b29ec24b5f3c929a79b55772b95c93311b7133f1cf7fa0a6141ef621f8e3c57`.
The base image is distinct from the prepared target runtime image
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`;
DR / EXP-527 corrected the pipeline test to use that exact target runtime;
network-none import smoke confirmed pinned dependencies, targeted contract
tests passed, and full offline suite: 948 tests, 941 passed, 7 skipped. No new
full-pipeline attempt has occurred; EXP-528's fresh readiness check reported
HTTP 200 / 10 remaining, reset `2026-10-07T14:46:32Z`, so no snapshot request
was made. DU / EXP-530 then exercised the actual CLI `main` and remote
composition with a synthetic 23-blob snapshot, one fake Worker proposal,
network-none prepared target sandbox, exact Docker verifier and temporary
SQLite stage. The single opt-in run passed in 2.764s with exact stage digest
readback and sanitized CLI digest evidence; full suite: 949 tests, 941 passed,
8 skipped. No GitHub request was made. This remains synthetic evidence. DV /
EXP-531 then exercised the real `DeepSeekProposalWorker` and bounded
`DeepSeekHTTPChannel` inside the synthetic CLI composition using an in-memory
fake connection and only a synthetic key-shaped marker. One fixed-host POST and
one credential callback were observed; the marker stayed out of request JSON,
candidate, CLI evidence and stdout/stderr. The proposal passed the same
network-none target sandbox, Docker verifier and exact-readback SQLite stage.
Full suite: 950 tests, 941 passed, 9 skipped. No real TLS handshake, socket,
model, credential or provider was used. This remains synthetic protocol/runtime
evidence. DW / EXP-532 then passed the exact CLI-produced `StagedArtifact`
through wrong-digest rejection and exact-digest `run_local_mock_publication`;
the mock PR receipt bound the same digest/repository/`agent/` branch. This is
local in-memory approval/policy/gateway/broker/journal evidence only. The CLI
itself still reports approval not created and publication not attempted; no
external write occurred. It does not establish authenticated human approval,
real PR publication, or production recovery. DT / EXP-529 then passed its
post-reset gate once (HTTP 200 / 60 remaining) and ran the exact pinned 23-blob
snapshot pipeline exactly once. The synthetic fake Worker candidate passed the
network-none target check (422/no row for malformed inputs; 200/one exact row
for valid input), pinned-identity Docker verifier, exact-digest SQLite stage/readback,
preview and local mock receipt. The test passed in 18.946s; full offline suite:
950 tests, 941 passed, 9 skipped; `git diff --check` passed. The suite emitted
SQLite unclosed-connection ResourceWarnings but exited successfully. No real
credential/model/provider or external write was used. This closes the full
snapshot-to-mock-stage experiment only: it is not live Worker evidence,
independent verifier trust, authenticated approval, production recovery or real
PR publication. DX / EXP-533 then fixed the SQLite connection leaks in
observation-store test fixtures: the focused tracemalloc/ResourceWarning run
passed 58 tests without warnings, and the 950-test offline suite again passed
(941 passed, 9 skipped) without ResourceWarnings; `git diff --check` passed.
This repairs test-resource hygiene only, not production durability. DY / EXP-534
then added a separate SQLite local typed-digest confirmation record. The exact
stage/intent/repository/branch binding is saved and read back before the local
mock gate, then linked to only the mock receipt ID. Its explicit flags are
`authenticated=false` and `external_write=false`. Focused tests: 7 passed with
ResourceWarning treated as error; full suite: 952 tests, 943 passed, 9 skipped;
`git diff --check` passed. This remains local operator-confirmation evidence,
not authenticated production approval or recoverable real publication. EXP-520
still needs a user-set spend ceiling and operator-owned credential injection.
The history begins with AO—BI (21),
This is image preparation, not target verification, live Worker evidence,
independently trusted verifier evidence, or production approval/publication. The
BK (22nd), BL (23rd), BM (24th), BN (25th), BO (26th) and BP (27th); BJ is a separate docs-only checkpoint. AU has
EXP-441 accepted, EXP-440 historically blocked on the absent image, and three drafts; AV is
5/5 accepted; Batch AW has EXP-450—454 accepted; AX has EXP-455 accepted; AY has
EXP-456 accepted; AZ has EXP-457 historically blocked; BA has EXP-458 accepted.
BB—BD contain the pre-run blockers EXP-459—461; BE has EXP-462 accepted; BF has
EXP-463 accepted as an ephemeral Control Plane patch experiment; BG has EXP-464
accepted as fake-only HTTP transport; BH has EXP-465 accepted as synthetic durable
stage/preview/mock-approval integration; BI has EXP-466 blocked before snapshot
intake on one sanitized GitHub read failure; BK has EXP-468 accepted with fake-only
request/body-read deadline interruption; BL has EXP-469 accepted with loopback-only
stdlib socket interruption tests; BM has EXP-470 accepted with loopback HTTPS
header/body interruption tests; BN has EXP-471 accepted with stalled-handshake
cancellation; BO has EXP-472 accepted with the local upload test explicitly
skipped because this OS buffered the full bounded request; BP has EXP-473
accepted for one local synthetic Worker/verified-HTTPS proposal round-trip; BQ
has EXP-474 accepted for the portable single-credential source interface with
synthetic-only conformance; BR has EXP-475 for status-only sanitized snapshot
diagnostics; BS has EXP-476 for its status-only CLI failure code; BT has EXP-477
positive anonymous API readiness evidence; BU's one fresh-state attempt
verified the full snapshot pin/content digest but stopped before execution on a
stale/double-prefixed candidate digest check; BV corrected the candidate digest
and verified the local suite, but its single preflight result was unavailable in
the tool output, so no pipeline execution occurred; BW showed 200/35, BX's one
pipeline invocation stopped before target code because the command argument had
a trailing newline, and BY then showed only 10 requests remaining (below the
25 threshold). The command whitespace is corrected and the offline suite passes,
but no pipeline retry is authorized until after rate reset and a fresh positive
readiness check. BZ has EXP-483 accepted: one fake-only provider attempt per
channel instance, including concurrent callers; this is not an account spend
cap. CB has EXP-485 accepted with an offline command-shape regression guarding
EXP-481's trailing-newline failure; CC has EXP-486 accepted and proves the
snapshot workspace is removed when that request validation fails. The Docker
path still requires a separate positive rate-limit gate. CD has EXP-487 accepted:
the `--remote-snapshot-execute` mode requires an injected immutable runtime
profile, pins the full fixed snapshot, maps only declared context, and emits
digest/verdict metadata without source or prompt text. Batch DF adds
`build_deepseek_remote_execution_profile` to assemble the fixed DeepSeek channel
and Worker around an injected credential source; Batch DG adds an importable
runtime entrypoint for explicit Docker verifier/sandbox and SQLite stage wiring.
Neither helper reads a key or was used for a live API/provider call. Operational
runtime validation and a safe real credential source remain open.
Direct module invocation without that injected profile returns exit 2 with
`remote-execution-runtime-unavailable` before network access; the no-argument
module invocation returns exit 0 with `evidence_origin=local_test` for the
synthetic demo only. Neither result is remote Worker evidence.
At that checkpoint the suite ran 917 tests: 913 passed, 4 skipped (3 opt-in Docker, 1 local
upload-backpressure).
Batch CE's single anonymous rate-limit check returned HTTP 200 / 60 after reset
and authorized only a separate pipeline card.
CF / EXP-489 then fetched the exact 23-blob pin and matched the fixed candidate
digest, but stopped before Worker invocation with `execution snapshot: claim
mismatch`; the Docker sandbox is closed by the executor's `finally` path and no
target test, verifier, stage, preview or receipt ran. EXP-490 in CG is accepted
as a local-only fix: `_make_tree_read_only` now preserves the executable bit
(`0500`) while making ordinary files read-only (`0400`), and a synthetic
copied-tree test proves the verifier digest remains unchanged. No Docker daemon
was used. At that checkpoint the offline suite was 917 tests, 913 passed and 4 skipped.
CH / EXP-491 returned HTTP 200 / 60; CI / EXP-492 then stopped at the same
generic executor snapshot-claim mismatch before Worker invocation, despite
EXP-490's local mode-preservation fix. No target test, verifier, stage, preview
or receipt ran. The traceback does not distinguish among bounded-read digest,
mode, or size-limit failures. CJ / EXP-493 is accepted: a synthetic regular+
executable snapshot reaches the Worker and verifier through actual claim/replay
checks using a fake-launched Docker backend, with both temporary sandboxes
cleaned; this does not prove the exact remote tree. CK / EXP-494 is a local
fake-transport task because `--remote-snapshot-metadata` currently calls the
contents reader and downloads blobs; it will make that CLI path truly two-GET
metadata-only before any separate bounded public diagnostic is considered.
CK / EXP-494 is accepted on fake transports: exactly two GETs, no blob endpoint,
and truthful metadata-only output. CL / EXP-495 is accepted: readiness plus
two-request metadata-only diagnostics showed one 220064-byte blob and aggregate
240290 bytes without fetching blob contents. This strongly explains, but does
not content-digest prove, the earlier pre-Worker failure: executor/verifier
per-file cap was 100000 while canonical snapshot intake allowed 262144.
CM / EXP-496 aligned the verifier per-file bound to the canonical
`MAX_SNAPSHOT_FILE_BYTES` and added synthetic executor/verifier boundary tests;
220064 bytes pass, 262145 bytes fail, and aggregate >512000 remains rejected.
At the EXP-496 checkpoint the full offline suite had 927 tests: 921 passed and
6 skipped.
EXP-497 used one fresh readiness check (HTTP 200 / remaining 33) and one pipeline
attempt. Exact snapshot/candidate digest and executor claim/replay passed, and
target execution produced its output digest; the verifier raised an exception,
reported only as `verifier-failed`. No verifier result, durable stage
save/readback, preview or receipt was produced. No retry is authorized. The
Batch CO then passed the exact synthetic request through the local verifier
entrypoint (942-byte response), but one real `network=none` verifier-container
call exited nonzero and was safely normalized as `verifier process: child exit
failed`. This means request shape alone does not explain the error. CP / EXP-499
now distinguishes only the exact fixed entrypoint rejection marker from a
generic child exit, without logging raw streams; this is diagnostic only and
does not identify the specific EXP-497 cause. CQ / EXP-500 added allowlisted
container-side validation categories and exact parent classification; a rebuilt
image's one synthetic verifier call still returned generic `child exit failed`,
so no known validation guard was identified. CR / EXP-501 exposed only a
validated numeric exit status; the one offline synthetic large-request call
returned status 1. CS / EXP-502 and CT / EXP-503 did not retain startup evidence
because of a harness ordering error and an unexpected status. CU / EXP-504
safely classified one fixed malformed-input probe as `python-import` (status 1,
stdout 0 bytes, stderr 547 bytes; raw stream withheld). EXP-505 then moved
remote imports to `TYPE_CHECKING` and lazy runtime branches only for remote
requests. A blocked-import subprocess test passed, the offline image rebuilt,
and its one real verifier call accepted a 220064-byte synthetic snapshot with a
bound PASS. EXP-508 / CY then started the credential-source latency budget
before invoking the callback and proved a finite late return fails before HTTP
connection construction; a late exception is also sanitized as timeout (25
targeted tests, 1 skipped). The synchronous
callback remains non-cancellable if it never returns; DNS cancellation remains
open. EXP-509 / CZ then used one opt-in synthetic composition with the actual
Docker verifier; its verifier returned bound PASS but stage persistence failed.
The exact Docker image/code verifier identity was allowed by executor validation
but rejected by `PublicationSeed`'s 128-character-only pattern (actual identity:
161 characters). EXP-510 / DA aligned the seed validator to accept only that
exact bounded identity, preserving rejection of arbitrary long labels. One new
opt-in retry reached VERIFIED, exact SQLite save/readback, preview and local
mock receipt, all bound to one digest. This used `LocalProcessSandboxBackend`
and a synthetic calculator snapshot; it is not exact-target Docker execution or
independent verifier trust. Current full offline suite is 931 tests, 924 passed,
7 skipped. CW / EXP-506
was stopped before snapshot intake: its single header-only readiness GET
returned HTTP 200 / remaining 8, below the card's threshold of 25. No pipeline
invocation or retry occurred. CX / EXP-507 was stopped after its local preflight
returned `No such image`, before any GitHub request; it remains blocked and was
not retried. EXP-511/512 pulled the exact image with isolated empty Docker
configs, and EXP-513 confirmed it in active context `desktop-linux`. EXP-514
used one new readiness GET (HTTP 200 / remaining 60) and one pipeline test.
The fixed candidate is not live Worker evidence: it is a
fixed Control Plane candidate, not live DeepSeek inference. No live provider or
publication gate is authorized. EXP-489, EXP-492, EXP-497, EXP-498, EXP-502
and EXP-503 remain BLOCKED.
Neither test count nor batch acceptance
substitutes for evidence in the right-hand column. Exit still requires one
reproducible selected-repository change through all six gates, with sanitized
and recoverable evidence and no credential disclosure.

## 2. Каноническая шкала доказательств

| Уровень | Значение |
|---|---|
| Реализовано и unit-tested | Код и автоматические тесты в этом репозитории; это не сквозное доказательство границы доверия |
| Spike | Узкая демонстрация конкретной интеграции или свойства; она не распространяется на соседние компоненты |
| Спроектировано | Решение принято в документах, но нет схем/кода/проверок либо они неполны |
| Не проверено | Свойство не может считаться установленным |

## 3. Что реализовано

| Область | Статус | Точная граница утверждения |
|---|---|---|
| Базовые контракты | Реализовано и unit-tested | 16 JSON Schema, fixtures, digest chain, subset validator и state machine |
| Local reference preparation | Реализовано и unit-tested | Ephemeral workspace, ограниченные изменения, patch, allowlisted tests, evidence, verification и staged change на fixture snapshot |
| Controlled mock publication и reconciliation | Реализовано и unit-tested локально | Связанный local harness проверяет свежие approval/policy/Gateway/Broker gates, digest-only SQLite journal, mock publication, matching recovery и fail-closed `reconciliation_required`; это не real-provider chain, production durability или multi-process isolation |
| Policy/Gateway/Broker контракты | Реализовано и unit-tested | Детерминированные классы и негативные сценарии; это не связанный production Authority Plane |
| Docker verifier profile | Локальный verifier image собран; все карточки Batch AM приняты, включая раскрытое исключение EXP-404 | Один принятый bounded request EXP-403 проверил UID 65532, read-only root, отсутствие Docker socket и restricted child environment; EXP-404 test report содержит два live synthetic runs вместо разрешённого одного. Kernel/daemon boundary and protection from privileged host compromise не attested |
| GitHub App | Spike | App создал тестовые branch/PR; это не доказывает полную авторизацию, atomic publication или recovery |
| Наблюдатель и обучение | Контракты, in-memory store и локальный SQLite journal реализованы и unit-tested | ObservationEvent/Checkpoint и локальная persistence/reopen/pre-dispatch failure semantics; collector, отчёты, access control, учебные ветки и production storage guarantees отсутствуют |
| Local executor shell и pinned replay | Реализовано и unit-tested локально | Bounded request/proposal, явные optional task instruction и caller-selected text context (лимиты и allowlist до вызова Worker), локальный exact commit/tree export, prepared-content digest binding и второй allowlisted replay в отдельной sandbox-сессии для pinned request; injected Worker/backend/verifier и process sandbox development fallback, не remote provenance и не independently trusted production verification |
| LLM Worker и субагенты | Fake adapters, loopback verified HTTPS composition, one live Worker-to-stage proposal (EXP-520) | Есть bounded input/output contract и unit-tested OpenAI Responses/DeepSeek Chat Completions adapters; DeepSeek HTTP имеет fixed host/path, TLS, byte bounds, injected key callback и same-process watchdog с socket shutdown/close. Fake tests, loopback stdlib HTTP и verified HTTPS с ephemeral сертификатом подтверждают interruption активных request/header/body reads и stalled TLS handshake на этом host; BP соединяет Worker с локальным HTTPS channel на synthetic response. EXP-520 подтвердил один live DeepSeek proposal для exact pinned public snapshot: only `backend/routes.py`, bounded HTTP/DB verifier PASS и локальный digest-bound stage. Credential source использован по разовому разрешению только в памяти, без копирования в Agent00X. EXP-508 включает конечное время callback в budget и не начинает HTTP при позднем возврате, но синхронный зависший callback не отменяется; DNS cancellation и process isolation не доказаны. Loopback не позволил воспроизвести send backpressure для максимального request body, поэтому узкий тест пропущен с явной причиной; upload interruption не доказано. Нет credential trust isolation, verified provider-level spend cap, independent verifier, authenticated provenance/approval, production durability или publication evidence. |
| Durable staged artifact | Validated canonical bundle, local SQLite store, exact-readback executor sink, read-only preview and typed-digest mock CLI, Batch AW EXP-450—454 | Bundle binds full remote snapshot seed, staged metadata digest, exact patch, source Git blob IDs, proposed contents and verifier evidence; executor withholds VERIFIED until save/load matches, and only an in-memory mock approval may follow. Temporary local SQLite evidence only; authenticated approval and production at-rest/crash guarantees are absent |

Batch EY / EXP-559 добавляет переданный caller-ом абсолютный SQLite stage
locator в remote execution profile и verified evidence только после успешного
immutable read-only открытия существующей базы, не создавая WAL/SHM sidecar.
Перед началом snapshot intake отклоняются относительный путь, symlink и
directory; synthetic/failure evidence не раскрывает locator. Batch EZ / EXP-560
доказал локальную передачу этого path и staged digest из verified evidence в
read-only approval-request CLI: exact stage reopened, request остаётся unsigned,
а исходные SQLite bytes неизменны; changed digest отклоняется без request.
Batch FA / EXP-561 использует такой request как вход test-only Ed25519 signer и
read-only signed-approval CLI; deterministic policy разрешает подпись на той же
SQLite stage/digest без записи в stage. Output остаётся
`identity_authenticated=false`, `provider_write=false`.
Batch FB / EXP-562 затем передаёт этот же signed approval в существующую local
controlled-publication композицию. Policy повторно проверяет подпись, Gateway
возвращает slow allow, single-use in-memory Broker открывает только mock channel,
а digest-only SQLite journal и один mock receipt завершаются на том же digest.
Это синтетическая локальная композиция, не live provider или production chain.
Это не доказывает retention, backup, cross-host durability, human identity,
production approval/recovery или real-provider publication.

Batch FC / EXP-563 добавляет `scripts/publish_signed_stage_mock.py`: CLI принимает
только существующие stage DB, digest, request, подписанный envelope и явный
operator-supplied trust profile; заново проверяет их exact binding, затем
повторяет Policy → slow Gateway → single-use in-memory Broker → временный
digest-only journal. Receipt сверяется по repository/branch/base/digest и
completed journal; ошибки подписи и policy останавливаются до controlled path.
Результат явно маркирован `destination=in_memory_mock_only`,
`external_write=false`, `identity_authenticated=false` и
`trust_profile_origin=operator_supplied_unverified`. CLI не принимает внешний
endpoint, не меняет входные файлы и не доказывает человеческую identity,
production trust, persistence/recovery или публикацию в GitHub.

Batch FD / EXP-564 добавляет `ProcessEnvironmentCredentialSource`: адаптер
получает только явно переданную mapping и имя одной переменной, ничего не
читает при создании и при вызове обращается только к этому имени. Ошибки и
диагностика не содержат значения. Это не чтение `.env`, не lookup другого
проекта и не защищённое хранилище: внешний менеджер должен сам инжектировать
значение в короткоживущий процесс; изоляция от того же пользователя,
OS-specific vault и ротация не доказаны. Live Worker call не выполнялся.

Batch FE / EXP-565 добавляет `scripts/run_pinned_deepseek_worker.py` для
фиксированного публичного pin → DeepSeek Worker → pinned Docker target/verifier
→ exact-readback SQLite stage path. Скрипт не принимает пользовательский target,
endpoint, model, image, task scope или команды; до публичного readiness запроса
показывает параметры и требует `RUN EXP-566 ONCE`. В тестах network, secret,
Worker, Docker и stage writer подменены, сам operator command не запускался.
Следующий реальный запуск ограничен одной попыткой, но account-level spend cap не
подтверждён; permit и интерактивная фраза не являются enrollment/identity proof.

## 4. Последняя локальная проверка

Команда:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Результат после Batch FI, 2026-10-08: **1046 тестов запущено: 1037 прошли,
9 пропущены**.
Пропуски соответствуют условиям skip в отдельных тестах; три Docker integration
tests требуют `RUN_DOCKER_SANDBOX_TESTS=1`, доступный Docker daemon и образ, а
loopback upload-backpressure test не смог воспроизводимо заблокировать bounded
request на этой ОС. Этот результат подтверждает только указанные
тестами свойства кода на текущей машине.

Проверки покрывают схемы, digests, состояние, sandbox lifecycle, fixtures,
negative contract paths, mock publication recovery, часть Gateway/policy/Broker,
canary scanner и threat corpus. Canary scanner ищет контрольное значение в
переданных ему поверхностях; он не доказывает отсутствие секрета в реальных
process list, crash dump, системной телеметрии или всех логах.

## 5. Исторические GitHub App spikes

На allowlisted репозитории `Agent00X-sandbox` были созданы тестовые branch/PR,
включая PR #1 и #2. Второй spike использовал fixture snapshot, а не snapshot
фактического удалённого репозитория. Эти результаты подтверждают ограниченную
возможность GitHub App получить installation token и выполнить конкретный путь
GitHub API. Они не подтверждают, что опубликованные файлы, approval, policy,
manifest, Broker, journal и recovery образуют единую безопасную цепочку.

Batch AK (EXP-373—382) закрепил один public repository и pinned commit/tree,
получил metadata-only tree inventory и проверил четыре allowlisted blob по Git
OID и содержимому. Selected-content digest независимо пересчитан; явно
`full_snapshot=false`. Отдельный bounded запрос к заведомо отсутствующему
commit вернул HTTP 404 без чтения response body. Исходная серия: 7/10 ACCEPTED;
EXP-375/376/381 остаются исторически BLOCKED на прежних критериях/запусках,
позднейшие карточки закрыли соответствующие tree metadata, allowlist и
decode-workflow вопросы без переписывания прежнего evidence.

Follow-ups EXP-392—394 подтвердили, что Python runtime изначально не загружал
CA по умолчанию, а использование существующего `/etc/ssl/cert.pem` только для
процесса проходит strict TLS verification. Для pinned commit/tree два bounded
GitHub REST representation подтвердили точные pins и сообщили
`verified=false, reason=unsigned`. Это именно заявление GitHub REST API; оно не
является independent signature validation, authorship proof или provenance
вне TLS trust path этого процесса. Ни один ответ не доказывает полный snapshot,
authenticated server provenance или publication chain. EXP-388/389 сохранены
как исторические BLOCKED; принятые follow-ups дают ограниченный результат по их
factual question, без повторов внутри исходных карточек.

## 6. Известные нарушения и открытые границы

1. `build_publish_manifest` сопоставляет workspace с вновь переданным mapping,
   но не фиксирует его как единственное проверенное содержимое. Локальный
   негативный сценарий принял подменённый после проверки файл. Устранено
   локальным fail-closed regression (см. раздел 9); сквозное доказательство
   в составе цепочки отсутствует.
2. `DeterministicPolicy.decide` проверяет approval относительно `staged_change`,
   но возвращает digest из `actuator_request`. Локальный негативный сценарий
   получил `allow` для иного digest. Устранено локальным fail-closed regression
   (см. раздел 9); сквозное доказательство в составе цепочки отсутствует.
3. GitHub publication path не является атомарной транзакцией и нуждается в
   корректной обработке обновления существующих файлов, частичных сбоев и
   reconciliation.
4. Local process backend — development fallback, а Docker smoke/profile не
   доказывают защиту от враждебного кода или полного обхода Gateway.
5. Наблюдение «на любой момент» возможно только в пределах записанной и
   разрешённой к хранению истории; незаписанное содержание нельзя восстановить.

Пункты 1–2 устранены на уровне локальных unit-regression (см. раздел 9).
Batch AA также проверяет composed local path и recovery на mock/in-memory/
ephemeral doubles, но production orchestrator, реальная publication chain и
её external proof отсутствуют. Batch AD проверяет deterministic twin-workspace
preparation и последовательный stale-manifest отказ, но не реальные
параллельные writers и filesystem locking (см. п.3 и открытые границы раздела
9). До проверок пунктов 4–5 нельзя обещать непробиваемую изоляцию или полный
исторический отчёт.

## 7. Текущие этапы

| Этап из плана 1.1 | Статус | Ближайший проверяемый результат |
|---|---|---|
| R0: наблюдение и память | Концепция готова | JSON Schema, валидаторы и негативные тесты ObservationEvent/Checkpoint/LearningCorrection/MemorySummary |
| R1: целостность и фиксация действий | Частично проверено | Нарушения 1–2 закрыты локальными regression; composed local harness, gateway-before-broker enforcement и deterministic workspace interleaving приняты, но production orchestration, real concurrent-writer evidence и external proof отсутствуют |
| R2: сквозной исполнитель | Continuation through Batch #275; EXP-748's one-shot public snapshot composition now passed with retained exact stage digest, observer run ID and bounded request counts; EXP-756 (Batch MK #276) is next READY for Worker-egress boundary design. | **OPEN:** live Worker isolation, independently trusted verifier/host, authenticated human approval, real controlled PR receipt and production recovery remain unproven. EXP-726 is DRAFT; a previously exposed credential is treated as compromised and revocation is unconfirmed. No provider write is authorized by this status. |
| R3: исторический Observer | Частично реализован: local SQLite journal/reopen, bounded structural reports with gap markers, content-addressed artifact resolution/materialization (EXP-642/653/668, EXP-730/731/740), and selected same-run event instrumentation. | **Частично:** collector is not comprehensive, journal/artifact origin and access control are not production-trusted, and the report does not restore and replay a full execution environment. |
| R4: учебная ветка | Частично реализована: metadata-only simulation-branch declaration (EXP-665) and strict in-memory workspace materialization for an eligible complete checkpoint (EXP-740). | **Частично:** no isolated alternative-step execution/replay or learning-transfer evaluation; no historical permissions/effects are replayed. |
| R5: эксперимент | Протокол и versioned casebook подготовлены (EXP-706/707); schedule consistency is tested locally. | **Не исполнен:** нет Worker-run repetitions, baseline/context comparison, transfer results or preregistered outcome analysis. |

Исторические M0/M0.5/M1/M2/M3/M4 больше не являются шкалой текущего плана.
Они обозначают происхождение имеющихся компонентов: базовые контракты и часть
local preparation существуют; M2/M3 не завершены; M4 отложен.

## 8. Правило изменения статуса

Этап меняет статус только при наличии кода, позитивных и негативных тестов,
воспроизводимой команды запуска, списка оставшихся ограничений и ссылки на
соответствующую гипотезу/ADR. Happy-path демонстрация, число документов или
одна успешная внешняя операция не превращаются в доказательство соседних свойств.

## 9. Evidence inventory (EXP-241, сверка 2026-09-13)

Инвентаризация собрана исполнителем по карточке EXP-241 и не меняет выводы
разделов 1–8: сверка статуса — предмет EXP-242. Уровни — по шкале раздела 2.

Штатная проверка, выполненная при сборе:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Результат 2026-09-13: **420 тестов, все прошли, 1 пропущен**. Пропущен
штатный opt-in Docker integration test (требует `RUN_DOCKER_SANDBOX_TESTS=1`,
доступный Docker daemon и образ). Результат подтверждает только свойства,
покрытые тестами, на текущей машине; число тестов не является доказательством
изоляции, сквозной публикации или end-to-end безопасности.

| Область | Артефакты | Evidence (commit) | Уровень |
|---|---|---|---|
| Базовые контракты | 16 исходных JSON Schema в `schemas/`, fixtures, `digests.py`, `validator.py`, `state_machine.py` | История `git log`, chain/contract-тесты | Реализовано и unit-tested |
| Observer R0 contracts and local journal | Observer schemas, `observation_store.py`, `test_observation_store.py` (итого 20 schemas; test-file count changes with the suite) | `ea4fd5a` / `f734226` (contracts), `c661abb`—`e0b8de2` (Batch AE) | In-memory and local SQLite behavior unit-tested: reopen, event/checkpoint persistence, causality, atomic pre-dispatch pair and malformed-journal refusal; collector, reports, access control and infrastructure durability remain unimplemented/unproven |
| Reference preparation и manifest binding | `repository_process.py`, `PreparedChange.verified_contents`, regression-тесты подмены и workspace interleaving | `e98cce3` (EXP-002), `ff79ab6`—`9a31d51` (Batch AD) | Unit-tested; deterministic twin-workspace и stale-manifest cases приняты; real concurrent writers и filesystem locks не доказаны |
| Policy/authority gate | `authority.py` (`DeterministicPolicy`, привязка digest), regression-тесты подмены | `274fbdc` (EXP-003), принят Control Plane | Unit-tested; нарушение п.2 раздела 6 имеет remediation evidence, сверка статуса — EXP-242 |
| Durable state и mock publication | `runtime_store.py` (SQLite transitions/audit), `publication.py` (journal/reconciliation), mock boundary, recovery-тесты | Batch-коммиты EXP-010—EXP-015 и далее (см. `git log`) | Реализовано и unit-tested, включая негативные и recovery-сценарии |
| Gateway/Broker/Actuator boundary hardening | Fail-closed проверки типов, digest, expiry, idempotency и привязок в `gateway.py`, `broker.py`, `actuator.py`, `github_actuator.py`, `mock_github.py`, `github_app.py` + regression-тесты, включая gateway-before-broker preflight | Batch-коммиты EXP-021—EXP-230 и EXP-246—EXP-261 (см. `git log`) | Реализовано и unit-tested локально; production Authority Plane не связан |
| GitHub App | Fake-only adapter tests now bind existing-file Contents updates to a blob SHA read from the staged base commit (EXP-535) | No provider request, branch, PR, or credential used | Partial contract only; real publication and recovery unproven |
| Observer runtime, обучение, LLM Worker | Отсутствуют как код | Без изменений | Спроектировано / Не реализовано |

Открытые границы сквозной цепи (без изменений по существу, см. раздел 6):
п.1–2 имеют remediation evidence (сверка — EXP-242); п.3 (неатомарная GitHub-публикация), п.4 (изоляция local backend/Docker) и п.5 (неполнота истории) остаются открытыми; локальный composed harness не создаёт production automatic chain approval → policy → manifest → Broker → journal → recovery; Docker-интеграция — только opt-in.

Batch AD обновил deterministic local workspace evidence (EXP-272—279).
Непроверенными остаются реальные parallel writers, filesystem locking,
crash safety и backend isolation. Batch AE (EXP-280—286) добавил локальную
versioned SQLite ObservationStore и unit evidence для reopen, checkpoint,
causality, transaction rollback и fail-closed отказа на corrupt records.
Это не power-loss/media-failure simulation, защита от privileged tampering,
multi-process concurrency, production collector или access control. Настоящий
inventory не является security certification и не доказывает external
publication.

Batch AF (EXP-288—307, 20 карточек; R2, batch 1/3) добавил локальный executor
shell и его composed failure-matrix coverage. Batch AG (EXP-308—327, 20 карточек;
R2, batch 2/3) добавил exact commit/tree export из локальной Git object database,
digest-bound prepared content и повторное исполнение allowlisted-команды в
отдельной local sandbox-сессии. Worker, backend и verifier остаются injected
fakes; результат маркирован `local_test`. Это не remote provenance,
independently trusted verification, production isolation, реальная модель,
публикация или reconciliation. Batch AH (EXP-328—347, 20 карточек; R2, batch
3/3) добавил composed локальный approval → policy → gateway → broker →
digest-only journal → mock endpoint path и SQLite recovery: matching receipt
восстанавливается без повторного publish, unknown/error/mismatched outcome
переходит в `reconciliation_required` без blind retry. Полный локальный suite
по завершении AH: 632 теста, 631 прошёл, 1 opt-in Docker test пропущен.
Это не remote/external publication, не real credentials/provider и не
доказательство production durability/isolation или завершения цели R2.
Batch AI (EXP-348—367, 20 карточек; отдельный локальный R2 follow-up)
добавил bounded subprocess JSON handoff ограниченного `VerifierInput` в
дочерний процесс и приём только bound `VerifierResult`: AI-1—AI-4 —
wire contract, AI-5—AI-12 — процессный адаптер и fail-closed поведение,
AI-13—AI-19 — интеграция и отказная матрица. На 2026-10-01 приняты все 20
карточек Batch AI (EXP-348—367);
полный локальный suite: 709 тестов, 708 прошли, 1 opt-in Docker test
пропущен. Это process-boundary prototype на текущем host: process
separation не представлена как trust independence; independently trusted
verifier, production sandbox/isolation, authenticated remote provenance, LLM Worker и
external providers остаются открытыми. DOC-001 и другие архитектурные идеи остаются проектными, если для них отдельно
не указаны существующие код и тестовое evidence. Внешние операции требуют
отдельных точных task cards и допуска.

Batch EW / EXP-557 recomputes recursive Git tree Merkle IDs from validated
paths, modes and object IDs before accepting a GitHub tree claim. It verifies
every subtree and the root OID, rejecting path/mode/blob-ID mutations and
missing/orphaned directory entries. Focused snapshot/pipeline suite: 79 tests
passed (1 skipped); full offline suite: 1005 tests (996 passed, 9 skipped);
`git diff --check` clean.
This strengthens content/tree integrity but does not reconstruct commit-object
bytes or establish authorship, signed provenance, or trust in GitHub/TLS; the
evidence origin remains `github_rest_api_claim`. R2/MVP remain OPEN.

Batch EX / EXP-558 adds `scripts/verify_signed_approval.py`. It reads a
persisted stage, EXP-552 request, signed envelope and explicit trust profile;
rebuilds the complete request from stage and target binding; requires exact
request and signed-field equality; then asks the existing policy to validate
expiry, explicit approver allowlist and Ed25519 signature. Tests cover exact
allow, altered request/signature/key, unlisted identity, expiry, duplicate JSON
keys, symlink input, wrong stage digest, CLI output and byte-for-byte unchanged
stage DB. Focused suite: 53 tests passed; full offline suite: 1016 (1007 passed, 9 skipped);
`git diff --check` clean. Output says `identity_authenticated=false` and
`provider_write=false`; the local trust profile is not enrollment evidence.
No real human signature, persisted historical stage, Gateway/Broker, credential
or provider effect; R2/MVP remain OPEN.

Batch FN / EXP-574 adds `scripts/reconcile_signed_stage_github.py` for an
already-persisted uncertain signed-stage attempt. It verifies the existing
stage/journal bindings before token acquisition, returns completed receipts
locally, and uses a distinct read-only Broker/channel (`contents:read`,
`pull_requests:read`) only for uncertain attempts. The recovery channel has no
publication methods; write coordination rejects its type, and recovery never
retries POST/PUT. Fake-only tests cover matching PR receipts, unknown
digest-only evidence, terminal/mismatch no-token behavior, and zero writes.
Focused suite: 106 tests passed; full offline suite: 1065 tests (1056 passed,
9 skipped); `git diff --check` clean. The CLI has not been run: no real
credential, key, network, GitHub call, provider write, branch, PR, Docker, SSH
or deployment occurred. R2/MVP remain OPEN; real recovery still requires a
separate exact task card and fresh user confirmation.

Batch FU / EXP-581 adds a verifier-side builder for the existing
`signed-verifier-response/v1` envelope. It accepts only canonical bounded
request/response records, checks exact request/result binding and nonce echo,
then signs the canonical response with an already-held Ed25519 key object. It
does not load/export a key, deploy a service, enroll key custody or assert host
independence; the verifier receipt still has
`independent_host_trust_established=false`, and audit-only executor behavior is
unchanged. Focused suite: 11 tests passed; full offline suite: 1067 tests
(1058 passed, 9 skipped); `git diff --check` clean. No key file, credential,
network, verifier execution, stage write or provider effect was used. A
separately trusted verifier host and out-of-band pinned key remain required;
R2/MVP remain OPEN.

Batch FV / EXP-582 adds `signed_verifier_service.py`, a transport-neutral
one-request core with an immutable profile digest. The BrainBooster profile
binds the selected repository and commit, normalized full-snapshot content
digest/file count, sole allowed change path, exact HTTP/DB command and timeout,
verifier image/code IDs and signer key ID. Requests are checked against that
profile before the injected verifier is called; results must carry the exact
runtime identity before the service signs the challenge-bound response.
Synthetic tests prove valid receipt verification, profile-digest sensitivity,
pre-run rejection of changed request fields and rejection of a spoofed runtime
ID. Focused suite: 5 tests passed; full offline suite: 1072 tests (1063 passed,
9 skipped); `git diff --check` clean. No key file, service transport, Docker
run, SSH, credential, stage write or provider effect was used. This is only
service-core wiring: deployment, out-of-band key pinning, independent host
trust and executor promotion remain unproven; R2/MVP remain OPEN.

Batch FW / EXP-583 adds a construction-only factory for the BrainBooster
`DockerContainerVerifier`. It takes an absolute Docker executable and sources
the image ID, verifier code digest and container timeout only from the fixed
profile; construction itself launches no process. Focused and full offline
suite evidence is recorded in WORK_QUEUE.md. No Docker command, container,
credential, network, SSH, stage write or provider effect was used. This does
not establish independent-host trust or deployment; R2/MVP remain OPEN.

Batch FX / EXP-584 adds `SignedVerifierClient`, which validates the immutable
profile and canonical bounded request before one injected transport call, then
checks the signed response against a copied pinned public key, fresh nonce,
request digest, profile digest and freshness bounds. Synthetic integration tests
cover both service/client sides without real transport or key storage. The
result remains `independent_host_trust_established=false` and audit-only; no
transport, deployment, key enrollment or executor trust promotion exists.
Focused suite: 8 passed; full offline suite: 1082 tests (1073 passed, 9
skipped); `git diff --check` clean. R2/MVP remain OPEN.

Batch FY / EXP-585 composes `SignedVerifierClient` with a complete fake
remote-snapshot execution. The valid synthetic signature and PASS are retained
as audit evidence, but the executor still returns
`verifier-trust-unestablished` and performs no durable stage save/read until an
independent trust domain is established. Focused executor/client suite: 61
passed; full offline suite: 1083 tests (1074 passed, 9 skipped);
`git diff --check` clean. No external service was contacted; R2/MVP remain OPEN.

Batch FZ / EXP-586 adds a bounded parser for raw Git commit objects and
recomputes the exact SHA-1 framing before accepting the unique root-tree header
only when it matches the pinned GitHub commit claim. One anonymous fetch of the
fixed public commit produced a 1065-byte object whose hash and tree matched the
repository pins. The temporary bare repository was removed. This verifies
content addressing, not authorship, a commit signature, GitHub identity, or the
HTTPS/TLS source; the fixed runtime intake still does not consume this check.
Focused snapshot parser suite: 43 passed; full offline suite: 1086 tests (1077
passed, 9 skipped); `git diff --check` clean. R2/MVP remain OPEN.

Batch GA / EXP-587 defines `signed-verifier-invocation/v1`: one canonical,
bounded JSON stdin record contains Base64 of the exact canonical verifier
request, a fresh nonce and the expected profile digest. The pure service handler
rejects malformed/duplicate/noncanonical records and profile mismatch before
verifier execution, then returns only the existing signed response bytes.
`SignedVerifierClient` now passes this single envelope to an injected transport;
the full fake remote-snapshot executor test uses the actual envelope/handler and
still stops before stage save because independent-host trust is false. No
remote process or service key enrollment was included in EXP-587; subsequent
Batch GC adds only a local subprocess transport. Key enrollment, deployment
and trust promotion remain open. Focused protocol/client/executor suite: 66
passed; full offline suite at EXP-587: 1091 tests (1082 passed, 9 skipped);
`git diff --check` clean. R2/MVP remain OPEN.

Batch GC / EXP-589 adds a synchronous one-shot subprocess transport for the
signed-verifier wire envelope. It requires an explicit absolute executable,
uses no shell, caller environment or caller working directory, sends the
bounded invocation on stdin, drains stdout incrementally to the signed-response
limit, discards stderr, and kills a child that exceeds the output or time limit.
Transport failures are sanitized and never retried. Focused client/executor
suite: 67 passed; full offline suite: 1096 tests (1087 passed, 9 skipped).
The process is still same-host, is not sandboxed or host-authenticated, and
does not establish independent verifier trust or change the executor trust
gate. No credential, real key, network, SSH, Docker, stage write, approval,
provider call or external effect occurred. R2/MVP remain OPEN.

Batch GD / EXP-590 adds `Ed25519SeedCredentialSource`, a narrow lazy adapter
from the existing opaque `CredentialSource` protocol. It accepts only a
canonical 32-byte seed encoded as 64 lowercase hexadecimal characters and
resolves it once at the final signing boundary, after request/profile and
verifier-result checks. The service does not cache the resulting key. This is
not secure storage, key enrollment, or memory erasure: Python may retain the
credential string/key in process memory, and no live API call is authorized by
the adapter. Synthetic tests prove the source is not called on rejected
requests or verifier identity and that malformed values are sanitized.
Focused service suite: 11 passed; full offline suite: 1100 tests (1091 passed,
9 skipped); `git diff --check` clean. No real credential or external effect
occurred. Independent verifier trust and R2/MVP remain OPEN.

Batch GE / EXP-591 makes the publication journal explicitly require SQLite
WAL mode and `synchronous=FULL` for new databases. Existing-journal recovery
first validates the schema without migration, then requires the persisted WAL
mode and applies FULL synchronous mode to that connection before recovery
writes. Tests verify both PRAGMAs, existing-file preservation on a no-write
open, and fail-closed behavior for a valid non-WAL database. This is stronger
local SQLite commit configuration only; it does not establish filesystem/power-loss behavior,
backup, replication, cross-host or production durability. Focused publication
suite: 40 passed; full offline suite: 1102 tests (1093 passed, 9 skipped);
`git diff --check` clean. No credential or provider effect occurred. R2/MVP
remain OPEN.

Batch GF / EXP-592 adds `GitHubRawCommitObjectSource` and makes fixed runtime
snapshot intake require a parsed raw commit object whose computed SHA-1 OID and
root tree match the fixed pins before Worker/target execution. The initial
source version used a commit-only filter; after that variant failed, Batch GH
removed the filter. The current source uses an isolated temporary bare object
directory, disabled credential helpers/global Git config/redirects, a
15-second aggregate timeout, a 2 MiB pack-file cap, a bounded object-count
check and cleanup. Offline tests cover source command constraints and failure
sanitization, synthetic commit-byte binding, and proof-before-Worker ordering.
Its first public attempt used a commit-only
partial-clone filter and failed safely; it was not retried. Batch GH / EXP-593
removed that unsupported filter, retained depth=1 and strict pack/object bounds,
and fetched the exact public commit once. The 1065-byte object recomputed to
commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` and root tree
`2007066217aadafd9887fb3e3069220333b4fddb`. The temporary object store was
removed. This is content-address integrity, not authorship, signature or
independent GitHub/TLS provenance. Focused
suite: 95 tests (2 skipped); full offline suite: 1112
tests (1103 passed, 9 skipped); `git diff --check` clean. No credential, provider
write, branch, PR, push or deployment occurred. R2/MVP remain OPEN.

Batch GI / EXP-594 then exercised the integrated intake once. Anonymous
header-only preflight returned HTTP 200 / 60 remaining; the runtime REST path
made exactly 25 GETs (commit, recursive tree, 23 blobs) and the depth-1 Git
source verified the same pinned commit and root tree. Full snapshot digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`
matched; 23 blobs totaled 240290 bytes. Output was metadata-only and the
temporary Git object store was cleaned. No credentials, Worker, Docker, stage,
approval, verifier or provider write was used. Snapshot intake is now freshly
proven through the raw-object gate, but Worker-to-publication remains unproven;
at EXP-594 time commit-signature metadata had not been checked. EXP-606 later
recorded GitHub's `verified=true, reason=valid` assertion, but local signature
verification/authorship and GitHub/TLS provenance remain independently
unproven. The
configured full offline suite was rerun after this integration: 1112 tests,
1103 passed, 9 skipped. `git diff --check` clean. R2/MVP remain OPEN.

Batch GJ / EXP-595 closes a proof bypass in `scripts/replay_staged_candidate.py`:
the fixed production composition now injects `GitHubRawCommitObjectSource` into
the REST snapshot reader, and the replay path requires the exact raw commit OID
and root tree proof before sandbox creation, verifier invocation or output-stage
creation. Successful replay evidence exposes only the fixed object identifiers
and `verified-by-object-hash`; it does not claim signer, author or transport
provenance. Regression tests cover source wiring and absent, malformed and
mismatched proof fail-closed ordering. Focused suite: 10 passed; configured full
offline suite: 1115 tests (1106 passed, 9 skipped); `git diff --check` clean.
No replay, Docker, credentials, Worker or network call was made. This removes a
local replay-path bypass but does not provide fresh Worker/verifier pipeline or
independent trust evidence. R2/MVP remain OPEN.

Batch GK / EXP-596 adds an explicit `--credential-source process-environment`
mode to the fixed Worker CLI, backed by the existing lazy
`ProcessEnvironmentCredentialSource(os.environ, "AI_PROCESS_API")`. After the
exact one-run phrase, the CLI checks only that the assigned name is present;
missing injection stops before readiness/network, and no mode falls back to
another. The default hidden terminal source is unchanged. Tests use synthetic
mappings only; focused suite: 7 passed; configured full suite: 1116 tests
(1107 passed, 9 skipped); `git diff --check` clean. No real environment value,
credential, network, Worker, Docker or stage was used. This is process
credential plumbing, not a secret vault, project-to-project bridge, process
isolation, or live Worker evidence. EXP-566 remains DRAFT pending fresh user
authorization and trusted injection; R2/MVP remain OPEN.

Batch GL / EXP-597 checked only whether the current task process contains the
three non-secret names required by the unsigned approval-request CLI:
`AGENT_GITHUB_TEST_REPOSITORY`, `AGENT_GITHUB_INSTALLATION_ID` and
`AGENT_GITHUB_REPOSITORY_ID`. All three were absent. The check emitted only
booleans and read no values, files or other projects. Thus no exact GitHub App
target binding can currently be constructed from this process environment;
the earlier public repository ID does not supply an installation identity.
No stage, secret, network or provider action was used. This is configuration
availability evidence only, not authorization or an App permission check.
R2/MVP remain OPEN.

Batch GM / EXP-598 adds a standalone Worker-CLI presence check selectable only
with `--check-credential-source --credential-source process-environment`. It
requires no stage path or run phrase and exits before Docker, readiness, network
or runtime; output is restricted to source mode, availability and
`value_read=false`. Synthetic tests cover present/missing mappings without
reading values. Focused suite: 9 passed; configured full suite: 1118 tests
(1109 passed, 9 skipped); `git diff --check` clean. The one authorized check of
the current task process returned `unavailable`; no value, file or other
environment data was read. This establishes that `AI_PROCESS_API` is not
currently injected into this runner, not whether a secret exists in another
project. EXP-566 remains DRAFT; R2/MVP remain OPEN.

Batch GN / EXP-599 repeated that exact no-value presence check after the owner
reiterated permission for necessary actions. The runner still reported
`unavailable` and `value_read=false` (exit 3); no credential, file, other
environment entry, readiness or network was accessed. The configured full
offline suite passed 1118 tests (1109 passed, 9 skipped), with `git diff
--check` clean. EXP-566 remains DRAFT.

Batch GO / EXP-600 inspected only the designated AI Process Architect
`README.md` and confirmed that no root `AGENTS.md` exists. The README documents
`AI_PROCESS_API` as an application/server environment setting and shows empty
configuration placeholders, but supplies no supported secret-manager
interface for non-disclosing injection into Agent00X. No `.env`, credential
store, value, unrelated source or process environment was read; no interface
was invoked. The owner must connect a trusted injection mechanism or designate
another supported interface before EXP-566 can proceed. This says nothing
about whether a key exists in the source project. EXP-566 remains DRAFT;
independent verifier trust, authenticated approval, controlled PR publication
and R2/MVP remain OPEN.

Batch GQ / EXP-602 bounds the caller's fixed DeepSeek HTTP deadline across DNS:
the single process-wide daemon resolver slot returns only validated numeric
addresses, the request waits no longer than its monotonic deadline, and the
default HTTPS connection uses those addresses while retaining the fixed
`api.deepseek.com` TLS hostname verification. A late DNS result is never used
to start a connection; resolver errors are sanitized; a permanently blocked
system resolver can occupy only one daemon slot and causes later attempts to
fail closed. Synthetic tests passed for slow, late and failed DNS, slot
exhaustion, and a loopback verified-HTTPS Worker round-trip through the default
connection path. Focused suite: 28 tests (1 skipped); full offline suite: 1121
tests (1112 passed, 9 skipped); `git diff --check` clean. No real DNS, provider,
credential, Worker run, or network endpoint was used. The OS resolver itself is
not cancellable; a synchronous credential-source callback and upload
backpressure also remain unbounded/unproven. R2/MVP remain OPEN.

Batch GR / EXP-603 bounds how long the HTTP caller waits for the synchronous
credential-source callback. A single process-wide daemon slot prevents
unbounded blocked callback threads; a timeout returns before connection
construction, and late success or exception is discarded/sanitized, so it
cannot start HTTP. Synthetic tests also prove that a stuck callback makes later
channels fail closed without invoking another source. Focused suite: 29 tests
(1 skipped); full offline suite: 1122 tests (1113 passed, 9 skipped);
`git diff --check` clean. The callback itself is not cancelled: it may continue
after the caller times out, a late source result may briefly remain in
source-owned Python memory, and one permanent callback occupies the slot for
the process lifetime. No memory-zeroization or hard cancellation claim is made.
No credential, live provider request or external effect occurred. R2/MVP remain
OPEN.

Batch GU / EXP-606 made one anonymous, proxy-disabled HTTPS GET to the exact
public commit endpoint using normal TLS verification. GitHub returned
`verification.verified=true`, `reason=valid`, `verified_at=2025-08-18T17:57:01Z`,
author login `SoldatovAlexander`, and committer login `web-flow` for
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`. Only these bounded fields were
retained; the signature, payload and message were not printed or stored. This
is GitHub's assertion that the signature is valid, not independent local
cryptographic verification or proof of human authorship; provenance still
relies on GitHub/TLS. No credential, retry or write occurred. EXP-606 accepted;
R2/MVP remain OPEN.

Batch GX / EXP-609 adds `scripts/run_signed_verifier_service.py`, a no-argument
one-shot process entrypoint for the fixed BrainBooster verifier service. It
reads at most one canonical invocation from non-interactive stdin, constructs
the fixed-profile Docker verifier without launching it at construction time,
resolves the signer seed lazily from the exact process-injected
`AGENT_VERIFIER_SIGNING_SEED` source only after verifier validation, and writes
only a bounded signed envelope to stdout. Errors produce one fixed stderr marker
with no request/exception data and no retry. Five synthetic tests cover exact
signed round-trip, verify-before-sign ordering, malformed/oversized/TTY input,
argument rejection, output bounding and redaction. Focused suite: 5 passed; full
offline suite: 1127 tests (1118 passed, 9 skipped); `git diff --check` clean.
No Docker run, credential, SSH, host deployment or external effect occurred.
This makes the service process invocable, but does not deploy it, establish key
custody/enrollment, authenticate the host or promote its receipt to trusted
executor evidence. R2/MVP remain OPEN.

Batch GY / EXP-610 corrects stored-candidate replay limitation labels so they
distinguish verified content/raw-commit object hashes from GitHub/TLS transport
provenance and human authorship, which remain independently unverified. Its
focused suite passed (10 tests) and the configured full offline suite passed
(1127 tests: 1118 passed, 9 skipped). One exact bounded replay attempt against
the preserved EXP-548 Worker stage then exited 2 with the fixed
`replay: operation failed closed` marker in under one second. EXP-612 repeated
the same source path/digest and classified it as `source-stage-invalid` before
readiness; EXP-613 then found no row for that key. These later checks reveal
that EXP-610 paired the replay DB with the earlier EXP-520 source digest, but
do not retroactively add a phase marker to its original output. EXP-614 used
the corrected EXP-548 path/digest below. No credential, provider write, branch,
PR, push or deployment occurred. R2/MVP remain OPEN.

Batch GZ / EXP-611 adds a fail-closed replay diagnostic marker with only
allowlisted internal phase codes; unrecognized errors map to
`operation-failed`, and no exception or response text is exposed. Synthetic
tests cover readiness classification and redaction of secret-like/unknown
messages. Focused replay suite: 13 passed; full offline suite: 1130 tests
(1121 passed, 9 skipped); `git diff --check` clean. This improves diagnosis
only: it is not evidence that any replay phase passed, and no live retry,
network, Docker, credential, stage read or provider action was performed.
R2/MVP remain OPEN.

Batch HA / EXP-612 used the new bounded phase marker for one fixed replay
attempt. It exited 2 with `source-stage-invalid` in 0.14 seconds. The card
paired the EXP-548 temporary DB path with `a685…`, the earlier EXP-520 source
stage key. Source-stage validation precedes readiness, snapshot intake and
Docker, so this attempt made no network request and ran no container; the
output database was not created. No retry occurred. The input pairing was
corrected using the separately preserved EXP-548 evidence.

Batch HB / EXP-613's value-free metadata check found no row for the supplied
`a685…` key and left the source file unchanged; its suppressed SQLite errors
mean the result alone cannot distinguish an absent row from a query/schema
failure. Reconciliation against accepted EXP-548 evidence corrected the input:
the replay stage is `/Volumes/DATA/Agent00X-local-evidence/exp548-stage.sqlite3`
at digest
`sha256:d9dab36eb53279b5707d05ddd3b73052a912366d613756cb2858b29d9eccf734`.
The `a685…` key was the earlier EXP-520 source stage, so the EXP-612 failure was
caused by pairing the wrong stage key with the replay-stage database; it does
not establish that the preserved EXP-548 artifact is invalid. EXP-613 output
contained only fixed booleans; no payload text was emitted or changed. A fresh
corrected replay card was used for EXP-614 below.

Batch HC / EXP-614 ran one bounded replay from the correct byte-preserved
EXP-548 stage at `/Volumes/DATA/Agent00X-local-evidence/exp548-stage.sqlite3`,
source digest `sha256:d9dab36eb53279b5707d05ddd3b73052a912366d613756cb2858b29d9eccf734`.
The fixed pinned snapshot matched commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`,
tree `2007066217aadafd9887fb3e3069220333b4fddb` and canonical content digest;
the 23-file intake and depth-1 raw commit proof passed. The fixed target HTTP/DB
probe ran in the network-isolated pinned target image, followed by the pinned
Docker verifier. Exact-digest stage readback and separate read-only preview
passed. New staged digest:
`sha256:470903b354771e167879fde402cf900100b2ce0bfe267461d1fd547573b7d984`;
artifact digest `sha256:9700cb4d14eb82dce02a99787db77a4b080bc2eb501f8db09465d6df9dbad1ea`.
The new stage is preserved outside Git at
`/Volumes/DATA/Agent00X-local-evidence/exp614-replay.sqlite3`, not backed up or
production durable. The CLI did not report the REST request count. This is a
replay of the accepted live Worker candidate, not a new model call; Docker
verifier remains same-host evidence. No credential, approval, GitHub write,
branch, PR, push or deployment occurred. GitHub/TLS provenance and human
authorship remain unproven. R2/MVP remain OPEN.

Batch HE / EXP-616 reviewed that exact staged patch read-only. It converts all
five numeric fields before SQL and rejects booleans, non-finite/fractional
floats and conversion errors. The fixed probe covers malformed strings and
non-finite float overflow but not a finite Python integer outside SQLite's
signed 64-bit range; such a value may still fail at INSERT with a server error.
This edge remains an untested contract risk before approval. The review did not
modify the stage, create approval or establish trust/publishability. No
credentials, network, Docker or provider effect occurred; R2/MVP remain OPEN.

Batch HF / EXP-617 extends the fixed target probe with both signed-64-bit
out-of-range integer boundaries for each of the five numeric fields, requiring
HTTP 422 and zero rows. Focused tests passed (4, 1 skipped); the configured
offline suite passed (1130 tests: 1121 passed, 9 skipped). One read-only replay
against the preserved EXP-614 source stage exited 2 with the fixed
`operation-failed` marker after 18.7s. The replay CLI does not identify the
failing phase, so this does not prove whether the candidate violated the new
contract or whether the target/verifier gates were reached. No output stage was
created; source database bytes were unchanged (file SHA-256
`adb8a8ce…02715f95`). No retry or provider write occurred. The finite-integer
contract remains unverified pending a separately scoped diagnostic; R2/MVP
remain OPEN.

Batch HG / EXP-618 adds a finite, fixed replay marker projection for the
allowlisted HTTP/DB probe categories, including the two signed-range cases.
Unknown, malformed, embedded or secret-like diagnostic text remains the generic
`operation-failed` marker. Focused suites passed (repository process 38, replay
CLI 15, target profile 4 with 1 skipped); full offline suite: 1132 tests
(1123 passed, 9 skipped). This hardens diagnostics only; it neither retries nor
explains EXP-617's prior failure, and no candidate/verifier gate is claimed.
No stage, network, Docker, credential or provider operation occurred. R2/MVP
remain OPEN.

Batch HH / EXP-619 attempted one separately carded replay with the expanded
SQLite-boundary probe and improved fixed diagnostics. It stopped at the
readiness gate after 0.52s with `readiness-gate-failed`, before snapshot intake,
target execution, verifier or stage write. The readiness output omitted the
quota/reset detail; the exact cause is therefore unknown. EXP-614 source bytes
remained unchanged and no EXP-619 output stage was created. No retry, credential,
model call, approval or provider write occurred. The candidate's signed-range
behavior remains unverified; R2/MVP remain OPEN.

Batch HI / EXP-620 made one separate anonymous header-only readiness GET
immediately after EXP-619. It returned HTTP 200 with `remaining=10` and reset
`2026-10-08 11:15:20 UTC`; no body or repository endpoint was accessed. This
quota snapshot is consistent with the EXP-619 readiness failure, but does not
prove its exact response values. A replay needs at least 25 remaining and
should not be attempted before reset; recheck once in its own card. No
credential, stage access or provider write occurred. R2/MVP remain OPEN.

Batch HJ / EXP-621 improves only local replay readiness diagnostics: non-200
HTTP status, malformed quota/reset metadata, and insufficient quota now map to
distinct fixed allowlisted codes; arbitrary exception text stays hidden. The
focused replay suite passed (17 tests); full offline suite: 1134 tests (1125
passed, 9 skipped). No network or stage access occurred. This does not rerun
EXP-619 or change its unknown historical gate result. R2/MVP remain OPEN.

Batch HM / EXP-624 adds `scripts/copy_staged_evidence.py`, a bounded local
no-overwrite copy for an exact staged digest. One byte-identical copy of the
EXP-614 SQLite stage was created outside Git; source and copy file SHA-256 both
equal `adb8a8ce…02715f95`, and read-only exact-digest preview reports verifier
PASS for the pinned repository/commit/path. Focused tests: 5 passed; full suite:
1139 tests (1130 passed, 9 skipped). This is a second copy on the same volume,
not independent backup, replication, power-loss proof or production durability.
Approval remains absent; no network or provider effect occurred. R2/MVP remain
OPEN.

Batch HP / EXP-627 closes an observed local copy race window by checking
source WAL/SHM sidecars and the main-file hash again after copy validation and
before atomic no-overwrite publication. Synthetic tests simulate a sidecar
appearing and a source-hash mismatch; neither publishes output or mutates the
source fixture. Focused suite: 7 passed; full suite: 1141 tests (1132 passed,
9 skipped). This is not a lock or proof of a race-free concurrent database
snapshot, independent backup or production durability; the copy remains on the
same volume. No real stage or external service was accessed. R2/MVP remain OPEN.

Batch HK / EXP-622 performed one bounded replay after the observed reset and
the embedded readiness/snapshot gates. It stopped at the expanded target probe
with `target-test-sqlite-range-status`, exit 2. This marker proves that at least
one signed-range case did not return the expected HTTP status; it does not show
which field or the actual status. The source hash remained
`adb8a8ce73cad24c66f5cd76b627243a62473030f45bc1f00705acce02715f95`; output
`exp622-replay.sqlite3` remained absent. Verifier and new stage persistence
were not reached. No retry, credential, Worker/model call, approval/signing or
provider effect occurred. R2/MVP remain OPEN.
Batch HR / EXP-629 prepared a bounded read-only preview of the exact EXP-614
stage for human review before any approval decision. The stage digest is
`sha256:470903b354771e167879fde402cf900100b2ce0bfe267461d1fd547573b7d984`;
artifact digest is `sha256:9700cb4d14eb82dce02a99787db77a4b080bc2eb501f8db09465d6df9dbad1ea`.
The pinned target is `SoldatovAlexander/brainbooster_full_v11` at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`; only `backend/routes.py` is
declared. The patch validates all five numeric fields before insert and rejects
booleans, fractional/non-finite floats, and values that cannot be parsed as
integers; this preview does not add new test evidence beyond the recorded replay.
Verifier verdict is PASS, but the verifier remains same-host and untrusted for
promotion. Approval is `not_created`; publication is `not_attempted`. The
EXP-624 copy remains byte-identical on the same volume. No signing, network,
credential, Worker/model, provider write, branch, PR, push or deployment
occurred. Human approver identity, branch choice, independent verifier trust,
durable recovery and controlled PR remain open. EXP-622 has the bounded
target-probe failure recorded above; R2/MVP remain OPEN.

Batch HS / EXP-630 documents `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1
python3 -m app_contracts.stage_preview <database> <staged-change-digest>` as an
exact-digest, read-only patch preview separate from approval-request creation.
The configured project runtime passed the existing five stage-preview CLI
tests. This is command discoverability only; it adds no stage, verifier,
approval, trust, or publication evidence. No database, network, credential,
Docker, signing, or provider effect occurred. R2/MVP remain OPEN.

Batch HT / EXP-631 states in README that a valid signed verifier response does
not authenticate an independent host/trust domain. Transport remains injected;
the available subprocess adapter is same-host, with no remote transport,
deployment or out-of-band signer-key enrollment evidenced. Receipts remain
audit-only and do not promote executor trust. This documents a limitation; it
does not establish independent verification. R2/MVP remain OPEN.

Batch HU / EXP-632 ran one in-memory Python SQLite binding check: signed-64
minimum and maximum stored, while one value below and above the range each
raised `OverflowError` and added no row. This is a plausible mechanism for the
EXP-622 marker, not proof of the actual failing target field or HTTP status.
Docs 24 and 27 record the exact EXP-622 failure, unchanged source hash, absent
output and the fact that verifier/stage gates were not reached. No replay,
stage, network, Docker, credential, approval or provider operation occurred.
R2/MVP remain OPEN.

Batch HV / EXP-633 updates the fixed future Worker runner instruction to reject
booleans, malformed/non-finite/fractional inputs and values outside signed-64
range for all five database-bound numeric fields before writes. The next
invocation now has fresh EXP-634 confirmation/process/task/permit IDs; offline
tests assert the exact prompt and identities. Focused CLI suite: 9 passed;
full offline suite: 1141 tests (1132 passed, 9 skipped); `git diff --check`
passed. At preparation time no readiness, network, credential, Worker, Docker,
approval or provider operation occurred. On 2026-10-08 the user explicitly
authorized exactly one EXP-634 DeepSeek call via the previously named
`AI Process Architect` source, with a user-set USD 1 ceiling and no retries.
The non-disclosing process-environment preflight returned `unavailable`,
`value_read=false` (exit 3); the stage path was absent. The card is BLOCKED
before readiness/network; no credential was read and no Worker, Docker,
approval or provider operation occurred. A full offline suite in an isolated
temporary venv passed: 1141 tests, 9 skipped. The default system Python lacked
project dependencies; no repository environment was changed. This adds no new
Worker candidate or verifier evidence. R2/MVP remain OPEN.

Batch HX / EXP-635 adds `SignedVerifierHTTPSTransport`: explicitly configured
HTTPS host, fixed `/v1/verify` POST, default port, hostname-verified TLS,
single total DNS/connect/TLS/write/read deadline, bounded request/response,
no auth/redirect/retry and sanitized failures. Fake-only focused suite: 22
passed; full offline suite: 1149 tests (1140 passed, 9 skipped);
`git diff --check` passed. No endpoint was selected or contacted. The adapter
is not wired to an operational remote service; its signed response remains
audit-only and `independent_host_trust_established=false`. No credentials,
Docker, signing, approval, provider write, branch, PR, push or deployment was
used. EXP-634 remains BLOCKED on safe credential-source availability; R2/MVP
remain OPEN.

Batch HY / EXP-636 exercises the EXP-635 transport against an ephemeral TLS
server bound only to `127.0.0.1`: a trusted SAN-matching certificate completed
one POST; a trusted wrong-host certificate and an untrusted certificate failed
before HTTP; a stalled response was interrupted by the total deadline. The test
uses an ephemeral certificate/key in a temporary directory and maps only the
HTTPS connection to the loopback port; no external DNS or endpoint was used.
Focused suite: 24 passed; full offline suite: 1151 tests (1142 passed, 9
skipped). No real endpoint, credential, Worker, Docker, stage, signing,
approval or provider action occurred. This validates local TLS mechanics only;
it does not establish remote host governance, signer enrollment or independent
verifier trust. R2/MVP remain OPEN.

Batch HZ / EXP-637 adds `SignedVerifierHTTPService` and a one-shot operator
entrypoint bound exclusively to `127.0.0.1` on an explicit unprivileged port.
It accepts only POST `/v1/verify`, exact JSON media types, one canonical bounded
Content-Length and fixed headers; it rejects malformed/profile-mismatched
requests before verifier or lazy signer-source invocation. Responses are
bounded signed JSON or fixed sanitized errors; the HTTP handler suppresses
request/exception logging. Tests include a full synthetic
client → actual loopback TLS → HTTP service → fake verifier → in-memory signer
exchange; the attestation remains `audit_only` and does not establish
independent-host trust. Focused service suite: 8 passed; full offline suite:
1159 tests (1150 passed, 9 skipped); `git diff --check` passed. The server
entrypoint was not run, no process credential was read, and no Docker, remote
endpoint, Worker, stage, approval, provider write or deployment occurred. A
separately governed TLS/access-control proxy, remote host, signer enrollment
and independent verifier trust remain open. R2/MVP remain OPEN.

Batch IA / EXP-638 adds `verify_git_commit_signature`: it rechecks the raw
commit OID/tree, imports one bounded public OpenPGP key into an isolated
short-path GnuPG home, requires its exact primary fingerprint, stores only the
exact commit in an isolated temporary Git repository, and accepts exactly one
`VALIDSIG` from that primary key. Prompts, external Git/GPG configuration,
credential helpers and key retrieval are disabled; tool output/errors are
bounded and sanitized. Synthetic integration tests exercise real Git/GnuPG
for valid signature, wrong pin/key, altered and unsigned objects, and deadline
failure. The typed proof explicitly leaves `identity_authenticated=false` and
`independent_transport_trust_established=false`; the snapshot origin is not
promoted. Focused signature + snapshot suites: 50 passed. No target commit/key,
network, credential, Worker, Docker, approval or provider effect was used.
This is a local verification primitive, not real owner identity or independent
source provenance; R2/MVP remain OPEN.
Full offline suite: 1164 tests (1155 passed, 9 skipped); `git diff --check`
clean. No real repository key was authenticated, so this does not close the
snapshot provenance gate.

Batch IB / EXP-639 made one exact-pin anonymous read-only attempt to compare the
commit signature against the selected signer's published public-key set. The
bounded pipeline reached local cryptographic verification, but no returned key
verified the exact raw commit; it emitted only the fixed sanitized
`signature-not-verified` marker and stopped without retry. No credential,
Worker, Docker, stage write, approval, provider write or publication occurred.
Focused tests: 22 passed; full offline suite: 1172 tests (1163 passed, 9
skipped); `git diff --check` passed. This is negative provenance evidence, not
identity authentication or independent source trust; R2/MVP remain OPEN.

Batch ID / EXP-641 adds an experimental lazy native credential source for the
single `Agent00X` / `AI_PROCESS_API` item. It explicitly selects only the
platform backend (macOS Keychain, Windows Credential Manager, Linux Secret
Service), never provisions/imports secrets, and passes the source lazily to the
fixed Worker runtime. The preflight reports backend availability only and
cannot establish that the item exists or is valid. Synthetic focused tests: 24
passed; full offline suite using the configured temporary venv: 1179 tests
(1170 passed, 9 skipped); `git diff --check` clean. The default system Python
lacks `cryptography`, so its full-suite attempt could not run; no project or
system dependencies were installed. The isolated status check returned
`unavailable`, `credential_item_checked=false`, `value_read=false` because the
check runtime lacks optional package `keyring`. No actual native manager/item,
credential, network, Worker, Docker, stage, approval or provider effect was
accessed. EXP-634 remains BLOCKED; R2/MVP remain OPEN.

Batch IE / EXP-642 adds `scripts/report_observation_history.py`, a deterministic
read-only report over one existing versioned SQLite observation journal. The
CLI verifies database integrity, supported schema, event/checkpoint schemas,
digests, cursor order and checkpoint trigger links before output. It emits only
structural event metadata (not rationale or raw payload), applies validated
process/run/branch and as-of-cursor filters, and marks collector coverage,
unknown outcomes, sequence/causal/invocation gaps, redaction and unresolved
artifact content explicitly. The source is always `local_unattested` and report
completeness always `partial`; it does not resolve artifacts, prove a complete
collector, reconstruct external state or implement replay. Focused suite: 5
passed; full offline suite: 1184 tests (1175 passed, 9 skipped);
`git diff --check` clean. Only synthetic journals were read; no credential,
network, Worker, Docker, stage, approval, provider effect or publication was
used. Criterion 14 is partially covered locally; R2/MVP remain OPEN.

Batch IF / EXP-643 adds an opt-in `JournaledProposalWorker` adapter and threads
an explicit observation-store option through `run_local_execution` and
`run_remote_snapshot_execution`. It writes `agent_started`, then commits a
valid tool-call checkpoint and sanitized `tool_requested` intent atomically
before `ProposalWorker.propose`. After dispatch, only fixed success/failure
metadata is recorded; raw Worker result and exception text are not persisted.
If terminal evidence cannot be stored, the result is explicitly unknown and a
later attempt using the same process/task and journal is refused. Focused
observer/executor/CLI suites: 101 tests (99 passed, 2 skipped); full offline
suite: 1189 tests (1180 passed, 9 skipped); `git diff --check` clean. Tests use
synthetic Workers and journals. This is opt-in and covers only the proposal
call; at that batch the fixed operator CLI was not wired, and
sandbox/verifier/stage/Gateway/publication actions remained uninstrumented. R1,
criterion 13, and R2/MVP remain OPEN/PARTIAL.

Batch IG / EXP-644 adds an optional `--observation-database` to the fixed
pinned runner. It accepts only a new absolute path with an existing non-symlink
parent, opens `SQLiteObservationStore` after operator confirmation and closes it
after the attempted run. The validated store is threaded through the fixed
runtime profile and remote snapshot pipeline to the existing Worker-call gate;
without this option prior behavior is unchanged. Synthetic tests prove an open
failure stops before readiness, the store reaches the executor, and a completed
synthetic proposal leaves three bounded events plus one checkpoint readable by
EXP-642's report CLI after close/reopen. This records only
`ProposalWorker.propose`: readiness, snapshot fetching, sandbox, verifier,
stage, Gateway and publication are not comprehensively observed. Focused suites:
60 tests (58 passed, 2 skipped); full offline suite: 1194 tests (1185 passed,
9 skipped); `git diff --check` clean. No credential, live Worker, network,
Docker, stage, approval, or provider action was used.
Criterion 13 remains partial; R1/R2/MVP remain OPEN.

Batch IH / EXP-645 extends that same optional journal run through
`IndependentVerifier.verify`. The verifier intent is checkpointed before
dispatch, references the preceding Worker terminal event, and continues the
same run ID/event sequence. Only fixed success/failure metadata is recorded;
verifier output and exception text are not stored. Pre-dispatch refusal blocks
the verifier; an unrecorded terminal event maps to `verifier-outcome-unknown`
and blocks reuse of the process/task journal. Focused observer/executor plus
synthetic remote-pipeline suites: 63 tests, no skips; full offline suite: 1198
tests (1189 passed, 9 skipped); `git diff --check` clean. Sandbox
creation/commands, snapshot/readiness, stage/Gateway/publication remain outside
this collector. Criterion 13 remains partial; R1/R2/MVP remain OPEN.

Batch II / EXP-646 adds one-shot journaled adapters for the target-test command
and the pinned/remote snapshot verifier-replay command. Batch IJ / EXP-647
extends the same run through exact-digest stage save and readback. Each operation
has a fixed label and pre-dispatch checkpoint/intent, followed only by fixed
success/failure metadata; argv, repository and stage content, stdout/stderr and
exception text are excluded. A failed gate blocks dispatch; loss of terminal
evidence is unknown and prevents retry through the adapter. Synthetic SQLite
pipeline tests verify shared-run order Worker → target test → replay → verifier
→ stage save → stage readback. Sandbox creation/cleanup, readiness/snapshot
checks, Gateway and publication remain unobserved. Criterion 13 remains partial;
R1/R2/MVP remain OPEN. Focused observer/executor/pipeline tests: 71 passed; full
offline suite: 1206 tests (1197 passed, 9 skipped); `git diff --check` clean.
Two existing SQLite `ResourceWarning`s appeared during the full suite, which
completed successfully. No credential or external effect.

Batch IK / EXP-648 composes one synthetic remote-snapshot execution, temporary
SQLite stage, the real unsigned approval-request CLI, deterministic test-key
signature, and the real signed-mock CLI into one same-digest receipt. The
repository/branch/base and staged digest match through every output; stage DB
and approval inputs remain byte-identical. The receipt explicitly reports
`identity_authenticated=false`, `external_write=false`, and
`trust_profile_origin=operator_supplied_unverified`. Focused pipeline/approval
suites: 20 tests (19 passed, 1 skipped); full offline suite: 1207 tests (1198
passed, 9 skipped); `git diff --check` clean. This is local synthetic
composition, not live Worker, authenticated human approval, real GitHub PR or
production recovery; R2/MVP remain OPEN.

Batch JL / EXP-679 then composed the fake Worker output through the same pinned
target Docker image and pinned verifier image, saved the exact stage in SQLite,
read it back by digest, and completed only a local mock receipt bound to that
digest. The exact corrected opt-in command passed once (1 test, 0.989s); the
full offline suite passed with 1263 tests (1254 passed, 9 skipped), and
`git diff --check` was clean. Both containers used the pinned images; no
containers from either image remained running afterward. This is local
synthetic composition evidence only: it does not prove a live Worker,
independent-host verifier, authenticated human approval, provider write or real
PR. EXP-634 remains blocked because its designated process injector is
unavailable; the existing hidden terminal prompt would require a separately
approved source amendment and fresh one-call confirmation. R2/MVP remain OPEN.

Batch JM / EXP-680 adds `verifier_trust_enrollment.py` and
`verifier-trust-enrollment.schema.json`. It validates a bounded canonical
Ed25519-signed enrollment against a caller-pinned authority public key, binding
the fixed HTTPS route, verifier/profile identity, response key, distinct host
IDs, host-separation evidence digest and expiry. Seven synthetic tests cover
binding, wrong authority, tampering, endpoint/profile mismatch, malformed and
duplicate JSON, expiry and schema. The parsed record explicitly keeps
`independent_host_trust_established=false`; there is no runtime trust promotion,
real enrollment key, OOB host evidence or remote deployment. R2/MVP remain OPEN.
The full offline suite after EXP-680 passed: 1270 tests (1261 passed, 9
skipped); `git diff --check` passed. Existing unrelated SQLite
`ResourceWarning`s remain.

Batch JN / EXP-681 wires the EXP-680 enrollment into
`SignedVerifierClient.from_trust_enrollment`. The factory accepts only the
fixed HTTPS transport with its exact validated endpoint, verifies the
authority-signed verifier/profile/key binding, and compares both expected host
IDs before constructing the client. Invalid authority, expiry, endpoint,
profile, verifier/key identity, host or transport fails before dispatch. The
successful synthetic exchange consumes the enrolled verifier key and exposes
only the enrollment digest; attestation remains `audit_only` and
`independent_host_trust_established=false`. Focused signed-verifier client
suite: 27 passed; full offline suite: 1273 tests (1264 passed, 9 skipped);
`git diff --check` clean. No real endpoint, key, deployment, host identity or
independent-verifier evidence was used. R2/MVP remain OPEN.

Batch JO / EXP-682 carries the validated enrollment digest through the signed
verifier attestation, executor failure result and bounded CLI evidence. Raw-key
clients leave it absent; malformed enrollment metadata is rejected without
stage calls or echo. The executor remains `FAILED /
verifier-trust-unestablished`, and host trust is still explicitly false. Focused
client/executor/CLI suites: 131 tests (129 passed, 2 skipped); full offline
suite: 1274 tests (1265 passed, 9 skipped); `git diff --check` clean. Synthetic
keys/enrollment and fake transport only: no actual OOB review, independent host,
remote endpoint or deployment. R2/MVP remain OPEN.

Batch JP / EXP-683 composes a synthetic authority-signed enrollment, the
enrollment-bound client, the HTTPS adapter type with a fake connection, the
remote-snapshot executor and CLI projection. The one signed PASS carries the
exact enrollment digest into bounded evidence but remains
`FAILED / verifier-trust-unestablished`; no durable stage call occurs. Focused
executor/CLI suites: 104 tests (102 passed, 2 skipped); full offline suite: 1274
tests (1265 passed, 9 skipped). The injected connection bypasses real TLS and
does not establish host separation, deployment or verifier independence.
Authenticated approval and real PR publication remain open; R2/MVP remain OPEN.

Batch JQ / EXP-684 defines a bounded canonical Ed25519 approver enrollment
binding the authority key, approver/key, exact trust-profile digest, provider
repository, fixed PR operation and expiry window. It validates only against a
caller-pinned authority public key and explicitly does not authenticate the
human behind the key. Six synthetic tests and the matching JSON Schema pass;
full offline suite: 1280 tests (1271 passed, 9 skipped); `git diff --check`
clean. This contract is not yet wired into approval verification and has no real
authority key, identity review or provider effect. Trusted signer enrollment,
authenticated approval and R2/MVP remain OPEN.

Batch JR / EXP-685 adds an opt-in read-only `verify_signed_approval` path and CLI
flag that require both an enrollment artifact and a caller-pinned authority key
mapping. It validates exact trust-profile digest, approval principal, provider
repository and fixed PR operation, then checks that the profile's key equals
the enrolled key before policy evaluation. Evidence includes only enrollment
and authority-key IDs/digests; `identity_authenticated=false` and
`provider_write=false`. Legacy verification remains explicitly
`operator_supplied_unverified`. Synthetic tests cover missing pins, wrong
authority/scope/key, expiry and malformed enrollment without changing stage
bytes. Focused suite: 15 passed; full offline suite: 1283 tests (1274 passed,
9 skipped); `git diff --check` clean. No real identity review, stage publication
or provider action. R2/MVP remain OPEN.

Batch JS / EXP-686 closes that local wiring gap only for the mock destination:
the new coordinator itself loads the exact signed approval and enrolled signer
against caller-pinned authority keys, binds the resulting artifact to the
publication seed, intent, provider/source identities and policy, then re-hashes
the stage returned by the downstream loader. It accepts only the exact
in-memory broker and mock endpoint before verification or stage loading, and
reuses all existing freshness/policy/gateway/broker/journal gates. A synthetic
run created one receipt with the exact staged digest and idempotency key; seed
mismatch and loaded-stage tampering stopped before gateway/broker/journal/
endpoint effects; provider-adapter attempts stopped before verifier/stage load.
Focused suite: 16 passed; full offline suite: 1284 tests
(1275 passed, 9 skipped). This remains synthetic local evidence: no human
identity authentication, real authority governance, provider write or real PR.

Batch JT / EXP-687 adds the enrolled signer path to the signed-stage mock CLI.
The CLI requires enrollment, a bounded `control-plane-authority-key-set/v1`
file and the independently supplied SHA-256 pin for that exact file; partial
arguments fail closed, while omission of all enrolled flags retains the
explicit legacy mode. The parser rejects symlinks, duplicate/unknown fields,
malformed keys and oversized input. The output adds only the key-set digest and
enrollment/authority IDs and digests, preserving `identity_authenticated=false`
and `external_write=false`. A full synthetic pinned-CLI continuation carries
the same observer run through enrolled approval to one exact-digest mock receipt;
repeat continuation is refused without journal mutation. Focused suites: 61
passed (49 schema/contracts, 11 mock CLI, 1 same-run integration); full offline
suite: 1292 tests (1283 passed, 9 skipped). Authority key-set digest still requires independent OOB
pinning, and the enrollment does not authenticate a human or enable real PR.

Batch JV / EXP-689's first Docker-composition attempt stopped before stage with
the fixed `pinned-worker-runtime-failed` marker; the initial test-only
container-command diagnosis was not confirmed. Batch JW / EXP-690 switched the
opt-in target test to `python3` but likewise did not reach stage. Batch JX /
EXP-691's test-local diagnostic reported only `VerifierProcessError`; source
inspection established that the Docker command had supplied a 63-hex verifier
code digest, rejected before container launch. Batch JY / EXP-692 corrected
that command value but its test guard still compared a truncated duplicate, so
the command skipped and launched no container.

Batch JZ / EXP-693 binds the opt-in guard to the constants imported from the
pinned profile. The one same-run Docker integration passed in 3.898s: fake
readiness/snapshot/Worker, target tests in the pinned `network=none` image,
PASS from the pinned verifier container, exact verifier identity stored with
the stage, enrolled approval, and one same-digest local mock receipt. The test
also checked contiguous same-run observer events, unchanged inputs, canary
absence and refusal to replay; post-run `docker ps` found no running containers
from either pinned image. The default local same-run integration passed. Full
offline suite: 1293 tests (1283 passed, 10 skipped); `git diff --check` clean.
This remains synthetic/local-host evidence: no live model, real snapshot
transport, independent verifier host, human identity proof or real GitHub PR.
EXP-634 remains blocked pending the approved credential-source amendment;
R2/MVP remain OPEN.

Batch KA / EXP-694 strengthened only the pinned snapshot evidence: one
anonymous readiness GET, 25 fixed REST GETs (commit/tree/23 blobs), and one
bounded raw commit-object fetch all completed; the full pinned owner/repository,
commit/tree, 23-file count, canonical content digest and object hash/root tree
matched. The claim remains `github_rest_api_claim`; authorship, commit signature
and authenticated remote provenance are unproven. In the single authorized
composition attempt, the synthetic CLI runtime returned `pinned_code=1` and
`runtime_code=1`; no exception class or safe inner failure code was retained.
No verified stage, approval or receipt is claimed. No retry is authorized by
EXP-694; a future diagnostic attempt requires a new task card. Post-run Docker
filters showed no running containers from either image. Full offline suite:
1294 tests (1283 passed, 11 skipped); `git diff --check` clean. No credentials,
live model, provider write, branch, PR, push or deployment occurred. EXP-634
remains BLOCKED; R2/MVP remain OPEN.

Batch KB / EXP-695 changes only the test harness: on nonzero runtime status it
extracts an explicitly allowlisted fixed `failure_code`, maps bounded HTTP
status codes to a constant category, and otherwise reports `unavailable`.
Synthetic cases verify malformed/unknown output and canary-like nested content
are not copied. Focused projection and existing local same-run tests: 2 passed;
full offline suite: 1295 tests (1284 passed, 11 skipped); `git diff --check`
clean. This does not reveal EXP-694's prior failure cause and no public/Docker
retry was made. EXP-694 remains BLOCKED; EXP-634 remains BLOCKED; R2/MVP remain
OPEN.

Batch KC / EXP-696 made one separate diagnostic attempt using the EXP-695
allowlisted failure-code projection. The public snapshot and raw commit object
again matched the fixed pin, but the CLI returned only
`remote-snapshot-execution-failed` (`pinned_code=1`, `runtime_code=1`); no
last-observer-stage marker or exception class was captured. No verified stage,
approval or mock receipt is proven. Docker cleanup filters found no running
containers. No retry is authorized by EXP-696. A future attempt requires
bounded projection of only a recognized last observer event and a new card.
EXP-634 remains BLOCKED; R2/MVP remain OPEN.

Batch KD / EXP-697 added a test-only projection that returns only the latest
recognized observer event/action label. Its sole integration attempt stopped
before reading the snapshot or launching Docker: anonymous `/rate_limit`
returned HTTP 200 with `remaining=10`, below the required 35. Full offline
suite: 1296 tests (1285 passed, 11 skipped); `git diff --check` clean. Do not
make another public read until a new rate-limit window and a separate exact
card. EXP-634 remains BLOCKED; R2/MVP remain OPEN.

Batch KE / EXP-698 refactors only the opt-in integration harness. Readiness and
snapshot collaborators are now injected at the pinned CLI runtime seam; the
public mode calls the bounded REST/raw-commit reader inside that runtime and
checks the returned snapshot before the synthetic Worker proposes a candidate.
The default local same-run and safe observer-marker tests passed (2 focused
tests); full offline suite: 1296 tests (1285 passed, 11 skipped);
`git diff --check` clean. No public API or Docker attempt was made; future
execution needs a separate card and a passing rate-limit preflight. No approved
credential injector is available, so EXP-634 remains blocked and no live
provider call occurred. R2/MVP remain OPEN.

Batch KF / EXP-699 adds an offline integration check for the real snapshot
reader and journal wrappers: a synthetic REST source serves content-addressed
blob/tree/commit data and a raw commit object; `_run_pinned_remote_execution`
fetches and validates it before invoking the synthetic Worker. The resulting
contiguous observer run includes commit/tree/blob reads, raw-object proof, pin
decision, Worker, local target replay, verifier and exact stage save/readback.
Three focused tests passed; full offline suite: 1297 tests (1286 passed,
11 skipped); `git diff --check` clean. No public network or Docker execution
occurred. This does not establish live snapshot transport, a real Worker,
independent verifier trust or PR publication. EXP-634 remains blocked because
no suitable injector is available; R2/MVP remain OPEN.

Batch KG / EXP-700 inspected both exact cached `linux/arm64` Docker image IDs,
then made one opt-in pinned composition invocation. The CLI failed before the
runtime seam (`runtime_code=unavailable`), so there is no evidence of snapshot
GETs, raw commit fetch, container execution, stage, approval or receipt. The
test did not retain bounded readiness status/remaining; its precise cause is
unknown and must not be inferred. No retry is authorized by EXP-700. Any later
public attempt needs a separate card that captures only fixed readiness status
and integer remaining. EXP-634 remains blocked; R2/MVP remain OPEN.

Batch KH / EXP-701 adds a strict, offline-tested readiness projection for the
opt-in public integration harness. It retains only a valid HTTP status and
nonnegative integer remaining count (`http-<status>:remaining-<integer>`), or
the constant `unavailable`; response bodies and arbitrary fields never enter
the marker. Focused tests: 3 passed; full offline suite: 1298 tests (1287
passed, 11 skipped); `git diff --check` clean. No readiness/network request was
made under this card. EXP-700 remains closed without retry, and its precise
readiness result is unknown. EXP-634 remains blocked; R2/MVP remain OPEN.

Batch KI / EXP-702 adds an offline regression for the default hidden-terminal
credential source: when synthetic GitHub readiness is below threshold, the
operator CLI calls readiness once and stops before runtime, `getpass`, stage
creation or credential resolution. Focused tests: 2 passed; full offline suite:
1299 tests (1288 passed, 11 skipped); `git diff --check` clean. This validates
the lazy input gate only; it does not authorize the DRAFT EXP-634 source change
or any live model call. EXP-634 remains blocked; R2/MVP remain OPEN.

Batch KJ / EXP-703 composes the production snapshot parser with the complete
offline same-run publication path. A synthetic content-addressed REST/raw-
commit source is fetched inside `_run_pinned_remote_execution`; the fetched
bytes feed the Worker, verifier and exact SQLite stage, then the actual
approval-request CLI and enrolled signed-mock CLI produce one receipt under
the same observer run and staged digest. Replay is rejected and stage/approval
inputs remain unchanged; receipt reports `external_write=false`. Focused tests:
3 passed; full offline suite: 1300 tests (1289 passed, 11 skipped);
`git diff --check` clean. This is synthetic/local evidence, not a live Worker,
independent verifier or real PR. EXP-634 remains blocked; R2/MVP remain OPEN.

Batch KK / EXP-704 (R2 continuation batch #227; 1 task) made one separately
carded anonymous public-read-only attempt after bounded readiness projection
was added. Both exact cached Docker image IDs and `linux/arm64` architectures
matched. The single readiness GET returned HTTP 200 with 10 remaining, below
the required 35; the CLI failed closed before snapshot REST reads, raw commit
fetch, runtime or Docker. No stage, approval or receipt was created; no retry
is authorized. This adds no successful execution evidence; R2/MVP remain OPEN.

Control Plane amendment 2026-10-08T22:15:11Z approved `hidden-terminal` as the
EXP-634 source, superseding the earlier process-environment-only amendment.
The distinct run confirmation has not been provided, and the active MVP
objective continues to prohibit credentials; no live call or secret input was
performed.

Batch KL / EXP-705 (R2 continuation batch #228; 1 task) adds strict bounded
readiness/snapshot-REST/raw-commit/runtime attempt-count diagnostics to the
opt-in public harness; request counts increment before dispatch and malformed
values collapse to `unavailable`. Offline gate coverage uses synthetic
`remaining=10`, confirms readiness once, no runtime/getpass/stage, and does not
contact the public endpoint. Focused tests: 3 passed; full offline suite: 1301
tests (1290 passed, 11 skipped); `git diff --check` clean. EXP-704's single
public attempt returned HTTP 200 / remaining 10 (<35) and stopped before
snapshot/runtime; no retry. This is not successful end-to-end evidence; R2/MVP
remain OPEN.

Batch KM / EXP-706 (R5 prep batch #1; 1 task) records a preregistered VP-21/22
protocol in docs/33. It fixes the target function/snapshot, four experimental
cells, transfer/regression oracle, five exploratory repetitions per cell,
decision thresholds and reporting rules. No model run or evaluation result
exists; R5 is prepared but not executed and criterion 16 remains incomplete.
No credentials, network, Docker, target execution or external action was used.

Batch KN / EXP-707 (R5 prep batch #2; 1 task) adds a machine-readable
`fixtures/experiments/r5-repository-change.json` casebook and four offline
integrity tests. The matrix expands to 25 unique invalid inputs, preserves the
known valid control, freezes five process scenarios and the 100-attempt
factorial schedule, and has no runtime results. Focused suite: 4 passed;
`git diff --check` clean. Full suite and target were not run. R5 and criterion
16 remain unfulfilled.

Batch KO / EXP-708 (R2 continuation batch #229; 1 task) made one fresh
anonymous read-only attempt using the exact cached `linux/arm64` images.
Readiness returned HTTP 200 / remaining 10 (<35); failure diagnostics include
one readiness GET, zero snapshot REST GETs, zero raw commit fetches and zero
runtime invocations. No Docker, stage, approval or receipt was reached; no
retry is authorized. This is the second separate carded observation of
remaining=10, not a successful snapshot run. R2/MVP remain OPEN.

Batch KP / EXP-709 (R2 continuation batch #230; 1 task) adds a bounded reset
epoch marker to public readiness failure diagnostics, emitting only a strict
Unix-seconds integer or `reset-unavailable`. Three focused projection tests
passed; `git diff --check` clean. No network or integration attempt occurred.
R2/MVP remain OPEN.

Batch KQ / EXP-710 (R2 continuation batch #231; 1 task) verified the exact
cached `linux/arm64` target/verifier image identities and made one public
read-only composition attempt. Readiness returned HTTP 200 / `remaining=10`
with reset `2026-10-08T22:47:09Z`; bounded counters were readiness=1, snapshot
REST=0, raw commit=0, runtime=0. The pipeline failed closed before snapshot,
runtime, Docker, stage or receipt; no retry is authorized under that card.
Two focused safe readiness/reset marker tests passed and `git diff --check` is
clean. No credentials, live model or provider write were used. R2/MVP remain
OPEN.

Supplemental full offline suite after Batch KQ / EXP-710:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` ran
1306 tests, passed with 11 skipped. Two existing SQLite
`ResourceWarning`s reported unclosed connections; no test failure occurred.
This is local regression evidence only, not a snapshot success or R2/MVP exit.
Control Plane records a precondition deviation for EXP-710: its prior-reset
gate could not be verified because EXP-708 retained no reset epoch. The single
bounded readiness GET established the first usable reset timestamp; EXP-711
requires that timestamp to have elapsed before any new request.

Batch KR / EXP-711 (R2 continuation batch #232; 1 task) made one post-reset
public read-only attempt. Readiness returned HTTP 200 / remaining 60; the
snapshot path issued 25 REST GETs and one bounded raw commit fetch, then invoked
the runtime once. It returned the fixed generic safe code
`remote-snapshot-execution-failed`; the last safe observer marker was
`tool_requested:SandboxSession.close.target-execution`. The card produced no
verifier, verified stage, approval or receipt evidence. The marker does not
identify whether the failure came from the target command, cleanup or another
runtime stage; retry is prohibited under that card.
No credential, live model or provider write was used. R2/MVP remain OPEN.

Batch KS / EXP-712 (R2 continuation batch #233; 1 task) compared two offline
paths after EXP-711: synthetic REST snapshot through enrolled mock receipt and
the pinned Docker synthetic composition. Both passed. The public failure did
not reproduce, and these controls do not isolate its root cause; no code change
or root-cause claim is made. No public network, credential, live model or
provider effect occurred. R2/MVP remain OPEN. The exact pinned target commit
is absent from the Agent00X Git object database; this checkout therefore cannot
replay that source offline. This does not rule out other local caches and is
not root-cause evidence.

Batch KT / EXP-713 (R2 continuation batch #234; 1 task) extends the integration
harness's safe observer marker to include only three exact sandbox failure
categories under a valid failed event/action; malformed/canary values remain
excluded. One focused projection test passed; no public attempt or runtime was
made. This improves future diagnostics but does not establish EXP-711's cause.
R2/MVP remain OPEN.
Batch KV / EXP-715 (R2 continuation batch #236; 1 task) adds an offline-tested,
strict allowlist projection for fixed target probe failure categories in the
integration harness. Three focused tests passed; no public request, Docker or
target execution occurred. EXP-714 remains the next separately carded public
read-only attempt after its recorded reset.
Supplemental full offline suite after EXP-715: 1307 tests (1296 passed,
11 skipped), no failures. Two existing SQLite `ResourceWarning`s for unclosed
connections remain; `git diff --check` is clean.
Batch KW / EXP-716 (R2 continuation batch #237; 1 task) verifies that the
integration harness retains only a fixed probe failure marker from a fake
session and excludes synthetic canary stderr from evidence. Two focused tests
passed; no network, Docker or target execution occurred.
Supplemental full offline suite after EXP-716: 1308 tests (1297 passed,
11 skipped), no failures; two existing SQLite warnings for unclosed
connections remain.
Supplemental full offline suite after EXP-713: 1306 tests (1295 passed,
11 skipped), no failures. Two existing SQLite `ResourceWarning`s for unclosed
connections remain; `git diff --check` clean.

Batch KZ / EXP-719 (R2 continuation batch #240) captured one bounded result
from the synthetic target Docker probe: fixed overflow input `level=1e309`
returned HTTP 500 and left zero SQLite rows. The probe retained no response
body or raw stderr. Exact cached image ID/architecture matched the pinned
`linux/arm64` runtime; no container remained after cleanup. This does not
establish behavior of the real pinned repository and does not resolve the
EXP-711 public runtime failure. No retry or external effect occurred; R2/MVP
remain OPEN.

Batch LA / EXP-720 (R2 continuation batch #241) captured only the synthetic
exception category `value`, but its middleware returned a replacement 500
instead of re-raising. Its explicit acceptance criterion was not met; the
card is BLOCKED and the category is provisional synthetic evidence only. No
exception text, traceback or response body was exposed. This is not root-cause
evidence for the pinned public repository's runtime failure. No public
request, credential or external effect occurred; R2/MVP remain OPEN.

Supplemental full offline suite after EXP-720 ran 1311 tests (1297 passed,
14 skipped), with no failures; all Docker/public opt-in variables were unset.
Two existing SQLite `ResourceWarning`s for unclosed connections remain.
R2/MVP remain OPEN.

Batch LB / EXP-721 (R2 continuation batch #242) confirmed the same fixed
`value` exception category with a middleware that persisted only the category
in a temporary in-container diagnostic table and re-raised the original
exception. The parent did not read response body, traceback or exception text.
This is synthetic-only evidence and does not resolve EXP-711. R2/MVP remain
OPEN.
Supplemental full offline suite after EXP-721, with Docker/public opt-in
variables unset: 1312 tests (1297 passed, 15 skipped), no failures. Two
existing SQLite `ResourceWarning`s for unclosed connections remain.

Batch LC / EXP-722 (R2 continuation batch #243) updated the deterministic
synthetic candidate's pre-insert validation and passed one exact-image,
network-isolated Docker run: all 25 malformed cases plus `1e309` produced
422/zero writes, and valid input produced 200/one exact row. This is fake
Worker/test-harness evidence only; it does not verify the public repository's
runtime or a live Worker proposal. R2/MVP remain OPEN.
Supplemental full offline suite after EXP-722, with Docker/public opt-in
variables unset: 1313 tests (1297 passed, 16 skipped), no failures. Two
existing SQLite `ResourceWarning`s for unclosed connections remain.

EXP-714's authorization expired without a request and was not reused. The new
Batch LD / EXP-723 card passed once: readiness was eligible; the exact pinned
public snapshot (REST commit/tree/23 blobs plus bounded raw commit) was
validated, and the updated deterministic fake Worker candidate passed in the
target container before the same-run pinned verifier and exact-digest stage.
The enrolled synthetic approval and local mock CLI returned a same-digest
`mock_published` receipt with `external_write=false`; it also explicitly
reported `identity_authenticated=false`. This demonstrates the strongest
current public-snapshot-to-local-mock composition, not a live Worker, real
human authorization, independent-host trust or actual PR. No credential or
provider write occurred. R2/MVP remain OPEN.

EXP-634's separate fresh `RUN EXP-634 ONCE` confirmation arrived at
`2026-10-09T08:16:27Z` UTC. The one operator invocation passed readiness and
acquired the exact pinned snapshot, then stopped at the hidden credential prompt
with bounded `worker-failed` evidence; no credential was entered. The
`DeepSeekHTTPChannel` resolves the credential before opening HTTPS, so code
ordering establishes that no DeepSeek HTTP request or model call occurred.
CLI evidence reports exact commit/tree and a raw commit verified by object hash,
with `approval=not_created`, `publication=not_attempted` and
`external_write=false`. The designated output path exists and was preserved
without reading its contents. No retry is permitted under this card. A new
card and fresh authorization are needed for another attempt; EXP-634 remains
BLOCKED and R2/MVP remain OPEN.

Batch LE / EXP-724 closed two test-owned SQLite connections that emitted
`ResourceWarning` under the full suite. Tracemalloc identified the exact
`sqlite3.Connection` context-manager sites in `test_publication.py` and
`test_worker_cli.py`; explicit close-on-exit preserves transaction semantics.
Focused suites: 90 tests (88 passed, 2 skipped). Full suite with tracemalloc and
ResourceWarnings enabled: 1313 tests (1297 passed, 16 skipped), no warnings or
failures; `git diff --check` clean. This is test-harness hygiene only and does
not change R2, independent verifier trust, authenticated approval or real PR
publication status; MVP remains OPEN.

Batch LF / EXP-725 added a second fixed authorization profile to the pinned
Worker operator CLI without changing the EXP-634 default. The EXP-726 phrase,
process/task IDs and permit ID remain bound together; wrong-phrase regression
stops before readiness and credential lookup; an unknown card ID is rejected
before preflight. Focused tests: 19 passed; full offline suite: 1316 tests
(1300 passed, 16 skipped); `git diff --check` clean.
No public request, Docker, credential prompt, live model or provider action
occurred. Batch LG / EXP-726 is prepared as DRAFT for the user to run from their
own interactive terminal after fresh `RUN EXP-726 ONCE` approval; its new stage
path was absent at preflight. EXP-634's failed hidden prompt is not retried.
R2/MVP remain OPEN.

Batch LH / EXP-727 and Batch LI / EXP-728 add a sibling synthetic journaled
snapshot composition whose in-process verifier service signs a PASS response
with an ephemeral Ed25519 key. `SignedVerifierClient` validates the response
signature, while correctly leaving it `audit_only` and
`independent_host_trust_established=false`. The complete executor reports only
`verifier-trust-unestablished`, makes zero stage save/readback calls and emits
no stage events; the positive sibling still performs one exact stage
save/readback. Focused cases: 2 passed; full offline suite: 1317 tests (1301
passed, 16 skipped); `git diff --check` clean. This synthetic caller-supplied
key proves neither verifier identity nor independent host trust; deployment
and OOB evidence remain absent. No external service, credential, Docker,
Worker/model or provider action occurred. R2/MVP remain OPEN.

Supplemental verification on 2026-10-09 reran both EXP-728 focused journaled
snapshot cases and the full offline suite against the current worktree. Focused
cases: 2 passed; full suite: 1317 tests, 1301 passed and 16 skipped. No live
network, Docker opt-in, credential or provider operation was enabled. The
rerun adds no independent-host trust or publication evidence; R2/MVP remain
OPEN.

Batch LK / EXP-730 adds a content-addressed local SQLite artifact prototype and
read-only event-ref resolution in the observer report. Only exact canonical
JSON event input/output references are resolved; the report emits digest and
size, never payload. Classification/redaction metadata is persisted and cannot
be changed on an idempotent reference. The 10,000-reference limit, malformed/missing/tampered
references, immutable insertion, redaction metadata and common credential
patterns have synthetic tests. Focused suite: 14 passed with tracemalloc and
ResourceWarnings enabled, no warnings. Full offline suite: 1325 tests (1309
passed, 16 skipped), no ResourceWarnings; `git diff --check` clean. This does
not resolve checkpoint/workspace artifacts or implement restore/replay, prove
unknown-secret absence, or establish collector completeness; criterion 14
remains partial, criterion 15 remains partial, and R2/MVP remain OPEN.

Batch LL / EXP-731 extends the same resolver across all seven declared
checkpoint reference fields, including state/context/workspace and authority
refs. It records checkpoint-to-reference association without returning bytes or
restoring any state. Focused report suite: 11 passed; full offline suite: 1326
tests (1310 passed, 16 skipped), with tracemalloc and ResourceWarnings enabled
and no warnings; `git diff --check` clean. This establishes only local
content-addressed availability, not artifact authenticity, trusted history,
checkpoint restore, replay, learning evaluation or complete collection.
Criterion 14 remains partial, criterion 15 remains partial, and R2/MVP remain
OPEN.

Batch LM / EXP-732 adds a separately signed, short-lived Control Plane decision
that is exact-bound to the verifier enrollment and host-separation evidence.
Without that decision, the signed verifier client remains audit-only and the
journaled snapshot execution stops before stage; a valid synthetic decision
lets the actual client/executor test path reach exact local stage save/readback.
The publication seed retains only attestation, enrollment and decision digests;
the bounded CLI reports those digests and the derived trust status. The
synthetic authority does not establish
real OOB review, key governance or an independent host; no live endpoint,
credential, deployment, human approval or provider write occurred. Criteria
1–3, 7, 11–12 and the real external gates remain open; MVP is not complete.

Batch LN / EXP-733 exposes the verifier attestation/key/profile, enrollment and
host-trust-decision digests in the read-only review and includes the same
record in the canonical approved intent, so a signed approval is bound to the
exact provenance metadata as well as the staged change and publication intent.
The stage preview explicitly says `recorded_digest_only_not_revalidated`
because signed evidence bytes and independent host evidence are not preserved
for revalidation after reopening; legacy stages report `not_recorded`. A
synthetic signed approval traverses local policy/gateway/broker gates to an
in-memory mock receipt with `external_write=false`. Focused suites: 79 passed;
full offline suite: 1342 tests (1326 passed, 16 skipped); `git diff --check`
clean. OOB verifier deployment/authority governance and authenticated human
identity remain unproven; there was no live Worker or provider PR. R2/MVP
remain OPEN.

Batch LO / EXP-734 stores only public signed verifier evidence with a successful
stage: canonical verifier attestation bytes, exact authority-signed enrollment
and host-decision records when available, and the bound request digest. Stage
revalidation checks record canonicalization, duplicate keys, bounded sizes,
hashes and agreement with the persisted verifier result. SQLite save/readback
preserved exact synthetic evidence; stage preview/CLI output omits raw bytes.
Legacy records without the optional envelope remain readable and report proof
unavailable. Focused suites: 107 tests (99 passed, 8 skipped); full offline
suite: 1343 tests (1327 passed, 16 skipped); `git diff --check` clean. This
does not revalidate authority signatures after reopen or reconstruct the
source verifier request (the full snapshot is intentionally not duplicated in
the stage). Real authority-key governance, OOB host review, live Worker,
authenticated approval and PR publication remain open; R2/MVP remain OPEN.

Batch LP / EXP-735 implements an explicit read-only revalidation step for
persisted verifier provenance. The caller provides the independently pinned
authority key set; enrollment and host-decision signatures are checked before
the response signature is checked against the enrolled verifier key. The
signed verifier result must equal the stored result, and its timestamp must be
within 300 seconds old / 30 seconds future skew. Synthetic post-SQLite-reopen
coverage accepts valid evidence and rejects a wrong authority key, modified
enrollment/decision/verifier signatures, and stale/future attestations.
Result flags preserve the boundaries: request input was not reconstructed,
identity is unauthenticated, and no provider write occurred. Focused tests: 32
passed; full offline suite: 1345 tests (1329 passed, 16 skipped);
`git diff --check` clean. The original request reconstruction and integration
of verified provenance into digest-bound authenticated approval are still
open; caller-pinned test keys do not establish production key governance or
OOB host separation. No credentials, network, Worker/model, approval or
provider write was used. R2/MVP remain OPEN.

Batch LQ / EXP-736 adds optional persisted verifier-evidence envelope v2.
The successful signed client propagates the exact canonical request bytes into
the stage; the bounded bytes are checked against the request digest before
storage. Reopened-stage validation parses and reserializes them byte-for-byte,
recomputes the full verifier snapshot-tree digest, compares all derivable
request fields against the immutable stage and request context, and rejects
noncanonical/duplicate/oversized/substituted input or candidate mismatch.
The request snapshot is rechecked for known credential patterns. A synthetic
SQLite round trip sets `request_input_reconstructed=true`; legacy v1 remains
readable with the flag false. Focused suite: 131 tests (123 passed, 8
skipped); full offline suite: 1345 tests (1329 passed, 16 skipped);
`git diff --check` clean. This establishes no identity or production host
trust, and is not yet bound into authenticated digest-bound approval. No
credential, network, Worker/model or provider write was used. R2/MVP remain
OPEN.

Batch LR / EXP-737 requires independently caller-pinned authority keys when
preparing approval for a remote-snapshot stage, revalidates the exact persisted
verifier proof, requires reconstructed request input, and binds the verified
provenance digests/status/key IDs into the signed intent. Signed-approval
consumption reloads the stage and repeats that validation before policy
evaluation. A synthetic end-to-end test verifies the positive path and rejects
wrong pins; remote stages with no signed proof stop before approval and leave
the stage database unchanged. Public key-set parsing is bounded, strict and
does not echo payload data on failure. Focused suite: 156 tests (148 passed, 8
skipped); full offline suite: 1348 tests (1332 passed, 16 skipped);
`git diff --check` clean. Synthetic pins do not establish production authority
governance or OOB host trust, and `identity_authenticated=false`; no live
Worker, external write or PR publication occurred. R2/MVP remain OPEN.

Batch LS / EXP-738 extends the synthetic signed-verifier snapshot path through
the actual enrolled signed-mock CLI. After exact SQLite stage reopen, both
verifier authority pins and approver enrollment are independently checked;
one in-memory mock receipt carries the stage digest, repository, branch and
idempotency key from the approval intent. Snapshot intake, Worker, sandbox,
verifier, stage and controlled mock publication all remain under one SQLite
observer run. Missing/wrong verifier pins and a mismatched observer-run ID
fail before receipt; approval-stage bytes remain unchanged. The CLI now exposes
the non-secret idempotency key in bounded receipt evidence. Focused suite: 37
tests (29 passed, 8 skipped); full offline suite: 1348 tests (1332 passed, 16
skipped); `git diff --check` clean. The test uses synthetic transport,
synthetic Worker/verifier/signers and an in-memory provider double; observer
completeness remains `partial`. Production authority/OOB trust, authenticated
human identity, live Worker and real PR publication remain open. R2/MVP remain
OPEN.

Batch LT / EXP-739 updates the existing opt-in public pinned-snapshot
composition to preserve signed verifier evidence/request bytes through stage
reopen, pass caller-pinned verifier keys to approval preparation and pass them
again through enrolled mock CLI consumption. Its local synthetic REST twin
reaches one same-run mock receipt with the exact stage digest and
idempotency key. Focused suite: 27 tests (19 passed, 8 skipped); full offline
suite: 1349 tests (1333 passed, 16 skipped); `git diff --check` clean. The
actual public/Docker test was skipped because both opt-ins were false and the
exact pinned runtime was unavailable; no readiness/snapshot GET or Docker run
occurred. This does not refresh public-runtime evidence after EXP-737. Worker
and verifier remain synthetic/non-independent in the updated composition;
authority/OOB trust, authenticated human identity and real PR publication stay
open. R2/MVP remain OPEN.

Batch LY / EXP-744 made its one authorized public-read-only attempt after the
EXP-743 signed-profile assertion fix. Both exact cached Docker image
preflights passed. The test made exactly one anonymous readiness GET and
received HTTP 200 with `remaining=31`, below its required threshold of 35
(reported reset epoch `1791545485`). It stopped before commit/tree/blob GETs,
raw Git fetch, Docker containers, snapshot intake, stage, approval or mock
receipt. No retry or other external request occurred. This result refreshes no
snapshot/runtime evidence. No credential, live Worker/model, human approval,
provider write, branch, PR, push or deployment occurred. A future public run
requires a fresh exact card; R2/MVP remain OPEN.

Batch LZ / EXP-745 passed its one fresh public/Docker integration after the
recorded rate-limit reset. The test's assertions confirm eligible readiness,
the exact pinned 23-file commit/tree/content digest, one bounded raw-commit
fetch, one runtime invocation, target/verifier execution and a same-run
in-memory mock receipt bound to the stage, with
`identity_authenticated=false`, `external_write=false` and observer
`completeness=partial`. The run took 21.516s. The test did not emit the concrete
stage digest or observer run ID, and its temporary evidence stores were removed;
therefore EXP-745 is blocked at evidence retention and does not provide a
reusable receipt artifact. No live model/key, human approval, provider write,
branch, PR or deployment occurred. EXP-747 adds opt-in sanitized success
evidence without external access; R2/MVP remain OPEN.

Batch MB / EXP-747 adds a test-only opt-in `AGENT00X_EMIT_PUBLIC_SNAPSHOT_EVIDENCE`
to emit one validated, content-free JSON summary only after the guarded public
integration has passed all assertions. It contains fixed snapshot/stage digest,
observer ID, bounded request counts and mock-only flags; normal test runs remain
quiet. Synthetic emitter test passed; remote pipeline suite: 28 tests (20
passed, 8 skipped); full offline suite: 1353 tests (1337 passed, 16 skipped);
`git diff --check` clean. No external access, Docker or credential was used in
EXP-747. EXP-748 is a fresh one-shot public card after a conservative reset
boundary; R2/MVP remain OPEN.
Final offline review additionally requires the exact pinned commit/tree/content
digest, 23-blob count and exact bounded request/runtime counters before emitting;
an over-limit counter produces no record. The strengthened targeted test and
same 28/1353-test suites passed.

## Current R2 continuation — 2026-10-09

Batch MY—ND / EXP-770—775 adds fixed-stage import diagnostics, stages only the
two schema files needed by `observation_store`, separates the Worker wire
protocol from the host HTTPS transport, and verifies environment entries
without assuming Docker ordering. EXP-774 passed a complete synthetic
`DeepSeekProposalWorker` round trip in pinned image
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`:
network-none, read-only root, non-root, all capabilities dropped,
no-new-privileges, bounded resources, exact fixed env, two read-only mounts,
blocked direct-IP/DNS, one fake host response, exact proposal and cleanup.
EXP-773's worker IPC now imports a transport-independent protocol module;
53 focused tests passed at that boundary. EXP-775's standard full offline suite
passed 1387 tests (19 skipped), and `git diff --check` passed.

This evidence uses a synthetic task and fake model response. It does not show
the reusable runtime adapter executing a real pinned repository snapshot, a
live LLM call, independently deployed verifier, authenticated human approval,
real GitHub PR publication, production authority governance or durable
observer evidence. The older EXP-520 proposal and EXP-548 replay remain
historical evidence with their documented trust and retention limitations; no
new provider request or write occurred here. The next card, EXP-776, extracts
the tested boundary into a reusable host-side `ProposalWorker` before composing
it with the exact pinned snapshot/verifier/stage pipeline. R2/MVP remain OPEN.

## R2 follow-up — reusable Worker and pinned-snapshot attempt

Batch NE / EXP-776 extracted `ContainerProposalWorker`: the host keeps the
model channel injected, while the actual proposal worker runs in the pinned
network-none image. Focused offline suite: 32 tests (one opt-in skip); the
single pinned-container run passed 15 tests, with one fake host response,
isolation inspection and cleanup.

Batch NF / EXP-777 connected it to the exact anonymous public snapshot for
`SoldatovAlexander/brainbooster_full_v11` at
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`. The one opt-in composition reached
the target test after the container Worker returned its proposal, then failed
at fixed `sqlite-range-status`. The target test rejects out-of-range SQLite
integers; the current synthetic candidate catches parse errors but lacks the
signed-64-bit check. Independent verifier, exact stage/readback, preview and
mock receipt were not reached. This is not a Worker transport failure and is
not accepted as a passing repository-change slice. The public operation was
read-only; no credential, live model, approval or provider write occurred.

Batch NG / EXP-778 is the fresh follow-up to strengthen and test that synthetic
candidate, then make one new pinned pipeline attempt. R2/MVP remain OPEN; live
Worker, verifier independence, authenticated digest-bound approval, real PR,
durability and production trust gates remain unproven.

EXP-778 locally hardened only the synthetic route candidate: bool, fractional,
non-finite, unparseable and signed-64-bit-overflow inputs across five numeric
fields fail before writes; one valid row inserts once. The 7-test offline suite
and `git diff --check` passed. Its one anonymous pinned-snapshot read for the
new candidate digest returned HTTP 403 with no digest/source output. No Docker
preflight or integration rerun occurred and no retry was made. The candidate
digest was subsequently recovered under EXP-779 from the read-only preserved
EXP-614 stage artifact for the same repository/commit, after validating the
recorded Git blob SHA-1 for `backend/routes.py`. The resulting candidate digest
is `sha256:6166fc4c2a73db910a064de140e71f7bfcbebe3b99846651a3c69770cce39a18`.
This is reproducible historical local evidence, not a fresh public read or a
new end-to-end run. HTTP 403 remains recorded without retry; no Docker
preflight or integration rerun occurred, and no new verifier, stage, approval
or publication evidence was added. R2/MVP remain OPEN.

Batch NI / EXP-780's one fresh pinned run successfully fetched and validated
the 23-blob target snapshot, obtained one ContainerProposalWorker proposal,
passed the target regression and pinned Docker verifier, and verified the
temporary durable-stage readback and preview assertions. It failed at the
test's local-mock call with `TypeError` because a required `base_branch` was
omitted. The mock function was not invoked, no receipt was created, and the
temp stage/evidence was not retained. This exposes a stale test harness call,
not a failure of the Worker/verifier or target fix. No retry or provider write
occurred. EXP-781 permits one new full attempt after passing `master` as the
local mock base branch; independent verifier trust, authenticated human
approval and real PR publication remain unproven.

Batch NJ / EXP-781 corrected the stale local-mock test call with base branch
`master` and passed one fresh full pinned composition in 17.127s. The 23-file
snapshot matched commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, tree
`2007066217aadafd9887fb3e3069220333b4fddb`, and content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
The one Worker proposal produced candidate digest
`sha256:6166fc4c2a73db910a064de140e71f7bfcbebe3b99846651a3c69770cce39a18`;
target and pinned container verifier passed; stage readback and verified
contents digest `sha256:1bbc49027fbf0a5dabe069bdf320b731c21ec346c95479ddefa216c3a439342d`
matched; preview remained `not_created`/`not_attempted`; local mock receipt
matched stage digest
`sha256:5dd2032094128b666ba178b5fe1b76fbe91f0b65693f9132138f236e5293ef00`.
The sanitized evidence record reported zero provider calls, no credential and
no external write. This establishes a reproducible local composition, not
independent trust-domain verifier operation, authenticated approval or real PR
publication. R2/MVP remain OPEN.

Batch NK / EXP-782 did not retain the new stage: after its 15-test focused
suite and successful pinned image/path preflights, the only anonymous snapshot
attempt returned sanitized HTTP 403 on a blob GET before Worker execution.
No target/verifier run, stage output, receipt or retry occurred. The prescribed
no-overwrite destination remains absent. A fresh task must use a distinct
public read path/source or wait; this failure is not evidence against the
Worker or verifier. R2/MVP remain OPEN.

EXP-784 then made one codeload GET with the repository's verified TLS context;
the returned in-memory archive had one root and 23 regular files, exact pinned
content digest, and route Git blob SHA-1 matching EXP-614. No archive bytes
were saved. Since the current snapshot evidence-origin model only accepts REST,
this remains source-validation evidence and has not been passed into execution.
EXP-785 added that typed archive source adapter. It keeps REST and codeload
origins distinct, uses the existing verified CA context and a one-shot
fixed-host transport, and validates blob, tree and content digests in memory
with path/type/size limits. The archive origin propagates through executor and
publication-seed binding with its own claim canonicalization. Offline focused
suite: 224 tests (10 skipped); full suite: 1408 tests (19 skipped);
`git diff --check` clean. EXP-786's one codeload GET reached the parser but
failed the exact-permission check before candidate digest verification and
before Worker execution; no stage output was written and no retry occurred.
The archived mode format differs from Git's compressed executable/non-executable
mode model. EXP-787 fixed this mapping and passed all 1409 offline tests (19
skipped). Its single codeload composition passed archive, Worker, target,
verifier and stage readback, but `stage_copy` rejected the temporary path
because it was not canonical; the new destination and local mock receipt were
not created. A local check confirmed tempdir paths need `.resolve()` on this
macOS host. EXP-788 corrects that caller path and allows one fresh composition.
No real approval/provider publication is authorized or performed.

EXP-788 passed the fresh codeload-origin composition in 5.741s and retained
the exact stage at `/Volumes/DATA/Agent00X-local-evidence/exp788-stage.sqlite3`
using no-overwrite stage copy. Stage and local mock receipt are bound to
`sha256:e66f65b6be74cc70dc6aa3a8cec658bc65c30051bddd9adb3d74536d4c347f51`;
the copied DB SHA-256 is
`991d4ffa21145432ba7f926c390c7d9f8d262b2604e31c70623d01424a66e46d`, with
artifact digest
`sha256:004b9583e19c1eb08506e792c97701803853f4a40a3b5672d36f75070452c8df`.
The sanitized record retained archive provenance, snapshot/candidate/verified
digests and verifier identity; no credential, provider call or external write
occurred. Batch NR below records the follow-up through the existing request and
synthetic signed-mock CLIs against this exact retained stage; real human approval
and PR remain unproven.

Batch NR / EXP-789 exercised the saved EXP-788 SQLite stage through both
existing operator CLI entry points. The opt-in subprocess test first generated
an unsigned request bound to the exact stage/artifact/verified-content digests,
then signed it only with the deterministic test fixture key and supplied a
short-lived authority enrollment signed by a key generated in process. The
signed-mock CLI emitted a same-stage `mock_published` receipt. The exact stage
database SHA-256 before and after remained
`991d4ffa21145432ba7f926c390c7d9f8d262b2604e31c70623d01424a66e46d`.
Focused: 1 test passed; standard offline suite: 1410 tests, 20 skipped;
`git diff --check` clean. The harness is skipped by default and uses temporary
test artifacts only. This is digest-bound CLI/mock evidence—not authenticated
human identity, a production trust anchor, a separately trusted verifier or a
real PR. No provider request/write, credentials, branch, push, deployment or
commit occurred. R2/MVP remain OPEN.

An offline EXP-791 preflight attempted to feed a typed codeload claim into the
existing signed-verifier operator composition. It failed closed before Worker
execution at `PinnedSnapshot.validate-fixed-pin`; inspection confirmed the
operator CLI hardcodes REST intake and requires a raw commit object. Codeload
uses archive/tree/content pins and has no raw commit object. No provider or
network operation occurred. Batch NT updates the scope to add a dedicated
Control Plane-selected archive-origin runtime path while preserving the REST
path and both pin contracts. Until then, the saved codeload stage cannot reach
the operator approval CLI with signed verifier evidence. R2/MVP remain OPEN.

Batch NT / EXP-791 is implemented and accepted after local Control Plane review.
The fixed operator card profile selects either REST or codeload (REST default),
and the single-use permit is bound to that selection. Codeload intake validates
the pinned archive claim without accepting a raw commit object; REST retains its
verified raw-commit requirement. Observer evidence includes only the fixed
`GitHubCodeloadArchive.GET.archive` label and bounded status, not archive bytes
or URL. The offline synthetic composition reached approval-request generation
and an enrolled signed-mock receipt with `identity_authenticated=false` and
`external_write=false`. Focused suite: 147 tests, 10 skipped. Full offline
suite: 1415 tests, 20 skipped. `git diff --check` passed. The archive reader,
verifier signer and approver/authority material in this integration are
synthetic; there was no actual archive GET, independent verifier host, live
Worker/provider call, credential, human identity, external write, branch/PR,
push, deployment or commit. This advances local trust plumbing only; R2/MVP
remain OPEN.

Batch NU / EXP-792 adds one subprocess composition test for the signed verifier
HTTP service. The child generates its Ed25519 signing key in memory, binds an
OS-assigned IPv4 loopback port and handles exactly one synthetic request; the
parent verifies the returned signature against the exact fixture/profile/nonce.
The test suite for this component passed 9 tests; the full offline suite passed
1416 tests (20 skipped). This is process separation on the same host over local
HTTP, with a synthetic verifier. Attestation and client still report
`independent_host_trust_established=false`; no host-trust promotion, remote
deployment, credential use, live Worker/provider request, or publication
occurred. R2/MVP remain OPEN.

Follow-up Batch NS / EXP-790 corrected an approval-boundary gap exposed by
EXP-789: approval preparation had required signed verifier provenance for
`github_rest_api_claim` but not `github_codeload_archive`. The check now applies
to both remote origins. The retained EXP-788 codeload stage, which has no signed
verifier evidence, exits the real approval-request CLI with code 2 and no stdout
request; its SQLite bytes remain unchanged. The approval unit suite passed 11
tests, the opt-in retained-stage gate passed 1 test, the full offline suite
passed 1411 tests (20 skipped), and `git diff --check` passed. EXP-789 remains
valid as CLI-plumbing evidence only and is explicitly not approval-eligibility
evidence. No network/provider call or write, credential, approval signature,
branch, PR, push, deployment or commit occurred. R2/MVP remain OPEN.
