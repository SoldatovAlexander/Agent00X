# Итоговый план MVP: Thin Vertical Slice

Статус: исследовательский прототип; план уточнён, реализация не завершена

Версия: 1.1

Дата: 2026-09-07

## 1. Цель

Проверить, позволяет ли предложенное представление целей, данных, состояния,
правил и полномочий исполнять агентом проработанную бизнес-функцию. Подтверждение
этой возможности является самостоятельным результатом; коммерческая экономия
не служит предварительным условием продолжения эксперимента.

Первый сквозной сценарий:

> агент подготавливает и проверяет изменение программного проекта, после чего
> инициирует публикацию Pull Request, не имея прямого доступа к GitHub и не
> получая credential ни в prompt, context, environment, workspace, trace или
> artifact.

MVP не является универсальной агентной платформой. Это минимальный вертикальный
срез Process, Execution и Authority Plane, достаточный для проверки главных
trust boundaries. Наблюдатель и обучение через контролируемое ветвление входят
в исследовательское ядро. Полная спецификация: [документ 28](28-observer-and-learning.md).

### Актуальная последовательность после переоценки

Этот порядок имеет приоритет над исторической последовательностью M0—M4 ниже.
Названия старых milestones сохраняются для связи с уже выполненной работой.

1. **R0 — постановка и контракты наблюдения.** Зафиксировать исследовательскую
   гипотезу, сценарии, формат события, checkpoint, LearningCorrection и memory
   summary. Концептуальная часть выполнена документами 28 и 30; машинные схемы
   и тесты ещё нужны.
2. **R1 — целостность и фиксация действий.** Закрыть подмену manifest после
   verification и рассогласование digest actuator request с approval. Сохранять
   checkpoint каждого решения и вызова до исполнения, в том числе для субагентов.
   При отказе журнала блокировать очередное действие. Добавить негативные тесты.
3. **R2 — реальный сквозной исполнитель.** Remote snapshot конкретного commit,
   один LLM Worker, независимая проверка, минимальный CLI и контролируемая
   публикация. Все проверки до внешнего write; реальные границы секретов и
   durable reconciliation. Основные пути R2 инструментированы наблюдением R1.
   Срез на 2026-10-07: этап R2 не завершён. На checkpoint до DI—DL было 70 батчей: 63 приняты и семь заблокированы (CN, CO, CS, CT, CW, CZ, CX). После него приняты DI / EXP-518 (71-й), DJ / EXP-519 (72-й) и DL / EXP-521 (74-й); DK / EXP-520 (73-й) на том checkpoint ещё оставался DRAFT. Тогда нумерация дошла до 74-го батча: 66 приняты, 7 исторически заблокированы, 1 DRAFT. CX / EXP-507 остановлен до readiness после первого preflight miss; отдельные Batch DC / EXP-512 и DD / EXP-513 подтвердили точный image в активном `desktop-linux` context. DE / EXP-514 принят 67-м: fresh readiness HTTP 200 / 60, exact-pin pipeline и stage-to-mock receipt прошли; это не live Worker. DF / EXP-515 принят 68-м: добавлен profile helper с injected `CredentialSource`; он не читает ключ. DG / EXP-516 принят 69-м: добавлен импортируемый runtime entrypoint, собирающий pinned Docker sandbox, verifier и SQLite stage для CLI; он пока не вызывался. DH / EXP-517 принят 70-м: remote CLI теперь требует свежий одноразовый permit и explicit Control Plane provider-call approval; live readiness запрос не выполнялся. CY / EXP-508 принят 61-м (поздний возврат callback блокирует HTTP), CZ / EXP-509 заблокирован 62-м (Docker verifier PASS, stage persistence отказал из-за verifier ID contract mismatch), DA / EXP-510 принят 63-м (exact Docker identity проходит через synthetic stage/readback/preview/mock receipt, не live Worker), DB / EXP-511 принят 64-м. CP, CQ, CR, CU, CV, CY, DA, DB, DC, DD, DE, DF, DG, DH и DL приняты:
   AO—BI (21), BK (22-й), BL (23-й), BM (24-й), BN (25-й), BO (26-й), BP (27-й), BQ (28-й), BR (29-й), BS (30-й), BT (31-й), BU (32-й), BV (33-й), BW (34-й), BX (35-й), BY (36-й), BZ (37-й), CB (38-й), CC (39-й), CD (40-й), CE (41-й, post-reset readiness принята: HTTP 200 / 60), CF (42-й, one-shot pipeline остановился до target execution на claim mismatch), CG (43-й, локальная коррекция mode preservation принята), CH (44-й, readiness после коррекции: HTTP 200 / 60), CI (45-й, повторный one-shot остановился на том же claim mismatch), CJ (46-й, локальная синтетическая диагностика executor claim/replay прошла), CK (47-й, metadata-only CLI исправлен и проверен fake tests), CL (48-й, readiness + metadata-only size diagnostic принят), CM (49-й, verifier snapshot per-file bound выровнен с source reader), CP (52-й, exact fixed rejection marker classified safely), CQ (53-й, child-side allowlisted failure categories added), CR (54-й, bounded child exit status exposed), CU (57-й, verifier startup stderr safely classified as python-import), CV (58-й, lazy remote imports allow the minimal verifier image to load; 220064-byte synthetic file gets bound PASS; full suite 927 tests, 921 passed, 6 skipped);
   Последующее обновление после EXP-544: нумерация дошла до R2 execution batch
   97; из последовательного продолжения AO—EJ принято 86, исторически
   заблокировано 10, а EXP-520 / Batch DK тогда оставался DRAFT. После одного
   разрешённого live Worker-прохода EXP-520 принят; состояние R2 всё ещё OPEN,
   поскольку независимый verifier, authenticated provenance, production
   approval и publication gates не закрыты.
   Batch DM / EXP-522 закрепил verifier HTTP/DB команду (`python3 -c` из
   `tests/test_remote_target_stage_pipeline.py`) с timeout 30 секунд и container
   timeout 60 секунд; один bounded run на четырёх pinned source files прошёл
   malformed 422/zero rows, overflow 422/zero rows и valid 200/one exact row.
   Full offline suite after EXP-522: 945 tests, 938 passed, 7 skipped.
   Batch DN / EXP-523 получил readiness HTTP 200 / 60 и проверил точный
   23-blob snapshot, но его единственная full-pipeline попытка завершилась в
   `prepare_change`: allowlisted target test command завершился ненулевым кодом,
   но обработчик выдавал только общее `verification failed; staged change was
   not created`; независимый verifier не запускался. Stage и mock receipt
   не созданы, повтор не выполнялся. Это не full-snapshot code execution, live
   Worker, independent-host verifier или publication evidence. Batch DO /
   EXP-524 добавил фиксированные диагностические маркеры для следующего
   bounded target test без вывода произвольного stdout/stderr; focused tests и
   full offline suite (947 tests, 940 passed, 7 skipped) прошли. Причина
   EXP-523 пока неизвестна; DP / EXP-525 повторно получил точный snapshot и
   candidate digest после readiness HTTP 200 / 35, но остановился до sandbox:
   daemon активен, а
   закреплённый Python base image отсутствовал. DQ / EXP-526 получил base
   image анонимно по digest (`sha256:8b29…`); выяснено, что это отдельный образ
   от подготовленного target runtime (`sha256:96cb…`). DR / EXP-527 выровнял
   pipeline test с target runtime и подтвердил его зависимости offline; full
   suite — 948 тестов, 941 пройден, 7 пропусков. Новая pipeline-попытка ещё не
   проводилась; EXP-528 заблокирован до snapshot intake: readiness вернул 10
   remaining и reset `2026-10-07T14:46:32Z`. Batch DU / EXP-530 затем прошёл
   одну synthetic CLI-композицию с Docker target/verifier и SQLite exact
   readback; full suite — 949 тестов, 941 прошёл, 8 пропусков. GitHub не
   запрашивался. DV / EXP-531 связал DeepSeek Worker/HTTP adapter с CLI, Docker
   target/verifier и SQLite exact readback через in-memory fake connection;
   950 тестов, 941 прошёл, 9 пропущено. Реальный TLS/model/credential не
   использовался. DT / EXP-529 после reset получил readiness HTTP 200 / 60 и
   ровно одну full pinned-snapshot попытку: все 23 blob прошли проверку
   snapshot digest; fake Worker предложил fixed candidate; target network-none
   test подтвердил HTTP 422/no-row для malformed и HTTP 200/one-row для valid
   input; Docker verifier, exact SQLite stage/readback, preview и local mock
   receipt прошли с одним digest. Test — 18.946s; полный suite — 950 тестов,
   941 passed, 9 skipped; `git diff --check` чист. Credential, live model и
   provider write не использовались. Это не live Worker, independently trusted
   verifier, authenticated approval, production recovery или real PR.
   DX / EXP-533 закрыл SQLite connections в observation-store test fixtures:
   tracemalloc-enabled focused suite (58 tests) прошёл без ResourceWarning,
   полный suite — 950 тестов, 941 passed, 9 skipped, также без ResourceWarning.
   Это устраняет загрязнение stderr следующего CLI test, но не меняет product
   code и не закрывает production durability/recovery gate. DY / EXP-534
   добавил отдельную SQLite запись локального typed-digest confirmation: exact
   stage digest и intent сохраняются и перечитываются до mock-gate, после чего
   запись связывается только с ID mock receipt. CLI явно сообщает
   `authenticated=false`, `external_write=false`; это не production approval.
   Семь focused tests и полный suite прошли: 952 теста, 943 passed, 9 skipped;
   `git diff --check` чист. DW / EXP-532 связал CLI-generated stage с local typed-digest
   rejection/acceptance и mock PR receipt под тем же digest/repository/branch;
   это не authenticated approval, real PR, production recovery или live
   snapshot pipeline.
   Batch DZ / EXP-535 устранил локальный request-shape gap для обновления
   существующего файла: fake-only GitHub adapter tests подтвердили Contents GET
   на exact base commit до branch/file writes и передачу validated blob SHA в
   Contents PUT; malformed/unknown metadata блокирует writes. Targeted suite —
   56 tests, full suite — 955 tests / 946 passed / 9 skipped. Ни один GitHub
   запрос не выполнялся. Это не подтверждает реальную публикацию, атомарность
   нескольких файлов или durable recovery; R2 остаётся открытым.
   Batch EA / EXP-536 добавил fake-only recovery по состоянию candidate branch:
   после simulated lost PUT response новый channel распознал уже записанный
   desired blob и не повторил PUT; для частичного двухфайлового результата он
   пропустил готовый файл и записал только оставшийся файл с base SHA. Любая
   третья версия блокирует все дальнейшие PUT этого retry. Focused suite — 59
   tests; full offline suite — 958 tests / 949 passed / 9 skipped. Нет live
   provider evidence, durable local journal integration или production recovery.
   Batch EB / EXP-537 связал SQLite `PublicationJournal` с типизированным
   `GitHubPullRequest`: старая таблица мигрируется с nullable receipt URL; fake
   PR был создан с потерей ответа, а после reopen точные ID/URL восстановлены
   read-only lookup-ом без второго POST. Пустой результат переводится в
   `reconciliation_required`. Targeted suite — 96 tests; полный suite — 963
   tests / 954 passed / 9 skipped. Это не real provider или production
   durability evidence; approvals и controlled live publication остаются
   открытыми. Batch EC / EXP-538 соединил typed GitHub App channel с теми же
   approval → policy → slow gateway → broker → SQLite journal gates, что и
   mock endpoint. Fake GET/POST показали создание PR, потерянный ответ и
   точное read-only восстановление ID/HTTPS URL без повторного POST. Это
   локальная композиция, а не live publication, production approval или
   доказанная durability; реальная публикация остаётся отдельным gate.
   Batch ED / EXP-539 добавил отрицательные integration tests для этой
   композиции: missing approval, policy deny и gateway deny не вызвали token
   mint или fake provider transport, а SQLite publication journal остался
   пустым. Targeted suite — 117 тестов; полный suite — 965 тестов, 956 passed,
   9 skipped. Это подтверждает только локальный fake-only порядок отказов.
   Batch EE / EXP-540 заменил spoofable module/name check на регистрацию и
   сверку точных type identities broker, channel и receipt; lookalike broker и
   channel отвергаются до stage loading и любых side effects, а gate module не
   импортирует provider adapter напрямую. Targeted suite — 118 тестов; полный
   suite — 966 тестов, 957 passed, 9 skipped. Identity registry — wiring внутри
   trusted процесса, не защита от произвольного кода в том же процессе.
   Batch EF / EXP-541 связал digest-bound проверенный file manifest с записью
   в candidate branch до создания PR под теми же approval/policy/gateway/broker
   gates и journal. Fake transports подтвердили порядок branch → file PUT → PR;
   потеря PR-ответа восстанавливается read-only без второго POST, а потеря
   ответа на file PUT останавливает цепочку до PR и переводит journal в
   `reconciliation_required`. Полный suite: 968 тестов (959 passed, 9 skipped).
   Это не live publication, multi-file atomicity или production recovery.
   Batch EG / EXP-542 добавил одну read-only сверку ref и Git blob SHA полного
   verified manifest после потери ответа file PUT. PR продолжается в той же
   попытке только при точном полном совпадении; иначе нет PR POST или повторных
   записей и journal остаётся `reconciliation_required`. Полный suite: 969
   тестов (960 passed, 9 skipped). Это не cross-process resume, атомарность
   нескольких файлов или live-provider evidence.
   Batch EH / EXP-543 добавил restart-time read-only reconciliation: после
   reopen matching PR закрывает ту же receipt, а при отсутствии подтверждённого
   PR journal остаётся `reconciliation_required` и сохраняет digest-only
   результат проверки candidate-branch files с UTC timestamp. Ожидаемый
   manifest digest привязан к journal до provider effect; несовпадение
   блокируется до GET. Публикация не возобновляется и старое approval не
   переиспользуется. Полный suite: 972 теста (963 passed, 9 skipped). Это local
   SQLite/fake evidence, не cross-host/production durability.
   Batch EJ / EXP-544 завершает ту же попытку после restart только если
   повторный read-only GET по исходному idempotency key находит exact typed PR
   receipt; absent/mismatched receipt сохраняет `reconciliation_required`, без
   POST/PUT, а digest-only file evidence остаётся. Targeted suite: 100 tests;
   полный suite: 973 теста (964 passed, 9 skipped); `git diff --check` чистый.
   Это fake-only локальное evidence, не live-provider recovery.
   Batch EK / EXP-545 (98-й рабочий execution batch) убрал hardcoded PR base:
   явная ветка проходит через intent/approval, actuator, GitHub/mock adapter и
   idempotency key; typed receipt и SQLite journal также связывают точную base
   branch. Focused suite — 324 теста (3 пропуска), полный standard unittest —
   974 теста (965 passed, 9 skipped), `git diff --check` чист. Только fake/local
   evidence; live publication, production approval/recovery и MVP остаются OPEN.
   Batch EL / EXP-546 требует явный allowlist `approver_id` в локальной policy
   и отвергает отсутствующий, malformed или неразрешённый claim до gateway и
   broker. Synthetic mock operator ограничен mock path. Это проверка строки,
   не аутентификация человека, проверка подписи или production approval.
   Focused suite — 180 тестов (1 пропуск), полный — 975 (966 passed, 9
   skipped), `git diff --check` чист; R2/MVP остаются OPEN.
   Batch EM / EXP-547 добавляет Ed25519-проверку подписи approval, привязанной
   к approver ID, intent/stage digest, репозиторию, policy и срокам. Synthetic
   mock signer и тестовый private key не дают production-auth evidence: enrollment,
   custody, revocation, human identity и independently trusted policy остаются
   открытыми. Focused suite — 229 тестов (1 пропуск), полный — 978 (969 passed,
   9 skipped), `git diff --check` чист; R2/MVP остаются OPEN.
   Batch EN / EXP-548 без повторного model call загрузил исходный stage EXP-520
   только для чтения, подтвердил тот же public snapshot pin, затем replay-нул
   сохранённое `backend/routes.py` через network-none target и exact Docker
   verifier. PASS, exact SQLite readback и новый stage digest
   `sha256:d9dab36eb53279b5707d05ddd3b73052a912366d613756cb2858b29d9eccf734`;
   verified contents digest совпал с исходным
   `sha256:8a0cd5df060c82eeea111337fccf527d26f0a24618bc3b5dace19cb9ff7a982e`.
   Это воспроизводимый replay сохранённого live Worker output, а не новый live
   вызов; verifier остаётся same-host Docker, snapshot — неподписанным GitHub
   API claim. Focused suite — 65 тестов (3 skipped), полный — 978 (969 passed,
   9 skipped), `git diff --check` чист. Approval и publication не выполнялись;
