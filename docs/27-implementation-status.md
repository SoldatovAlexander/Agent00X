# Статус реализации и доказательств

Статус: единственный оперативный статус проекта

Версия: 1.1

Дата сверки: 2026-10-08

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
production end-to-end система: происхождение snapshot — GitHub API claim,
verifier доверен только в same-host/container контуре, signer синтетический,
mock и fake-provider evidence не равны реальной publication, а текущий project
working tree не содержит persisted SQLite stage из EXP-520. Production runtime,
independent verifier trust, signer enrollment, durable recovery и real PR
остаются открытыми; observer collector, отчёты и учебные ветки также не
реализованы.
Нельзя заявлять production-ready, отсутствие всех утечек секретов или доказанную
неуязвимость Gateway.

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
blob contents не читались. Это public API claim, не signature/authorship
evidence. General caller-selected remote input не поддержан; фиксированный
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
на текущей ОС и явно пропускает узкий тест с объяснением. Key-provider callback,
DNS cancellation и upload backpressure остаются без доказательства.
Batch BP connected `DeepSeekProposalWorker` to the real channel and a loopback
verified HTTPS stub, producing only a fixed synthetic proposal. It verifies
adapter composition, not model inference or useful target work.
EXP-508 now starts the monotonic budget before credential lookup and rejects a
callback that returns after expiry before constructing the HTTP connection. A
synthetic slow-callback test proves no request is initiated. The synchronous
callback still cannot be interrupted if it never returns, and DNS resolution
runs inside `connection.request` before a socket may exist for the watchdog to
shut down. Thus this is not an end-to-end hard deadline; loopback interruption
evidence still does not prove cancellation of a blocked callback or DNS lookup.
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
cap не подтверждён. Текущий checkout не содержит stage DB, а точные временные
пути stage DB из EXP-520 и EXP-548 сейчас также отсутствуют. Поэтому approval
CLI на фактическом candidate stage пока не запускался. Остаются independently
trusted verifier и authenticated snapshot provenance; hard transport/runtime
timeout (включая синхронный credential callback, DNS и upload interruption);
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
same-host evidence and the snapshot remains an unsigned GitHub API claim.
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
snapshot provenance remains an unauthenticated GitHub API claim, and the
same-host verifier is not independently trusted. Accepted as a live Worker-to-
stage experiment, not as R2 exit evidence.

### R2 exit matrix (remote metadata rechecked 2026-10-07; local suite updated 2026-10-08)

