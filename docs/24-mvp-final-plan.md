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
   9 skipped), `git diff --check` чист; R2/MVP остаются OPEN.
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
   воспроизводимо replay-нут в EXP-548, но verifier пока не принадлежит
   независимо управляемому trust domain; GitHub snapshot остаётся неподписанным
   API claim; production-grade authenticated approval, recovery и real PR
   publication не доказаны. Для реальной публикации всё ещё нужны точная карточка,
   отдельное свежее подтверждение пользователя и evidence полного controlled
   пути. Не считать suite или batch count критерием закрытия R2; полный gate-by-
   gate аудит остаётся в документе 27. R3—R5 остаются отдельными последующими
   этапами.

### Отложенная кроссплатформенная работа с секретами (после MVP)

Для локальной synthetic-проверки используется только фиктивный источник,
совместимый с portable `CredentialSource`; реальный API key в код, `.env`, prompt,
очередь задач или evidence не добавляется. После прохода MVP, до регулярного
использования реальных credentials или упаковки продукта для других ОС, провести
отдельную работу:

- определить поддерживаемые режимы запуска (интерактивный пользователь,
  headless/CI, заблокированная сессия), модель угроз, ротацию и отзыв ключа;
- выбрать и реализовать OS-specific adapters за тем же узким интерфейсом:
  macOS Keychain, Linux credential service (конкретный backend выбрать после
  проверки desktop/headless окружений), Windows Credential Manager;
- определить безопасное первоначальное внесение и удаление секрета, ACL и
  поведение при отсутствующем, заблокированном или недоступном хранилище;
- проверить каждый adapter на целевой ОС: разрешённый/отказанный/заблокированный
  доступ, missing/revoked credential, ротация и отсутствие секрета в логах,
  аргументах процесса, prompt, файлах и persisted evidence;
- явно подтвердить, что vault защищает хранение, но не исключает краткое
  присутствие секрета в памяти процесса во время HTTPS-запроса.

Это post-MVP hardening и отдельный план работ; portable interface и synthetic
tests сами по себе не являются реализацией или доказательством защищённого
хранилища. Batch FD / EXP-564 добавил lazy adapter для одного значения,
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
подменённые runtime зависимости; операторская команда не запускалась. Для
реального запуска нужна отдельная карточка EXP-566 и свежее подтверждение.
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