R2/MVP остаются OPEN.

   Batch EO / EXP-549 добавил `scripts/replay_staged_candidate.py`: он принимает
   только source DB/digest и новый output path, извлекает candidate исключительно
   из проверенной SQLite-стадии, повторно получает exact pinned snapshot и
   использует фиксированные target/verifier/test contracts. Общий already-read
   snapshot executor вынесен в модуль без Worker/credential/approval/publication
   imports; прежний `worker_cli` re-export сохранён. Фейковые offline tests
   подтверждают read-only source, exclusive output, точный candidate, отказ до
   sandbox при bad stage/readiness/pin и чистый CLI import без sensitive adapters.
   CLI не запускалась на внешней цели в этом batch. Focused suite — 76 тестов
   (4 skipped), полный — 985 (976 passed, 9 skipped), `git diff --check` чист.
   Это инструмент воспроизводимости, не новый live Worker, independently
   governed verifier, provenance, approval или publication; R2/MVP остаются OPEN.
   Batch EP / EXP-550 добавил immutable binding между source slug и
   installation-scoped GitHub App repository ID. Verified seed/intent сохраняют
   оба значения; mismatch отсекается до policy/broker, а только копия staged
   metadata переводится в provider identity для file adapter. Focused suite —
   246 passed; полный offline suite — 992 (983 passed, 9 skipped),
   `git diff --check` чист. Binding tested with synthetic IDs only; production
   runtime composition, authenticated approval and real PR остаются открытыми.
   R2/MVP остаются OPEN.
   Batch EQ / EXP-551 (R2 execution batch 104/104) провёл dual identity через
   fake approval→policy→gateway→broker→GitHub App→journal/recovery. Подпись
   покрывает intent с source slug и provider ID; stage record не мутируется;
   response loss после fake PUT/PR восстановлен read-only без второго PR POST.
   Provider-ID mismatch отклоняется до policy, loader, broker, transport и
   journal. Focused suite — 181 passed; полный — 994 (985 passed, 9 skipped),
   `git diff --check` чист. Только synthetic IDs/transports; R2/MVP остаются OPEN.
   Batch ER / EXP-552 (R2 execution batch 105/105) подготовил локальный
   read-only CLI экспорта unsigned approval request из точной verified SQLite
   stage. Полный bounded JSON связывает stage/contents digest, source slug,
   provider repository ID, base commit/branch, head branch, operation, approver,
   policy, approval ID и timestamps; включает patch review и точные canonical
   Ed25519 signing bytes, но не ключ или подпись. Synthetic tests подтверждают
   воспроизводимость и mutation sensitivity для каждого intent/approval field,
   а также неизменность stage DB и отсутствие provider/credential imports.
   Focused suite — 19 passed; полный offline suite — 1000 (991 passed,
   9 skipped); `git diff --check` чист. Человеческая подпись, signer enrollment,
   production runtime composition и publication остаются отдельными gates;
   R2/MVP остаются OPEN.
   Batch ES / EXP-553 (R2 execution batch 106/106) проверил полный
   synthetic signer round-trip: ephemeral Ed25519 key подписывает точные bytes
   из EXP-552 export, после чего существующий `DeterministicPolicy` принимает
   запись только для точной стадии/intent и allowlisted public key. Изменённый
   intent отвергается по digest mismatch. Это unit-test policy decision без
   downstream effects, а не подпись человека/enrollment или публикация.
   Focused suite — 40 passed; полный offline suite — 1001 (992 passed,
   9 skipped); `git diff --check` чист. R2/MVP остаются OPEN.
   Batch ET / EXP-554 (R2 execution batch 107/107) протянул экспортированный
   approval, подписанный только временным synthetic Ed25519 signer, через
   Approval→Policy→slow Gateway→single-use Broker→SQLite journal→
   `MockGitHubEndpoint`. Получен один mock receipt с теми же target/branch/base/
   stage/idempotency bindings и completed journal row; неверная подпись
   остановилась до Gateway/Broker/mock effect. Focused suite — 73 passed;
   полный offline suite — 1002 (993 passed, 9 skipped); `git diff --check`
   чист. Это не real PR, human signer enrollment или production runtime;
   R2/MVP остаются OPEN.
   Batch EU / EXP-555 исправил оперативную сводку документа 27: она теперь
   различает один live Worker proposal и replay evidence от synthetic/mock
   доказательств и перечисляет stage DB, которой нет в текущем working tree.
   Batch EV / EXP-556 реализовал ранее документированный отдельный
   `allowed_approver_ids` в `PolicyConfig`: разрешённые IDs требуют публичные
   Ed25519 keys, но настроенный key без явного allowlist не даёт authority.
   Regression подтверждает deny до Gateway/Broker/journal/provider effects.
   Focused suite — 108 passed; полный offline suite — 1004 (995 passed,
   9 skipped); `git diff --check` чист. Allowlist остаётся policy утверждением,
   не аутентификацией личности или enrollment; R2/MVP остаются OPEN.
   Batch EW / EXP-557 (R2 execution batch 110/110) добавил пересчёт Git
   Merkle tree IDs полного recursive listing: каждый subtree и root OID
   вычисляются из path/mode/object IDs и сверяются с API claim. Mutation и
   missing-entry regressions проходят; это усиливает целостность snapshot, но
   не подтверждает commit-object bytes, authorship, signed provenance или
   GitHub/TLS trust. Evidence origin остаётся `github_rest_api_claim`;
   focused suite — 40 passed; полный offline suite — 1005 тестов (996 passed,
   9 skipped), `git diff --check` чист; R2/MVP остаются OPEN. Позднее EXP-606
   получил от GitHub API `verified=true, reason=valid` для закреплённого commit;
   это assertion GitHub, не independent local signature verification и не
   proof of human authorship.
   Batch EX / EXP-558 (R2 execution batch 111/111) добавил read-only verifier
   подписанного approval artifact: CLI перестраивает EXP-552 request из exact
   SQLite stage, требует полного совпадения request и проверяет Ed25519 через
   `DeterministicPolicy`. Профиль ключей передаётся оператором и явно не
   удостоверяет identity/enrollment; output — только `policy_allowed` или
   `denied`, без downstream effects. Focused suite — 53 passed; полный suite —
   1016 тестов (1007 passed, 9 skipped); R2/MVP остаются OPEN.
   BJ и CA — отдельные docs-only checkpoints, не рабочие батчи.
   Есть исторические BLOCKED/DRAFT карточки, перечисленные в
   оперативном evidence-документе 27. Публичный snapshot выбранного проекта
   `SoldatovAlexander/brainbooster_full_v11` закреплён за commit
   `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` и tree
   `2007066217aadafd9887fb3e3069220333b4fddb`; полный 23-file content digest
   был получен через bounded anonymous GitHub API. Это API claim, не доказательство
   подписи, авторства или provenance вне TLS/API trust path.

   Для target `backend/routes.py` известен baseline: в exact Python 3.11.16
   container malformed `level` дал HTTP 500 без DB row, valid payload — HTTP 200
   и одну запись. Отдельный Control Plane candidate в disposable writable
   container copy дал HTTP 422/no-write для пяти malformed numeric fields и
   overflow, сохранив valid HTTP 200/one row. Этот candidate не был получен от
   Worker, не записывался в репозиторий и не прошёл stage/approval/publication.
   Batch EXP-548 затем replay-нул сохранённый live Worker candidate через полный
   23-blob snapshot и pinned target/verifier images; это всё ещё same-host
   Docker evidence, не production runtime или независимый trust domain.

   Перед любым новым live MVP-вызовом отдельно решить, нужен ли он: EXP-520 уже
   выполнил один разрешённый live DeepSeek call с пользовательским лимитом $1 и
   lazy in-memory `AI_PROCESS_API` из AI Process Architect; ключ не копировался
   в Agent00X и не выводился. Для дальнейшего использования по-прежнему нужны
   точная карточка, свежая авторизация, ограничение числа попыток и безопасный
   `CredentialSource`; синтетический callback проверяет только wiring, не
   является системным хранилищем.

   Локальные Fake Worker adapters и fixed fake DeepSeek HTTPS transport проходят
   контрактные тесты; дополнительно EXP-520 зафиксировал один live LLM request,
   а EXP-548 воспроизвёл только сохранённый результат без нового model call.
   Worker вызывается только через bounded API adapter. Batch BQ оформил platform-neutral callable
   `CredentialSource` contract и проверил только synthetic provider; это не
   системное хранилище. Batch BR добавляет sanitized HTTP status diagnostics
   для snapshot errors, а BS сохраняет status-only failure code в CLI; оба
   не выводят response body и не делают retries. Реальный
   credential provider/account spend cap не настроены. Batch BZ ограничивает
   каждую инстанцию DeepSeek channel одной попыткой до credential lookup;
   это не account-level spend cap. Batch BK добавил
   same-process watchdog, закрывающий соединение при deadline во время HTTPS
   request/read; fake tests и loopback-only stdlib HTTP и HTTPS socket tests
   подтверждают разблокировку header/body read через shutdown+close с проверенным
   локальным TLS сертификатом; отдельный loopback peer подтвердил interruption
   зависшего TLS handshake до ServerHello. Key callback deadline и DNS/kernel
   cancellation отдельно не доказаны; попытка искусственно заблокировать
   допустимый upload объём loopback TCP не удалась на текущей ОС, поэтому один
   narrow test пропускается с причиной. Upload backpressure не доказан; watchdog
   не является process isolation. Batch BP связал Worker с этим transport в
   loopback-only verified HTTPS synthetic round-trip. Это проверка связи
   адаптеров, не live inference/proposal. Batch AW добавил canonical SQLite stage,
   exact-digest save/readback, read-only preview и digest-only mock approval;
   Batch BH требует durable stage и для remote-snapshot composition. Это
   синтетические локальные доказательства, не production durability или
   аутентифицированное пользовательское одобрение.

   В Batch BI однократный opt-in эксперимент, который должен был связать точный
   snapshot, Docker sandbox, Docker verifier, stage и mock receipt, остановился
   на sanitized `snapshot response failed` при первом commit request. По карточке
   повтор запрещён; snapshot contents, Worker proposal, target/container
   execution, stage и approval не получены. Для этого эксперимента был офлайн
   собран verifier image, но target-код не запускался.

   Batch BU получил exact-pin snapshot и все 23 blob, но остановился до
   исполнения на stale/double-prefixed synthetic digest. BV исправил ожидаемый
   digest и расчёт; локальные 905 тестов проходят (4 пропущены). Одноразовый
   rate-limit результат BV потерялся при передаче вывода, поэтому pipeline не
   запускался и повтор не выполнялся. Одноразовый preflight BW разрешил один
   pipeline-кейс, но EXP-481 остановился до target execution из-за завершающего
   перевода строки в test-command аргументе; точечное исправление подтверждено
   offline-suite, но сквозной запуск повторять нельзя. EXP-482 после intake
   показал `remaining=10`, ниже порога 25; дальнейший pipeline отложен до
   rate-limit reset и нового видимого readiness check. Batch CB добавил
   offline regression: исходный probe command с завершающим переводом строки
   отклоняется при сборке `ExecutionRequest`, а нормализованный проходит; это
   предотвращает повтор именно этой конфигурационной ошибки, но не заменяет
   ещё не пройденный контейнерный pipeline.

   Batch CC добавил offline regression на cleanup snapshot lease при ошибке
   формы execution command: run не вызывается, временный workspace удаляется;
   это не подтверждает прохождение pipeline. Локальный suite по состоянию на
   2026-10-07: запущен 911 тестов, из них 907 прошли и 4 пропущены (3 opt-in
   Docker, 1 loopback upload backpressure).
   Batch CD добавил `--remote-snapshot-execute`: только с injected Control Plane
   profile CLI запрашивает полный exact pin, проверяет commit/tree/content digest
   и blob count, запускает existing composition API и выводит лишь bounded
   digest/verdict evidence; без runtime profile команда отказывает до сети.
   Synthetic тесты подтвердили dispatch/redaction, но не сделали live snapshot,
   Worker или Docker run. Batch DF добавил helper для сборки injected DeepSeek
   Worker profile, а DG — importable runtime entrypoint для explicit verifier,
   pinned Docker sandbox и SQLite stage. Runtime пока не запускался; безопасный
   реальный `CredentialSource` не настроен. Preview/typed-digest CLI проходит только через mock gates, а
   authenticated approval и real PR publication отсутствуют.
   Batch CN (50-й) прошёл fresh readiness (HTTP 200 / remaining 33), exact pinned snapshot intake, candidate digest, executor claim/replay и target execution, но остановился в verifier с `verifier-failed`; durable stage readback, preview и receipt не достигнуты. Повтор запрещён. Batch CO (51-й) подтвердил, что synthetic запрос с файлом 220064 байта проходит локальный entrypoint, но real verifier container завершился generic `child exit failed`. Batch CP/CQ/CR/CS/CT/CU локализовали container startup issue до отсутствующих remote imports в минимальном verifier image; Batch CV (58-й) исправил и доказал import boundary и verifier PASS на синтетике. Batch CW (59-й) остановлен до snapshot intake: единственный readiness GET вернул HTTP 200 / remaining 8 при минимуме 25; pipeline не запускался. EXP-507 / Batch CX остановлен до readiness после первого локального preflight `No such image`; GitHub-запрос не делался. EXP-511—513 / DB—DD повторно получили exact execution image анонимно и подтвердили его в активном `desktop-linux` context (`linux/arm64`). Batch DE / EXP-514 прошёл один новый readiness GET (HTTP 200 / remaining 60), затем один exact-pin pipeline: pin/candidate digest, target 422/no-write и 200/one-write, Docker verifier PASS, exact-digest SQLite stage/readback, preview и local mock receipt; offline suite — 931 тест, 924 прошли, 7 пропущены. Это фиксированный Control Plane candidate, не live Worker/model-generated change, не independent verifier trust и не production approval/publication. EXP-509 / CZ выявил несогласованность: реальный Docker verifier PASS, но 161-символьный Docker image/code ID не проходил `PublicationSeed`; EXP-510 / DA принял только точный формат этого ID, после чего synthetic pipeline достиг SQLite exact readback, preview и local mock receipt.
   Batch DF / EXP-515 добавил `build_deepseek_remote_execution_profile`: helper
   собирает DeepSeek Worker вокруг injected `CredentialSource`, verifier,
   sandbox и stage sink; создание профиля не вызывает credential callback и
   проходит CLI validation до snapshot intake. Batch DG / EXP-516 добавил
   importable `run_remote_snapshot_with_runtime`: fixed Docker target backend,
   configured container verifier, SQLite stage lifecycle и injected source
   сходятся в existing fail-closed CLI; malformed task/profile не создаёт DB.
   Batch DH / EXP-517 добавил одноразовый verified-TLS header-only readiness
   evidence и permit, привязанный к фиксированному pin/task/card с threshold,
   TTL 120 секунд и explicit provider-call approval. CLI отказывает до intake
   без свежего permit; это local accidental-replay guard, не authentication.
   Batch DI / EXP-518 теперь требует явный digest-pinned execution image в
   runtime factory (immutable image ID или `@sha256` reference), передаёт
   значение без fallback и отвергает mutable/invalid refs до Docker adapter,
   SQLite, permit consumption, credential callback и GitHub. Targeted CLI: 35
   тестов; полный offline suite на 2026-10-07: 943 теста, 936 прошли, 7
   пропущены. Batch DJ / EXP-519 собрал dependency-only Python 3.11.16 arm64
   image `sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`
   из 15 wheel hashes, принятых в EXP-462; multi-stage Docker build прошёл с
   `--network=none`, smoke подтвердил FastAPI/Uvicorn/multipart versions, image
   не содержит target source, wheelhouse или DB. Полный suite — 943 теста, 936
   прошли, 7 пропущены. Ни target app, ни Docker verifier, readiness, модель,
   credentials или внешняя запись не запускались. Batch DL / EXP-521 собрал
   matching Python 3.11.16 arm64 verifier image
   `sha256:f343041a8b7353341bc933f9bcff48a5415f585e8e642b4d22c1d0d35e22705a`
   из зависимостей exact EXP-519 image; два offline build с
   `SOURCE_DATE_EPOCH=0` дали один ID. Verifier code digest
   `sha256:b1336165e906e8bd2801ff61bcc6a3740c683639416f80caea40e3e8d22825a5`.
   Read-only network-none import smoke прошёл; полный suite —
   944 теста, 937 прошли, 7 пропущены. Это не independently trusted verifier.
   Batch DK / EXP-520 принят после ровно одного live DeepSeek proposal call:
   пользователь разрешил однократное in-memory использование `AI_PROCESS_API`
   из AI Process Architect и установил пользовательский предел $1. Fresh
   readiness прошёл, exact 23-blob snapshot совпал; proposal изменил только
   `backend/routes.py`, HTTP/DB verifier прошёл, digest-bound artifact сохранён
   локально для review. Credential не копировался в Agent00X и не выводился.
   Предел расходов провайдера на уровне аккаунта не подтверждён; отсутствуют
   independent verifier trust, authenticated provenance, production approval
   и публикация. Повтор live-вызова не выполнялся.
   Полный offline suite по состоянию на 2026-10-07: 943 теста, 936 прошли и 7
   пропущены (6 opt-in Docker, 1 loopback upload backpressure).
   EXP-489 остановился после exact snapshot intake и candidate digest check на
   `execution snapshot: claim mismatch`; Worker/test/verifier/stage не запускались.
   Docker read-only snapshot copier сбрасывал executable bit при `chmod 0400`;
   EXP-490 локально исправил mode preservation (`0500` executable / `0400`
   regular files), а synthetic digest regression и полный suite прошли: 917
   тестов, 913 прошли и 4 пропущены. Это не Docker/live evidence. Повтор
   pipeline требует новой отдельной task card и readiness. EXP-494 также
   устранит расхождение: `--remote-snapshot-metadata` сейчас вызывает contents
   reader и скачивает blobs; для diagnostics CLI должен читать только commit и
   tree metadata, не выдавая API claim за content digest/provenance.
   R2 остаётся открытым: полезный live Worker proposal получен в EXP-520 и
   replay-нут в EXP-548 и повторно в EXP-614 после текущего raw-commit proof
   gate. Verifier пока не принадлежит независимо управляемому trust domain.
   EXP-606 зафиксировал GitHub API assertion `verified=true, reason=valid`, а
   EXP-594/614 проверили байты raw commit object по pinned OID; это не
   независимая локальная проверка подписи, не доказательство авторства и не
   независимость GitHub/TLS transport. Production-grade authenticated approval,
   recovery и real PR publication не доказаны. Для реальной публикации всё ещё нужны точная карточка,
   отдельное свежее подтверждение пользователя и evidence полного controlled
   пути. Не считать suite или batch count критерием закрытия R2; полный gate-by-
   gate аудит остаётся в документе 27. R3—R5 остаются отдельными последующими
   этапами. Batch GI / EXP-594 (2026-10-08) свежо прошёл интегрированный
   anonymous snapshot intake: HTTP 200 / 60 на header-only preflight, ровно 25
   REST GET, 23 проверенных файла / 240290 bytes и raw commit proof с точными
   pinned commit/tree; content digest совпал. Это закрывает только gate свежего
   snapshot intake. Вызов Worker, независимый verifier, digest-bound approval и
   controlled PR publication этой проверкой не подтверждались; R2/MVP остаются
   OPEN. Batch GJ / EXP-595 также закрывает локальный proof bypass в stored-
   candidate replay: production reader теперь получает bounded raw-commit source,
   а proof exact commit/tree проверяется до sandbox и output stage. Это
   synthetic/offline regression evidence; replay не запускался, свежего Worker
   или независимого verifier evidence пока нет. Batch GK / EXP-596 добавляет
   явный CLI-путь для процессно-инжектированного `AI_PROCESS_API` через lazy
   `ProcessEnvironmentCredentialSource`; значение не извлекается вручную из
   другого проекта. Это transport boundary, не защищённое хранилище и не live
   evidence; EXP-566 остаётся DRAFT до свежего разрешения и безопасной инъекции.
   Актуальное уточнение на 2026-10-08: Batch GU / EXP-606 получил от GitHub
   `verified=true, reason=valid` для pinned commit (assertion сервера, не
   независимая локальная криптографическая проверка). Batch GX / EXP-609
   добавил фиксированный one-shot signed-verifier service entrypoint, но он не
   развернут, не запущен на отдельном host и не подтверждает независимый trust.
   Batch HC / EXP-614 успешно replay-нул сохранённый live Worker candidate
   через current snapshot/raw-commit gate, network-isolated target test,
   pinned Docker verifier и exact SQLite readback; новый stage
   `sha256:470903b354771e167879fde402cf900100b2ce0bfe267461d1fd547573b7d984`
   сохранён вне Git. Это не новый Worker call и не production durability.
   Digest-bound human approval, trusted signer enrollment, independently
   trusted remote verifier, durable recovery и controlled real PR остаются
   открытыми; R2/MVP не завершены.

   Последующие диагностические batches HF—HJ не дали нового успешного
   candidate evidence после EXP-614. EXP-617 добавил в фиксированный target probe
   обе границы SQLite signed int64 для всех пяти числовых полей; его единственный
   replay завершился generic `operation-failed`, без доказательства того, какая
   фаза запускалась. EXP-618 добавил только offline allowlisted failure-marker
   projection (full suite 1132: 1123 passed, 9 skipped). EXP-619 отдельно
   остановился на `readiness-gate-failed` за 0.52s до snapshot intake;
   EXP-620 последующим одиночным anonymous header-only GET зафиксировал HTTP
   200, remaining 10 и reset `2026-10-08T11:15:20Z` — это временный planning
   snapshot, не доказательство точных заголовков EXP-619. EXP-621 добавил
   offline-различение фиксированных readiness failure классов (full suite
   1134: 1125 passed, 9 skipped). Batch HK / EXP-622 после наблюдавшегося reset
   выполнил ровно один replay; он завершился exit 2 с фиксированным маркером
   `target-test-sqlite-range-status`. Source file hash остался
   `adb8a8ce…02715f95`, новый output отсутствует; verifier и stage persistence
   не достигнуты. Маркер подтверждает только несовпадение ожидаемого HTTP
   status хотя бы для одного signed-range case, но не раскрывает точное поле
   или фактический status. Batch HU / EXP-632 отдельно подтвердил, что
   стандартный Python SQLite сохраняет signed-64 min/max, но отклоняет значения
   за диапазоном через `OverflowError` без новой строки. Это правдоподобный
   механизм target failure, но не доказательство конкретной причины replay.
   Исторический успешный EXP-614 остаётся replay того же Worker candidate, не
   новым Worker call. Credentials, approval, provider write, PR, push или
   deployment не выполнялись. Независимый verifier trust, authenticated
   digest-bound human approval, durable recovery и controlled real PR остаются
   открыты; R2/MVP остаются OPEN.

   Дополнение после Batch HM / EXP-624: `exp614-replay.sqlite3` скопирован
   без перезаписи в `exp614-replay-backup.sqlite3`; source и copy byte-identical,
   а read-only preview подтверждает тот же stage/artifact digest и verifier PASS.
   Это дополнительная копия на том же volume, не новый replay/stage digest,
   cross-host backup, replication, power-loss proof или production recovery.
   Approval не создан, controlled PR не выполнялся; R2/MVP остаются OPEN.

   Batch HV / EXP-633 обновляет только локальную фиксированную инструкцию
   будущего Worker-вызова: все пять полей `level`, `correct`, `wrong`, `total`,
   `time_ms` должны отклонять signed-64 overflow до DB write. Runner теперь
   привязан к новым ID EXP-634 и требует новую точную terminal phrase. Focused
   suite — 9 passed; full offline suite — 1141 tests (1132 passed, 9 skipped).
   На момент подготовки никакой Worker, credential, сеть, Docker, approval или
   provider effect не запускался; R2/MVP остаются OPEN. Последующее обновление
   2026-10-08: пользователь отдельно разрешил один EXP-634 live-вызов, но
   назначенный безопасный process-environment source preflight ответил
   `unavailable` (`value_read=false`, exit 3), stage отсутствует. Карточка
   переведена в BLOCKED до readiness/network; credential не читался, Worker и
   Docker не запускались.