| Gate | What current evidence demonstrates | Evidence still required for R2 exit |
|---|---|---|
| Fixed remote repository snapshot | One fresh anonymous fixed-CLI intake returned `snapshot_ready`, `authenticated=false`, exact pinned commit/tree, 23/23 file metadata and full content digest; each Git blob ID and the complete recursive root tree ID are recomputed from content/entries. | Commit-object bytes, signature/authorship and remote provenance evidence; API/TLS claim alone is insufficient. |
| Worker change | Batch DK / EXP-520 made one expressly authorized live DeepSeek call against the exact pinned public snapshot; it produced a useful single-file `backend/routes.py` proposal and verified stage. EXP-548 rehydrated that stored output unchanged and reproduced PASS with a new exact-digest stage through the same pinned target/verifier pipeline, without another model call. | Independent verifier trust, authenticated snapshot provenance, verified provider/account-level spend cap, and a trust boundary around the in-process credential callback remain open; no retry or publication was performed. |
| Bounded execution and test | Batch BA directly executed the exact pinned route blob; Batch BE exercised selected pinned app modules with real Uvicorn loopback HTTP in exact Python 3.11.16 image, `container-network-none`, `network_isolated=true`: malformed integer produced 500 / zero rows; valid produced 200 / one exact row. Batch BF (EXP-463) tested a fixed Control Plane patch in only the writable container copy: every malformed numeric field plus overflow returned HTTP 422 / zero writes, while valid input remained 200 / one exact row. EXP-548 replayed the live Worker candidate from the persisted stage against the full 23-blob exact snapshot; the pinned HTTP/DB verifier returned PASS and the new exact SQLite stage/readback matched the verified contents. | Independently governed verifier trust and authenticated snapshot provenance remain open; pin full app runtime/dependencies, timeouts and production recovery. |
| Independent verification | Verifier input/result cross a bounded child-process JSON boundary and re-run the test. EXP-510 also completed a synthetic stage through the actual pinned Docker verifier image. | Verifier in a separately trusted implementation/environment with an authenticated, replay-resistant result; same-host process/container separation is insufficient. |
| Durable stage and human approval | Validated canonical stage artifact is stored/reloaded through local SQLite; exact-digest readback is required before VERIFIED. EXP-552 exports an unsigned review request; EXP-553/554 use a synthetic signer for policy/mock-chain evidence. EXP-558 rebuilds that request from the saved stage and verifies a signed envelope through policy without effects. EXP-563 wraps the exact-stage signed verification and controlled mock path in a bounded local operator CLI. | No historical EXP-520/548 stage DB currently exists at its recorded paths, so the verifier CLI has not consumed the live Worker stage. Authenticated production approval, trusted human signer enrollment and production durability/recovery guarantees remain absent; the supplied trust profile itself is not authenticated. |
| Controlled Pull Request publication and recovery | Fake-only GitHub App composition binds the verified manifest to the seed and journals before branch/file effects (EXP-541); post-loss exact read-only blob-SHA confirmation (EXP-542), reopen file-state evidence (EXP-543), and fake PR receipt recovery without duplicate POST (EXP-537/538). EXP-545 binds explicit base branch; EP/EQ (EXP-550/551) bind source slug and installation-scoped ID and exercise fake provider response-loss recovery. EXP-554 proves the approval format passes controlled mock gates; EXP-563 adds a local mock-only CLI. EXP-573 adds a fixed-target live-capable GitHub App CLI behind an exact-digest terminal confirmation, tested only with fake transports and synthetic approval. | EXP-573 has not been run and provides no live PR receipt. No current project artifact contains the persisted EXP-520/548 Worker stage; the publication CLI has not consumed a real Worker stage or authenticated human approval. Still missing: trusted signer enrollment, fresh authorization for provider use, real PR receipt, independently trusted verifier, and production-grade durable recovery demonstrated against the approved provider without blind retry. No direct credentials to Worker or verifier; no multi-file atomicity claim. |

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
| R2: сквозной исполнитель | Локальная серия Batch AF–AH завершена: 3/3 батча по 20 карточек; Batch AI: 20/20; Batch AK: исходно 7/10 ACCEPTED и 3/10 исторически BLOCKED, bounded follow-ups EXP-392—394 приняты; AL: 4/5 + 1 DRAFT; AM: 5/5, у EXP-404 раскрыто локальное исключение; AN: 4/5 + 1 BLOCKED; execution continuation: AO—BI = 21 батч (AO 5/5, AP 4/5 + 1 DRAFT, AQ–AT 5/5, AU 1 ACCEPTED + 1 BLOCKED + 3 DRAFT, AV 5/5, AW 5/5, AX 1/1, AY 1/1, AZ 1 BLOCKED, BA 1/1, BB–BD по 1 BLOCKED, BE 1/1, BF 1/1, BG 1/1, BH 1/1, BI 1 BLOCKED); BJ — docs-only сверка; BK — 22-й рабочий батч, EXP-468 accepted 1/1; BL — 23-й рабочий батч, EXP-469 accepted 1/1; BM — 24-й рабочий батч, EXP-470 accepted 1/1; BN — 25-й рабочий батч, EXP-471 accepted 1/1; BO — 26-й рабочий батч, EXP-472 accepted with one explicit upload-backpressure skip; BP — 27-й рабочий батч, EXP-473 accepted 1/1; BQ — 28-й рабочий батч, EXP-474 portable credential-source contract (synthetic-only); BR — 29-й рабочий батч, EXP-475 sanitized HTTP-status diagnostic; BS — 30-й рабочий батч, EXP-476 safe CLI status code; BT — 31-й рабочий батч, EXP-477 accepted, anonymous rate-limit preflight `HTTP 200` / `60` remaining; BU — 32-й рабочий батч, EXP-478 one fresh-state pinned pipeline attempt, exact snapshot verified but stopped before code execution; BV — 33-й рабочий батч, EXP-479 candidate digest correction verified locally, full suite 905 tests / 4 skipped, pipeline gated because the one-shot preflight output was unavailable; BW — 34-й рабочий батч, EXP-480 accepted with `HTTP 200` / 35 remaining; BX — 35-й рабочий батч, EXP-481 blocked before target execution by trailing whitespace in test command; BY — 36-й рабочий батч, EXP-482 accepted with `HTTP 200` / 10 remaining, below the 25-call threshold; BZ — 37-й рабочий батч, EXP-483 enforces one fake-only provider attempt per channel instance; CB — 38-й рабочий батч, EXP-485 adds an offline command-shape regression for the EXP-481 error; CC — 39-й рабочий батч, EXP-486 proves lease cleanup on that rejection; CD — 40-й рабочий батч, EXP-487 wires fail-closed pinned remote execution CLI with sanitized digest evidence; latest suite: 916 tests, 912 passed, 4 skipped. Batch BE подтвердил actual local HTTP baseline (500/no-write); BF проверил control-plane-proposed 422 candidate только в ephemeral copy; BG добавил fake-only DeepSeek HTTPS channel; BH потребовал exact-readback durable stage в remote composition и связал его с preview и mock-only typed-digest approval; BK—BM подтвердили cancellation сетевых phases watchdog/loopback tests; BN подтвердил TLS handshake interruption; BO не смог reproducibly block bounded upload на текущей ОС; BP подтвердил только локальную синтетическую цепочку Worker/HTTPS/proposal; BQ закрепил только portable interface, без OS vault adapter; BR сохраняет только status code, не response body, без retries; BS пробрасывает только numeric status в CLI failure code. Полезное поведение тестировалось, но candidate не получен от Worker и не сохранён; live model, trusted verifier, authenticated approval, production durability, real PR/recovery остаются открыты. Provider writes require separate authorization. |
| R3: исторический Observer | Не начат | Отчёты по сохранённой истории, причинности и пробелам |
| R4: учебная ветка | Не начат | Simulation branch без переноса старых прав и external writes |
| R5: эксперимент | Не начат | Сравнение полной и упрощённой организации данных по заранее заданному набору задач |

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