### Ограниченный прототип системного credential source и отложенный hardening

Batch ID / EXP-641 добавляет экспериментальный lazy adapter к одному
нативному менеджеру текущей ОС: macOS Keychain, Windows Credential Manager или
Linux Secret Service через явно разрешённые backend-классы `keyring`; автоматический
выбор backend и fallback запрещены. Фиксированный элемент — service `Agent00X`,
account `AI_PROCESS_API`. Adapter только читает элемент при реальном вызове, не
создаёт и не импортирует его. CLI preflight проверяет только доступность backend,
не существование credential item и не его значение. Тесты используют только
synthetic backend. Это ограниченный экспериментальный источник, не универсальное
хранилище, не межпроектный инжектор и не evidence безопасности нативного backend;
обновлённый статус и ограничения приведены в документе 27.

В текущей разработке и для локальной synthetic-проверки по-прежнему можно
использовать фиктивный `CredentialSource`; реальные API keys не добавляются в
код, `.env`, prompt, очередь задач, evidence, аргументы CLI или shell history.
После MVP, до регулярного использования реальных credentials или упаковки
продукта для других ОС, провести отдельную работу:

- определить поддерживаемые режимы запуска (интерактивный пользователь,
  headless/CI, заблокированная сессия), модель угроз, ротацию и отзыв ключа;
- проверить выбранные адаптеры на поддерживаемых версиях ОС, включая Linux
  desktop/headless режимы и доступность разблокированной пользовательской сессии;
- определить безопасное первоначальное внесение и удаление секрета, ACL и
  поведение при отсутствующем, заблокированном или недоступном хранилище;
- проверить каждый adapter на целевой ОС: разрешённый/отказанный/заблокированный
  доступ, missing/revoked credential, ротация и отсутствие секрета в логах,
  аргументах процесса, prompt, файлах и persisted evidence;
- явно подтвердить, что vault защищает хранение, но не исключает краткое
  присутствие секрета в памяти процесса во время HTTPS-запроса.

Это post-MVP hardening и отдельный план работ; portable interface, текущий
прототип и synthetic tests сами по себе не являются универсальной реализацией
или доказательством защищённого хранилища. Batch FD / EXP-564 добавил lazy adapter для одного значения,
переданного внешним менеджером в process mapping: это только транспортная
граница, не encrypted vault и не изоляция от процессов того же пользователя.
Live model experiment требует отдельной точной карточки, свежего явного
разрешения и ограниченного числа вызовов/расходов; внешний provider call в
EXP-564 не выполнялся.

Batch EY / EXP-559 связывает успешное verified evidence с явным абсолютным
путём SQLite stage, переданным runtime caller-ом. Путь включается только после
read-only проверки существующего SQLite файла; ошибки и профили без locator его
не выдают. Проверка использует immutable SQLite open, чтобы не создавать WAL/SHM
sidecar и не мешать следующему read-only consumer. Для повторного локального
approval/review нужен стабильный путь вне auto-cleaned temp directory. Это
улучшает адресуемость локального evidence, но не закрывает production durability
или recovery. Batch EZ / EXP-560 локально связывает stage path + digest из
verified evidence с существующим read-only approval-request CLI: точная стадия
переоткрывается без изменения байтов и порождает только unsigned request. Это
не human identity, production durability, approval signature или publication.
Batch FA / EXP-561 соединяет тот же evidence с test-only подписанием запроса и
read-only signed-approval CLI: deterministic policy разрешает exact digest-bound
подпись на той же stage, при этом `identity_authenticated=false` и
`provider_write=false`. Это синтетическая проверка policy boundary, не human
enrollment, production trust-profile governance или разрешение на публикацию.
Batch FB / EXP-562 продолжает ту же локальную цепочку после policy allow:
контроль публикации повторно проверяет подписанный approval через deterministic
Policy, затем требует slow Gateway allow и single-use in-memory Broker, пишет
digest-only journal и создаёт ровно один mock PR receipt. Это не вызов внешнего
provider, не production publication chain и не доказательство human identity.
Batch FC / EXP-563 упаковывает эту композицию в локальный CLI с повторной
проверкой exact stage/request/signed approval/trust profile. Он принимает только
пути к уже существующим локальным входам, не принимает endpoint или adapter,
пишет временный digest-only journal и возвращает ограниченный mock receipt.
Отказ до gates и отсутствие изменений входов покрыты негативными тестами.
Это устраняет ручной тестовый handoff, но не заменяет enrollment signer-а,
аутентификацию trust profile, production journal/recovery или live publication.
Batch FE / EXP-565 готовит фиксированный runner remote Worker-to-stage с
проверкой локального наличия закреплённых Docker images и точным интерактивным
подтверждением перед readiness/network/credential lookup. Его тесты используют
подменённые runtime зависимости; операторская команда не запускалась. После
неуспешного signed-range probe EXP-622 Batch HV / EXP-633 уточняет фиксированную
инструкцию и identity будущего Worker-вызова. На 2026-10-08 пользователь
подтвердил единственный разрешённый EXP-634 вызов с лимитом USD 1, но
`process-environment` source оказался недоступен; карточка BLOCKED до любого
сетевого запроса. Batch HX / EXP-635 затем добавил локальный one-shot HTTPS
transport для подписанного verifier response: fixed route, verified TLS,
bounded DNS/deadline/body и sanitized failure. Endpoint не настроен и transport
не вызывался; focused tests — 22 passed, полный offline suite — 1149 тестов
(1140 passed, 9 skipped). Подпись/TLS не продвигают verifier в independent
trust domain. Batch HY / EXP-636 дополнил этот результат loopback HTTPS
интеграцией: 24 focused tests passed, полный offline suite — 1151 тест
(1142 passed, 9 skipped). Настоящий TLS handshake прошёл на localhost с
одноразовым тестовым сертификатом; trusted hostname mismatch, untrusted
certificate и stall отвергнуты. Это не удалённый endpoint, signer enrollment
или independent-host trust. Batch HZ / EXP-637 добавил fixed-profile
`SignedVerifierHTTPService` и одноразовый server entrypoint, жёстко привязанный
к `127.0.0.1` и explicit unprivileged port. Синтетическая клиентская цепочка
прошла через реальный loopback TLS, HTTP adapter, fake verifier и in-memory
signer; malformed/profile-mismatched requests rejected before verifier/signer.
Focused service suite — 8 passed, полный offline suite — 1159 тестов
(1150 passed, 9 skipped). Server не запускался; внешний TLS/access-control
proxy, remote host, signer enrollment и independent trust отсутствуют.
Пользователь сообщил, что подходящего инъектора нет. В runner уже существует
policy-approved `TerminalPromptCredentialSource` с скрытым вводом и отказом при
echo fallback; Control Plane подготовил DRAFT-amendment EXP-634 на этот источник.
Это меняет credential source: до свежего подтверждения пользователя live-вызов
не запускается. EXP-634 остаётся BLOCKED.
Пользователь повторно подтвердил один DeepSeek live-вызов через безопасную
инъекцию из AI Process Architect, с лимитом USD 1 и без повторов; свежий
non-disclosing preflight в 16:55 UTC снова показал
`process_environment/unavailable`, `value_read=false` (exit 3). Поэтому не
было readiness-запроса или вызова модели; разрешение не использовано, и
EXP-634 остаётся BLOCKED до доступности назначенного инъектора.

Batch IA / EXP-638 добавляет локальную OpenPGP-проверку точного raw commit
object против явно закреплённого primary fingerprint. Синтетический signed
commit проходит через реальный Git/GnuPG verifier; неверный fingerprint/key,
изменённый объект и unsigned commit отвергаются. Это только криптографическое
доказательство подписи ключом, не identity/authorship и не независимая
snapshot provenance. Реальный GitHub commit/key, сеть, credential, Worker,
Docker, approval и publication не использовались; R2/MVP остаются OPEN.
Полный offline suite после Batch IA: 1164 теста (1155 прошли, 9 пропущены);
`git diff --check` чист.
Batch IB / EXP-639 выполнил единственную разрешённую bounded anonymous
проверку подписи закреплённого публичного commit. Публичный ключ из выбранного
signer key set не подтвердил подпись точного raw commit; CLI вернул только
фиксированный sanitized `signature-not-verified` marker и остановился без
повтора. Полный offline suite: 1172 теста (1163 прошли, 9 пропущены);
`git diff --check` чист. Это отрицательное provenance evidence, а не основание
доверять snapshot; R2/MVP остаются OPEN.
4. **R3 — наблюдатель и исторический отчёт.** Отчёты сейчас/на момент T,
   причинные ссылки, отделение фактов от оснований и интерпретаций; проверки
   неполной истории, поздних ответов и отказов. Детерминированный отчёт допустим
   первым, LLM-объяснение не заменяет доказательства.
5. **R4 — учебная ветка.** Корректировка человека, восстановление из checkpoint
   в симуляции, новый branch и candidate-конфигурация без старых полномочий.
   Исходная история сохраняется, внешние действия автоматически не повторяются.
6. **R5 — эксперимент.** Штатные случаи, исключения и новые похожие задачи;
   сравнение полной и упрощённой организации данных. Проверить перенос
   корректировки и отсутствие регрессий, записать ограничения и отрицательные
   результаты. VP-20—VP-23 обязательны для завершения исследовательского среза.
   VP-21/VP-22 используют preregistered [протокол R5](33-r5-experimental-protocol.md);
   его наличие не является результатом эксперимента.

Безопасность проверяется внутри каждого этапа, а не только после сборки.
Оптимизация Router, несколько протоколов, рекурсивные команды, оборудование и
полноценный Organization UI не блокируют исследовательский прототип.

## 2. Демонстрационный сценарий

```text
User goal
  -> Process Contract
  -> repository snapshot
  -> Worker in sandbox
  -> patch + tests + evidence
  -> independent verification
  -> immutable Staged Change
  -> user approval of digest
  -> publish_pull_request Intent
  -> Agent I/O Gateway
  -> deterministic Policy Decision
  -> GitHub Actuator
  -> Credential Broker obtains short-lived GitHub App token
  -> branch + commit + push + Pull Request
  -> sanitized Action Receipt
```

Worker получает read-only snapshot исходного репозитория и отдельный writable
ephemeral workspace. Он может сформировать patch, но не имеет GitHub credential,
прямого сетевого egress и права публикации.

## 3. Границы MVP

### Входит

- один Process Pattern `repository-change`;
- один Orchestrator, один Worker и независимый Verifier;
- durable process state и checkpoint до каждого решения и вызова инструмента;
- сборщик событий агента/субагентов, read-only Observer и исторические отчёты;
- версионируемая корректировка и учебная ветка без внешних writes;
- sandbox backend на базе готового механизма изоляции;
- персональный Gateway для Worker;
- минимальные canonical contracts;
- детерминированная policy с deny-by-default;
- staging и approval по digest;
- GitHub Actuator с одной операцией `publish_pull_request`;
- Credential Broker и короткоживущий GitHub App installation token;
- Action Receipt, audit и secret-leak test;
- минимальный CLI для задачи, approval, отчёта и разбора ошибки.

### Не входит

- универсальный marketplace;
- production-grade multi-tenant control plane;
- рекурсивная глубина более одного уровня;
- динамическое обучение Router;
- полный импорт skills нескольких экосистем;
- все протоколы одновременно;
- семантический injection detector на каждом сообщении;
- MHS и реальное оборудование;
- автоматическое слияние PR или deployment;
- долгоживущие PAT и общие `.env`;
- два полноценных пользовательских режима и дообучение весов модели.

## 4. Компоненты

| Компонент | Минимальная ответственность | Не делает |
|---|---|---|
| Process Runtime | Состояния, переходы, retry, checkpoint | Не интерпретирует credential |
| Orchestrator | Декомпозиция и выбор следующего шага | Не применяет изменения |
| Worker | Анализ snapshot, patch и evidence | Не имеет внешней сети и GitHub identity |
| Verifier | Тесты и acceptance criteria | Не публикует результат |
| Sandbox Manager | Workspace, mounts, quotas, network default-deny | Не принимает бизнес-решения |
| Gateway | Identity, schema, provenance, policy call, audit | Не хранит секреты |
| Policy Engine | Allow/deny по typed attributes | Не принимает свободный prompt как правило |
| Approval Service | Подтверждение точного digest | Не изменяет staged action |
| GitHub Actuator | Зарегистрированная операция публикации | Не исполняет произвольный shell/API request |
| Credential Broker | Получение и использование scoped credential channel | Не возвращает token агенту |
| Audit Sink | Метаданные, digests и receipts | Не пишет секрет или полный prompt по умолчанию |
| Observation Collector | События и checkpoint до действия, причинные ссылки | Не зависит от добровольного отчёта Worker |
| Observer | Отчёты по разрешённой истории, пробелы и основания решений | Не читает скрытые рассуждения, не управляет агентами |
| Learning Branch Runtime | Новая ветка, candidate-конфигурация и eval | Не переписывает прошлое и не переносит старые grants |

## 5. Sandbox profile

Sandbox реализуется готовыми backend, а не собственным гипервизором. Интерфейс
`SandboxBackend` отделяет платформу от конкретной технологии.

Минимальный профиль:

- отдельный process/container boundary;
- read-only mount repository snapshot;
- writable ephemeral workspace;
- no host credential mounts;
- empty/minimal environment allowlist;
- default-deny egress;
- отдельный Gateway socket/endpoint;
- CPU, RAM, disk, process count и timeout limits;
- cleanup после завершения;
- artifact export только через Gateway.

Первый backend выбирается экспериментом между Docker и Podman. gVisor или
Firecracker рассматриваются как усиленные Linux-профили после измерения угроз и
накладных расходов. Personal Mode на macOS/Windows может использовать иной
backend при сохранении одного security contract.

Verifier считается независимым только если target execution и проверка идут в
отдельном доверенном контуре, а результат связан с точным request/profile и
свежим challenge, подписан ключом, заранее закреплённым Control Plane. Docker
контейнер на машине Worker, self-reported `verifier_id` и nonce echo сами по
себе независимость или identity не доказывают. Подписание результата не должно
возвращать target execution в доверенную зону Worker.

## 6. Adaptive Gateway

Gateway выбирает профиль проверки по источнику, trust domain, taint, порту,
capability, чувствительности и потенциальному side effect.

### Fast Path

Допустим, если одновременно выполнены условия:

- transport identity подтверждена;
- schema и подпись корректны;
- сообщение не запрашивает новую capability;
- нет secret operation или внешнего side effect;
- provenance и taint не потеряны;
- payload остаётся внутри разрешённого trust domain;
- размер, rate и TTL допустимы.

Fast Path выполняет дешёвые детерминированные проверки. Он не означает, что
внутренний A2A-трафик считается доверенным.

### Slow Path

Включается для внешнего/tainted контента, protocol boundary, tool request,
write, secret operation, privilege transition, чувствительного вывода или
аномалии. Дополнительно применяются content inspection, injection screening,
DLP, расширенная policy evaluation, verifier и/или human approval.

### Degraded Path

При недоступности policy или неоднозначной классификации допускаются только
явно разрешённые read-only операции. Write, publish и secret operations
блокируются.

## 7. Authority flow для GitHub

### Intent Contract

`publish_pull_request` содержит repository ID, base commit, patch/artifact
digest, branch proposal, title, body artifact reference, owner, audience,
idempotency key и expiry. Произвольные URL, shell command и credential fields
запрещены схемой.

### Policy Decision

Проверяются:

- identity и непрерывная delegation chain;
- repository и installation allowlist;
- approved staged digest;
- base commit и отсутствие конфликта;
- разрешённая branch namespace;
- пройденные тесты и verdict Verifier;
- owner, audience, TTL, budget и idempotency;
- актуальная policy version.

### Credential и actuator

Предпочтителен GitHub App. Broker получает короткоживущий installation token с
минимальными repository permissions и предоставляет его только доверенному
GitHub Actuator через закрытый канал внутри Authority Plane. Actuator создаёт
branch/commit/push/PR или использует эквивалентную ограниченную API-последовательность.
Token не возвращается вызывающей стороне и уничтожается после операции.

### Receipt

Receipt содержит process ID, intent digest, staged digest, policy decision ID,
approval ID, repository, branch, commit SHA, PR ID/URL, idempotency key,
timestamps, sanitized status и postcondition result. Token и чувствительные
заголовки отсутствуют.

## 8. Рабочие потоки

### Поток A. Canonical contracts

Результат: JSON Schema/Pydantic-модели Process Contract, Intent Contract,
Staged Change, Policy Decision, Approval и Action Receipt.

### Поток B. Sandbox и Gateway

Результат: Worker без прямой сети; все внешние операции проходят через Gateway;
Fast/Slow/Degraded profiles наблюдаемы в audit.

### Поток C. Repository process

Результат: воспроизводимый patch, allowlisted tests, Evidence Bundle и независимый
verdict.

### Поток D. Authority Plane

Результат: policy, approval, GitHub Actuator, Broker и idempotent publication.

### Поток E. Security validation

Результат: canary credential не найден вне Broker boundary; попытки network,
schema, digest, replay и injection bypass заблокированы.

### Поток F. Product shell

Результат первого прототипа: CLI «цель → preview → approval → PR» с отчётом
наблюдателя и учебной веткой. Organization view — следующий этап, не gate прототипа.

## 9. Историческая основа

Этот раздел описывает уже созданные компоненты по прежней шкале M0—M4. Он не
задаёт порядок текущей работы: тот определён этапами R0—R5 в разделе 1.

### Milestone M0. Executable contracts — выполнен

- схемы и примеры сообщений;
- state machine;
- invariant tests;
- fixture repository и mock GitHub endpoint.

Выход: контракты проходят позитивные и негативные tests.

Результат: реализованы шестнадцать schemas, валидная цепочка, негативные fixtures,
canonical digest, cross-contract invariants, state machine, machine-readable
invariant catalog, fixture repository и mock GitHub boundary.

### Milestone M1. Safe local preparation — частично реализован

`SandboxBackend` и development-only process backend реализованы. Последний проверяет
workspace lifecycle, command allowlist и минимальный environment, но честно не
заявляет network/kernel isolation. Docker backend и smoke-проверки уже добавлены;
они не доказывают все заявленные границы изоляции.

Reference flow уже применяет declared changes только в ephemeral workspace,
строит unified patch, запускает allowlisted tests и создаёт связанные digest
Evidence Bundle, Verification Report и Staged Change. Path traversal, провал
тестов и изменение исходного snapshot покрыты негативными тестами.

- Process Runtime;
- Worker sandbox;
- snapshot/workspace;
- patch, test и evidence;
- Verifier.

Выход: проверенное staged change создаётся без сети и секретов.

### Milestone M2. Controlled publication — частично реализован, не закрыт

- Gateway;
- minimal policy;
- approval по digest;
- GitHub Actuator;
- Credential Broker;
- Action Receipt.

Исторический результат: GitHub App spike создал тестовый PR. Выход этапа не
достигнут: нет сквозной доказанной связи staged change → approval → publication.

### Milestone M3. Adversarial validation — частично реализован, не закрыт

- network bypass;
- token canary scan;
- changed digest/replay;
- tainted input;
- policy unavailable;
- crash before/during/after publication;
- duplicate request.

Есть component-level негативные тесты. Выход этапа не достигнут: отсутствует
проверка реальной сквозной публикации и известны нарушения целостности.

### Milestone M4. Dual UX — отложен после исследовательского прототипа

- Personal guided flow;
- Organization audit/policy view;
- EU, latency и approval metrics.

Выход: два пользовательских режима работают на одной модели контрактов.

## 10. Критерии завершения исследовательского среза

Инженерный срез завершён только если:

1. PR создаётся из одобренного staged digest;
2. Worker не имеет GitHub network path и credential;
3. canary credential отсутствует во всех проверяемых поверхностях;
4. изменение digest отзывает approval;
5. повтор intent не создаёт второй side effect;
6. недоступность policy запрещает публикацию;
7. audit восстанавливает полную цепочку без сохранения секрета;
8. crash recovery не приводит к слепому повтору;
9. Personal пользователь понимает действие до approval;
10. эксперт через CLI видит identity, policy, evidence и receipt;
11. ограничение MVP технически отключает неготовые возможности;
12. записаны время выполнения и затраты; оптимизация Gateway/Router не является gate;
13. checkpoint каждого решения и вызова записан до исполнения;
14. наблюдатель восстанавливает историю в пределах сохранённых данных и явно
    указывает пробелы, неизвестные исходы и источники объяснения;
15. учебная ветка не изменяет исходную историю и не повторяет внешние действия;
16. на заранее заданных критериях оценены исполнение функции, вклад организации
    данных и перенос корректировки на новые случаи, включая регрессии.

Завершённый эксперимент может дать отрицательный результат по пункту 16:
это не подтверждение гипотезы, но основание для её корректировки. Завершение
инженерного среза и подтверждение исследовательской гипотезы отмечаются отдельно.

## 11. Решение после исследовательского среза

### Подтверждение гипотезы

Все критерии раздела 10 выполнены, функция исполняется на заранее определённом
наборе случаев, а полная организация данных показывает проверяемый вклад против
упрощённого варианта. Ограничения и residual risks документированы.

### Частичное подтверждение

Контракты и отдельные части функции работают, но вклад организации данных,
перенос корректировки или одна из границ остаются неопределёнными. Результат
фиксируется как частичный, следующий эксперимент сужается до конкретного пробела.

### Неподтверждение или остановка среза

- token появляется у агента или в журнале;
- Worker может обойти Gateway;
- произвольный URL/command достигает Actuator;
- approval применим к другому digest;
- повтор запроса создаёт дубликат;
- внутренний A2A Fast Path позволяет privilege transition;
- невозможно установить итог внешнего side effect.

## 12. Решения после среза

По результатам принимаются отдельные решения о process runtime, sandbox backend,
policy engine, protocol SDK, Router, skill portability и Function Packs. Ни одна
из этих технологий не выбирается заранее только ради полноты архитектуры.

### Контрольная точка 2026-10-08 — локальная композиция approval/publication

Batch IK / EXP-648 проверяет один synthetic remote-executor stage через штатные
approval-request и signed-mock CLIs до mock receipt с тем же staged digest,
repository, branch и base. Stage DB и approval input files не меняются при
consumption. Это не live Worker, не authenticated human approval, не реальный
GitHub PR и не production recovery; criteria 1—3 и остальные открытые пункты
раздела 10 не закрыты. Полный актуальный статус и доказательства — в документе
27 и карточке EXP-648 в `.opencode/tasks/WORK_QUEUE.md`.

Обновление 2026-10-08 после Batch IZ / EXP-667, Batch JA / EXP-668, Batch JB /
EXP-669, Batch JC / EXP-670, Batch JD / EXP-671 и Batch JE / EXP-672: R2 дошёл
до continuation batch #195; фиксированного общего числа
батчей у открытого этапа пока нет. EXP-667 добавил partial observer history только
для approval/publication-продолжения сохранённого stage; EXP-668 научился явно
помечать self/forward causal references; EXP-669 добавляет opt-in observer к
stored-candidate replay от readiness до stage readback, но синтетически и без
Worker/model invocation. Это не закрывает сквозной collector,
independent-host verifier, trusted human signer или реальный PR. EXP-634 остаётся
заблокированным: подходящего credential injector нет, а источник допускается
менять только новой точной карточкой и свежим подтверждением live-вызова. Одна
публичная read-only попытка EXP-670 остановилась в observer snapshot-route
allowlist до tree GET; EXP-671 исправил маршруты локально. Отдельная попытка
EXP-672 дошла до target test, но сохранённый старый candidate не прошёл новый
SQLite signed-64 boundary case; verifier и stage не достигнуты. Обе карточки
остановлены без повторов. Live Worker/verifier/publication evidence по-прежнему
не добавлено.

Batch JF / EXP-673 (continuation batch #196; 1 задача) добавляет в read-only
stage-preview CLI явный `--format text`: человекочитаемый digest-bound обзор
точного stage и patch с безопасным экранированием терминальных control/bidi
символов. JSON остаётся форматом по умолчанию; SQLite открывается read-only.
Focused suite — 7 passed; полный offline suite — 1258 тестов (1249 passed,
9 skipped), `git diff --check` clean. Это локально улучшает review UX, но не
подтверждает usability, authenticated approval или публикацию; R2/MVP остаются
OPEN.

Batch JG / EXP-674 (continuation batch #197; 1 задача) связывает existing
exact-canary scanner с новым terminal review output: чистый synthetic preview
проходит, маркер, добавленный только в patch fixture, локализуется как
`stage-preview`, а ошибка не раскрывает значение. Focused suite — 8 passed;
полный offline suite — 1259 тестов (1250 passed, 9 skipped), `git diff --check`
clean. Это одна синтетическая поверхность, не полный скан runtime/evidence; R2
criterion 3 и MVP остаются OPEN.

Batch JH / EXP-675 (continuation batch #198; 1 задача) расширяет synthetic
canary-check до fake composition `pinned CLI → Worker → stage → approval request
→ signed mock`. Фальшивый credential callback прочитан ровно один раз; sentinel
проверен в CLI stdout/stderr, stage/observer DB, approval/signature/trust
файлах, observer report и mock receipt — совпадений нет. Focused composition —
1 passed; полный offline suite — 1259 тестов (1250 passed, 9 skipped),
`git diff --check` clean. Это не live Worker/verifier scan; criterion 3 и R2/MVP
остаются OPEN.

Batch JI / EXP-676 (continuation batch #199; 1 задача) ограничивает exact-canary
scanner сверху: максимум 64 surfaces, 1 MB на surface, 100 000 узлов и 64
уровня; cyclic, unsupported и oversized значения fail closed. Ранее scanner
полностью сериализовал каждый объект через `json.dumps(default=str)` без
лимита. Focused suites — 30 passed; полный offline suite — 1261 тест
(1252 passed, 9 skipped), `git diff --check` clean. Это ограниченный exact-canary
helper, не общий detector secrets; R2/MVP остаются OPEN.

Batch JJ / EXP-677 (continuation batch #200; 1 задача) проверяет фильтрацию
точного имени `AI_PROCESS_API`: синтетическая переменная присутствует только в
специально собранном environment родительского test subprocess и отсутствует в
реальном child local-sandbox; mocked Docker exec содержит лишь три фиксированные
переменные. Targeted sandbox suite — 19 тестов (18 passed, 1 Docker opt-in
skipped); полный offline suite — 1263 теста (1254 passed, 9 skipped),
`git diff --check` clean. Образ `python:3.12-alpine` отсутствует, pull не
выполнялся; реальная Docker isolation здесь не подтверждена, criterion 2 и
R2/MVP остаются OPEN.

Batch JK / EXP-678 (continuation batch #201; 1 задача) запускает реальный
`DockerSandboxBackend` на уже локальном pinned `TARGET_RUNTIME_IMAGE_ID`
`sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812`
(`linux/arm64`) ровно один раз. Родительский процесс получил только заданный
командой synthetic `AI_PROCESS_API`; container env и `docker inspect Config.Env`
его не содержат. Подтверждены `NetworkMode=none`, отказ сетевого/DNS probe,
read-only root/snapshot, capabilities drop, no-new-privileges, лимиты и writable
workspace. Контейнер завершён и удалён; других работающих контейнеров с этим
image нет. Opt-in test — 1 passed; полный offline suite — 1263 теста (1254
passed, 9 skipped), `git diff --check` clean. Это подтверждает target container,
но не полную изоляцию live Worker, независимость Docker daemon или production
host; criterion 2 и R2/MVP остаются OPEN.

Batch JL / EXP-679 (continuation batch #202; 1 задача) провёл одну полную
локальную синтетическую композицию: fake Worker → pinned target Docker image →
pinned verifier Docker image → exact SQLite stage save/readback → same-digest
local mock receipt. Точный opt-in тест прошёл (1 passed); полный offline suite —
1263 теста (1254 passed, 9 skipped), `git diff --check` clean. Оба контейнера
работали без сети; после прогона контейнеров с этими image не осталось. Это
усиливает локальное Docker evidence, но fake Worker, synthetic snapshot и mock
receipt не доказывают live Worker, independent-host verifier, authenticated
human approval или реальный PR. EXP-634 отдельно остаётся BLOCKED: подходящего
инжектора нет, а скрытый terminal prompt требует отдельного подтверждения смены
источника и свежего подтверждения единственного live-вызова. R2/MVP остаются
OPEN.

Batch JM / EXP-680 (continuation batch #203; 1 задача) добавляет подписанный
Control-Plane enrollment contract для будущего remote verifier: он связывает
фиксированный HTTPS endpoint, verifier/profile identity, response key, разные
Worker/verifier host IDs, digest OOB host-separation evidence и короткое окно
действия. Контракт проверяется только против caller-pinned authority public
key; все тесты синтетические. Verified record намеренно оставляет
`independent_host_trust_established=false`: протокол не доказывает, что
подписанные host claims реальны, и не меняет trust flags клиента/executor.
Remote deployment, OOB key enrollment, evidence проверки host separation и
интеграция с runtime остаются следующими воротами; R2/MVP OPEN.

Batch JN / EXP-681 (continuation batch #204; 1 задача) добавил фабрику
HTTPS-клиента, которая принимает verifier signing key только из проверенного
EXP-680 enrollment и требует точные endpoint, verifier/profile IDs, а также
ожидаемые Worker/verifier host IDs. Ошибочные привязки и transport без строгого
HTTPS-типа отклоняются до dispatch. Даже с валидным synthetic enrollment ответ
остаётся audit-only: `independent_host_trust_established=false`. Focused client
suite — 27 passed; полный offline suite — 1273 теста (1264 passed, 9 skipped),
`git diff --check` clean. Реальный authority key, deployment и verifier-host
evidence отсутствуют; R2/MVP остаются OPEN.

Batch JO / EXP-682 (continuation batch #205; 1 задача) переносит digest
проверенного enrollment из `SignedVerifierClient` в bounded signed-attestation
metadata, затем в `ExecutionResult` и CLI failure evidence. Malformed digest
отвергается до stage; даже валидный digest не меняет `FAILED /
verifier-trust-unestablished`, `independent_host_trust_established=false` и
нулевые stage save/load. Focused suites — 131 tests (129 passed, 2 skipped);
полный offline suite — 1274 теста (1265 passed, 9 skipped); `git diff --check`
clean. Использованы только синтетические ключи/enrollment и fake transport;
реальная OOB проверка, отдельный host и deployment не выполнены. R2/MVP OPEN.

Batch JP / EXP-683 (continuation batch #206; 1 задача) объединяет OOB enrollment,
`SignedVerifierClient.from_trust_enrollment`, точный тип HTTPS transport с fake
connection, remote-snapshot executor и ограниченный CLI projection. Один
синтетический signed PASS передал точный enrollment digest, но завершился
`FAILED / verifier-trust-unestablished` до stage save/readback. Focused
executor/CLI suite — 104 теста (102 passed, 2 skipped); полный suite — 1274
(1265 passed, 9 skipped); `git diff --check` clean. Fake connection не
подтверждает TLS/network/host separation; реальный OOB trust/deployment,
authenticated approval и PR остаются открытыми. R2/MVP OPEN.

Batch JQ / EXP-684 вводит canonical authority-signed approver-key enrollment,
привязанный к digest конкретного trust profile, provider repository и только
операции `publish_pull_request`. Проверка принимает authority public key только
из caller-pinned mapping и явно оставляет `human_identity_authenticated=false`;
контракт пока не встроен в signed-approval CLI и не устанавливает, что ключ
принадлежит человеку. Focused tests — 6 passed; полный suite — 1280 тестов
(1271 passed, 9 skipped); `git diff --check` clean. Только синтетические ключи.
Нужны OOB authority provisioning/identity review и отдельная runtime integration;
R2/MVP OPEN.

Batch JR / EXP-685 добавляет opt-in read-only проверку подписанного approval
через authority-enrolled approver key. Enrollment связывается с точным trust
profile digest, stage-bound approver ID, provider repository и операцией PR; CLI
выдаёт только bounded IDs/digests. Без обоих входов (enrollment и caller-pinned
authority keys) переход fail-closed; legacy output остаётся
`operator_supplied_unverified`. Даже успешная проверка сообщает
`identity_authenticated=false`, `provider_write=false` и не публикует approval.
Это локальный протокольный путь; реальная OOB идентификация, интеграция с
controlled publication и provider PR остаются открытыми.
Focused suite — 15 passed; полный offline suite — 1283 теста (1274 passed,
9 skipped); `git diff --check` clean. Использованы синтетические stage, signer,
authority key и enrollment; реальных ключей, identity proof и внешних действий
не было. R2/MVP OPEN.

Batch JS / EXP-686 соединяет этот verifier с существующими локальными
publication gates через coordinator, который сам перечитывает точную stage,
подписанный approval, trust profile и authority enrollment. Перед любым
collaborator сверяются provider/source identity, `PublicationSeed`, intent,
policy и digest; повторно загруженный staged change снова хэшируется. Новый
путь принимает только точные `InMemoryCredentialBroker` и `MockGitHubEndpoint`,
затем проходит свежие Approval → Policy → Gateway → Broker → Journal проверки
до mock receipt. Synthetic positive case создал один receipt под тем же digest
и idempotency key; seed mismatch и подмена загруженного staged change
отказаны до side effects, provider adapter — ещё до verifier/stage load.
Focused suite — 16 passed; full suite — 1284 tests (1275 passed,
9 skipped); `git diff --check` чист. Это не human identity authentication,
реальный Worker, независимый verifier, GitHub publication или MVP completion.

Batch JT / EXP-687 добавляет такой же enrolled режим в mock CLI: он требует
authority enrollment, bounded public key-set JSON и отдельный ожидаемый digest
key-set, сравнивая точные байты до signature/policy verification. Bundle
отвергает symlink, duplicate/unknown fields, malformed IDs/keys и превышение
размера; неполный флаговый набор не понижает путь до legacy. Операторский
integration test проходит от synthetic pinned CLI/remote snapshot через тот же
observer run до enrolled approval и одного digest-bound in-memory mock receipt;
повтор отвергнут без изменения журнала. Focused suites — 61 passed (49
schema/contracts, 11 mock CLI, 1 same-run integration); полный suite — 1292
tests (1283 passed, 9 skipped); `git diff --check` clean. Ожидаемый key-set digest остаётся
operator-pinned внеполосно; enrolled key не аутентифицирует человека и не
разрешает real PR. R2/MVP остаются OPEN.

Batch JU / EXP-688 сверяет scorecard с этой новой интеграцией: синтетический
observer run теперь подтверждён от pinned operator CLI через Worker/verifier
fixtures и stage до enrolled approval и mock receipt. Это усиливает локальное
evidence для критериев 7, 13 и 14, но не закрывает их: Worker/verifier
синтетические, а полнота реального capture, разрешение артефактов и durable
recovery не доказаны. Точный integration test прошёл; live EXP-634 остаётся
BLOCKED, R2/MVP остаются OPEN.

Batch JZ / EXP-693 прошёл одну полную local Docker composition этого же
synthetic observer run: pinned CLI с fake readiness/snapshot/Worker, тест в
закреплённом target container, verifier PASS в закреплённом verifier container,
durable stage с точным `docker-image:<image>/code:<digest>` verifier ID и один
enrolled digest-bound mock receipt. Тест прошёл; после него `docker ps` не
показывал работающих контейнеров ни одного из двух образов. Локальный same-run
тест также прошёл; полный offline suite — 1293 теста (1283 passed, 10 skipped).
Это усиливает synthetic evidence критериев 1, 2, 7, 13 и 14, но не доказывает
live Worker, независимость Docker daemon/host, authenticated human approval,
полный runtime capture или реальный PR. R2/MVP остаются OPEN.

Batch KA / EXP-694 (continuation batch #217; 1 задача) впервые прочитал весь
pinned snapshot настоящим anonymous GitHub REST transport: HTTP 200 readiness,
25 GET (commit, recursive tree, 23 blobs) и один ограниченный raw commit fetch.
Owner/repository/commit/tree, 23 файла, canonical SHA-256 content digest и
хэш/root-tree Git commit object совпали с pin. Это улучшает evidence критерия 1
до `github_rest_api_claim` + content/object-hash consistency, но не доказывает
подпись, authorship или authenticated provenance. Единственная Docker
композиция с синтетическим Worker остановилась с bounded `pinned_code=1`,
`runtime_code=1`; внутренний failure code тест не сохранил. Повтора в Batch KA
не будет. До PASS stage, enrolled mock receipt и реального Worker evidence не
дошло; оба образа остались без работающих контейнеров. Full offline suite:
1294 теста (1283 прошли, 11 пропущено), `git diff --check` clean. No
credentials/provider writes; EXP-634 remains blocked, R2/MVP остаются OPEN.

Batch KB / EXP-695 (continuation batch #218; 1 задача) добавил в интеграционный
test harness только allowlisted projection уже существующего JSON `failure_code`.
Вложенные payloads, исключения, произвольный текст и неизвестные коды не
переносятся в assertion; fixed HTTP status category сводится к constant marker.
Synthetic unit tests и existing same-run test прошли; полный offline suite —
1295 тестов (1284 passed, 11 skipped). Это не диагностировало внутреннюю
причину EXP-694 и не повторяло public/Docker попытку; Batch KA remains BLOCKED,
EXP-634 remains blocked, R2/MVP остаются OPEN.

Batch KC / EXP-696 (continuation batch #219; 1 задача) сделал одну диагностическую
попытку после EXP-695. Публичный snapshot и raw commit object снова совпали с
pin, однако CLI вернул только allowlisted `remote-snapshot-execution-failed`
(`pinned_code=1`, `runtime_code=1`); event/exception boundary не сохранила
подшаг. Ни stage PASS, ни receipt не доказаны. После запуска контейнеры не
остались активными. Повтора по Batch KC не будет; для следующего шага сначала
нужна безопасная проекция последнего observer event, затем отдельная карточка.
EXP-634 остаётся BLOCKED; R2/MVP остаются OPEN.

Batch KD / EXP-697 (continuation batch #220; 1 задача) добавил bounded
observer-event projection, но единственная интеграционная попытка остановилась
до snapshot/Docker на anonymous `/rate_limit`: HTTP 200, `remaining=10`, при
требуемом минимуме 35. Полный offline suite прошёл: 1296 тестов (1285 passed,
11 skipped), `git diff --check` clean. Следующий public read нельзя запускать
до нового rate-limit окна; отдельная новая карточка нужна после ожидания.
EXP-634 остаётся BLOCKED; R2/MVP остаются OPEN.

Batch KE / EXP-698 (continuation batch #221; 1 задача) принял офлайн-refactor
интеграционного harness: readiness и snapshot collaborators теперь поступают
через runtime seam CLI; в public mode actual bounded REST/raw-commit reader
вызывается внутри runtime, до синтетического Worker, а fetched bytes проверяются
до построения кандидата. Фокусированные тесты — 2 passed; полный offline suite —
1296 тестов (1285 passed, 11 skipped); `git diff --check` clean. Public/Docker
путь не запускался: для него нужна новая отдельная карточка и успешный
rate-limit preflight. Подходящего credential injector сейчас нет, поэтому
EXP-634 остаётся BLOCKED и live-вызов не выполнялся; R2/MVP остаются OPEN.

Batch KF / EXP-699 (continuation batch #222; 1 задача) добавил offline same-run
проверку production snapshot reader: тест строит синтетические Git blob/tree/
commit identities и API responses, затем `_run_pinned_remote_execution`
использует настоящий `read_github_snapshot_contents`, journal wrappers и raw
commit verifier до Worker. REST intake, pin decision, Worker, local target,
verifier и точные stage save/readback события находятся в одном contiguous
observer run. Три focused tests прошли; полный offline suite — 1297 тестов
(1286 passed, 11 skipped); `git diff --check` clean. Это усиливает offline
evidence, но не доказывает live transport, реальный Worker или публикацию.
EXP-634 остаётся BLOCKED из-за отсутствия подходящего инжектора; R2/MVP
остаются OPEN.

Batch KG / EXP-700 (continuation batch #223; 1 задача) повторно открыл только
одну проверку public read-only composition после офлайн-refactor. Обе точные
закреплённые Docker images были найдены и совпали по ID/`linux/arm64`, но
опт-in CLI завершился до runtime (`runtime_code=unavailable`). Harness не
сохранил bounded readiness status/remaining; точная причина gate неизвестна и
не выводится из результата. Snapshot GET/raw commit, target/verifier run,
stage, approval и mock receipt не достигнуты. Повтора по карточке нет. Следующий
public retry требует новой карточки с safe projection readiness результата.
EXP-634 остаётся BLOCKED; R2/MVP остаются OPEN.

Batch KH / EXP-701 (continuation batch #224; 1 задача) устранил пробел
диагностики EXP-700 в test harness: readiness evidence теперь проецируется
строго в конечную строку `http-<status>:remaining-<integer>` либо постоянный
`unavailable`. Дополнительные поля, malformed values и canary-like строки не
выводятся; readiness/network не вызывались. Focused tests — 3 passed; полный
offline suite — 1298 тестов (1287 passed, 11 skipped); `git diff --check`
clean. Это не повторяет EXP-700: точное значение его readiness не восстановлено,
и новая public попытка требует отдельной карточки. EXP-634 остаётся BLOCKED;
R2/MVP остаются OPEN.

Batch KI / EXP-702 (continuation batch #225; 1 задача) доказал fail-closed
порядок credential prompt: при synthetic readiness ниже порога default
`hidden-terminal` CLI вызывает readiness один раз, не входит в runtime, не
вызывает `getpass` и не создаёт stage. Focused tests — 2 passed; полный offline
suite — 1299 тестов (1288 passed, 11 skipped); `git diff --check` clean.
Секрет, сеть, Worker/model или provider effect не использовались. Это не
авторизует смену источника EXP-634: он остаётся BLOCKED, а R2/MVP — OPEN.

Batch KJ / EXP-703 (continuation batch #226; 1 задача) объединил две локальные
линии: production `read_github_snapshot_contents` получил content-addressed
synthetic REST/raw-commit source внутри pinned runtime, а его exact fetched
bytes прошли тот же observer run через fake Worker, local target/verifier,
SQLite stage/readback, approval-request CLI и enrolled signed mock receipt.
Receipt содержит тот же staged digest и `external_write=false`; повтор отвергнут,
stage и approval inputs не изменились. Три focused tests прошли; полный offline
suite — 1300 тестов (1289 passed, 11 skipped); `git diff --check` clean.
Это не live Worker, public transport, independent verifier или PR. EXP-634
остаётся BLOCKED; R2/MVP остаются OPEN.

Batch KK / EXP-704 (continuation batch #227; 1 задача) выполнил одну отдельную
public-read-only попытку после добавления безопасной readiness-проекции.
Закреплённые target/verifier images совпали с ожидаемыми ID и `linux/arm64`.
Единственный readiness GET вернул HTTP 200 / remaining 10 — ниже порога 35;
CLI остановился до snapshot REST, raw commit fetch, runtime и Docker. Stage,
approval и receipt не создавались; повтор закрыт. Это не добавляет успешного
snapshot/Worker/verifier evidence; R2/MVP остаются OPEN. В актуализации этого
этапа Control Plane одобрил замену источника EXP-634 на hidden terminal input,
но это не является подтверждением запуска и не меняет запрет текущей цели на
использование credentials; live-вызов не выполнялся.

Batch KL / EXP-705 (continuation batch #228; 1 задача) подготовил безопасные
счётчики readiness/snapshot REST/raw commit/runtime для будущих failure
diagnostics; transport attempts считаются до dispatch, а malformed counters
сводятся к `unavailable`. Offline hidden-terminal gate использует
`remaining=10` и подтверждает один readiness вызов без runtime, `getpass` или
stage. Focused tests — 3 passed; полный offline suite — 1301 тест
(1290 passed, 11 skipped); `git diff --check` clean. Публичный integration test
не повторялся. Ранее EXP-704 получил readiness HTTP 200 / remaining 10 (<35)
и остановился до snapshot/runtime. Это не сквозной успех; R2/MVP остаются OPEN.

Batch KM / EXP-706 (R5 prep batch #1; 1 задача) пререгистрировал протокол VP-21/
VP-22 в docs/33: fixed repository-change function and snapshot, four-cell
structured-vs-flat × correction/no-correction comparison, held-out field/type/
range cases, regression oracle, all-attempt reporting and exploratory decision
thresholds. Protocol and links in docs/12/22/24/27/28 were cross-checked. No
model, credentials, network, Docker, target execution or external effect was
used. This is study design only; R5 and criterion 16 remain unfulfilled.

Batch KN / EXP-707 (R5 prep batch #2; 1 задача) сделал casebook из docs/33
машиночитаемым: пять numeric fields × пять invalid classes расширяются в 25
уникальных 422/zero-row cases; зафиксирован known-valid 200/one-row control,
пять scenario outcomes и A–D × 5 repeats × 5 scenarios = 100 attempts.
Четыре focused tests прошли; `git diff --check` clean. Полный suite и target
не запускались; нет model outcome. R5/criterion 16 не выполнены.

Batch KO / EXP-708 (R2 continuation batch #229; 1 задача) выполнил одну новую
anonymous read-only попытку на тех же закреплённых Docker images. Readiness
вернул HTTP 200 / remaining 10 (<35); failure output сохранил bounded счётчики:
readiness=1, snapshot REST=0, raw commit=0, runtime=0. Docker, stage, approval
и receipt не достигнуты; повтор по карточке запрещён. Это вторая отдельная
карточка с quota=10, не успешный snapshot evidence. R2/MVP остаются OPEN.

Batch KP / EXP-709 (R2 continuation batch #230; 1 задача) добавил bounded
`reset-unix=<epoch>` marker для корректного целого Unix reset epoch, иначе
`reset-unavailable`. Это позволяет планировать следующую readiness-проверку,
не раскрывая сырые headers/body. Три focused tests прошли; `git diff --check`
clean. Публичных вызовов не делалось; R2/MVP остаются OPEN.

Batch KQ / EXP-710 (R2 continuation batch #231; 1 задача) проверил точные
cached Docker image IDs (`linux/arm64`) и сделал одну интеграционную попытку.
Readiness вернул `remaining=10`, reset `2026-10-08T22:47:09Z`; bounded
counters: readiness=1, snapshot REST=0, raw commit=0, runtime=0. Интеграция
остановилась до snapshot/runtime/Docker/stage/receipt; повтор по карточке
запрещён. Фокусные safe-marker тесты: 2 passed, `git diff --check` clean.
Никаких credentials/model/provider writes не было; R2/MVP остаются OPEN.
Supplemental full offline suite after this attempt: 1306 tests, 11 skipped,
no failures; two existing SQLite `ResourceWarning`s reported unclosed
connections. This does not establish snapshot/runtime success.
Control Plane records the EXP-710 precondition deviation: its prior-reset gate
could not be verified because EXP-708 retained no reset epoch. The one bounded
readiness GET established the first usable reset timestamp; the next card
requires that timestamp to have elapsed.

Batch KR / EXP-711 (R2 continuation batch #232; 1 task) ran once after the
recorded quota reset. Readiness passed (`remaining=60`); the exact pinned
snapshot path made 25 REST GETs and one raw commit fetch, then invoked the
runtime once. It returned the generic safe category
`remote-snapshot-execution-failed` and observer marker
`tool_requested:SandboxSession.close.target-execution`; verifier/stage/receipt
were not evidenced. This marker does not identify whether the failure was in
the target command, cleanup or another runtime stage. No retry is authorized. No credential, live model or
provider write occurred; R2/MVP remain OPEN.

Batch KS / EXP-712 (R2 continuation batch #233; 1 task) ran the offline
synthetic REST-to-mock composition and pinned Docker synthetic composition;
both passed. No public transport was used. The observed EXP-711 failure did not
reproduce on either synthetic path, so this narrows but does not isolate the
cause to the public-fetched snapshot/runtime combination. No source fix or
root-cause claim is supported; R2/MVP remain OPEN.
The target commit is absent from the Agent00X Git object database, so the exact
source is unavailable for offline replay from this checkout.

Batch KT / EXP-713 (R2 continuation batch #234; 1 task) extends only the
test-harness observer marker with a strict allowlisted sandbox failure category.
Canary-like or malformed event values remain redacted; focused projection test
passed. This is diagnostic preparation only, not a new public attempt or root
cause; R2/MVP remain OPEN.
Batch KV / EXP-715 (R2 continuation batch #236; 1 task) adds a strict
test-harness projection for fixed HTTP/DB probe failure categories. Only the
exact marker and allowlisted category are retained; arbitrary output is
discarded. Three focused offline tests passed; no network/Docker/target run.
Supplemental full offline suite after EXP-715: 1307 tests (1296 passed,
11 skipped), no failures. Two existing SQLite `ResourceWarning`s for unclosed
connections remain.
Batch KW / EXP-716 (R2 continuation batch #237; 1 task) verified the diagnostic
wrapper with a fake session: evidence retained only the allowlisted probe
category, while canary-like stderr stayed out of the evidence map. Two focused
tests passed; no network/Docker/target execution.
Supplemental full offline suite after EXP-716: 1308 tests (1297 passed,
11 skipped), no failures; two existing SQLite warnings for unclosed
connections remain.

Batch KZ / EXP-719 (R2 continuation batch #240) ran one local, network-isolated
Docker diagnostic against the synthetic FastAPI/SQLite app and signed-64
candidate. The fixed overflow payload `level=1e309` returned HTTP 500 with
zero rows; the probe retained only that bounded status/count marker. The
exact cached runtime image matched `linux/arm64`; the container was closed and
the post-check found no remaining container. This is not evidence about the
real pinned target, and EXP-718's failed probe was not retried. R2/MVP remain
OPEN.

Batch LA / EXP-720 (R2 continuation batch #241) returned only
`overflow-exception:category=value` for the synthetic overflow path, but its
middleware replaced rather than re-raised the exception. The explicit
re-raise criterion was not met; EXP-720 is BLOCKED and its result is
provisional synthetic evidence only. It says nothing about the real pinned
repository. R2/MVP remain OPEN.

Supplemental offline suite after EXP-720, with Docker/public opt-in variables
unset: 1311 tests, 1297 passed and 14 skipped; no failures. Two existing
SQLite `ResourceWarning`s for unclosed connections remain. The suite adds no
evidence about the real pinned target; R2/MVP remain OPEN.

Batch LB / EXP-721 (R2 continuation batch #242) repeated the synthetic overflow
diagnostic with an exception re-raise: the test middleware persisted only an
allowlisted category to a temporary in-container SQLite table, re-raised the
original exception, and the parent projected only `category=value`. This
confirms the synthetic handler throws a `ValueError`-class exception for the
fixed overflow case. It does not characterize the real pinned repository or
resolve the public runtime failure. R2/MVP remain OPEN.
Supplemental full offline suite after EXP-721, with Docker/public opt-in
variables unset: 1312 tests (1297 passed, 15 skipped), no failures. Two
existing SQLite `ResourceWarning`s for unclosed connections remain.

Batch LC / EXP-722 (R2 continuation batch #243) changed only the deterministic
test-harness candidate to enforce exact non-bool Python integers in signed-64
range before SQLite. One synthetic Docker run passed 25 malformed field/value
cases and the `1e309` overflow case with 422/zero rows; a valid control stayed
200/one exact row. The candidate is used by the fake Worker in the public
composition test, but this does not prove behavior of the pinned target source
or a real Worker. R2/MVP remain OPEN.
Supplemental full offline suite after EXP-722, with Docker/public opt-in
variables unset: 1313 tests (1297 passed, 16 skipped), no failures. Two
existing SQLite `ResourceWarning`s for unclosed connections remain.

Batch KU / EXP-714 expired without execution; its time-gated authorization was
not reused. Batch LD / EXP-723 then made one newly carded anonymous read-only
attempt. It passed readiness and verified the exact pinned public snapshot
(commit/tree/content digest/23 blobs plus bounded raw commit), the updated fake
Worker proposal, same-run target and pinned verifier, exact stage readback,
and an authority-enrolled synthetic approval through the local mock receipt
with `external_write=false`. This is stronger R2 composition evidence, but the
receipt has `identity_authenticated=false`, and there was no live Worker,
trusted separate-host verifier, real human approval or PR. R2/MVP remain OPEN.

EXP-634's fresh `RUN EXP-634 ONCE` confirmation arrived at
`2026-10-09T08:16:27Z` UTC. The one invocation passed readiness and fetched the
exact pinned snapshot, then failed at the hidden credential prompt before the
DeepSeek channel opened HTTPS; no credential or model request was used. The
bounded CLI output reports `worker-failed`, `approval=not_created`,
`publication=not_attempted` and `external_write=false`. The designated stage
path exists and is preserved without inspecting its contents. This one
invocation is spent and cannot be retried under EXP-634; another attempt needs a
new exact card and fresh user authorization. R2/MVP remain OPEN.

Batch LF / EXP-725 added a distinct fixed EXP-726 authorization profile to the
operator CLI; EXP-634 remains the default. Offline regressions bind the new
phrase, permit and process/task identity, reject a mismatched phrase before
readiness or credential lookup, and reject an unknown card ID before preflight.
Focused CLI suite: 19 passed. Full suite: 1316 tests (1300 passed, 16 skipped).
Batch LG / EXP-726 is DRAFT: the user must run its fixed command from
their own interactive terminal and freshly confirm `RUN EXP-726 ONCE`; Codex
will not relaunch an inaccessible hidden prompt. No new live call has occurred.
R2/MVP remain OPEN.

Batch LH / EXP-727 and Batch LI / EXP-728 extend that regression through the
actual `SignedVerifierClient`: a synthetic in-process verifier signs a PASS
response with an ephemeral Ed25519 key, the client validates the signature,
and the executor still stops with `verifier-trust-unestablished` before stage
persistence because host independence is false. The positive sibling still
saves and reads back its exact stage. Focused cases: 2 passed; full offline
suite: 1317 tests (1301 passed, 16 skipped); `git diff --check` clean. The
synthetic key is not OOB identity or host evidence. R2/MVP remain OPEN.

Control Plane reconciliation 2026-10-09: inspection of the user's terminal
showed the EXP-726 command/script was not running; the shell treated the
confirmation and credential-prompt text as commands. The credential value was
visible in terminal output and must be considered compromised. No DeepSeek
request or model invocation is evidenced. EXP-726 remains DRAFT and must not be
retried with that credential; the user must revoke it before any newly carded
attempt. Revocation is not confirmed. Do not retain or reproduce the value.
The operator sequence was clarified: submit the complete command once at the
shell prompt, enter `RUN EXP-726 ONCE` only after the running program prints its
confirmation prompt, and enter a newly issued credential only at the subsequent
hidden-input prompt. Missing prompts or a returned shell stop the attempt; this
documentation change does not authorize a run.

Batch LM / EXP-732 adds a separate authority-signed, short-lived verifier-host
trust decision bound to one validated enrollment, endpoint, verifier profile
and key, distinct worker/verifier host IDs, and a host-separation evidence
digest. Enrollment and a signed verifier response alone remain audit-only; the
journaled synthetic snapshot path can reach exact local stage save/readback only
with the extra decision, and its bounded CLI carries only decision/attestation
digests. Synthetic keys and evidence prove the contract path only: no OOB host
review, authority-key governance, independent deployment, human approval or
real publication has occurred. R2/MVP remain OPEN.

Batch LN / EXP-733 carries the stage's verifier attestation, key/profile,
enrollment and host-trust-decision digests into the read-only stage review and
the canonical intent covered by the approver's signature. Reopened stages label
these as `recorded_digest_only_not_revalidated`; legacy stages explicitly say
`not_recorded`. The signature round-trip rejects a substituted trust digest,
and synthetic trust-bearing evidence traverses the existing policy/gateway/
broker chain to an in-memory mock receipt bound to the exact staged digest
(`external_write=false`). Focused suites: 79 passed; full offline suite: 1342
tests (1326 passed, 16 skipped); `git diff --check` clean. The signed trust
evidence bytes, authority-key governance, host evidence and OOB deployment
proof are still not persisted/reverified, and approver identity remains
unauthenticated. No live Worker or PR publication occurred; R2/MVP remain OPEN.

Batch LO / EXP-734 carries the canonical signed verifier response, authority-
signed enrollment and host-trust decision (when present), plus the verifier
request digest into an optional bounded stage proof envelope. The actual
synthetic signed-client/executor path stored and read back byte-identical
evidence in SQLite; preview and CLI expose only proof availability/digests.
Malformed, duplicate-key, oversized and digest-mismatched proof fails closed;
legacy stages remain readable but cannot claim proof availability. Focused
suite: 107 tests (99 passed, 8 skipped); full offline suite: 1343 tests (1327
passed, 16 skipped); `git diff --check` clean. To avoid duplicating the full
source snapshot into local evidence storage, only its signed request digest is
retained; request-input reconstruction and authority-signature revalidation
after reopen remain follow-ups. No authority key, credential, live Worker,
authenticated approval, external write or PR publication was used. R2/MVP
remain OPEN.

Batch LP / EXP-735 adds read-only cryptographic revalidation for a reopened
stage when the caller supplies an independently pinned authority public-key
set. It verifies the signed enrollment and host-trust decision, then verifies
the persisted verifier response with the enrolled verifier key, checks the
exact stored result and enforces the 300-second age / 30-second future-skew
bound. A synthetic SQLite readback produced verified provenance; wrong
authority key, substituted enrollment/decision signatures, tampered verifier
signature and stale/future attestations fail closed. The result explicitly
reports `request_input_reconstructed=false`, `identity_authenticated=false`
and `provider_write=false`. Focused tests: 32 passed; full offline suite:
1345 tests (1329 passed, 16 skipped); `git diff --check` clean. This does not
reconstruct the original verifier request or connect revalidated provenance
to authenticated digest-bound approval; synthetic keys do not establish real
authority governance, OOB host separation, live Worker or PR publication.
R2/MVP remain OPEN.

Batch LQ / EXP-736 advances the optional signed-evidence envelope to v2 for
newly verified stages. It retains the exact canonical verifier request bytes
emitted by the signed client (bounded by the verifier request limit), and
stores only the small test-command/timeout binding metadata alongside them.
After SQLite reopen, revalidation parses and reserializes the request
byte-identically, checks its digest against the signed response, recomputes
the complete verifier snapshot tree, and binds candidate contents and all
stage-derived request/result digests before setting
`request_input_reconstructed=true`. The retained snapshot is scanned for
known credential patterns; request bytes stay out of repr, preview and normal
CLI evidence. Legacy v1 records remain readable and continue to report
request reconstruction unavailable. Focused suite: 131 tests (123 passed, 8
skipped); full offline suite: 1345 tests (1329 passed, 16 skipped);
`git diff --check` clean. This reconstructs the exact signed input but does
not establish real authority governance, OOB verifier independence, or
authenticated approval/PR publication. No credentials, network, Worker/model
or provider write were used. R2/MVP remain OPEN.

Batch LR / EXP-737 binds caller-pinned, cryptographically revalidated verifier
provenance into remote-snapshot approval intent. Preparation and later signed-
approval consumption independently reopen/revalidate the exact staged proof;
missing or wrong pins and tampered proof fail before policy approval. An
end-to-end synthetic test reconstructs the verifier request, signs a matching
approval, and verifies it on consumption; unsigned remote-verifier fixtures
are now explicitly rejected before approval. Focused suite: 156 tests (148
passed, 8 skipped); full offline suite: 1348 tests (1332 passed, 16 skipped);
`git diff --check` clean. Authority pins and signatures are synthetic, do not
establish production OOB key governance or authenticated human identity, and
no real Worker, external write or PR publication occurred. R2/MVP remain OPEN.

Batch LS / EXP-738 connects that trust path through the actual enrolled
signed-mock CLI in the same synthetic REST snapshot observer run. The test
reopens the exact stage, independently validates signed verifier provenance
and enrolled approver approval, and returns one in-memory receipt bound to the
same stage digest, repository, branch and idempotency key. Missing/wrong
verifier pins and an unknown observer run fail before receipt; the journal
remains one run and records the local-mock publication event. Focused suite:
37 tests (29 passed, 8 skipped); full offline suite: 1348 tests (1332 passed,
16 skipped); `git diff --check` clean. This is synthetic/fake-only evidence;
the observer explicitly remains partial, the Worker is synthetic, and there is
no production authority/OOB trust, authenticated human identity, external write
or real PR. R2/MVP remain OPEN.

Batch LT / EXP-739 updates the opt-in pinned-public snapshot integration for
the EXP-737 trust contract: its verifier signs the exact verifier result and
request, approval preparation receives a separate caller-pinned verifier key
set, and the enrolled mock CLI receives those pins again on consumption. The
offline synthetic REST twin reaches a same-run in-memory mock receipt and
keeps `identity_authenticated=false`, `external_write=false`, and observer
completeness `partial`. Focused remote-pipeline suite: 27 tests (19 passed, 8
skipped); full offline suite: 1349 tests (1333 passed, 16 skipped);
`git diff --check` clean. The refreshed actual pinned-public/Docker test was
skipped because opt-ins and the exact runtime were not configured; no readiness
or snapshot GET and no Docker execution occurred. Thus previous public-read
evidence is not refreshed against the current approval contract. Production
authority/OOB trust, live Worker, authenticated human identity and real PR
publication remain open; R2/MVP remain OPEN.

Batch LU / EXP-740 validates and materializes a content-addressed
`workspace-manifest/v1` into immutable in-memory path/content pairs only for a
complete `restore_mode=simulation` checkpoint with no pending, in-flight or
known external-effect refs. The manifest, canonical bytes, base64 payloads,
per-file SHA-256 digests, safe relative paths, case-fold collisions, size
bounds and credential-pattern scanner are checked through a read-only SQLite
artifact store. Tests confirm event/checkpoint and artifact-database bytes
remain unchanged; evidence and repr omit file contents. Focused suite: 11
tests passed; `git diff --check` clean. This does not write or execute a
workspace, replay a branch, authenticate artifact origin or prove collector
completeness. Criterion 15 remains partial; criterion 16 is not run, and
R2/MVP remain OPEN.

   Batch LY / EXP-744 attempted the corrected public-snapshot/Docker composition
   once. Both exact cached Docker image inspections passed; the single anonymous
   readiness GET returned HTTP 200 / 31, below the card's threshold of 35
   (reset epoch `1791545485`). The pipeline stopped before snapshot REST/Git
   reads, containers, stage, approval or mock receipt. No retry occurred. This
   adds no new public snapshot or runtime evidence; a future attempt needs a
   fresh exact card. No credential, live Worker/model, human approval, provider
   write or publication occurred. R2/MVP remain OPEN.

   Batch LZ / EXP-745 passed one post-reset public/Docker test through the
   same-run in-memory mock receipt. Assertions validated the exact pinned
   23-file snapshot, one bounded raw-commit fetch, one runtime invocation, and
   receipt/stage digest equality with `identity_authenticated=false`,
   `external_write=false`, observer `completeness=partial`; test duration was
   21.516s. The quiet test emitted no concrete stage digest or observer run ID
   before temporary stores were deleted, so the required reusable evidence is
   incomplete and EXP-745 is recorded BLOCKED. A future public attempt needs a
   fresh card; EXP-747 improves local opt-in evidence output only. No live
   model or provider write occurred; R2/MVP remain OPEN.

   Batch MB / EXP-747 adds a guarded, opt-in success evidence line to the
   public snapshot integration test. It validates and emits only fixed fields:
   pinned snapshot/stage digests, observer run ID, bounded call counters and
   mock receipt flags; default tests remain quiet and failure emits no success
   evidence. Synthetic test, 28-test focused suite (8 skipped), 1353-test full
   suite (16 skipped) and `git diff --check` passed. No public access or Docker
   invocation occurred in this local batch. The new exporter does not itself
   refresh EXP-745's missing run identifiers; EXP-748 is required to do that
   under a fresh one-shot card. R2/MVP remain OPEN.
   Final local hardening binds the emitted summary to the exact configured
   snapshot pin and requires the exact bounded one-run request counts; an
   unexpected count emits no record. The strengthened focused test, 28-test
   remote suite (8 skipped), 1353-test offline suite (16 skipped), and
   `git diff --check` passed. No external request or Docker run occurred.

Актуализация 2026-10-09, Batch MY—ND (6 R2 локальных batch, по 1 задаче):
EXP-770—774 локализовали и устранили проблемы тестового container Worker
startup/IPC: закреплённый образ импортирует package и Worker, получает ровно
две read-only mount (код и два требуемых schema-файла), блокирует IP/DNS и
проходит синтетический однократный Worker→fake-host response→proposal round
trip под сетевыми и ресурсными ограничениями. Batch ND / EXP-775 подтвердил
полный offline suite: 1387 tests, 19 skipped, 0 failures; `git diff --check`
чист. Это новая synthetic boundary evidence; она не является запуском Worker
на pinned GitHub snapshot, live model call, независимым verifier host,
authenticated digest-bound approval или реальным PR. Непосредственный R2-шаг:
вынести test-only process bridge в повторно используемый host-side
`ProposalWorker`, затем подключить его к pinned-snapshot→verifier→durable-stage
composition с fake channel. Live model требует свежей exact task card,
доступного безопасного credential source и отдельного разрешения; provider
write/PR остаётся отдельным будущим gate. R2/MVP остаются OPEN.

Последующее уточнение 2026-10-09: Batch NE / EXP-776 вынес проверенную
container boundary в reusable host-side `ContainerProposalWorker`; 32 offline
focused tests (1 opt-in skip) и один opt-in pinned-container round trip (15
tests, all passed) подтвердили one-shot injected fake channel и cleanup.
Batch NF / EXP-777 впервые подключил этот Worker к exact pinned public snapshot
pipeline. Anonymous read-only snapshot intake и Worker proposal прошли до
target test, который остановился на `sqlite-range-status`; independent
verifier, exact stage и mock receipt не были достигнуты. Анализ показал, что
deterministic candidate не проверяет SQLite signed-64-bit границы для пяти
полей, поэтому это candidate/test-contract gap, а не доказанный дефект Worker.
Новый Batch NG / EXP-778 обновляет только synthetic candidate/probe и затем
делает одну свежую композиционную проверку. Real model, verifier trust,
approval и PR остаются отдельными открытыми gates; R2/MVP остаются OPEN.

EXP-778 local candidate validation now rejects signed-64-bit overflow for all
five numeric fields before writes and preserves one valid insert; its 7-test
offline suite and `git diff --check` passed. The one anonymous exact-snapshot
read intended to derive the revised candidate digest returned HTTP 403, so the
profile digest was not changed and the pinned Worker/target/verifier pipeline
was not re-run. No retry occurred. A new exact public-read attempt must wait
until anonymous access is available; this is a temporary R2 gate, not evidence
of Worker/verifier success. R2/MVP remain OPEN.

Batch NH / EXP-779 recovered the deterministic candidate digest from the
preserved EXP-614 read-only stage artifact rather than repeating the failed
public request. The artifact records the same repository and pinned commit;
the stored `backend/routes.py` bytes match their recorded Git blob SHA-1, and
the source stage is documented as having passed the historical pinned raw
commit/snapshot gate. Applying the EXP-778 deterministic transform yields
`sha256:6166fc4c2a73db910a064de140e71f7bfcbebe3b99846651a3c69770cce39a18`.
This recovers a locally reproducible digest from retained historical evidence;
it is not a fresh public read or a new Worker/verifier/stage run. The HTTP 403
remains recorded without retry. R2/MVP remain OPEN.

Batch NI / EXP-780 added opt-in fixed-field success evidence and verified the
formatter offline (8 focused tests, one opt-in skip); both pinned Docker images
were present. Its one new anonymous intake completed the pinned 23-blob snapshot
and the composition passed Worker proposal, target test, pinned container
verifier, stage readback and preview. It then failed before invoking the local
mock publisher because the test used the stale call signature and omitted the
required `base_branch` argument. No receipt/evidence record was emitted, the
temporary stage was cleaned, and no retry or external write occurred. Batch
NJ / EXP-781 fixes only the test invocation (`master` base branch) and allows
one fresh composition. R2/MVP remain OPEN.

Batch NJ / EXP-781 passed the complete local pinned composition in one attempt:
23-file pinned anonymous snapshot → one `ContainerProposalWorker` proposal →
target PASS → pinned Docker verifier PASS → exact in-run stage readback →
preview → local mock receipt. Snapshot content digest is
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`;
candidate digest is
`sha256:6166fc4c2a73db910a064de140e71f7bfcbebe3b99846651a3c69770cce39a18`;
stage and receipt bind
`sha256:5dd2032094128b666ba178b5fe1b76fbe91f0b65693f9132138f236e5293ef00`.
The pinned verifier identity and verified-contents digest are recorded in
EXP-781's evidence. The report explicitly says one Worker call, no credential,
no provider call, `external_write=false`, approval not created and publication
not attempted. This is the first newly retained evidence for the full local
repository-change composition after EXP-614. It does not establish a separate
verifier trust domain, authenticated human approval, cross-host stage recovery
or real controlled PR publication. R2/MVP remain OPEN.

Batch NK / EXP-782 attempted to retain a newly generated exact stage for the
operator approval CLI. Focused suite passed 15 tests (one opt-in skip), the
destination was confirmed absent, and both pinned Docker images were present.
The single public attempt received HTTP 403 on a blob GET before snapshot
intake completed, so no Worker, verifier, stage copy, approval or receipt was
created. No retry occurred. The evidence directory has no retained full
23-file snapshot; another exact card must choose a distinct anonymous source
or wait for API availability. R2/MVP remain OPEN.

Batch NM / EXP-784 performed one direct HTTPS GET to the fixed codeload URL
using the project's existing verified TLS context (default roots plus
`certifi`). In-memory checks found exactly 23 files and reproduced pinned
content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`;
the route Git blob SHA-1 also matched the preserved EXP-614 base. No archive
was saved. This proves the alternate endpoint can serve the same bytes, but
the existing snapshot model was explicitly REST-origin-only. Batch NN / EXP-785
added a separately typed `github_codeload_archive` origin, a fixed-host
one-shot verified-TLS transport, and strict in-memory archive validation for
paths, sizes, Git blob IDs, root Git tree ID, and canonical content digest.
Executor and publication-seed binding preserve source-specific claim digests;
REST canonicalization remains unchanged. Focused tests: 224 (10 skipped); full
offline suite: 1408 (19 skipped); `git diff --check` clean. No live request or
Docker run occurred in EXP-785. Batch NO / EXP-786 made one codeload GET and
stopped before Worker because archive POSIX file permissions did not match the
parser's overly strict `0o644`/`0o755` check. The pinned content digest was not
reached in that run; no stage was written and no retry occurred. EXP-787 maps
safe POSIX permissions by executable bit while still rejecting special bits,
then made one fresh archive-origin composition. The mapping tests and full
offline suite passed (1409 tests, 19 skipped); the archive, Worker, target,
pinned verifier and in-run stage readback all passed. Stage copy stopped because
the temporary source path was not canonical under macOS (`/var` vs resolved
path); no durable output or mock receipt was created, and no retry occurred.
EXP-788 resolved the temporary DB path before the copy helper and passed one
fresh codeload-origin full pinned composition in 5.741s. The exact verified
stage was retained at `/Volumes/DATA/Agent00X-local-evidence/exp788-stage.sqlite3`
without overwrite. Stage and local mock receipt share digest
`sha256:e66f65b6be74cc70dc6aa3a8cec658bc65c30051bddd9adb3d74536d4c347f51`;
the copy has artifact digest
`sha256:004b9583e19c1eb08506e792c97701803853f4a40a3b5672d36f75070452c8df` and
database SHA-256
`991d4ffa21145432ba7f926c390c7d9f8d262b2604e31c70623d01424a66e46d`.
This is still a local synthetic mock, not operator-signed human approval or
real PR publication. Batch NR / EXP-789 passed that exact retained stage through
the existing request CLI and signed-mock CLI using only a test approver key,
process-generated temporary authority enrollment, synthetic repository IDs,
and the in-memory mock endpoint. The unsigned request and mock receipt were
bound to the retained stage digest; the receipt explicitly remains
`identity_authenticated=false` and `external_write=false`. The SQLite file was
byte-identical before and after. This closes CLI plumbing against a real saved
stage artifact, but not human identity/authenticated approval, independent
verifier trust, production authority governance, cross-host durability or real
controlled PR publication. R2/MVP remain OPEN.

Follow-up review of EXP-789 found that the successful codeload-origin request
had bypassed the signed verifier-provenance prerequisite that already applied
to REST-origin stages. Do not treat that synthetic request/receipt as an
approval-eligible path. Batch NS / EXP-790 makes both remote origins require
caller-pinned verifier provenance before emitting an approval request. The
retained EXP-788 stage now fails closed with no request output because it has
no signed verifier evidence; a future eligible stage must carry independently
validated verifier evidence. R2/MVP remain OPEN.

The first offline attempt to combine archive-origin snapshot claims with the
signed-verifier operator helper stopped at `PinnedSnapshot.validate-fixed-pin`
before Worker execution: `worker_cli` still constructs a REST request and
requires a raw commit object, which codeload does not provide. This is an
operator-runtime source-selection gap, not a reason to relax either source's
pin contract. Batch NT / EXP-791 adds an explicit Control Plane-selected
codeload path, origin-bound execution permit and redacted observer event, then
tests the signed-verifier/approval plumbing with synthetic authority. R2/MVP
remain OPEN.

EXP-791 implementation and Control Plane review passed locally. REST remains
the default and both origins are fixed allowlisted profile/permit values; the
permit is origin-bound. The codeload branch checks the complete owner/repo,
commit, tree, content digest and file-count claim, requires no raw commit
object, and records one fixed archive tool label with bounded status only. A
synthetic typed codeload claim traversed signed verifier provenance, reconstructed
approval request, and the enrolled in-memory mock receipt (`identity_authenticated=false`,
`external_write=false`). Focused tests passed 147 (10 skipped); full offline
suite passed 1415 (20 skipped); `git diff --check` passed. This test patches
the archive reader and trust authorities with synthetic fixtures: no real
codeload request, independent verifier host, live Worker/provider request,
credential, human identity or GitHub write occurred. R2/MVP remain OPEN.

Batch NU / EXP-792 adds a successful signed-verifier HTTP exchange with the
service in a distinct local child process. The verifier signing key is created
inside that process and only the public key plus bounded port/status metadata
crosses the pipe. Focused HTTP-service tests passed 9; the full offline suite
passed 1416 tests (20 skipped). This establishes same-host process-boundary
transport evidence only: the listener is loopback HTTP, the verifier is a
synthetic acceptor, and `independent_host_trust_established=false`. It does not
meet the separate-host or out-of-band host-trust requirement. R2/MVP remain
OPEN.
