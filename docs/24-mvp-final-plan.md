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

1. **R0 — постановка и контракты наблюдения.** Исследовательская гипотеза и
   сценарии описаны в документах 28 и 30; JSON Schema для ObservationEvent,
   Checkpoint, LearningCorrection и MemorySummary и их contract/regression tests
   реализованы. Этап остаётся частичным: runtime collector, полнота журнала,
   полноценные restore/replay и production durability не доказаны.
2. **R1 — целостность и фиксация действий.** Закрыть подмену manifest после
   verification и рассогласование digest actuator request с approval. Сохранять
   checkpoint каждого решения и вызова до исполнения, в том числе для субагентов.
   При отказе журнала блокировать очередное действие. Добавить негативные тесты.
   Локальные негативные regression-тесты для verified-file manifest, staged
   digest, approval/intent и actuator request проходят; pre-dispatch journal
   gates блокируют dispatch при отказе checkpoint/intent записи. Это локальное
   тестовое свидетельство, а не подтверждение полноты instrumentation для
   субагентов или эксплуатационной durability журнала; R1 остаётся частичным.
3. **R2 — реальный сквозной исполнитель.** Remote snapshot конкретного commit,
   один LLM Worker, независимая проверка, минимальный CLI и контролируемая
   публикация. Все проверки до внешнего write; реальные границы секретов и
   durable reconciliation. Основные пути R2 инструментированы наблюдением R1.
   **Актуальный checkpoint (2026-10-19; детали и 16 критериев — в
   [статусе реализации](27-implementation-status.md)):** R2/MVP остаются OPEN.
   После EXP-1384 были выполнены EXP-1391—1393 и локальная EXP-1395.
   EXP-1395 добавила replay сохранённого stage через фиксированный trusted-HTTPS
   verifier с caller-pinned публичными trust-записями и exact trust digests в
   evidence; CLI не вызывает Worker/model и сохраняет обязательный Docker
   target sandbox opt-in. Это только подготовленная возможность: runtime replay
   не запускался; authority signature не появилась. EXP-1465 израсходовала
   одну отдельно подтверждённую попытку: strict-host-key SSH запустила
   одноразовый verifier и получила маркер `ready`, но полный bootstrap был
   обрезан каналом вывода до локальной проверки. Подписей, verifier HTTP request,
   verified replay или Docker invocation не было; карточка BLOCKED, повтора без
   новой точной карточки и подтверждения нет. Host-fingerprint evidence есть из
   EXP-1385/1386, а EXP-1436 обновила comparison локального Mac и `testdev`.
   Пользователь закрепил digest текущего v2 authority key-set
   `sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`
   и принял EXP-1436 (`sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`)
   только как различие хэшированных fingerprints с точностью наблюдения до
   даты. Это не доказывает идентичность deployment, работу runtime или
   изоляцию verifier. Последующая локальная проверка выявила, что исходная
   EXP-1269 SQLite-БД сопровождается WAL/SHM sidecars, и
   `SQLiteStagedArtifactStore(read_only=True)` отказывает до SQLite-open.
   EXP-1467 superseded. EXP-1483 создала и проверила отдельный mode-0600
   standalone snapshot этого stage вне Git: staged digest сохранён, SQLite
   `integrity_check=ok`, destination WAL/SHM отсутствуют, исходные main/WAL/SHM
   остались byte-identical. EXP-1468 superseded: она ссылается на прежние
   verifier image/code/source-bundle pins. Batch AIH синхронизировал локальные
   transfer helpers с image `sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`,
   code `sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`
   и bundle `sha256:3d7c9c30b2afc53c53b9a1427e95e113d684111209979ee5e7fbce2fe437dad4`;
   batch-end suite прошёл (1,886 tests, 25 skipped). Эти pins локальны и ещё
   не переданы на testdev. EXP-1490 затем проверила portable OCI archive в
   памяти: config digest оказался
   `sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`,
   отличный от прежнего classic-store pin; layer DiffIDs совпали. EXP-1491
   обновила config bridge и remote image check к отдельным manifest/config ID,
   не сравнивая storage `.Size`, и сформировала новый source bundle
   `sha256:d0d51e4a37ba0dc86cd649acf79e7bab3c790dc680bd0ea81df5291782b0f35f`.
   Batch AVI suite прошёл (1,895 tests, 25 skipped). Bundle из Batch AIH
   `sha256:3d7c9c30b2afc53c53b9a1427e95e113d684111209979ee5e7fbce2fe437dad4`
   superseded; актуальный source bundle —
   `sha256:d0d51e4a37ba0dc86cd649acf79e7bab3c790dc680bd0ea81df5291782b0f35f`,
   а актуальный classic-store config ID —
   `sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`.
   EXP-1493 (bundle transfer) и EXP-1494 (image import) остаются отдельными
   DRAFT gates; ни один helper ещё не запускался на testdev. Ответ пользователя
   `RUN EXP-1468 ONCE` не был
   исполнен и не авторизует изменённый scope. Batch AII добавил и
   протестировал локальный bootstrap-capture/session supervisor: он
   ограниченно читает bootstrap в памяти, валидирует текущий профиль,
   сохраняет только публичную строку mode 0600, печатает digest/port и держит
   strict SSH handle для последующего запроса. Его runtime не запускался; это
   не удалённая готовность. Для продолжения нужны новые согласованные карточки
   и отдельное точное разрешение на актуальные remote transfer/import/replay.
   **EXP-1498 (Batch AJA):** retained EXP-1269 candidate воспроизведён один раз
   через актуальный публичный snapshot, target `network=none` sandbox и текущий
   локальный same-host verifier; результат `fresh_pass`. Новый stage сохранил
   byte-identical `verified_contents` и единственный путь `backend/routes.py`,
   но это не повтор Worker/model и не независимая проверка. Observer остаётся
   partial на cursor 87; approval и publication не выполнялись. R2/MVP остаются
   OPEN. EXP-1499 перенесла это ограниченное evidence в checkpoint. EXP-1500
   затем подтвердил fail-closed поведение: без verifier provenance trust
   `build_approval_request` отказал до создания approval request; подпись и
   provider action не выполнялись. EXP-1493 (current source-bundle transfer)
   и EXP-1494 (current image import) остаются отдельными DRAFT gates. Для
   будущего remote replay нужны их отдельные свежие разрешения и последующая
   точная карточка с актуальными pins; старое подтверждение EXP-1465 не
   применялось к другому scope. Batch AJC завершился полным suite: 1,895 тестов,
   25 пропущено; это regression evidence, не end-to-end доказательство.
   Подготовительный аудит EXP-1502 установил дополнительную несовместимость:
   текущий `BRAINBOOSTER_VERIFIER_PROFILE` имеет digest
   `sha256:afffe37328631803e9c1afa2631085b5f2bd7ab02feffdbe344f9df35deb7556`,
   тогда как `exp1383_macos_keychain_signer.swift` принимает только профиль
   `sha256:603f0e674e131ef795f115f099cdeb514452a82def41e5b5853f84f62d7ff281`
   и ограничен EXP-1383. Разрешение использовать ключ было только для
   EXP-1383; signer не читался/не запускался. До нового live replay требуется
   отдельное решение о совместимом authority signer и его точном scope.
   EXP-1503 в Batch AJF прошёл локальный synthetic REST-to-signed-mock-receipt
   composition test с `external_write=false` и
   `identity_authenticated=false`; это не реальный verifier или публикация.
   EXP-1505 в Batch AJH подтвердил локальный отказ GitHub publication при
   synthetic `identity_authenticated=true` до provider configuration; это не
   human-identity evidence. Полный offline suite Batch AJI прошёл: 1,896 тестов,
   25 пропущено за 77.443 секунды; remote gates остаются DRAFT, а independent
   verifier trust и MVP — OPEN.
   EXP-1380 оставила one-shot
   listener на testdev; позднее SSH-процесс завершился с кодом 2 без HTTP 200,
   то есть без подтверждённого verifier-запроса. EXP-1394 затем отдельным
   подтверждённым strict-host-key запуском получила свежий public bootstrap для
   `https://testdev.local/v1/verify` (port 49231, fixed verifier profile,
   caller-pinned CA/key digests). Локальный parser подтвердил схему и pins,
   сохранив `trust=unestablished`; verifier HTTP request/response не было.
   Это само по себе не даёт verifier trust или host-separation proof.
   EXP-1391 создала только для
   локального эксперимента одноразовый in-memory Control Plane Ed25519 signer,
   проверила enrollment и enrollment-bound host-decision. Эти записи были
   краткосрочными, истекли 2026-10-17 в 18:54 UTC и не являются независимо
   управляемым authority source; host evidence доказывает лишь различие двух
   наблюдённых fingerprint, не аттестацию хостов. Verifier-запрос не выполнялся.
   EXP-1392 сверила commit/tree metadata двумя анонимными GitHub GET, а EXP-1393
   проверила полный 23-файловый snapshot codeload-архива и raw Git commit object:
   commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, tree
   `2007066217aadafd9887fb3e3069220333b4fddb`, content digest
   `sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
   Это доказывает соответствие публичных Git object/content pins, не authorship
   или подпись commit. EXP-1385 сохранила `verifier-host-separation-exp1385.json`
   (digest `sha256:82a1c8915d819c5c71fa395a411575a1268b72ecb96efeaed8c235305e6fb941`),
   где на 2026-10-17T18:33:56Z получены разные hashed fingerprints локального
   macOS Worker-хоста и Linux testdev verifier-хоста. Scope артефакта ограничен
   различием fingerprints; он не доказывает аутентичность текущего deployment,
   verifier runtime или isolation. В артефакте указан старый disposable
   EXP-1386 key-set digest, отличный от текущего EXP-1383 key-set.
   EXP-1410 после этого создала локальный EXP-1383-only
   Ed25519 signer, использующий назначенный пользователем macOS Keychain этого
   Mac; он выдаёт public key-set/digest и содержит ограниченный detached-signing
   путь, но не является универсальным credential store. `--sign` читает raw
   representation generic-password item в память процесса; реальная подпись не
   выполнялась, а non-exportable Ed25519 защита этим не доказана. Исторический
   EXP-1410 key-set digest
   `sha256:6e1491662c6e108ff8952f6d42cd15e2f69259a91975aee920471c6edb8701b8`
   superseded by the separate EXP-1435 v2 key-set; pinning applies only to the
   current v2 digest recorded below. Реальные trust-записи не
   подписывались. Pin и ограниченное принятие EXP-1436 теперь получены, но
   остаётся собрать актуальное read-only evidence текущего verifier runtime /
   deployment и подходящее evidence изоляции. EXP-1453 выполнена один раз по
   отдельному разрешению: bounded systemd/Docker/listener queries на testdev не
   нашли совпадающих сервисов, контейнеров или listener на 49231. Это не
   исключает другие механизмы развертывания и не доказывает host isolation.
   Затем понадобятся отдельные точные карточки и разрешения для
   подписи и запроса к verifier. Даже разовый smoke с
   disposable signer не будет независимой проверкой. Полный offline suite после
   EXP-1393 прошёл: 1,859 tests, 25 skipped; это regression evidence, не
   сквозной runtime результат. EXP-1383 остаётся DRAFT; полного
   verifier/approval/publication пути нет. После EXP-1395 полный offline suite
   прошёл: 1,867 tests, 25 skipped; это regression evidence, не live verifier
   result.
   **Обновление 2026-10-18 (EXP-1418–1421):** попытка обеспечить строгую
   non-exportable Ed25519 подпись через Security `SecKey` не состоялась:
   `SecKeyCreateRandomKey` вернул OSStatus `-4`; synthetic `SecKeyCreateWithData`
   подписал тестовое сообщение, но его атрибут остался `extractable=true`;
   `SecItemImport` без Keychain target вернул `errSecUnknownFormat/-25257` для
   проверенных raw/PKCS#8 представлений. Эти проверки не обращались к
   пользовательскому Keychain и не создавали ключ. Существующий EXP-1410
   generic-password signer копирует raw representation в память процесса и
   не выполнял реальную подпись. EXP-1419 исправила только недостижимую форму
   аргументов `--sign`; это не доказательство Keychain-подписи. Текущий public
   key-set digest по-прежнему требует явного пользовательского pin, а
   fingerprint-only evidence EXP-1385 — review/acceptance или отдельно
   разрешённого обновления. Это историческое evidence было дополнено
   EXP-1436; новая fingerprint-only запись ожидает user review. Bootstrap EXP-1394
   (`sha256:798af1e26ed75159b0bf755a8083971b2796b5d6c826bc47afd425415513725c`)
   использовал ephemeral CA, истёкший 2026-10-17T21:28:48Z; он не подходит для
   текущего enrollment. Пользователь разрешил bounded in-process использование
   ключа только для EXP-1383; это не заменяет явный pin key-set и review
   evidence. Новый bootstrap/verifier request не запускался. EXP-1383,
   независимая проверка, approval, publication и весь R2/MVP остаются OPEN.
   EXP-1422 сопоставила локальные пробы с [официальным CryptoKit Keychain sample](https://developer.apple.com/documentation/cryptokit/storing-cryptokit-keys-in-the-keychain): Ed25519 `Curve25519.Signing.PrivateKey` не имеет прямого `SecKey`-представления и для хранения в Keychain показан generic-password путь; документированный Secure Enclave signer использует P-256. Поэтому подтверждённого Apple-native неэкспортируемого Ed25519 пути на этом Mac пока нет. Алгоритм не меняли; реальная подпись не выполнялась. Требуется решение Control Plane: bounded in-process signer либо другой поддерживаемый Ed25519 источник.
   EXP-1423 дополнительно fail-closed отключила `--sign` и `--provision` до stdin/Keychain access; legacy Keychain item и public key-set не менялись. Synthetic-only self-test, help и оба отрицательных вызова прошли; полный offline suite: 1,867 tests, 25 skipped. Это предотвращает случайное использование пути, который раскрывает key bytes процессу, но не закрывает доверие или R2/MVP.
   **EXP-1435:** пользователь разрешил bounded in-process использование macOS Keychain исключительно для EXP-1383, без экспорта/вывода приватных байтов. Старый EXP-1410 item не трогали; отдельный v2 Ed25519 item создан, а public-only key-set сохранён в `control-plane-authority-keys-exp1383-v2.json` (digest `sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`). Generic-password реализация неизбежно держит raw representation в памяти локального процесса; это не hardware-backed/non-exportable защита. Синтетическая проверка signer и help прошли; приватный материал не выводился и не сохранялся в проект. Пользователь подтвердил допустимость памяти signer-процесса, но явный pin нового digest и review/acceptance актуального EXP-1436 host-fingerprint evidence всё ещё нужны до реальной trust-подписи. EXP-1383, независимая проверка, approval/publication и R2/MVP остаются OPEN.
   EXP-1424 зарегистрировала отдельный credential-free local Worker profile. Один запуск EXP-1425 получил HTTP 200 / remaining 60, затем выполнил ровно один локальный Ollama вызов и остановился на bounded `target-test-malformed-status-level-bool` до verifier/stage. Observer cursor 76, `completeness=partial`; `external_write=false`; approval/publication не выполнялись. Обе сохранённые SQLite DB имеют mode 0600 и `quick_check=ok`; owned Ollama daemon остановлен. EXP-1427 выяснила, что обработчик принимает `dict`, поэтому JSON boolean остаётся boolean; FastAPI параметрической coercion здесь нет. EXP-1428 уточнила подсказку модели про `bool` как подкласс `int`, но остановилась до snapshot/model после провала отдельного ручного Python default-context TLS probe; это не было проверкой runner transport. EXP-1429 нашла установленный certifi bundle, а EXP-1430 успешно выполнила через него анонимный TLS-verified GitHub quota GET. EXP-1432 подтвердила, что runner transport уже загружает certifi и требует hostname/CERT_REQUIRED; его runtime отдельно не вызывался. EXP-1433 зафиксировала quota reset на 2026-10-17 23:29:10 UTC при remaining 35. EXP-1434 зарегистрировала новый Worker-профиль с уточнённой bool-инструкцией; focused (51) и полный (1,868/25 skipped) suites прошли, локальные image pins и чистые пути БД проверены, но двухчасовое разрешение истекло до quota gate и runtime не запускался. Для нового запуска нужны свежая карточка/авторизация и quota check в допустимом окне. Полный offline suite 2026-10-19 прошёл: 1,868 tests, 25 skipped — только regression evidence. EXP-1436 обновила Mac/testdev fingerprint comparison; artifact находится в `REVIEW`, не принят и не доказывает deployment/runtime/isolation. Это не меняет последний успешный Worker→target→same-host verifier→stage evidence EXP-1269; независимый verifier, approval, PR и MVP открыты.
   **Обновление 2026-10-19 (EXP-1438—1441):** проверка модели остановилась на
   сравнении несовместимых форматов: Ollama возвращает bare-hex digest, а
   прежний predicate ожидал `sha256:` prefix. EXP-1440 подтвердил, что
   `qwen2.5-coder:7b` имеет digest
   `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`, который
   совпадает с code pin после снятия prefix. Это metadata-only свидетельство;
   inference, snapshot и Worker не запускались. EXP-1442 добавила в local-ollama
   CLI обязательную exact version/model/digest проверку после quota permit и до
   snapshot/Worker runtime; подтверждены только synthetic tests. EXP-1441 —
   DRAFT для одной новой live-попытки с корректным форматом pin, свежей
   одноразовой авторизацией и quota preflight. Независимый verifier, approval,
   PR и MVP остаются OPEN.
   **Уточнение 2026-10-19 (EXP-1447—1448):** чтение pinned target source
   установило, что `/save-session` заранее применяет `int(data.get(...))` к
   пяти числовым полям; поэтому JSON `true` превращается в `1` прежде, чем
   Worker-код сможет проверить строгий тип. EXP-1447 уточнила требование:
   удалить эти преобразования, проверить исходные значения через
   `type(value) is int` и signed-64 границы до любого DB/cursor действия.
   EXP-1441 и EXP-1448 superseded до запуска; EXP-1585 — DRAFT, runtime не разрешён.
   Полный offline suite 2026-10-19: 1,876 тестов, 25 пропущено; это только
   regression evidence. Пользователь выбрал для EXP-1383 ограниченное
   in-process использование Keychain-ключа; явный pin публичного key-set и
   acceptance fingerprint-only evidence всё ещё нужны до подписи. Последняя
   подтверждённая Worker→target→same-host verifier→stage цепочка остаётся
   EXP-1269; независимый verifier, approval, controlled PR и MVP открыты.
   EXP-1450 и EXP-1451 добавили/зафиксировали TTY-only gates для approval
   signing, publication и reconciliation: non-TTY попытки отказываются до
   чтения seed или provider configuration/transport. Это synthetic/local
   evidence; TTY не аутентифицирует человека и ни один provider request не
   выполнялся.
   **Уточнение EXP-1513 (2026-10-19):** Worker Ollama channel теперь передаёт
   в chat endpoint локальный manifest digest reference `sha256-<64 hex>`, а не
   mutable model tag после metadata preflight. Source audit Ollama v0.40.3
   подтверждает разрешение reference в manifest resolver и общий chat route;
   focused tests (9) и full offline suite (1,896 tests, 25 skipped) прошли.
   Установленный CLI также сообщил version 0.40.3, но Ollama server был
   остановлен, поэтому подтверждения реального digest-reference запроса или
   inference нет. EXP-1585 остаётся DRAFT за точным gate `RUN EXP-1585 ONCE`;
   независимый verifier, approval, controlled PR и MVP остаются OPEN.
   EXP-1452 распространила TTY-presence gate на обычный Worker CLI до trust
   artifact loading, Docker, credential lookup, readiness и model preflight;
   synthetic exact-phrase pipe отказ откалиброван отдельным регрессионным
   тестом. Полный suite: 1,877 tests, 25 skipped. EXP-1449 уточнила identity
   boundary: подпись доказывает владение ключом и digest binding, но не
   личность человека; `identity_authenticated` остаётся `false`, а
   authenticated-human-approval criterion — OPEN. Локально проверены точные
   EXP-1383 key-set digest
   `sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`
   и EXP-1436 evidence digest
   `sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`;
   оба ждут явного пользовательского pin/acceptance. Подпись и verifier request
   не выполнялись.
   EXP-1269 — последняя подтверждённая успешная цепочка restricted Worker →
   target tests → same-host pinned verifier → exact stage/readback; approval и
   publication в ней не запускались. EXP-1310 остановился до модели при
   readiness 31 (<36). Для независимого verifier локальная сборка и synthetic
   container checks проходят; следующие исторические попытки ещё не
   подтверждали удалённую image identity:
   EXP-1314 и EXP-1330 сообщили load status 0, затем failed inspect; EXP-1315
   также не подтвердил образ. EXP-1318 подтвердил наличие Docker CLI и
   доступность daemon на testdev, но не образ. Свежая EXP-1320 exact-ID probe
   сообщила `REMOTE_IMAGE_ID_ABSENT` до EXP-1330; после неоднозначного импорта
   EXP-1330 текущее присутствие образа неизвестно. EXP-1332 отдельно вернула
   `REMOTE_INSPECT_FAILED` (exit 11), не подтвердив ни присутствие, ни
   отсутствие. EXP-1334 после отдельного разрешения вернула
   `REMOTE_IMAGE_ID_ABSENT` (exit 10): точный ID отсутствует после EXP-1330;
   query не установила причину. Повторов и иных команд не было. Повторный
   импорт требует обоснованного нового пути и свежего разрешения. EXP-1344/1345
   уточнили локальную OCI identity: manifest/descriptor digest совпадает с
   локальным image ID, а config digest отличается. Единственная разрешённая
   read-only проверка EXP-1346 на testdev вернула только
   `REMOTE_IMAGE_IDENTITY_MISMATCH`, не различив отсутствие config ID и
   несовпадение tuple. Отдельно разрешённый exact-ID query EXP-1347 подтвердил
   `REMOTE_CONFIG_IMAGE_ID_PRESENT` (exit 0): config digest присутствует в Docker
   image store. EXP-1348's отдельный разрешённый tuple inspect вернул
   `REMOTE_CONFIG_IMAGE_TUPLE_MISMATCH` (exit 11), не раскрывая поле. По отдельной
   авторизации EXP-1349 один field-facts inspect вернул
   `id=match|platform=match|size=mismatch|layers=match` (exit 11): установлен
   только факт несовпадения размера; сырые metadata не выдавались. EXP-1350
   локально подтвердил по одному `docker image save` цепочку OCI index → pinned
   manifest → exact config digest → девять layer digests и ordered DiffIDs.
   В сочетании с EXP-1349 это даёт bounded evidence совпадения переносимого
   содержимого на testdev; `.Size` остаётся диагностикой хранения и не служит
   криптографическим идентификатором образа. Причина различия размера не
   измерена. Повтор удалённой диагностики запрещён. После этого EXP-1371
   одной read-only strict-host-key SSH-командой запустил переданный launcher
   только с `--help` и получил `VERIFIER_IMPORT_SMOKE_OK`. Это подтверждает
   Python import readiness bundle на хосте, но не Docker/image readiness,
   service/runtime readiness, bootstrap, verifier behavior или host trust.
   Текущий локальный offline suite после EXP-1381: 1,859 тестов, 25 пропусков.
   Даже подтверждённый импорт
   не докажет deployment/service или host trust. EXP-1312 истекла, а
   EXP-1354 израсходована; следующий Worker-вызов не планируется, поскольку
   успешный stage EXP-1269 сохранён.
   EXP-1351 требует authority-signed enrollment ключа approver до входа в
   GitHub App publication path; это закрывает локальный обход через
   `operator_supplied_unverified` profile, но не подтверждает личность человека
   и не разрешает публикацию. Digest-bound authenticated approval, controlled
   real PR и provider-side recovery не доказаны; ни один критерий MVP не закрыт
   этим checkpoint.
   После подготовки профиля EXP-1352 одноразовая EXP-1354 получила quota 60 и
   один локальный ответ модели, но остановилась на
   `target-test-malformed-status-level-bool`: verifier/stage не достигнуты,
   повтор запрещён. Для дальнейших downstream-проверок использовать уже
   принятую успешную EXP-1269, а не наращивать Worker-повторы.
   EXP-1353 выбрал для следующей независимой проверки одноразовый user-process
   verifier на testdev через локальный SSH-forward и фиксированный
   `https://testdev.local/v1/verify`. До запуска нужны отдельный digest-pinned
   host bundle, управляемый вне verifier authority key set, подписанные
   enrollment/host-decision и evidence разделения хостов; image identity сама
   по себе этого не доказывает. Удалённая карточка пока не READY.
   EXP-1356 добавил строгий локальный preflight публичного bootstrap с
   caller-pinned digest, точным профилем, CA и ключом signer. Результат всегда
   `trust=unestablished`: это не enrollment, не host decision и не удалённый
   verifier-вызов.
   EXP-1357 подтвердил два одинаковых локальных host-bundle build на 32 файлах;
   digest EXP-1300 устарел. EXP-1358 проверил новую import-closure и manifest:
   добавлен только публичный `verifier_image_pin.py`, concrete credential reader
   не появился. EXP-1359 локально закрыл несовместимость адреса: one-shot
   launcher требует exact config-ID inspect перед запуском контейнера,
   запускает по этому ID и только после bound result возвращает идентичность
   manifest из подписанного профиля. EXP-1361 заменил post-capture check на
   потоковый лимит вывода 256/4,096 bytes и timeout 15 секунд с kill/reap.
   Пять adapter-тестов, семь launcher-тестов и 16 bundle-тестов прошли; полный
   suite — 1,826/25 skipped. Сборщик включает import launcher, извлечённый
   архив импортируется. Новый локальный архив: 33 файла, digest
   `sha256:63813cbc6666e543c6b15250631f94689242fd04113c0a544126d2d868b03a86`,
   545,795 байт исходников. Это dirty-worktree evidence, не deployment pin.
   EXP-1360 сверил два byte-identical in-memory build,
   все 33 manifest hash/size и полный набор имён: к принятому набору EXP-1301
   добавлены только публичный pin-модуль EXP-1358 и fixed adapter EXP-1359.
   Конкретного нового credential reader, secret path или динамического alias
   нет. EXP-1361 пересобрал архив после output-bound hardening; его новый digest
   выше заменяет значение EXP-1360. Это всё ещё не разрешение на deployment.
   EXP-1362 добавил локально протестированный streamer для ровно этого
   digest с безопасным receiver. По отдельной карточке и свежему подтверждению
   EXP-1363 один раз передала архив на `alex@192.168.88.101`; получен только
   маркер `BUNDLE_TRANSFER_CONFIRMED`, означающий проверку digest/manifest и
   создание target-каталога. Docker, verifier-сервис и verifier-запрос не
   запускались; runtime readiness, host trust и enrollment не доказаны.
   EXP-1365 добавил detached-signature API для authority trust records без
   передачи закрытого ключа в эти модули; 19 focused tests passed. Изменение
   исходников потребовало отдельного локального обновления bundle pin в
   EXP-1366. После обновления pin полный suite прошёл: 1,841 тест, 25
   пропусков. Новый local-only bundle digest —
   `sha256:5536709798de2a5756a62be351b839598b763025ac4c45635a6f7f272cbdaacd`
   (33 файла, 552,056 source bytes, архив 593,920 байт). Это dirty-worktree
   source identity, не новая deployment authorization. Реального authority
   signer-а, enrollment и host-trust decision пока нет. После этого изменения
   EXP-1367 подготовил новую уникальную target path. После свежего точного
   подтверждения EXP-1368 один раз передала обновлённый bundle с digest
   `sha256:5536709798de2a5756a62be351b839598b763025ac4c45635a6f7f272cbdaacd`;
   получен `BUNDLE_TRANSFER_CONFIRMED` после receiver-side проверки архива,
   manifest и файлов. Это только факт передачи файлов: удалённый import smoke,
   service/runtime readiness, независимое доверие и verifier-запрос не
   подтверждены; Docker и сервис не запускались. Позднейший EXP-1371 подтвердил
   только импорт launcher на удалённом хосте, не запуская Docker, сервис,
   tunnel или verifier request. Ни один критерий MVP не закрыт этими шагами.
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
**Актуализация R2 checkpoint (EXP-1562—1573, 2026-10-19):** EXP-1562 прошёл
только на локально конвертированном verifier-кандидате `f935…`, не на
configured pin `4bc…`; локальный Docker daemon доступен, но наличие exact
configured ID не подтверждено (EXP-1563—1565). Отдельный offline-built
кандидат `b2bf…` присутствует как `linux/amd64`; после закрепления
`--platform=linux/amd64` в фиксированном verifier argv три явно названных
synthetic container-теста прошли (EXP-1566—1568). Это same-host regression
evidence, не independent verifier. EXP-1569 обновила воспроизводимый local
verifier-host bundle pin до `6e2e…` (33 members, 566543 source bytes,
604160 archive bytes); transfer не выполнялся. Batch-end full offline suite:
1947 tests, 26 skipped. Последний успешный Worker→target→same-host verifier→stage
остаётся EXP-1269; свежего Worker, independent remote verifier, authenticated
human approval, provider receipt и controlled real PR evidence нет. R2/MVP
остаются OPEN. EXP-1571 не проверила namespace Docker CLI plugins. EXP-1572
уточнила: `docker buildx v0.27.0-desktop.1` доступен, два локальных builder
работают; официальный Docker exporter поддерживает одно-платформенный Docker
archive output. Это ещё не artifact evidence: нужен bounded offline export и
проверка точного результата. Поэтому config `b2bf…` нельзя объявлять portable
production pin по имеющимся фактам, тем более что EXP-1540—1543 выявили отличие
OCI config от Docker config. EXP-1573 реализовала bounded exporter, но единственная
попытка вернула `EXPORT_FAILED`; retry/diagnostics не выполнялись. Cleanup
временного container был вызван, но его итог не попал в первоначальный marker,
поэтому остаточное состояние не подтверждено. Pin не менялся.
Добавлены девять synthetic tests exporter/validator и cleanup-marker path;
полный offline suite прошёл (1956 tests, 26 skipped).

**Обновление R2 checkpoint (EXP-1574—1577, 2026-10-19):** EXP-1574 добавила
`run_finished(failed)` только после успешно записанного `agent_finished(failed)`
для известных отказов локальных mock CLI; pending/unknown истории остаются
открытыми, а production GitHub publisher не затронут. Это не завершает
Observer completeness. EXP-1575/1576 не классифицировали установленный Buildx
capability; более раннее принятое EXP-1572 evidence о версии и driver остаётся
действующим. EXP-1577 повторно попыталась один bounded offline export с
allowlisted error classification, но вернула `EXPORT_FAILED|reason=unknown`;
archive identity не подтверждена, image не загружен/тегирован, pin не менялся.
Cleanup только созданного временного container не сообщил ошибку. Последний
успешный Worker→target→same-host verifier→stage остаётся EXP-1269. Новый Worker,
independent verifier runtime/trust, authenticated approval, provider receipt и
controlled PR evidence отсутствуют. Критерии остаются OPEN/PARTIAL, R2/MVP —
OPEN. Batch-end full offline suite прошёл: 1,965 tests, 26 skipped; это
regression evidence, не end-to-end acceptance.
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

### Control Plane decision record — human approver identity (2026-10-19)

Keep the protocol claim `identity_authenticated=false` until an independently
verifiable identity binding exists. The current Ed25519 approval signature can
prove possession of an enrolled signing key and bind its canonical request to
one exact staged digest, repository, operation and validity window. The
`approver_id` in that request is a declared key label; enrollment alone does
not prove which natural person controls the key. A TTY gate proves only that
stdin is attached to a terminal. A fresh user decision in the Control Plane
may authorize one precisely described operation operationally, but the current
application protocol has no signed assertion from that channel and therefore
cannot treat it as independently verifiable identity evidence.

Keep the three principals distinct:

- **Enrollment authority:** the Control Plane authority key-set that signs an
  approver-key enrollment. Pinning that public set establishes which key may
  enroll keys; it does not identify the human approver.
- **Digest approver:** the holder of the enrolled Ed25519 key who signs an
  exact approval request. Current evidence establishes key possession and
  request integrity only, not a human-to-key mapping.
- **Provider account:** a GitHub App installation/token identity may establish
  which installation performs a provider operation. It does not establish
  which human approved that operation unless an independently trusted mapping
  links the provider principal to the approved person and exact digest.

No currently configured, supported identity provider or signed Control Plane
assertion independently binds a human subject to `approver_id` in the runtime.
Do not add such a provider, claim a user mapping, or set
`identity_authenticated=true` by inference. A future claim would require a
separately reviewed trust source that signs a subject-to-approver binding for a
specific audience, exact staged digest, operation and single-use nonce, with
bounded issue/expiry times and a defined revocation/key-rotation check before
publication. Expiry/revocation of the approval, enrollment, authority pin and
provider installation must independently stop the write; none may be inferred
from a valid signature alone.

For the present MVP, exact-digest signatures and fresh Control Plane consent
remain separate gates. They may support a narrowly user-authorized operation
only after its own exact task card and fresh confirmation; the resulting
evidence and receipt must continue to say `identity_authenticated=false`.
Because the plan's current publication criterion requires authenticated human
approval, that criterion remains OPEN until a supported identity binding is
implemented and verified. This decision is a boundary clarification, not an
MVP scope reduction or publication authorization.

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
validated verifier evidence. The exact opt-in saved-stage negative-path test
was rerun against the current worktree and retained DB: 1 test passed, asserting
empty stdout, the fixed unavailable-trust diagnostic and byte-identical source
database. This confirms fail-closed local behavior only, not a fresh signed
verifier attestation. R2/MVP remain OPEN.

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

Batch NW / EXP-794 prepares the HTTPS client for the user-selected internal
endpoint `https://testdev.local/v1/verify`: valid `.local` DNS names are no
longer rejected, and an optional private PEM CA can be added only with a
caller-pinned SHA-256 digest (maximum 1 MiB). Default plus certifi roots,
certificate-chain validation, hostname checking, bounded one-shot transport and
sanitized failures remain enabled. A real loopback TLS integration uses a
synthetic SAN-matching `testdev.local` certificate and verifies rejection of
wrong-host, untrusted and digest-mismatched certificates. This is local
transport evidence only. The `.local` name has not been resolved or advertised,
the custom CA is not deployed, the TLS/access-control proxy and process-only
signer credential injection are not configured, and independent-host/OOB trust
is not established. EXP-793 is READY for read-only testdev preflight; its exact
commands still require confirmation in OpenCode for macOS. No remote commands
or writes were made. R2/MVP
remain OPEN. The focused client suite passed 29 tests; full offline suite at
that checkpoint passed 1416 tests (20 skipped), with `git diff --check` clean.

EXP-795 adds an explicit `--signing-seed-source systemd-credential` mode for the
verifier operator entrypoint. Its lazy source reads only the fixed signer seed
name from systemd's `CREDENTIALS_DIRECTORY`, rejects symlinks and non-regular or
oversized inputs, and reports opaque errors; the existing process-environment
mode remains an explicit alternative/default. Synthetic tests verify source
selection and source behavior only. No systemd unit, encrypted credential,
signer key, service-manager invocation or remote host was touched. Combined
focused source/service tests passed 27 tests; the full offline suite passed 1421
tests (20 skipped), and `git diff --check` passed. R2/MVP remain OPEN.

Batch NX / EXP-796 updates both authority-signed verifier enrollment and
host-trust decision validators to accept the chosen `testdev.local` endpoint;
all route/host/port/expiry/signature constraints remain. The enrollment JSON
Schema validates the `.local` record. EXP-797 then wires a `SignedVerifierClient`
into `run_remote_snapshot_with_runtime` only when the caller supplies the exact
fixed endpoint, BrainBooster verifier-profile digest, and an authority-validated
independent-host decision whose worker/verifier host IDs match caller-pinned
values. Docker verifier mode remains the default explicit alternative;
audit-only or expired enrollment/decision fails before SQLite, the Worker
credential, and runtime entrypoint side effects. Focused trust/runtime suite:
99 tests, 2 skipped; full offline suite: 1424 tests, 20 skipped; `git diff
--check` clean. No host setup, network call, real OOB evidence, Worker or
provider operation occurred. R2/MVP remain OPEN.

R2 continuation has reached Batch #324 of an open-ended stage; the total number
of batches is not fixed because external trust, approval and publication gates
remain unresolved. The `.local` verifier-host substage is 5 batches / 7 tasks
(NW, NX, NY and NZ accepted: 6 tasks; NV/EXP-793 accepted with a recorded
duplicate read-only hostname invocation: 1 task). Host setup remains not started.

Batch NY / EXP-798 exposes that trusted HTTPS client through the pinned Worker
operator CLI behind an explicit `--verifier-backend trusted-https` choice. The
CLI accepts only digest-pinned public authority, enrollment, host-decision and
CA artifacts, checks the CA/TLS configuration before readiness or credential
prompt, and passes the validated client plus expected host IDs into the existing
runtime contract. Docker remains the default; trusted HTTPS mode checks only
the target image. Synthetic CLI tests prove wiring and fail-closed bad-digest
behavior without network or Worker calls. The full offline suite now passes
1427 tests (20 skipped). `testdev.local` has not been resolved, configured or
contacted; actual host setup and external trust evidence remain outstanding.
R2/MVP remain OPEN.

Batch NZ / EXP-799 hardens the systemd credential source against a fixed
credential path that is a FIFO: the source now requires a nonblocking open and
fails closed if that flag is unavailable. The synthetic child-process test
proves prompt rejection without exposing path or value. Full offline suite:
1429 tests, 20 skipped. This improves local credential-source liveness only;
the actual systemd credential directory, verifier host, remote trust and Worker
have not been exercised. R2/MVP remain OPEN.

Batch OA / EXP-800 updates the README's test baseline and documents the explicit
`.local` trusted-HTTPS CLI plus systemd credential-source option. It explicitly
states that host/DNS/proxy/signing credential/OOB trust are not configured or
verified. This is documentation reconciliation, not new runtime evidence.
R2/MVP remain OPEN.

Batch OB / EXP-801 routes the pinned operator CLI through the existing
`ContainerProposalWorker` by default, with the host-process worker available
only via an explicit legacy/development option and no fallback. The fixed
runtime accepts the selected proposal worker and observation mode wraps that
same instance. Synthetic tests cover lazy channel wiring, explicit legacy mode,
and fail-closed construction errors; existing opt-in container evidence remains
the only Docker evidence. Full offline suite: 1432 tests, 20 skipped.
No model call, remote `.local` host setup, Docker execution, live verifier, or
publication occurred. R2/MVP remain OPEN.

Batch OC / EXP-802 exercises the pinned CLI default `restricted-container`
through a one-shot synthetic model channel and the pinned target/verifier Docker
profiles. The deterministic repository-change run completed target tests,
verifier PASS, exact SQLite stage/readback and a same-digest enrolled local-mock
receipt, with one observer run ID and one synthetic channel call. The opt-in
Docker test passed in 2.037 seconds; the full offline suite passed 1432 tests
with 20 skipped. No public network, real credential/provider, live
model, independently trusted remote verifier, authenticated human approval or
external PR occurred. R2/MVP remain OPEN.

Batch OD / EXP-803 extends the restricted-default Docker composition to the
public pinned snapshot of `SoldatovAlexander/brainbooster_full_v11` at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`. One bounded anonymous read-only
attempt fetched the exact 23-file snapshot, ran one synthetic model-channel call
inside the Worker composition, passed target tests and pinned verifier, stored
and read back the exact stage, and emitted an enrolled local-mock receipt.
Retained evidence binds tree `2007066217aadafd9887fb3e3069220333b4fddb`, content
digest `sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`,
stage digest `sha256:871ee8ad2ede91232e5f32272265c5e6d74a433aaa06566782737ccf8f736101`,
and observer run `run-9851f08d0cec4452afac4f5f3360807d`; counts were 1 readiness,
1 commit, 1 tree, 23 blob GETs, 1 raw commit fetch and 1 runtime invocation.
Receipt remains `external_write=false`, `identity_authenticated=false`,
`completeness=partial`. This proves public snapshot-to-local-mock composition,
not a live model, independent verifier trust, authenticated human approval or
real PR. R2/MVP remain OPEN.

Batch OE / EXP-804 adds an opt-in no-overwrite destination to the guarded
public composition harness. The destination and SQLite sidecars are checked
before transport construction; after all composition assertions pass, the
exact stage database is copied with digest verification and only bounded
digest/size metadata is emitted, never its path or contents. Synthetic offline
tests prove copy/readback and source immutability. The full suite passes 1433
tests with 20 skipped. No retained public stage has yet been produced with
this feature; a future run's embedded verifier trust would remain synthetic,
so such a stage is review material, not approval-eligible or independent-host
evidence. R2/MVP remain OPEN.

Batch OF / EXP-805 made one fresh readiness request before attempting the
retained-stage public run. It returned HTTP 200 but `remaining=33`, below the
card's required 35, so the pipeline stopped before snapshot GET, Docker,
Worker or stage creation. No retry was made; this is a quota-gate stop, not a
composition failure. A later attempt requires a fresh card and an independently
available quota window. R2/MVP remain OPEN.

EXP-806 / Batch OG completed one read-only SSH preflight. testdev is on Python
3.12.3 with Docker 29.1.3; neither pinned verifier image is present. Cached
Ubuntu package candidates exist for `avahi-daemon` 0.8-13ubuntu6.2 and Caddy
2.6.2-6ubuntu0.24.04.3. Ports 80/443 are free; other application listeners
remain in use and must not be displaced. The OpenCode executor appended only a
local `echo SSH_EXIT=$?` to the exact SSH command to capture status; no extra
SSH/network call or remote mutation occurred. A host-setup card must explicitly
transfer the exact verifier image before service startup. R2/MVP remain OPEN.

EXP-807 / Batch OH completed one strictly read-only SSH preflight. `alex` cannot
use non-interactive sudo (`SUDO_EXIT=1`, password required); Python
cryptography 41.0.7 imports successfully, and testdev runs systemd 255 with
`systemd-creds encrypt` support for stdio, named credentials and host/TPM keys.
No credentials or configuration were read and no host mutation occurred. The
SSH identity therefore cannot install Avahi/Caddy or provision system service
files without a new user-provided elevation path. Do not bypass this boundary
through Docker or another privilege route. `testdev.local` remains configured
only as a local application contract; DNS, TLS and verifier service have not
been deployed. EXP-812 / Batch OM then completed one exact read-only SSH
preflight: testdev is `x86_64` / DPKG `amd64` / Docker `linux/x86_64`,
`testdev.local` resolves on the host to link-local IPv6, and `sudo -n` still
fails (`SUDO_EXIT=1`). Local macOS `dscacheutil` returned no record, and the
application resolver `socket.getaddrinfo` raised `gaierror`; client-side
`.local` resolution is not working yet. The current offline suite passes 1445
tests (21 skipped). No setup or host mutation occurred. R2/MVP remain OPEN.

EXP-808 / Batch OI made one fresh anonymous GitHub readiness GET after the
prior quota-gate stop. The exact pinned local target/verifier image inspections
passed, but readiness again returned HTTP 200 with `remaining=33`, below the
required 35. The test stopped before snapshot/tree/blob requests, raw commit
fetch, Docker containers, Worker or retained-stage creation. No retry occurred;
the exact EXP-808 stage path and SQLite sidecars are absent. A later run needs a
fresh card after quota replenishment. The executor also made one unlisted,
read-only filtered `/private/tmp` metadata check before the run; a later
unfiltered listing request was denied. No file contents or changes resulted.
R2/MVP remain OPEN.

EXP-809 / Batch OJ adds an operator-only Linux utility to generate a fresh
Ed25519 verifier key, send its 64-hex seed only through stdin to the fixed
`systemd-creds --with-key=host` invocation, and atomically save validated
encrypted output with no overwrite and mode 0600. It emits only the public key,
key ID and bounded digests; it does not enroll authority trust or establish host
independence. It refuses non-root execution. Eleven unit tests passed with a
fake tool and synthetic key; the full offline suite passed 1444 tests with 20
skipped. The utility has not been run with real `systemd-creds`, on Linux or on
testdev. R2/MVP remain OPEN.

EXP-793 / Batch NV completed its read-only preflight from OpenCode. The primary
session reported hostname `testdev`, systemd 255, `/usr/bin/systemd-creds`, no
stdout for `avahi-daemon`, `caddy` or `nginx`, and `enp2s0` at
`192.168.88.101/24`. Due to a malformed duplicate UI dispatch, the separate
canceled session repeated only `hostnamectl --static`; total SSH calls were
eight, with one duplicated read-only command. No host writes, service changes,
secret/configuration reads or deployment occurred. The captured interface list
was truncated after its initial lines. This permits preparation of a separate
exact setup card, not host configuration by itself. R2/MVP remain OPEN.

EXP-810 / Batch OK passes the exact public pinned snapshot at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` (23 files) through one restricted
Docker Worker runtime, target tests, pinned independent Docker verifier,
exact SQLite stage/readback, preview and same-digest local-mock receipt. The
attempt used one readiness GET, one commit GET, one tree GET, 23 blob GETs and
one raw commit fetch; no retries. Staged digest is
`sha256:086e5abcd1c6d4f4bcf0c968ddc4dcd59c53cbe3d9ec36d813ccc6449ca6b489`.
The stage was retained as a no-overwrite local review artifact. Receipt remains
`mock_published`, `external_write=false`, `identity_authenticated=false`, with
partial observer completeness. No live model/provider, host verifier, human
approval or PR publication occurred. This strengthens local snapshot-to-mock
composition evidence only. The positive mock approval-request path used a
test-generated verifier authority key set confined to its temporary run
directory, not a retained out-of-band trust anchor. The retained stage therefore
remains ineligible for approval without caller-pinned verifier provenance;
R2/MVP remain OPEN.

EXP-811 / Batch OL adds an opt-in regression harness over the exact retained
EXP-810 public snapshot stage. The actual approval-request CLI returned exit 2,
empty stdout and the fixed `verifier provenance trust is unavailable`
diagnostic; the stage database remained byte-identical. Focused test passed;
ordinary discovery skips the harness without exact stage inputs. This confirms
the mock receipt is not approval-eligible without pinned verifier provenance;
it is not positive trust or human-approval evidence. R2/MVP remain OPEN.

EXP-819—821 / Batches OT—OV resolved a Docker architecture mismatch through
bounded metadata/preflight steps. The previously pinned Python manifest digest
resolves locally to `linux/arm64`, so EXP-818 stopped before building for
testdev. One public Docker Hub metadata request found the version-pinned Python
3.11.16 slim OCI index
`sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e`
and its `linux/amd64` child
`sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761`.
Both Dockerfiles and fixed runtime references pin the immutable multi-platform
index. EXP-825 built target image `sha256:cc32f8cd0d05f92082b9e796ff28e3ea4567426844755b09650a6c37e83acce5`
as `linux/amd64`; the initial verifier image had an incomplete import closure
and its one synthetic request failed closed. EXP-827 added the missing observer
modules and updated the source-derived code digest to
`sha256:5a8cec6b880c085d047b28043502ad75a309cb3c2773f3797670844dce6b2714`.
The corrected verifier image
`sha256:8e9452efd0f24c0db4bd64dc90fee9ed173b6d4c7f4cf08696ac2d3f5168bc74`
is `linux/amd64`, but its one synthetic request and one direct import smoke
both failed closed with process exit 1; the sanitized adapter withheld the
underlying startup detail. No trust enrollment or testdev setup followed. No
testdev DNS/TLS, service, or host configuration occurred. The chosen endpoint remains
`https://testdev.local/v1/verify`; local client resolution and privileged host
setup are still open. R2/MVP remain OPEN.

EXP-831 records the next source-level correction: the verifier image must carry
only the two schemas that `observation_store` loads at startup, under
`/opt/agent00x/schemas`, and bind their content into the verifier code digest.
The new digest is `sha256:3b48eb35f4abb55a539aed008c6c2ded93df006b6dab2da3c9e541a7ab73c7b3`;
focused tests and full offline suite passed (1446 tests, 21 skipped). EXP-832
then built schema-complete verifier image
`sha256:6c0426fd6aee71ffdd119a98f6699d3958d01e1798dc8773185211c42e9b5574`
(`linux/amd64`); one synthetic request passed under the network-none, non-root
profile. It is local evidence only, not testdev enrollment or independent-host
attestation. No testdev DNS/TLS/service setup has occurred.

EXP-833 aligns the fixed target profile to target image
`sha256:cc32f8cd0d05f92082b9e796ff28e3ea4567426844755b09650a6c37e83acce5`
and verifier image
`sha256:6c0426fd6aee71ffdd119a98f6699d3958d01e1798dc8773185211c42e9b5574`, both
previously inspected as `linux/amd64`; it pins the matching source/schema code
digest from EXP-831. Focused tests passed (65 tests, 3 skipped) and full offline
suite passed (1446 tests, 21 skipped). EXP-834 authorizes one quota-gated public
read-only snapshot composition with fake Worker/local-mock receipt; this still
does not prove verifier-host trust, authenticated approval or provider write.

EXP-834 passed once against the pinned public commit: readiness, commit, tree and
23 blob reads plus one raw commit fetch; the target and schema-complete verifier
passed, and a same-digest local SQLite stage/readback produced a mock receipt.
The retained artifact's SHA-256 is
`a70abe067529c5ca8ce836d08e33395e555211c9dc6de32905a29e6bbe6c816a`.
This was an anonymous public-read-only fetch and local mock only:
`external_write=false`, `identity_authenticated=false`, observer completeness
`partial`. It does not satisfy verifier-host trust, authenticated approval, or
live provider execution.

EXP-835 runs the real approval-request CLI against that exact retained stage
without any verifier trust key set. It exits 2 with the fixed
`verifier provenance trust is unavailable` diagnostic, emits no request, and
leaves the stage database byte-identical. This closes the newest-stage
negative-path regression only; it does not provide positive verifier trust or
approval evidence. Full offline suite: 1447 tests, 22 skipped.

EXP-836 verifies local credential wiring end to end with a synthetic seed:
`SystemdCredentialSource` supplies it only at signing time, one real loopback
HTTP request receives a valid profile/nonce-bound Ed25519 PASS response, and the
seed is absent from the response. Focused test passed; full offline suite:
1448 tests, 22 skipped. This does not exercise `systemd-creds`, an actual
systemd unit, remote `.local` TLS, host separation, OOB trust or publication.

EXP-837 removes a version-coupling defect in stored-candidate replay: a valid
historical source stage may be treated as candidate data without treating its
old verifier identity as current trust. The candidate still must pass the
current pinned target and verifier, and replay output is checked against the
current verifier identity. A synthetic regression passed; the exact EXP-548
source stage was validated read-only. Full offline suite: 1449 tests, 22
skipped. This enables a fresh replay attempt but does not itself re-run the
public snapshot, target, verifier or live Worker.

EXP-838 then replayed that exact preserved candidate once through the pinned
public snapshot reader and current images. Snapshot/commit proof completed, but
the expanded target test stopped with `target-test-sqlite-range-status`; the
verifier and output stage were not reached, and there was no retry. A bounded
read-only observer report retained 67 events/33 checkpoints with partial
completeness. The old candidate therefore needs a fresh compliant proposal
before it can be verified by the current target. No model call, credential,
approval or publication occurred.

EXP-839 makes successful replay evidence distinguish the historical source
verifier result (`not_carried_forward`) from a fresh current-verifier PASS
(`fresh_pass`). The regression uses a different historical verifier ID and
confirms the replay invokes the current verifier and stores only its ID. Focused
replay suite: 20 tests passed; full offline suite: 1449 tests, 22 skipped;
`git diff --check` passed. This clarifies successful future replays but does not
change the failed EXP-838 result or create a replacement Worker proposal.

EXP-840 adds an optional operator-supplied IP-literal TCP destination for the
trusted HTTPS verifier path. The URL, TLS SNI/certificate hostname, enrollment
and signed host-trust decision remain pinned to `https://testdev.local/v1/verify`;
the CLI preflight prints the selected dial address. A real loopback TLS test
proved the override skips DNS while validating a SAN for `testdev.local` and
sends one unauthenticated POST. Focused suites: 57 tests passed; full offline
suite: 1451 tests, 22 skipped; `git diff --check` passed. This addresses only
client DNS routing: no testdev request, deployment, independent-host trust,
live Worker, approval or publication occurred. R2/MVP remain OPEN.

EXP-841 hardens that route override to RFC1918, loopback, IPv4 link-local and
IPv6 ULA addresses; public, reserved, unspecified, multicast and scoped IPv6
addresses are rejected. Combining a dial override with an injected connection
factory is also rejected to avoid a false claim about the selected route. A
real loopback TLS regression with a trusted certificate for the wrong SAN
failed before the verifier received HTTP; the matching `testdev.local` case
still passed. Focused client suite: 30 tests passed; full offline suite: 1451
tests, 22 skipped; `git diff --check` passed. No testdev request or host change
occurred. R2/MVP remain OPEN.

EXP-842 adds an optional local Ollama backend for a fresh Worker proposal when
no model credential is available. It uses one fixed `qwen2.5-coder:7b` model
and a bounded, credential-free request to loopback; proposal generation stays
inside the network-none container through the existing IPC. Dedicated
confirmation profiles prevent mixing this path with DeepSeek authorization.
Offline synthetic tests cover request/response rejection and credential-source
non-use. EXP-843 installed Ollama and pulled the one approved model, but its
confirmation was entered at a plain zsh prompt and that card is blocked. EXP-844
then received the exact confirmation at its visible CLI prompt. Its sole local
Chat Completions request failed with HTTP 499 after 30.273 seconds while Ollama
cold-loaded the model. No response, candidate, verifier PASS, approval or
publication resulted; the exclusive SQLite stage passed integrity check and
contains zero staged artifacts. Ollama was stopped, with no retry. EXP-845
raises only the local-model end-to-end timeout to 180 seconds while preserving
the remote DeepSeek 30-second cap, one-call limit and no-retry behavior. Focused
tests pass (75 tests, 1 skipped); full offline suite passes (1465 tests, 22
skipped), and `git diff --check` is clean. No new live model or GitHub request
was made during EXP-845. EXP-846 then made exactly one local model request;
Ollama returned HTTP 200 after about 58.1 seconds (624 generated tokens), but the
CLI emitted only the sanitized `remote-snapshot-execution-failed` result. The
fresh stage passed SQLite integrity check and contains zero staged artifacts;
the server was stopped without retry. No proposal, verifier PASS, approval or
publication resulted, and the underlying pipeline failure is not diagnosed.
R2/MVP remain OPEN. EXP-847 adds fixed sanitized markers to distinguish
unexpected snapshot-preparation failures from execution-pipeline exceptions;
HTTP-specific markers and allowlisted execution result codes remain intact.
Synthetic redaction tests pass. CLI suite: 59 tests (2 skipped); full offline
suite: 1467 tests (1445 passed, 22 skipped). This diagnostic change does not
retroactively identify the EXP-846 failure or prove a candidate.
EXP-848 used a new profile but stopped with `pinned-worker-runtime-failed`
before any local model POST; its exclusive stage remained absent. EXP-849 adds
fixed safe readiness-fetch/ineligible markers and a separate one-shot profile.
The single readiness attempt was rejected as `github-readiness-ineligible`
(`provider_attempts=0`); status/remaining were intentionally not emitted, so the
exact cause is unknown. No snapshot/model request or stage was produced; no
retry occurred. EXP-849 CLI suite passed (31 tests); R2/MVP remain OPEN.
EXP-851 then passed one quota-gated public snapshot → restricted Worker →
target tests → pinned same-host verifier run. Local Ollama returned HTTP 200;
the exact staged change digest is
`sha256:a034c79c6552b5ebc4a2a788d439c579d0024f178675415e586192d0b4403209`,
with one artifact and a read-only integrity-valid stage. The CLI explicitly
reports snapshot-source authentication, verifier authority/host trust and
production durability as limitations. No approval, signature or publication
occurred; this does not satisfy independent testdev verifier or controlled PR
gates. R2/MVP remain OPEN.

EXP-880 restored the exact public `linux/amd64` Python base child previously
identified in EXP-820/821. One anonymous digest-pinned pull completed after
the local preflight; image inspect confirmed its immutable ID/RepoDigest and
`linux/amd64`. No build or container ran. The parent OCI index pull in EXP-879
had resolved locally to arm64 and remains BLOCKED. The base input is available
for a separately carded offline rebuild; no verifier trust, testdev parity,
approval or publication evidence was added. R2/MVP remain OPEN.

EXP-881's offline amd64 target build succeeded but did not reproduce the
previously accepted image ID: it yielded
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`
instead of `sha256:cc32f8cd0d05f92082b9e796ff28e3ea4567426844755b09650a6c37e83acce5`.
The verifier build and request were not attempted. This mismatch leaves
reproducibility unproven; R2/MVP remain OPEN.

EXP-882 found the four base rootfs layers of the new target image identical to
the accepted amd64 child, but the historical `cc32…` image layers/config are
not retained locally, so the ID discrepancy remains unexplained. EXP-883 then
built new local candidate verifier image
`sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`
from target candidate `sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`;
one synthetic network-none/non-root request passed. No profile pins, remote
trust, approval, or publication changed. R2/MVP remain OPEN.

EXP-886 aligned the local BrainBooster profile to target image
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`
and verifier image
`sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`.
The source-derived verifier code digest and fixed repository/snapshot stayed
unchanged; the full offline suite passed (1489 tests, 23 skipped). This is
local same-host profile alignment only. The earlier image-ID discrepancy is
unexplained and the profile update does not establish remote trust, approval,
or controlled publication. R2/MVP remain OPEN.

EXP-887 passed the one quota-gated anonymous public-read-only snapshot replay
using the newly aligned local images. The pinned 23-file snapshot, one Worker
runtime invocation, target and verifier all passed; the same staged digest
`sha256:4db19a974060e24ba88b5ff9298de255802c7c43c4917c6d90ac5256c8353926`
was read back and bound to a retained SQLite stage and local mock receipt.
Receipt is still `external_write=false`, `identity_authenticated=false`, and
observer completeness remains `partial`. No live model, verifier-host trust,
human approval or provider publication occurred. R2/MVP remain OPEN.

EXP-888 no-cache-built the target using the exact source Dockerfile and lock,
with `--pull=false --platform linux/amd64 --network=none`. It produced
`sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`,
which differs from the profile target image ID `sha256:9a6f…`. The verifier was
not built in this card. The discrepancy means current profile/build identity
is not yet reproducible from the project Dockerfile; R2/MVP remain OPEN.

EXP-889 built source-Dockerfile verifier candidate
`sha256:4025f0542be43cd1b58ef582c1a3a22a277b5cb8aab6f489cdf51013ba1ec2a4`
from target candidate `sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`.
One synthetic request passed in the existing network-none/non-root profile.
The profile was not changed; repeat-build evidence is still needed before
calling the current source image identities reproducible. R2/MVP remain OPEN.

EXP-890 repeated the no-cache build with the byte-identical source Dockerfile,
lock, 15-file wheelhouse and locally available amd64 base child. The build
succeeded offline but returned target image
`sha256:fc76bf3f55111ca1382975359add565c94c92a2d8c983d07d2ff0e59249f2903`,
not EXP-888's `sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`.
Per the card, work stopped before verifier build or smoke test. The target
image and temporary context are retained for a separate bounded diagnosis;
source image reproducibility and R2/MVP remain OPEN.

EXP-891 read-only image inspection found that the two targets share the first
five rootfs layer digests; only the final dependency layer differs. Their
bounded config fields match, but Created timestamps and final layer digests
differ. Docker history for EXP-890 failed because the daemon reported its
snapshot missing, so no retry was made and the diagnosis remains partial.
R2/MVP remain OPEN.

EXP-892 exported only `/opt/target-python` from stopped containers and compared
the trees. Hundreds of generated `__pycache__/*.pyc` files differ; source
package files in the comparison did not. The target Dockerfile's pip install
does not disable bytecode compilation, making timestamp-bearing `.pyc` the
likely source of the final-layer drift. This diagnosis does not itself prove a
fixed build is reproducible. R2/MVP remain OPEN.

EXP-893 added pip `--no-compile` to the target dependency-install step. The
standard offline suite passed (1489 tests, 23 skipped). No image was built in
this task; reproducibility of the new target image is still pending. R2/MVP
remain OPEN.

EXP-894 built the corrected target twice from the same byte-identical source
context with no cache, pull, or network. Both inspected as `linux/amd64`, but
IDs differed: `sha256:c7017777…` and `sha256:4134ac8f…`. The repeatability
check is blocked; rootfs-layer versus config-metadata drift is being isolated.
The build context and images remain local. R2/MVP remain OPEN.

EXP-895 found that EXP-894 images share their first five rootfs layers but
their final dependency layer digests differ (`sha256:ebb0bf8c…` versus
`sha256:590cc335…`). Created timestamps differ too, so top-level metadata is
not the sole cause. Next compare extracted dependency file content. R2/MVP
remain OPEN.

EXP-896 copied `/opt/target-python` from each stopped image and `diff -qr`
reported identical paths and file bytes. The final rootfs layer mismatch is
therefore in filesystem/tar metadata rather than dependency file contents.
No container was started. Reproducibility is still not proven. R2/MVP remain
OPEN.

EXP-897 compared mtime, mode, owner/group, and size for all dependency-tree
entries. Only mtimes differed: all entries had epoch `1791743424` in build A
and `1791743429` in build B; modes, ownership, sizes and paths matched. The
five-second wall-clock difference explains the final-layer drift. A fixed
mtime normalization and repeat build are next; R2/MVP remain OPEN.

EXP-898 added a fixed epoch-zero mtime normalization after the target pip
install, retaining `--no-compile` and both pinned base references. The offline
suite passed (1489 tests, 23 skipped). No image was built; deterministic
image-ID verification remains pending. R2/MVP remain OPEN.

EXP-899 rebuilt that normalized target twice with no cache, pull, or network.
Both images inspected as amd64, but IDs still differed:
`sha256:1f05d8e7…` and `sha256:33a67335…`. The corrected pipeline remains
non-reproducible; contexts and images are retained for bounded diagnosis.
R2/MVP remain OPEN.

EXP-900 found identical first five rootfs layers for EXP-899, but the final
layer still differs (`sha256:9e7b5924…` vs `sha256:cc74aa46…`) along with
Created timestamps. The builder-stage normalization was insufficient; inspect
final target filesystem metadata next. R2/MVP remain OPEN.

EXP-901 found matching mtime/mode/owner/size for all exported child entries.
That `docker cp` form omitted `/opt/target-python` itself, so its metadata was
not checked and the diagnosis is incomplete. EXP-902 inspects that root
directory directly; R2/MVP remain OPEN.

EXP-902 copied the actual `/opt/target-python` directory entry from both stopped
images. Root metadata matched (mtime 0, mode 755, owner/group 501:0, size
1088), as did the child entries and file bytes. The final layer digest still
differs, leaving archive/layer serialization or unmeasured metadata as an open
question. R2/MVP remain OPEN.

EXP-903 saved both normalized images and confirmed distinct final layer tar
hashes (`d15f46f6…` vs `81ac1c91…`). The large sorted listings exceeded output
limits, so no reliable direct listing comparison was recorded. The tar listing
showed an `opt/` parent entry at build time; EXP-904 will inspect its exact
mtime. R2/MVP remain OPEN.

EXP-904 found `/opt` itself had mtime `1791743701` in build A and `1791743708`
in build B, matching the seven-second build interval. Mode, owner/group and
size matched. The builder normalization covered `/opt/target-python` but not
its `/opt` parent, which the final COPY creates with wall-clock mtime. This
accounts for the final-layer drift; a scoped normalization/copy adjustment
and repeat build remain. R2/MVP remain OPEN.

EXP-905 normalizes the entire builder `/opt` tree, then creates runtime
`/opt/target-python` through a read-only BuildKit bind mount and `cp -a` in a
single runtime RUN layer before normalizing runtime `/opt`. The offline suite
passed (1489 tests, 23 skipped). No image build was run; reproducibility is
pending. R2/MVP remain OPEN.

EXP-906 built the new target twice with no cache, pull, or network. Both
inspected as amd64 but IDs differed (`sha256:e03c5d3e…` and
`sha256:0b11293e…`). The task context and images are retained. The next
diagnostic checks whether `/workspace` metadata is a residual variable.
R2/MVP remain OPEN.

EXP-907 found `/workspace` metadata identical across images (mtime
`1791572324`, mode 755, owner/group 501:0, size 64), ruling it out. EXP-908
compares rootfs layer IDs against top-level Created timestamps. R2/MVP remain
OPEN.

EXP-908 confirmed matching first five rootfs layers but different final layer
digests (`sha256:5ec03402…` and `sha256:79d88056…`); image Created timestamps
also differ. EXP-909 found `/tmp` identical (mtime `1789689600`, mode 777,
owner/group 501:0, size 64) with no leftover mountpoint. EXP-910 verifies the
current final `/opt` subtree. R2/MVP remain OPEN.

EXP-909 ruled out `/tmp` (`mtime 1789689600`, mode 777, owner/group 501:0,
size 64; no `/tmp/opt`). EXP-910 found `/opt` paths and bytes identical;
exported child and root metadata show epoch-zero normalization. Final-layer
tar serialization remains the open mismatch; compact listing fingerprints
are next. R2/MVP remain OPEN.

EXP-911 found identical raw and sorted `tar -tvf` listing fingerprints for the
two final layers even though their DiffIDs differ. EXP-912 localized the first
byte difference to offset `3212749` but did not map it to an archive member
before cleanup. EXP-913 will locate that offset using tar member offsets;
R2/MVP remain OPEN.

EXP-915 decompressed the two retained final layers and matched their raw
SHA-256 values to the distinct RootFS DiffIDs. The first difference maps to
the `root` directory TAR header: mtime `1791744099` vs `1791744104`; parsed
mode and ownership match. EXP-916's preflight had an incorrect platform
expectation for the locally resolved OCI index, so no build or test ran.
EXP-917 normalized `/` mtime and passed the full offline suite (1489 tests,
23 skipped), but two no-cache offline amd64 builds still differed in the last
RootFS layer (`sha256:e8d69095…` vs `sha256:e07e674c…`). EXP-918 confirmed
the exported layer root entry still carries wall-clock mtime despite an
in-layer `touch /` (`1791744745` vs `1791744751`); `/opt` and its entries are
epoch-normalized. EXP-919 tests BuildKit's documented `SOURCE_DATE_EPOCH`
plus image-exporter `rewrite-timestamp=true` behavior. The first EXP-919
attempt was rejected because `rewrite-timestamp` conflicts with the `--load`
Docker exporter; no image was produced. EXP-920 repeated the same conflict
without `--load` because the image exporter stores/unpacks by default; no
image was produced. EXP-921 explicitly disables `store` and compares only
exported metadata, without loading or pushing; both exports succeeded but
top-level OCI index digests differed. Their descriptors include provenance
attestations with per-build references, so EXP-922 disables provenance and
compares the image manifest itself; both exports produced the same
linux/amd64 Docker manifest digest. EXP-923 removed the ineffective `touch /`
and passed the full offline suite (1489 tests, 23 skipped). EXP-924 repeated
fixed-epoch export from a fresh context copied from the cleaned Dockerfile;
both no-cache offline builds produced identical linux/amd64 Docker manifest
digest `sha256:95410961…`. EXP-925 produced two byte-identical OCI archives
(SHA-256 `4c80035f…`) with matching manifest, config, six compressed layers,
six DiffIDs, and linux/amd64 descriptor. EXP-926 loaded the archive locally;
Docker identifies it by manifest digest rather than config digest. EXP-927
confirmed the exact image is linux/amd64 with expected DiffIDs. EXP-928
successfully imported FastAPI, Pydantic and Uvicorn in a non-root, read-only,
network-none container. EXP-929 pinned that reproducible image in the
target profile and passed the full offline suite (1489 tests, 23 skipped).
EXP-930 passed the existing Docker sandbox integration test against the pinned
image: network/DNS blocked, read-only snapshot/root, non-root, zero
capabilities, resource bounds, and no host/API canary leakage. EXP-932 fetched
one commit-pinned public archive and confirmed its 23-file mode-aware tree
digest matches the current profile value (the separate content-only digest
differs; the profile field name is misleading). EXP-933 ran the target HTTP/DB
probe once in the pinned sandbox and failed at `malformed-status`; source
inspection found integer coercions without strict input/range validation.
No valid-write assertion was reached and no retry occurred. A separate
disposable-copy remediation is assigned as EXP-934; it does not change the
pinned snapshot. EXP-934 passed the same HTTP/DB probe on that disposable
candidate (`malformed=5`, `overflow=1`, `sqlite_range=10`, `valid=1`); this is
candidate evidence only, not upstream. Its integer-only rule would reject
numeric strings accepted by the original route, so it was not selected.
EXP-935 then passed one fresh codeload
→ containerized synthetic Worker → bounded target HTTP/DB probe → pinned
Docker verifier → exact SQLite stage save/readback → CLI preview → same-digest
local-mock receipt composition in 11.551s. Evidence records one Worker
channel call and no credentials/provider calls; approval was not created and
publication was not attempted. This is not a real model call, trusted
independent host, authenticated human approval, or PR. EXP-875 testdev
verification remains open. EXP-936 separately verified that the EXP-935
candidate preserves the base route's ASCII integer-string behavior over
loopback HTTP: one request returned 200 and wrote one exact parsed SQLite row
in the pinned network-none runtime. This remains disposable candidate
evidence only. MVP remains OPEN.
EXP-937 then passed one fresh REST/raw-commit pinned snapshot → synthetic
Worker → isolated target → pinned Docker verifier → signed verifier
attestation → digest-bound approval request and synthetic signed approval →
policy/gateway → enrolled local-mock receipt composition in 32.766s. The
bounded reads were readiness=1, commit=1, tree=1, blobs=23 and raw commit
fetch=1; runtime invocation=1. The receipt explicitly says
`identity_authenticated=false`, `external_write=false`, observer completeness
`partial`; no stage was retained. This advances local approval-chain evidence
but is not independent verifier-host trust, real human approval, or a PR. The
full offline suite after EXP-937 passed 1489 tests with 23 skipped. EXP-938
clarified the profile's Python identifier as `PINNED_SNAPSHOT_TREE_DIGEST`;
the old `PINNED_CONTENT_DIGEST` remains a compatibility alias. The value,
tree canonicalization and wire field names did not change. Full suite after
that clarification passed 1490 tests, 23 skipped.
EXP-939 refreshed the verifier-host source-bundle identity after later source
changes: the old EXP-870 pin (`sha256:5c9e9a1c…`) is stale; two exact local
builds with the current pin both returned
`sha256:13b6c68db8dee5ee8a8e61825ce95b1ca76fb183d02709a7bcc8342b77f0f643`,
75 members and 1,182,276 source bytes. The 12 focused bundle tests passed and
`git diff --check` passed. No network, SSH, credentials, service, or remote
state was used. The old EXP-871 transfer card must not be executed; a fresh
transfer card and user confirmation remain required. EXP-875 and R2/MVP remain
OPEN.
EXP-940 then inspected the exact current profile verifier image in the fixed
local Docker context: the pinned ID is present, `linux/amd64`, with nine rootfs
layers and the expected verifier entrypoint, non-root user and workdir.
`git diff --check` passed. No image mutation, container, network, SSH or remote
operation occurred. This does not prove the image on testdev or independent
host trust. EXP-875 was superseded because it targeted the stale image reported
by the failed EXP-868 transfer; the current exact-pin read-only check is EXP-941
and remains pending its visible OpenCode confirmation.
EXP-943's first exact local Linux launcher-integration run stopped before test
discovery because the pinned verifier image lacks `cryptography`; it also
reported the expected amd64-image/arm64-host mismatch. No test or remote action
occurred, and the card will not be retried. A separate dependency-pinned Linux
test card is needed before treating the new launcher integration as verified.
EXP-944 supplied four hash-verified public wheels in a bounded container-only
install and ran the launcher integration once in the exact pinned
`linux/amd64`, network-none image. The test reached the launcher but failed:
its synthetic request used the one-file `fixture/repository` profile while the
launcher retained the fixed 23-file production profile, and `main` returned 2.
No external or host dependency state changed. EXP-944 is closed and will not be
retried. EXP-945 aligns only the test's server/client profile with its
synthetic request, leaves the production default unchanged, and permits one
local rerun from the retained wheelhouse. This remains launcher integration
evidence only, not independent verifier-host trust.
That one EXP-945 run passed: after rechecking the four retained wheel hashes,
the exact pinned `linux/amd64`, `--pull=never`, `--network none` container
installed dependencies only in bounded `/tmp` and ran the launcher integration
successfully (1 test, 0.255s). It verified the real ephemeral-TLS/loopback
exchange, valid signature, one verifier call, HTTP 200, and no independent-host
trust claim. `git diff --check` passed. EXP-941 and the independent-host,
authenticated-approval, and controlled-PR gates remain open; R2/MVP remain OPEN.
Supplemental full offline suite after EXP-945 passed 1491 tests with 24
skipped in 81.305s; `git diff --check` remained clean.

### Актуальный checkpoint — 2026-10-13

R2/MVP остаются OPEN. На текущем pin EXP-990 прошёл публичный read-only
snapshot, restricted-container local-Ollama Worker, target tests и pinned
same-host Docker verifier; stage и observer evidence сохранены. EXP-1018/1019
добавили WAL-aware standalone review copy, а EXP-1021/1022 проверили обе
стороны process-crash границы только с durable SQLite mock provider. Эти
результаты не доказывают отдельный verifier trust domain, power-loss или
cross-host durability, authenticated human approval либо recovery реального
provider.

Независимый verifier gate не пройден. EXP-1047 проверил отсутствие прежнего
verifier pin на `testdev`; EXP-1049 подтвердил Docker platform `linux/x86_64`, а
EXP-1050 — отсутствие там точного pinned amd64 target-runtime image. EXP-1051
собрал локальный amd64 verifier
`sha256:321c268a841de8cc354125ae25113b38835208f0e0f766f443514b63f1167b0c`
с code digest
`sha256:921f13783dd687610a8c51348d9c096367ee9280436df92ac2ff9f67ceae9d1e`;
EXP-1052 выровнял `VERIFIER_BASE_IMAGE`, а EXP-1055 успешно выполнил два
synthetic runtime-теста на local Docker (`network=none`, `pull=never`). Новый
image не передавался и не запускался на `testdev`. Подготовленный ранее
EXP-1048 import отозван из-за ARM64 mismatch; точный amd64 import требует новой
карточки и свежего подтверждения пользователя. Service, signing-key custody и
out-of-band host-separation evidence не подтверждены. Staged change поэтому не
eligible для доверенного approval. Реального PR, provider write, push или
deployment нет.

R5 preparation продвинулся отдельно: EXP-1027 добавил renderer точных v4
context bytes; EXP-1058 закрепил весь слепой Worker-ввод вместе с pinned
`backend/routes.py` (826 bytes) и фиксированными synthetic S3–S5 controls.
EXP-1059 измерил 20 полных scenario×arm inputs через pinned local tokenizer:
все десять A/B и C/D сравнений ≤1%, максимальное 0.199203%. Это даёт только
eligibility формата для отдельной карточки Worker-run, не outcome evidence;
100 R5 попыток не запускались и criterion 16 остаётся OPEN. EXP-1029 расширил фиксированный
offline target-probe до 25 invalid field/class cases с DB reset перед каждым,
сохранив non-finite и valid controls. Это улучшает заранее заданный oracle,
но пока не является запуском candidate, модели или Worker и не даёт outcome
evidence. EXP-1031 добавил bounded `agent00x-worker-result/v2` для patch,
clarification, blocked и denied исходов; terminal result проходит до CLI и
Observer, а executor завершает запуск до target tests/verifier/stage. Для S4
`timeout/unknown` по-прежнему передаётся как фиксированный контекст, не как
доступная модели tool capability. Никаких R5 model attempts не запускалось;
criterion 16 остаётся OPEN.

Полный offline suite, повторно выполненный 2026-10-13 на текущем worktree:
1,561 тест, 1,536 прошли, 25 пропущено; `git diff --check` чист. Это regression
evidence локального кода и не меняет перечисленные внешние trust/approval/
publication gates. Gate-by-gate доказательства и ограничения см. в
[актуальной матрице реализации](27-implementation-status.md).

Дополнение к checkpoint 2026-10-13 после EXP-1042/1043: targeted Linux/ARM64
suite `test_ephemeral_signed_verifier_https.py` прошёл 6/6, 0 skipped в pinned
network-none контейнере с четырьмя hash-verified dependency wheels. EXP-1043
синхронизировал verifier-host requirements manifest с этими четырьмя runtime
зависимостями и добавил regression на реальный manifest плюс его byte-exact
содержимое в bundle; focused suite 13/13 и полный offline suite 1,554, 25
skipped. Это доказывает локальную воспроизводимость bundle/dependency
декларации, не remote install. Независимый verifier trust на testdev,
service/key custody, authenticated approval, controlled PR и R5 Worker
criterion по-прежнему OPEN; MVP не завершён.

Control Plane пересчитал текущий verifier-host bundle в памяти после EXP-1043:
`sha256:7c8df7dfcd49eff4240a5122a7d198a57a5298eb8d6786cd1749c1bf9b9e1901`
(78 members, 1,226,299 source bytes, 1,300,480 archive bytes). Он заменяет
digest из EXP-1000 для текущего source state. Архив не сохранялся и не
передавался; testdev deployment и независимое доверие не проверялись.

Дополнение после EXP-1046: локальная Ollama 0.40.3 с `OLLAMA_NO_CLOUD=1`
подтвердила loopback bind `127.0.0.1:11434`; ровно два ограниченных GET
получили версию и digest установленной `qwen2.5-coder:7b`
(`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`).
Сервер остановлен, inference и Worker не запускались. Это локальное metadata
evidence, не OS-level egress attestation. Следующий R5-run всё ещё требует
точной карточки и воспроизводимого сетевого ограничения для model/Worker
процесса; criterion 16 и MVP остаются OPEN.

Дополнение после EXP-1047: строго read-only SSH к `testdev` прошёл проверку
host key и BatchMode-authentication; Docker daemon доступен, но точного
verifier image ID `sha256:34069c176da27372d66a7a358eb12b977d920735ab3eb27d6bdfe7b1cc5f77e8`
на хосте нет. Поиск другого tag и retry не выполнялись. Для импорта/развёртывания
нужны отдельная точная карточка и свежее подтверждение пользователя; R2/MVP
остаются OPEN.

Дополнение после EXP-1049: Docker daemon `testdev` сообщает `linux/x86_64`,
тогда как локальный verifier image EXP-1032 — `linux/arm64`. Предложенный
EXP-1048 ARM64 import отозван до исполнения; наличие эмуляции не проверялось.
Перед любым remote transfer нужен совместимый amd64 verifier image и отдельное
свежее подтверждение пользователя на точную удалённую операцию. R2/MVP остаются
OPEN.

EXP-1050 used one strict, read-only SSH command to inspect the exact pinned
`linux/amd64` target-runtime image on `testdev`. Host-key verification,
BatchMode authentication, and Docker access passed, but the exact image ID
`sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187`
was absent (`No such image`, exit 1). No fallback/tag lookup, transfer, build,
pull, or remote mutation occurred. Along with EXP-1047, both candidate pinned
images are absent on `testdev`; EXP-1049's `linux/x86_64` platform also does not
match the local ARM64 verifier. Any future transfer or remote build requires a
new exact task card and fresh approval. R2/MVP remain OPEN.

EXP-1051 built verifier image
`sha256:321c268a841de8cc354125ae25113b38835208f0e0f766f443514b63f1167b0c`
from the accepted amd64 child base, with `--pull=false` and `--network=none`;
local inspect reports `linux/amd64` and 48,849,495 bytes. Its verifier code
digest is
`sha256:921f13783dd687610a8c51348d9c096367ee9280436df92ac2ff9f67ceae9d1e`.
The first full-suite run exposed the stale source-level `VERIFIER_BASE_IMAGE`
constant; EXP-1052 synchronized that constant with the Dockerfile. The targeted
consistency test passed, and the full offline suite passed (1,555 tests, 25
skipped); `git diff --check` is clean. This is local image/source evidence only:
the image was not transferred or run on testdev. Remote verifier trust,
service readiness, authenticated approval and controlled publication remain
OPEN; R2/MVP are not complete.

### Обновление после EXP-1179 — завершение расписания R5, 2026-10-13

Запланированный dispatch R5-001—100 завершён, но это закрывает только очередь
попыток: verified outcome нет. Сводные метаданные ledger: 29 UNKNOWN,
10 blocked, 2 denied, 55 failed и 4 needs-input; stage пуст. В подсчёте не
использовалось содержимое prompt/response/candidate. Результаты и безопасные
reason-code записаны в [матрице реализации](27-implementation-status.md) и
подробном outcome review (§16 протокола R5, [документ 33](33-r5-experimental-protocol.md)).
Следующий шаг — отдельное Control Plane review итогов и решение о redesign или
остановке гипотезы, а не новый запуск по той же 100-ID очереди. R5/criterion 16,
независимый verifier, authenticated approval и controlled PR остаются OPEN;
MVP не завершён.

### Контрольная точка 2026-10-14 — обновление verifier image и границ доказательств

EXP-1190 добавил checkpoint решения о соответствии скопированного sandbox tree
закреплённому snapshot до Worker dispatch; отказ/неизвестный исход записи
останавливает Worker. Локальные и pinned-pipeline tests прошли, но R1 остаётся
частично открытым: полнота collector и production durability не доказаны.
EXP-1191 пересобрал amd64 verifier image из текущей source closure:
`sha256:f9cf14612cd0632eb20e42d6a78f91e7b1b73b09d7947c2edd67fc23e9dfcbc2`,
code digest `sha256:33502d811d02277d7f3ff9f385faf575b4f851c06fb7b2f99722dc3ddb6791bb`.
EXP-1192 проверил его двумя локальными synthetic контейнерными сценариями:
bounded PASS, UID 65532, read-only root, no Docker socket, restricted
environment и snapshot 220,064 bytes. EXP-1193 обновил transfer helper и fake
tests к текущим image metadata; полный suite прошёл 1,696 tests, 25 skipped.
EXP-1196 повторил synthetic canary composition на target image
`sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187` и
текущем verifier image выше; exact `linux/amd64` inspections прошли, один
opt-in test завершился PASS. Проверены только перечисленные stdout/stderr,
SQLite, approval/trust inputs, observer report и local mock receipt.
`external_write=false`, `identity_authenticated=false`; полнота всех runtime
поверхностей и отсутствие реального provider credential этим не доказаны.

Это восстанавливает локальную согласованность image/source и проверяет runtime
на том же Docker host; не подтверждает remote identity, независимый verifier,
service readiness, approval или публикацию. EXP-1184 — однократный импорт
предыдущего image — уже израсходован; EXP-1188 не установил remote identity,
EXP-1189 superseded. EXP-1194 подготовлена как DRAFT на один импорт только
нового точного image и ждёт свежего подтверждения пользователя. Даже успешный
импорт не закрывает доверие к verifier-host: нужны отдельно разрешённые
service/readiness, signing-key custody и OOB host-separation evidence. Без
независимого verifier staged change не eligible для доверенного approval; без
approval и recovery evidence реальный PR не разрешён. R2 и MVP остаются OPEN;
получение локального Docker evidence не считается завершением Thin Vertical
Slice.

### Актуальная контрольная точка — 2026-10-14, EXP-1200–1206

Batch ZG / EXP-1200 прошёл local preflight и один точный gate, но остановился
на `github-readiness-ineligible` (`provider_attempts=0`, observer cursor 4,
partial). Snapshot, model inference, Worker, target tests и verifier не
запускались; Ollama остановлена. Observer evidence сохранился с mode 0600,
stage DB не создан. EXP-1200 исчерпана и не повторяется.

Далее выполнены четыре локальных батча: ZH / EXP-1201 создал новые writable
observer/stage SQLite DB с POSIX mode 0600 и не меняет mode существующих DB;
источник verifier теперь имеет digest
`sha256:c1f02c1f6548c6edf1f3d6ea0bdb5ead061d25c0c38efbfbcfc801f7eea18135`.
ZI / EXP-1202 собрал image, но его единственная inspect-команда ошиблась на
формате; карточка заблокирована без повтора. ZJ / EXP-1203 read-only inspect
подтвердил текущий image
`sha256:49a7d7d14e0545069be45246d5184e3547d50a3a5fae521f17d433b4ea89bb14`,
`linux/amd64`, 48,850,700 bytes, sole tag
`agent00x-verifier-exp466:036dbb36501340cc8e3957e4506c0d04`. ZK / EXP-1204
прошёл два synthetic `network=none` verifier-container теста (UID 65532,
read-only root, no Docker socket); это same-host runtime evidence. ZL / EXP-1205
обновил fake-tested transfer helper: девять ordered DiffIDs, stream guard
48,864,256 bytes в памяти, 12 fake-runner tests и полный offline suite прошли.
Реального transfer/SSH не было.

Batch ZM / EXP-1206 — DRAFT для единственного импорта только этого точного
image в Docker store `alex@192.168.88.101`; требуется новое свежее разрешение
пользователя, так как прежнее разрешение относилось к другому image ID. В
последовательности ZH–ZM всего 6 батчей: 4 карточки приняты, 1 заблокирована,
1 ожидает разрешения. Импорт, если будет разрешён и подтвердится, сам по себе
не установит service readiness, independent verifier trust, ключевое хранение
или host separation.

R2/MVP остаются OPEN. Обязательны: remote verifier service/readiness и
независимое OOB-доказательство разделения host/trust; свежая композиция
закреплённого snapshot → Worker в ограниченной среде → target tests → именно
текущий независимый verifier; authenticated digest-bound approval, recovery и
controlled real PR. EXP-1198 является прошлой source-pin композицией и не
переносится на EXP-1201/1203 image; EXP-1196 canary scan тоже ещё не повторён
на новом image. Никакие same-host synthetic результаты не закрывают эти gates.

### Актуальная контрольная точка — 2026-10-14, EXP-1209–1219

Batch ZP / EXP-1209 остановился после одной anonymous readiness-проверки с
`github-readiness-ineligible` (`provider_attempts=0`, observer cursor 4);
snapshot, модель, Worker, target tests и verifier не запускались. Observer DB
прошла проверку целостности с mode 0600; stage DB не создана. Принадлежащий
запуску Ollama-процесс и listener остановлены. Повтора нет.

Batch ZQ / EXP-1210 получил ровно один bounded header-only результат
`READINESS|200|10|1791984759`; quota reset был назначен на 2026-10-14
16:32:39 Europe/Moscow. Остаток 10 был ниже порога 36 для подготовки новой
Worker-попытки. Batch ZR / EXP-1211 после точного image/platform и source-digest
preflight выполнил ровно один offline synthetic canary composition на текущих
target и verifier images; тест прошёл за 2.921 секунды. Он использовал
synthetic in-memory snapshot/Worker и local mock approval/publication,
проверил перечисленные output, SQLite, approval/trust/report и receipt
поверхности. Receipt сохраняет `external_write=false` и
`identity_authenticated=false`; это same-host synthetic evidence, не live
provider/model вызов, не независимая удалённая проверка и не публикация.

Разрешённый пользователем один импорт EXP-1184 относился к старому image ID
`sha256:321c268a841de8cc354125ae25113b38835208f0e0f766f443514b63f1167b0c`.
Карточка EXP-1184 уже израсходовала единственный runner-вызов и завершилась
`REMOTE_LOAD_IDENTITY_UNCONFIRMED`; по ней повтор запрещён. Это разрешение не
переиспользуется для повторного запуска и не переносится на текущий EXP-1206
image `sha256:49a7d7d14e0545069be45246d5184e3547d50a3a5fae521f17d433b4ea89bb14`.
EXP-1206 остаётся DRAFT до отдельного точного решения по текущему image; новый
remote импорт не выполнялся.

Batch ZT / EXP-1213 выполнил ровно один anonymous header-only запрос и получил
`READINESS|200|10|1791984759` в 16:11 Europe/Moscow — до reset в 16:32:39.
Порог 36 не достигнут, поэтому новая Worker-попытка не подготовлена; для
повторной readiness-проверки после reset потребуется отдельная карточка.

Batch ZV / EXP-1215 выполнил стандартный offline suite текущего рабочего
дерева: 1,699 тестов за 80.611 секунды, 25 skipped, exit 0. Это подтверждает
только локальную регрессионную целостность и не закрывает сквозные MVP gates.

Batch ZW / EXP-1216 исправил несогласованность readiness policy: runtime ранее
разрешал permit при 25 оставшихся запросах, тогда как карточки require минимум
36. Теперь runtime требует 36; граничный тест подтвердил deny при 35 и accept
при 36. Focused suite: 62 теста, 2 skipped; полный offline suite: 1,700 тестов
за 80.663 секунды, 25 skipped, exit 0. Доступный quota evidence всё ещё
равен 10 и снят до reset; Worker не запускался.

Batch ZX / EXP-1217 добавил новую fixed CLI identity для будущего local-Ollama
run EXP-1218: `RUN EXP-1218 ONCE`, process/task
`process-exp-1218-local-001` / `task-exp-1218-local-001`, публичный snapshot и
backend `local-ollama`. Focused suite: 37 passed; полный suite: 1,700 тестов,
25 skipped, exit 0. Модель не запускалась; EXP-1218 остаётся за условием
post-reset readiness >=36.

Batch ZY / EXP-1218 прошёл exact `linux/amd64` image и private DB preflight,
после reset readiness gate пропустил один restricted local-Ollama вызов. Ollama
вернул один HTTP 200 на loopback; CLI затем завершился с
`remote-execution-pipeline-failed` (exit 1), run
`run-15ae81252ff042fc98aa0abafdc6d082`. Redacted observer report частичный:
75 events/37 checkpoints, `tool_failed` на cursor 72. Observer/stage DB — mode
0600, `quick_check=ok`; Ollama остановлен, listener отсутствует. Target-test
PASS, current verifier PASS и verified stage не подтверждены; карточка
BLOCKED без повтора. Batch ZZ / EXP-1219 использовал строго read-only,
allowlisted observer metadata query и классифицировал cursor 72 как
`sandbox-command-nonzero`. Точный sandbox command/output и verifier status не
установлены; candidate/source/model payload не читались.

Batch AAA / EXP-1220 проверил только allowlisted action label на том же
observer cursor 72. Результат `FAILED_ACTION|unclassified`: ни один action не
совпал с фиксированным безопасным списком. Запрос не расширялся, payload и
stage DB не читались.

Batch AAB / EXP-1221 связал terminal event на cursor 72 ровно с его causal
`tool_requested` event по ID, run и соседним sequence. Результат —
`SandboxSession.run.target-tests`; команда, output, candidate и stage DB не
читались. Значит наблюдаемое падение относится к target-test вызову, но
причина ненулевого кода остаётся неизвестной. EXP-1218 не повторяется.

Batch AAC / EXP-1222 протащил только фиксированную allowlisted test-failure
category через executor в CLI; arbitrary stdout/stderr и exception text не
попадают в evidence. EXP-1223 собрал и проверил новый verifier image для
обновлённой source closure: image
`sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`,
`linux/amd64`, code digest
`sha256:5227a5cfa1c4da78ff9f62809a6f7737c5d6d5a8a6e3e562ec9993e6fa533e5e`;
два synthetic runtime tests прошли. Полный suite: 1,702 теста, 25 skipped.
Ни один Worker повторно не запускался. Более диагностичный marker ещё не
проверен на новой локальной Worker-попытке; старый EXP-1218 остаётся BLOCKED.

Batch AAE / EXP-1224 обновил fake-tested transfer helper для нового verifier
image: exact `linux/amd64` ID, sole tag, nine ordered DiffIDs и in-memory
archive size 48,864,768 bytes; 12 fake-runner tests и полный offline suite
(1,702 tests, 25 skipped) прошли. Сам transfer runner, SSH и testdev не
использовались.

Batch AAF / EXP-1225 получил свежее точное разрешение на один импорт image
`sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07` в
Docker image store testdev. Единственная попытка завершилась
`REMOTE_LOAD_IDENTITY_UNCONFIRMED` (exit 18); образ мог загрузиться частично или
полностью, но remote identity не подтверждена. Повтора, диагностики и cleanup
не было; карточка BLOCKED. EXP-1206 SUPERSEDED.

Batch AAG / EXP-1226 заблокирован до запуска тестов из-за неверного unittest
selector. Batches AAH–AAI / EXP-1227–1228 заблокированы до Docker из-за
несовпавшего с профилем verifier digest в ручном opt-in; контейнеры не
запускались. Batch AAJ / EXP-1229 прошёл exact current-image/source-digest
preflight и одну same-host synthetic Docker composition на target image
`sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187` и
verifier image `sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`;
тест завершился PASS за 2.574 s. Composition использовала synthetic
snapshot/Worker и local mock approval/publication; receipt сохраняет
`external_write=false`, `identity_authenticated=false`. В серии ZH–AAJ всего
29 батчей: 21 приняты, 7 заблокированы и 1 SUPERSEDED. Remote verifier
readiness/trust остаются непроверенными; неопределённый результат EXP-1225 не
позволяет утверждать наличие образа на testdev. Не доказаны свежая публичная
snapshot→real Worker→target→independent remote verifier композиция,
authenticated digest-bound approval, recovery и controlled real PR. R2/MVP
остаются OPEN.

Batch AAK / EXP-1230 обновил локальный CLI contract: local Ollama теперь
требует явный `--credential-source not-applicable`, и тесты подтверждают, что
этот путь не строит credential source и не читает `AI_PROCESS_API`; DeepSeek
отвергает `not-applicable`. Добавлена новая fixed identity
`RUN EXP-1230 ONCE` / `process-exp-1230-local-001` /
`task-exp-1230-local-001` для будущей попытки на current pins. Focused suite —
37 passed; полный offline suite — 1,702 теста, 25 skipped. Worker/model и
network ещё не запускались. По состоянию через AAK: 30 батчей, 22 приняты,
7 заблокированы, 1 SUPERSEDED. Следующий R2 шаг — проверить anonymous GitHub
readiness перед отдельной свежей карточкой для полной local-Ollama попытки;
credential-free synthetic PASS не закрывает реальный Worker, remote verifier,
approval, recovery или PR gates.

Batch AAL / EXP-1231 выполнил одну anonymous verified-TLS readiness-проверку и
получил `READINESS|200|35|1791988401` (exit 0); reset — 2026-10-14 17:33:21
Europe/Moscow. 35 запросов ниже требуемого порога 36, поэтому Ollama, snapshot и
модель не запускались. Нужна новая readiness-проверка после reset и отдельная
карточка fresh Worker attempt. Счётчик через AAL: 31 батч, 23 приняты, 7
заблокированы, 1 SUPERSEDED. R2/MVP остаются OPEN.

Batch AAM / EXP-1232 зарегистрировал отдельный future profile EXP-1233 для
одного credential-free local-Ollama запуска: фиксированные phrase/process/task,
public snapshot origin и backend `local-ollama`. Focused CLI suite — 37
passed; full offline suite — 1,702 теста, 25 skipped. Worker, модель и сеть не
запускались. Через AAM: 32 батча, 24 приняты, 7 заблокированы, 1 SUPERSEDED.
EXP-1233 требует отдельной точной execution card, а quota gate сейчас ниже
порога; R2/MVP остаются OPEN.

Batch AAN / EXP-1233 подготовлен как следующий fresh local-Ollama сценарий на
current target/verifier pins с `--credential-source not-applicable`, exact
one-shot identity и ограничением на один model request. Карточка остаётся
DRAFT до post-reset anonymous readiness >=36; текущий результат 35 не даёт
запускать daemon/snapshot/model. Даже при полном локальном PASS это будет
same-host composition, а не independent verifier-host evidence. Счётчик через
AAN: 33 батча, 24 приняты, 7 заблокированы, 1 SUPERSEDED и 1 DRAFT. R2/MVP
остаются OPEN.

Фактический результат AAN / EXP-1233: после reset readiness составил
`READINESS|200|60|1791992019`, затем один credential-free local-Ollama run
получил закреплённый public snapshot и выполнил один local model request.
Target tests завершились allowlisted категорией `target-test-malformed-status`;
current verifier PASS и verified stage отсутствуют, approval не создан,
publication не запускалась. Ollama остановлен, обе SQLite БД прошли
`quick_check=ok` с mode `0600`; candidate/source/model payload и raw test command
или output не читались. EXP-1233 — BLOCKED без повтора.

Batch AAO / EXP-1234 одним anonymous GET получил HTTP 200 для публичного
`backend/routes.py` на pinned commit. `POST /save-session` принимает общий
`dict` и выполняет `int(...)` над пятью числовыми полями; явная schema/range
validation и перевод ошибок преобразования в HTTP 422 в этом route отсутствуют.
Этого недостаточно, чтобы установить причину `target-test-malformed-status`;
повтор Worker не разрешён. Через AAO: 34 batches, 25 accepted, 8 blocked,
1 superseded. R2/MVP всё ещё OPEN: независимый verifier, authenticated
digest-bound approval, recovery и controlled real PR не доказаны.

Batch AAP / EXP-1235 статически проследил безопасную проекцию failure marker:
probe ожидает HTTP 422 для каждого invalid numeric input (включая `true`, `1.5`,
строку `"1"` и выход за signed 64-bit), а несовпадение статуса классифицируется
как `target-test-malformed-status`. Candidate не читался, поэтому конкретное
неуспешное значение не установлено. Через AAP: 35 batches, 26 accepted,
8 blocked, 1 superseded. Это сузило диагностическую область, но не разрешает
повтор Worker и не подтверждает target PASS, verifier, stage, approval или PR.
R2/MVP остаются OPEN.

Batch AAQ / EXP-1236 уточнил `TASK_INSTRUCTION`: все пять session fields
должны быть JSON integer tokens; boolean, float, любая строка (включая
числовую `"1"`) не приводятся и отклоняются. Сохраняются требования HTTP 422
до DB write для invalid input, signed-64-bit range и HTTP 200/ровно одной строки
для valid input; target change path остаётся только `backend/routes.py`.
Добавлены контрактные проверки текста инструкции. Focused CLI suite: 37 passed;
full suite: 1,702 passed, 25 skipped; scoped `git diff --check` passed. Через
AAQ: 36 batches, 27 accepted, 8 blocked, 1 superseded. Ни Worker, ни модель не
запускались; R2/MVP остаются OPEN.

Batch AAR / EXP-1237 зарегистрировал новый профиль EXP-1238 после уточнения
numeric contract: фиксированные phrase/process/task ID, публичный snapshot
origin `github_rest_api_claim` и backend `local-ollama`. Дополнительный synthetic
CLI-тест подтвердил `pinned-docker`, `restricted-container`,
`credential-source not-applicable` и нулевые credential lookups. Focused suite:
38 passed; full suite: 1,703 passed, 25 skipped; `git diff --check` passed.
Через AAR: 37 batches, 28 accepted, 8 blocked, 1 superseded. Это только
подготовка профиля: readiness после reset и отдельный Worker card ещё нужны;
R2/MVP остаются OPEN.

Batch AAS / EXP-1238 подготовлен как отдельный one-shot retry после EXP-1233,
свежим профилем и уточнённым strict JSON integer contract. Карточка остаётся
DRAFT до следующего GitHub quota reset; затем требуется один anonymous
readiness check с HTTP 200 и remaining >=36. Локальные preflight уже прошли:
оба pinned images совпали по ID и `linux/amd64`, verifier-context digest test
прошёл, Ollama client — 0.40.3. Предварительный `lsof` подтвердил отсутствие
listener, а оба EXP-1238 DB пути отсутствуют и не являются symlink; оба условия
повторить перед start/write. До прохождения gate не запускать daemon, snapshot
или модель. При проходе — финальная проверка listener/model, максимум
один local model request и никаких credentials или внешних записей. Даже
полный локальный PASS не докажет независимый verifier,
authenticated approval или controlled PR. Через AAS: 38 batches,
28 accepted, 8 blocked, 1 superseded, 1 draft. R2/MVP остаются OPEN.

Batch AAT / EXP-1239 обновил `R2 exit matrix` в docs/27 по evidence на
2026-10-14. Матрица явно разделяет текущий pinned snapshot, неуспешный
EXP-1233 Worker/test outcome, same-host synthetic EXP-1229 PASS, неопределённый
remote image status EXP-1225, отсутствие current verified stage и human
approval, а также отсутствие реального PR/recovery receipt. EXP-1238 остаётся
DRAFT; независимый verifier и R2/MVP не подтверждены. Через AAT: 39 batches,
29 accepted, 8 blocked, 1 superseded, 1 draft. Изменён только статус-документ;
`git diff --check` прошёл.

Batch AAU / EXP-1240 подтвердил one-shot границу `LocalOllamaChatCompletionsChannel`:
канал отправляет максимум один HTTP request и не повторяет соединение/HTTP
ошибки; `ContainerProposalWorker` читает один model request frame и вызывает
канал один раз. Новая fake connection-failure регрессия подтвердила ровно один
POST и невозможность второго вызова на том же канале. Focused suites: 23 passed,
1 skipped; `git diff --check` прошёл. Ollama не запускался; через AAU: 40
batches, 30 accepted, 8 blocked, 1 superseded, 1 draft. R2/MVP остаются OPEN.

Batch AAV / EXP-1241 актуализировал таблицу 16 критериев Thin Vertical Slice
в docs/27 на 2026-10-14. Критерии 1, 2, 7, 10 и 13 отражают current-pin
EXP-1233 attempt как частичный failure до verifier/verified stage/approval/
publication; фиксированные observer counts/DB integrity отражены без чтения
candidate/source/model payload. Все незакрытые статусы и отрицательный результат
критерия 16 сохранены. Через AAV: 41 batches, 31 accepted, 8 blocked,
1 superseded, 1 draft. `git diff --check` прошёл; R2/MVP остаются OPEN.

Batch AAW / EXP-1242 сверил точный accepted EXP-1229 card с его тестом и
зафиксировал, что current-pin same-host synthetic Docker composition также
сканирует synthetic canary в ограниченном наборе runtime/persisted поверхностей:
потоки вывода Worker/approval/publication, stage и observer SQLite, approval и
trust-файлы, observer report и локальный mock receipt. Целевой и verifier image
IDs и source digest указаны в criterion 3 docs/27. Это не live credential/model
тест и не доказательство полного сбора всех поверхностей. Через AAW: 42 batches,
32 accepted, 8 blocked, 1 superseded, 1 draft. `git diff --check` прошёл;
R2/MVP остаются OPEN.

Batch AAX / EXP-1243 уточнил Worker task instruction перед отдельной попыткой
EXP-1238: exact Python integer check (`type(value) is int`, поскольку `bool`
является подклассом `int`), signed-64 bounds до DB call и сохранение defaults
для пропущенных полей. Это профилактическая точность контракта; она не
устанавливает точную причину EXP-1233. Focused suite: 38 passed; full offline
suite: 1,704 tests, 25 skipped; `git diff --check` прошёл. В AAX: 43 batches,
33 accepted, 8 blocked, 1 superseded, 1 draft. R2/MVP остаются OPEN.

Batch AAY / EXP-1244 закрепил в DRAFT карточке EXP-1238 SHA-256 Worker CLI и
контрактных тестов, включая точную post-EXP-1243 task instruction. Это повышает
воспроизводимость следующего bounded attempt, но не является runtime evidence.
В AAY: 44 batches, 34 accepted, 8 blocked, 1 superseded, 1 draft. R2/MVP
остаются OPEN.

Batch AAZ / EXP-1245 добавил profile-level regression: EXP-1238 передаёт
строгий integer contract в runtime Worker arguments и ограничивает target path
`backend/routes.py`. Focused suite: 38 passed; полный offline suite: 1,704 tests,
25 skipped. Test source SHA-256 обновлён в EXP-1238 и EXP-1244; это доказывает
передачу контракта в аргументы, но не выполнение модели или изменение target.
В AAZ: 45 batches, 35 accepted, 8 blocked, 1 superseded, 1 draft. R2/MVP
остаются OPEN.

EXP-1238 прошёл единственный post-reset readiness gate с
`READINESS|200|35|1791992064`, ниже порога 36. Попытка остановлена до Ollama,
snapshot и модели; карточка теперь BLOCKED и не повторяется. Batch ABA / EXP-1246
зарегистрировал distinct local-ollama identity (`RUN EXP-1246 ONCE`) и прошёл
focused/full suites (39; 1,705 tests, 25 skipped). Batch ABB / EXP-1247 прошёл
fresh readiness `READINESS|200|60|1791996011` и один credential-free local model
request на exact snapshot, но снова завершился `target-test-malformed-status`
до verifier/stage. Run ID `run-fe793efd813b45fa859eeaf9ea615cc0`, cursor 74,
partial; candidate/source/model output не читался; обе DB прошли integrity check
и mode 0600, Ollama остановлен. Approval/publication не было. Batch ABC / EXP-1248
обновил ограниченное evidence для критериев 2, 7, 10, 13 и R2 exit matrix без
продвижения статусов. Через ABC: 48 batches, 37 accepted, 10 blocked,
1 superseded, 0 draft. Worker PASS, independent verifier, approval и publication
не доказаны; R2/MVP остаются OPEN.

Batch ABD / EXP-1249 уточнил Worker prompt по фиксированному acceptance oracle,
не предполагая причину повторного `target-test-malformed-status`, и зарегистрировал
profile EXP-1250. Focused suite: 40 passed; full offline suite: 1,706 tests,
25 skipped. Batch ABE / EXP-1251 прошёл post-reset readiness
`READINESS|200|60|1791999646` и выполнил ровно один local-Ollama вызов. Target
tests завершились фиксированным `target-test-malformed-status`; run
`run-5cde42df8f474fa39d3dcb188b1ed096`, cursor 74, partial. Candidate/source/model
output не читался; verifier PASS, verified stage/readback, approval и publication
не возникли. Ollama остановлен, listener отсутствует; обе DB дали
`quick_check=ok`, mode 0600. EXP-1251 BLOCKED, без повтора. Через ABE: 50 batches,
38 accepted, 11 blocked, 1 superseded, 0 draft. R2/MVP остаются OPEN.

Batch ABF / EXP-1252 повысил диагностическую точность фиксированного target
probe: маркер различает только конечные пары field/class и phase для 25
invalid cases, без значений, response body, candidate или model output. Acceptance
oracle не менялся, а исторические EXP-1233/1247/1251 остались aggregate/unknown;
R5 preregistered study не переоткрывался. Изменение `repository_process.py`
изменило verifier source closure: старый image pin заменён после offline
rebuild на `sha256:ada0c0c0bc91e418582231a002e90b3bf1a3cdeaa52efc43cd2ee2c946940959`
с code digest
`sha256:2c1cdcc3dd64132e04f8a626ca7c2e5e0ab254363e657a5add9a11075af1e0db`;
`linux/amd64`, два synthetic verifier-container tests прошли. Focused suites:
103 tests (8 skipped), target-contract 10 (1 skipped); полный offline suite:
1,706 tests (25 skipped); `git diff --check` прошёл. Через ABF: 51 batch,
39 accepted, 11 blocked, 1 superseded, 0 draft. Ни один новый Worker вызов,
independent-host trust, authenticated approval или publication не доказаны;
R2/MVP остаются OPEN.

Batch ABG / EXP-1253 зарегистрировал отдельный credential-free профиль для
одной будущей локальной диагностической попытки: `RUN EXP-1253 ONCE`,
`process-exp-1253-local-001`, `task-exp-1253-local-001`. Synthetic tests
подтвердили точные profile mappings, restricted-container backend и ноль
credential lookups; focused suite — 41 passed, full suite — 1,707 tests,
25 skipped, `git diff --check` прошёл. EXP-1254 прошёл image/profile/database
preflights, но единственный readiness gate вернул
`READINESS|200|35|1791999670` (<36). Ollama, snapshot и модель не запускались;
карточка BLOCKED без повтора. Через ABG: 52 batches, 39 accepted, 12 blocked,
1 superseded, 0 draft. R2/MVP остаются OPEN.

Batch ABH / EXP-1255 зарегистрировал новый post-gate профиль
`RUN EXP-1255 ONCE`, `process-exp-1255-local-001`,
`task-exp-1255-local-001`. Profile tests passed: 42; full suite: 1,708 tests,
25 skipped; `git diff --check` прошёл. EXP-1256 прошёл readiness
`READINESS|200|60|1792003470` и выполнил ровно один local model call. Новый
фиксированный marker локализовал первый отказ: `target-test-malformed-status-
level-bool` — boolean `level` не дал HTTP 422. Run
`run-0d35d6f0298642088ab531bf51abad69`, cursor 74, partial. Candidate/source/
model output не читался; verifier/stage, approval и publication не достигнуты.
Ollama остановлен, listener отсутствует, обе DB `quick_check=ok`, mode 0600.
EXP-1256 BLOCKED без повтора. Через ABH: 53 batches, 39 accepted, 13 blocked,
1 superseded, 0 draft. R2/MVP остаются OPEN.

Batch ABI / EXP-1257 зарегистрировал новый credential-free local профиль
`RUN EXP-1257 ONCE`, `process-exp-1257-local-001`, `task-exp-1257-local-001`.
В prompt добавлена только ограниченная подсказка EXP-1256: `level=true` должен
дать HTTP 422; точный integer type проверяется до преобразования/обращения к
БД для пяти полей. Профильные тесты: 43 passed; полный suite: 1,709 tests,
25 skipped; `git diff --check` прошёл. EXP-1258 переведён в READY только для
одной анонимной readiness-проверки после 2026-10-14 21:44:30 МСК; miss означает
стоп до daemon/snapshot/model без повтора. Через ABI: 54 batches, 39 accepted,
13 blocked, 1 superseded, 1 ready, 0 draft. R2/MVP остаются OPEN.
Локальный pre-reset preflight EXP-1258 (20:52:31 МСК) подтвердил оба точных
image pin (`linux/amd64`), verifier closure/digest test (PASS), Ollama client
0.40.3, отсутствие listener и отсутствие новых путей БД. Readiness, daemon,
snapshot, модель и Worker ещё не запускались.

Batch ABJ / EXP-1259 исправил только local transfer runner: текст stdout
`docker image load` больше не считается доказательством образа; после успешного
exit runner делает один exact-ID inspect и принимает только полный pinned tuple
с пустым RepoTags. Fake suite: 11 passed; полный offline suite: 1,708 tests,
25 skipped; `git diff --check` прошёл. Live transfer/SSH не запускались;
удалённое состояние EXP-1225 остаётся неизвестным, его one-shot потрачен.
Через ABJ: 55 batches, 40 accepted, 13 blocked, 1 superseded, 1 ready,
0 draft. R2/MVP остаются OPEN.

Batch ABK / EXP-1260 зарегистрировал новую фразу transfer-gate
`RUN EXP-1261 ONCE`: неверные/старые фразы не вызывают runner, точная фраза
вызывает его ровно один раз (в тесте — mock). Focused suite: 13 passed; полный
offline suite: 1,710 tests, 25 skipped; `git diff --check` прошёл. EXP-1261 —
DRAFT, ожидает отдельного свежего подтверждения на один импорт точного image
ID в Docker image store `alex@192.168.88.101`; live transfer не выполнялся.
Через ABK: 56 batches, 40 accepted, 13 blocked, 1 superseded, 1 ready,
1 draft. R2/MVP остаются OPEN.
Локальный exact inspect EXP-1261 подтвердил immutable ID, единственный pinned
tag, `linux/amd64`, размер и девять упорядоченных DiffID; удалённая цель не
проверялась.

Batch ABL / EXP-1262 воспроизвёл текущий verifier-host source bundle двумя
последовательными сборками без сохранения архива: digest
`sha256:5dffc70360b50678b5ee722cc05f5fb6bfa9384dde6ffb82f240f012ed76ae8d`,
81 member, 1,282,712 байт исходников; metadata совпали. Удалённая доставка и
service trust не проверялись. Через ABL: 57 batches, 41 accepted, 13 blocked,
1 superseded, 1 ready, 1 draft. R2/MVP остаются OPEN.

Batch ABM / EXP-1263 сверил R2 exit matrix с локальными evidence ABJ–ABL.
Текущие verifier/Worker/stage gates уточнены: EXP-1258 ещё не прошёл readiness,
EXP-1261 на момент этой записи ожидал свежего разрешения на новый import, а
bundle digest доказывает только воспроизводимость локального пакета. Удалённая identity/readiness,
independent trust, verified stage, authenticated approval и реальный PR не
доказаны. Через ABM: 58 batches, 42 accepted, 13 blocked, 1 superseded,
1 ready, 1 draft. R2/MVP остаются OPEN.

Текущий Control Plane update (2026-10-14): единственная readiness-проверка
EXP-1258 вернула `READINESS|200|35|1792003499` (<36), остановившись до daemon,
snapshot, model и Worker. После отдельного точного разрешения EXP-1261 был
запущен один раз через видимый gate; результат `REMOTE_INSPECT_FAILED` (exit
16), поэтому точный remote image tuple не подтверждён и образ мог быть
импортирован. Повторов, удалённой диагностики и cleanup не было. Текущий учёт:
58 batches, 42 accepted, 15 blocked, 1 superseded, 0 ready, 0 draft. R2/MVP
остаются OPEN.

Control Plane update (2026-10-15): EXP-1264 добавил bounded read-only
inspector с отдельным exact gate и проверкой полного image tuple; пять
synthetic tests и полный offline suite (1,715 tests, 25 skipped) прошли.
Удалённая команда не запускалась. EXP-1265 — DRAFT до свежего точного
разрешения на один SSH `docker image inspect`; это не импорт, не диагностика
сервиса и не подтверждение готовности verifier. Текущий учёт: 60 batches/cards,
43 accepted, 15 blocked, 1 superseded, 0 ready, 1 draft. R2/MVP остаются OPEN.

Control Plane update (2026-10-15): EXP-1266 зарегистрировал отдельный свежий
one-shot профиль restricted-container Worker с локальным `qwen2.5-coder:7b`;
подсказка `type(value) is int` и invalid matrix сохранены без изменений.
Focused CLI tests: 44 passed; полный offline suite: 1,716 tests, 25 skipped.
Модель и snapshot ещё не вызывались. EXP-1267 ожидает точного preflight и
единственного anonymous readiness ответа с remaining >=36. Учёт: 62
batches/cards, 44 accepted, 15 blocked, 1 superseded, 0 ready, 2 draft.
R2/MVP остаются OPEN.

Control Plane update (2026-10-15): EXP-1267 прошёл единственный anonymous
readiness gate (`READINESS|200|60|1792082595`) и подтвердил pinned public
commit/tree/content digest, но один restricted local-Ollama Worker вызов снова
остановился на `target-test-malformed-status-level-bool`. Verifier и stage не
достигнуты; approval не создан, publication не выполнялась, provider write не
было. Run `run-3b6bad10579d4a8697aaab7fd0c09c20`, observer cursor 74/partial;
обе БД `quick_check=ok`, mode 0600; owned Ollama остановлен. Повтора нет.
Текущий учёт на тот момент: 62 batches/cards, 44 accepted, 16 blocked,
1 superseded, 0 ready, 1 draft. R2/MVP остаются OPEN.

Control Plane update (2026-10-15): EXP-1268 добавил пошаговый fail-fast recipe
для проверки JSON integer type и SQLite bounds до cursor/DB access; новый
one-shot профиль и prompt покрыты тестами. Полный offline suite: 1,716 tests,
25 skipped. EXP-1269 остаётся DRAFT до следующего rate reset GitHub
(`1792082595`, 2026-10-15 19:43:15 МСК); readiness пока не запрашивался.
Учёт: 64 batches/cards, 45 accepted, 16 blocked, 1 superseded, 0 ready,
2 draft. R2/MVP остаются OPEN.

Control Plane update (2026-10-15): EXP-1270 упростил и упорядочил prompt
Worker для pre-database валидации, сохранив все acceptance cases. Focused CLI
tests: 44 passed; full offline suite: 1,716 tests, 25 skipped. Нового model
вызова не было. EXP-1269 остаётся DRAFT до reset `1792082595` и точного
preflight. Текущий учёт: 65 batches/cards, 46 accepted, 16 blocked,
1 superseded, 0 ready, 2 draft. R2/MVP остаются OPEN.

Control Plane preflight (2026-10-15 18:56 МСК): локальные точные preflight
проверки EXP-1269 прошли: transport suite — 12 тестов, pinned command contract
— 1 тест, оба Docker image ID/platform совпали (`linux/amd64`), Ollama client
0.40.3 доступен, listener отсутствует, оба пути БД свободны, `git diff --check`
чист. Reset `1792082595` ещё не наступил; карточка остаётся DRAFT. Readiness,
daemon, snapshot и модель не запускались.

Control Plane recheck (2026-10-15 19:15 МСК): те же две локальные contract
suite прошли повторно (12 transport tests, 1 pinned-command test); оба exact
image ID/platform совпали (`linux/amd64`), Ollama сообщил client 0.40.3 без
запущенного сервера/listener, оба пути БД остаются свободными, `git diff --check`
чист. Reset `1792082595` ещё впереди; EXP-1269 остаётся DRAFT, сетевой запрос,
daemon, snapshot и model не запускались.

Control Plane regression revalidation (2026-10-15 19:21 МСК): полный offline
suite на текущем worktree прошёл — 1,715 tests, 25 skipped. Сетевые, Docker,
Ollama, model и provider-вызовы не выполнялись. Это локальное regression
evidence и не меняет статусы MVP или EXP-1269.

Control Plane update (2026-10-15): EXP-1271 перевёл локальный transfer helper
на актуальный проверенный verifier image `sha256:ada0c0c0bc91e418582231a002e90b3bf1a3cdeaa52efc43cd2ee2c946940959`
и свежий gate `RUN EXP-1272 ONCE`; focused suite — 13 тестов, verifier
context-contract — 1 тест, полный offline suite — 1,716 тестов (25 skipped).
Exact local image tuple/save stream совпали. EXP-1272 получил отдельное свежее
разрешение; remote `docker image load` вернул status 0, но последующий exact-ID
inspect завершился `REMOTE_INSPECT_FAILED` (exit 16), поэтому image identity не
подтверждена. Повторов,
диагностики и cleanup не было. Для отдельного read-only inspection потребуется
новая карточка и свежая авторизация. Remote verifier readiness/trust, verified
stage, authenticated approval и controlled PR остаются открыты.

Control Plane update (2026-10-15): после неоднозначного EXP-1272 (единственный
разрешённый импорт вернул `REMOTE_INSPECT_FAILED`, exit 16) spent transfer gate
отключён, чтобы исключить случайный повтор. EXP-1273 перевёл отдельный
read-only inspector на текущий verifier и gate `RUN EXP-1274 ONCE`; focused
fake suites прошли (12 transfer, 5 inspector), полный offline suite — 1,715
тестов, 25 skipped. EXP-1274 остаётся DRAFT до свежей точной авторизации на один
SSH inspect; повторов, диагностики или cleanup после импорта не было. Remote
readiness/trust, verified stage, authenticated approval и controlled PR открыты.

Control Plane update (2026-10-15): единственный отдельно разрешённый read-only
inspect EXP-1274 завершился только маркером `REMOTE_INSPECT_FAILED` (exit 11).
Маркер не различает недоступность SSH и ошибку Docker inspect; точная
идентичность образа на testdev не подтверждена. Повторного SSH, диагностики и
cleanup не было; EXP-1274 переведён в BLOCKED. R2/MVP остаются OPEN.

Control Plane result (2026-10-15): EXP-1269 прошёл один post-reset readiness
gate (`READINESS|200|60|1792086236`) и ровно одну credential-free local Worker
попытку на закреплённом public snapshot. При `OLLAMA_NO_CLOUD=1` модельный
digest совпал; restricted Worker, target tests, current pinned same-host Docker
verifier и stage/readback завершились `status=verified`. Staged digest
`sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0`,
verification digest `sha256:2d228a9e9a6faa35b2024a9dc5f19db1db068f8c8b6e0f2b4845eb81ffd0465`;
observer run `run-dacc14f7789d4d35aafca58cfe5cf8d1`, cursor 88/partial. Both DBs
passed `quick_check=ok`, mode 0600. `external_write=false`; approval and
publication were not attempted. Это первая успешная текущая restricted
Worker→target→same-host verifier→stage цепочка после предыдущих target failures,
но snapshot provenance остаётся GitHub REST API claim, observer completeness
partial, а независимый remote verifier, authenticated approval и реальный PR
не доказаны. R2/MVP остаются OPEN.

EXP-1275 повторил один synthetic Docker canary-composition test на текущем
verifier pin; тест прошёл (1 test, 2.568s), canary отсутствовал на заявленных
поверхностях, same-digest local-mock receipt совпал. Это не real credential,
model/API call, remote verifier, human approval или PR. R2/MVP остаются OPEN.

EXP-1276 локально разделил фиксированные маркеры inspector-а для ошибки запуска
SSH-клиента, его exit 255 и nonzero удалённой команды, сохранив exact tuple,
один вызов и redaction. Focused suite: 5 passed; полный suite: 1,715 tests,
25 skipped. Для EXP-1276 ни SSH, ни Docker не запускались.

Control Plane result (2026-10-15): EXP-1277 получил отдельное свежее точное
разрешение; gate введён один раз, единственный read-only SSH вызов вернул только
`REMOTE_INSPECT_FAILED` (exit 11). Точный image tuple не подтверждён; маркер не
различает недоступность SSH и ошибку Docker inspect. Повторов, диагностики,
cleanup, запуска сервиса, удалённых изменений, публикации или commit не было.
EXP-1277 BLOCKED; идентичность образа и remote verifier readiness/trust не
доказаны. R2/MVP остаются OPEN.

Control Plane update (2026-10-15): EXP-1278 локально подготовил bounded
read-only probe для выяснения, доступны ли на testdev Docker CLI/daemon и exact
текущий verifier image. Helper скрывает все данные и оставляет только fixed
markers; 6 focused tests passed, including `/bin/sh -n` без исполнения; полный
offline suite — 1,721 tests,
25 skipped, `git diff --check` чистый. Вызовов SSH/Docker/network не было.
EXP-1279 остаётся DRAFT до отдельного свежего точного разрешения на один probe;
повторы и диагностика после него не разрешены. R2/MVP остаются OPEN.

Batch ACA / EXP-1280 уменьшил source closure verifier-host bundle: теперь он
включает только 27 модулей, статически достижимых из HTTP/service roots, плюс
четыре фиксированных launcher/dependency/schema файла. Два in-memory build
совпали побайтно: `sha256:31ca7d3df0ad03bd64e0924d34b107f1f25a6157fecbd132d7b4a4e50875a3c4`,
31 member, 541,323 source bytes. 13 focused bundle tests и полный suite
(1,721 tests, 25 skipped) прошли; launcher импортирован из распакованного
bundle без старта сервиса. Архив не сохранялся и не передавался; исходники из
грязного worktree не являются утверждённым deployment pin. Независимый
verifier trust, approval и controlled PR остаются открытыми.

Batch ACB / EXP-1281 отделил `CredentialSource` protocol от реализаций,
читающих значения из systemd directory, скрытого terminal prompt и native
keyring. Verifier `signer_key_source` зависит только от узкого protocol-модуля;
старый `credential_source` re-export сохраняет identity типов для существующих
потребителей. Current verifier-host bundle включает `credential_protocol.py`
и исключает `credential_source.py`, не нужный этому сервису. 57 focused tests
и bundle suite (14 tests) прошли; полный suite: 1,723 tests, 25 skipped. Две
сборки совпали: `sha256:261fce4785b2b0fd17c369d3faf9c53873a8319af66d7ec03abacc32eda3e791`,
31 member, 533,249 source bytes. Это уменьшает локальную поверхность доступа к
секретам на host, но не доказывает host trust/deployment, approval или PR; R2/MVP
остаются OPEN.

Batch ACC / EXP-1282 сверил R2 exit matrix с текущими evidence до EXP-1281.
Таблица теперь учитывает успешную restricted Worker→target tests→same-host
verifier→exact stage/readback цепочку EXP-1269 и отдельно фиксирует, что remote
image identity осталась неподтверждённой после EXP-1272/1274/1277. Перепроверены
также текущий bundle EXP-1280/1281, partial observer, отсутствие authenticated
approval и реального PR. Документация не повышает same-host или synthetic
результаты до independent-host trust; R2/MVP остаются OPEN.

Batch ACD / EXP-1283 добавил opt-in observer gate вокруг отдельного host-side
model-channel запроса: checkpoint/intent сохраняются до dispatch, а после него
фиксируется только bounded terminal status без prompt/response. Повтор блокируется
в текущем и восстановленном run. CLI wiring и event semantics проверены на fake
channel; live model call не выполнялся. Существующий успешный EXP-1269 предшествует
этому hook и не получает задним числом нового evidence. Collector остаётся
partial; R2/MVP остаются OPEN.

Batch ACD / EXP-1284 rebuilt the current verifier image offline after the
observer source change and pinned image
`sha256:76a3d7da42cd26f00d145379c6b3467a480f4d0cba48f0e499ea3140bc79e5a1`
to code digest
`sha256:e9b018828f24eea5aa1b50a65720587c1fcb7905baeff9f3c7c8fe599f997c2f`.
The exact inspect returned `linux/amd64`, size 48,851,536 and nine ordered
layers; both synthetic container tests passed. EXP-1285 refreshed the local
transfer pin and gates. EXP-1286 ran once after fresh authorization and returned
`REMOTE_INSPECT_FAILED` (exit 16): remote `docker image load` returned success,
but the subsequent exact-ID inspect failed. The image may have imported, but
its identity is unconfirmed. No retry, separate inspection, diagnosis or cleanup
followed. EXP-1287's separately authorized read-only inspect returned
`REMOTE_INSPECT_FAILED` (exit 11); remote image presence/identity remains
unknown. No retry, diagnostic SSH or cleanup followed. EXP-1288 registered a
fresh exact-gated local-Ollama profile.
EXP-1289 made one
public-snapshot Worker attempt: the journaled local model call completed and
was recorded, but the run exited 1 on a restricted sandbox command before the
verifier or stage. EXP-1290 classified the sole failure as
`sandbox-command-nonzero`; the specific target assertion remains unknown and
the attempt was not retried. Both databases passed integrity and mode checks;
the stage is empty and Ollama is stopped. No approval or PR evidence exists;
R2/MVP remain OPEN.

EXP-1291 pins the credential-free local Ollama request to temperature 0 and
seed 42 (caller overrides rejected); the DeepSeek wire payload is unchanged.
This control improves reproducibility but does not explain the previous target
test failure. EXP-1292 prepared fresh exact-gated profile EXP-1293. Its one
readiness check returned `READINESS|200|35|1792090084`, below the required 36;
the attempt stopped before snapshot intake, Ollama startup, model inference and
the exact gate. EXP-1293 is BLOCKED and must not be retried. A new profile/card
is required after reset. R2/MVP remain OPEN.

EXP-1294 records only a bounded numeric sandbox return code in observer events
and the structural report; synthetic tests prove argv/stdout/stderr are not
persisted or projected. This improves failure evidence but does not explain
EXP-1289's target command. EXP-1295 rebuilt and pinned the local verifier after
that shared observer/schema change: image
`sha256:8caa34a8e516f9be31a54f0271ccabee3b088ecc7f3ce9c2dad49f3fe42c133f`, code
`sha256:223fd6f35c73892c1a5d4e43b2294da7f7ef7a9d6004181ab16c954f62e79d18`,
`linux/amd64`, size 48,851,685, nine layers. Two bounded synthetic verifier
container tests and the full 1,735-test offline suite passed (25 skipped).
Transfer/inspect helpers now use fresh gates EXP-1296/1297. EXP-1296's separately
authorized one-shot transfer returned `REMOTE_INSPECT_FAILED` (exit 16): the
runner reports image-load success, but its exact-ID inspect failed. Remote
presence is possible and identity unconfirmed; no retry/diagnostic/cleanup
followed. EXP-1297 received separate fresh authorization and its single
strict-SSH read-only inspect returned `REMOTE_INSPECT_FAILED` (exit 11). No
retry, diagnosis or cleanup followed; remote image presence/identity remain
unknown. R2/MVP OPEN.

EXP-1298 registers a fresh one-shot local-Ollama Worker profile EXP-1299 after
the prior profile stopped at a below-threshold readiness result. EXP-1293 stays
BLOCKED and is not reused. The new full offline suite is 1,736 tests (25
skipped). EXP-1299's one readiness request returned HTTP 200 / remaining 35,
below the required 36; it stopped before snapshot, daemon, model and Worker.
Do not retry that card; a new profile/card is required after reset. There is no
new Worker/verifier/stage evidence. R2/MVP OPEN.

EXP-1300 rebuilt the verifier-host source bundle after EXP-1294 changed its
observation schema: two sequential in-memory builds matched at
`sha256:d8c8e2a40975d0ebcfe05210d98f2779bc032f975d6def84909d93e9313ec8de`
(31 members, 536,278 source bytes). This is a local dirty-worktree pin, not a
reviewed deployment artifact. EXP-1301 independently checked its in-memory
manifest and source bytes, confirmed two deterministic builds and zero
unresolved local imports, and found no concrete credential reader or
secret-bearing path in the bundle. The bundle contains only the opaque
credential protocol and injected-source signer adapter. Focused tests: 14
passed; full offline suite: 1,736 tests (25 skipped). This does not establish
deployment provenance or host trust. EXP-1297's separately authorized remote
inspect also returned `REMOTE_INSPECT_FAILED` (exit 11); image identity remains
unknown. Independent verifier trust, authenticated approval and controlled PR
remain unproven; R2/MVP OPEN.

EXP-1302 registered a fresh one-shot profile EXP-1303 after EXP-1299's readiness
miss; the older blocked profiles remain non-reusable. The new profile pins a
distinct process/task identity and requires exact gate `RUN EXP-1303 ONCE`.
Focused CLI tests: 48 passed; full offline suite: 1,736 tests (25 skipped).
EXP-1303 then passed post-reset readiness (`200`, remaining 60), consumed the
pinned public snapshot and completed one local model call. Its target test
command returned 1 (`sandbox-command-nonzero`); verifier and stage were not
reached, and no retry or raw output inspection followed. Observer run
`run-4182b6f6c90c431fbe83b23489665c65` contains 77 events through cursor 76,
including the model-channel intent/completion pair at cursors 66/67 and the
target failure at cursor 74 (return code 1). Both DBs passed `quick_check=ok`,
mode `0600`; the stage has zero rows. WAL/SHM sidecars remain, not cleaned up.
The owned Ollama daemon was started during local preflight before the readiness
GET (a sequencing deviation), inference began only after readiness passed, and
the daemon was stopped. The target assertion is still unknown; R2/MVP remain
OPEN. EXP-1304's read-only code audit found the fixed probe emits one of 57
bounded failure codes. EXP-1305 now persists only the exact allowlisted code
for the fixed target command, validates it against a strict schema enum, and
projects it as bounded diagnostic metadata; malformed or extra output is
discarded. This self-reported code is not trusted verification evidence and
cannot influence approval/publication. Focused tests passed (79 tests); after
the EXP-1306 image/code pin refresh, the full offline suite passed (1,740 tests,
25 skipped). The rebuilt image passed the exact metadata inspect, but both
synthetic container tests failed because `brainbooster_target_profile.py`, now
imported by `observer_runtime.py`, is absent from the verifier image context.
EXP-1306 is blocked. EXP-1307 added the missing profile to the local runtime
context and passed both bounded container tests, but the full suite found the
image/code pin self-referential: the hashed profile contained the pin itself.
EXP-1308 moved verifier identity metadata to a host-side module outside the
image context. Focused tests passed (104; 2 skipped); one offline
`linux/amd64` Docker build and independent code-digest calculation matched.
The exact image inspect returned
`sha256:babefaa38e0e068f3af35b9f00d0ff0ea319a69e3a13697fe471b3e01a2cdf6a`,
size 48,854,834 and nine ordered layers; both synthetic container tests and the
full suite passed (1,744 tests, 25 skipped). The new source-closure digest is
`sha256:f63ecc2359fe0c9dcd51893d55d831bacb33daa0b289a3b87d0b6a65de1d660f`.
Two in-memory verifier-host bundle builds matched at
`sha256:98a8432f7d6eb48f9079d30979b8887daa3ea4358958e5c062ca83b6a285ae67`
(32 members, 540,864 source bytes). These are local dirty-worktree pins, not
deployment pins. No Worker retry or remote verifier action occurred.

EXP-1309 registers a distinct credential-free profile for EXP-1310 against the
repaired local verifier pin. After fresh one-attempt authorization, its single
readiness request returned HTTP 200 / remaining 31 (<36), so EXP-1310 is BLOCKED
before the CLI's independent check, snapshot, Ollama or model. No retry. A
bounded read-only check of the old EXP-1303 failure event found only
`sandbox_return_code`: that run predates EXP-1305's allowlisted failure-code
projection. Its raw command output remains unread. EXP-1311 registers fresh
profile EXP-1312, requiring a new authorization and a readiness request only
after the recorded reset; EXP-1312 remains DRAFT. R2/MVP remain OPEN.

EXP-1313 refreshed the local stream/inspect helpers to the EXP-1308 verifier
image. The archive measured 48,868,864 bytes and both bounded helper tests and
the offline suite passed (1,744 tests, 25 skipped). This only prepares an exact
transfer path: no SSH/import or remote verifier check occurred; EXP-1314/1315
remain DRAFT pending separate fresh authorizations. R2/MVP remain OPEN.

**Обновление 2026-10-19 (EXP-1383 trust inputs):** пользователь закрепил
публичный v2 authority key-set digest
`sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`
и принял EXP-1436 только как свидетельство различия хэшированных fingerprints
Worker Mac/testdev с точностью наблюдения до даты
(`sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`).
Это не доказывает идентичность текущего deployment, работу verifier runtime
или изоляцию хостов. Подпись host-decision и запрос к verifier не выполнялись
и не разрешены этой фиксацией. EXP-1383 остаётся DRAFT до получения подходящего
актуального evidence для этих утверждений и отдельной точной карточки/разрешения
на последующие операции; R2/MVP остаются OPEN.

**Проверка публичного snapshot HEAD (EXP-1454, 2026-10-19):** один анонимный
read-only вызов `git ls-remote
https://github.com/SoldatovAlexander/brainbooster_full_v11.git HEAD` вернул
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, совпадающий с закреплённым snapshot
commit. Это подтверждает совпадение объявленного HEAD только на момент
наблюдения; не доказывает authorship/signature commit, доступность всех
content-addressed объектов или доверие к исходному коду. Worker и прочие этапы
runtime не запускались; R2/MVP остаются OPEN.

**Control Plane update (Batch AIE/AIF, 2026-10-19):** lifecycle-завершение
Observer интегрировано в локальные Worker, replay, executor, R5, stage-approval
и mock-publication пути; незавершённые/неизвестные эффекты остаются открытыми.
Текущий локальный verifier pin:
`sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`,
code digest
`sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`;
bundle pin:
`sha256:3d7c9c30b2afc53c53b9a1427e95e113d684111209979ee5e7fbce2fe437dad4`.
Единственный финальный offline suite прошёл: 1 886 тестов, 25 пропущено;
`git diff --check` прошёл. Это локальные regression/synthetic проверки, а не
доказательство независимого доверия к хосту, deployment, аутентифицированного
approval или реальной публикации провайдера. Критерии 13/14 остаются PARTIAL,
R2/MVP — OPEN.

**Локальный R2 checkpoint (EXP-1580—1583, 2026-10-19):** новый маршрут
Buildx `--load` → bounded `docker image save` не подтвердил portable archive:
единственный запуск EXP-1580 вернул `CLEANUP_FAILED`. EXP-1581 доказала только
отсутствие точного временного image tag; состояние dependency-copy container
неизвестно, и повторного запроса/cleanup не было. EXP-1583 улучшила будущий
фиксированный marker, чтобы при cleanup failure различать собственные
container/tag и включать только точный сгенерированный ID контейнера; это не
восстанавливает ID прошлой попытки. Latest successful Worker→target→same-host
verifier→stage остаётся EXP-1269. Критерии остаются OPEN/PARTIAL, R2/MVP —
OPEN.

**Подготовка следующего локального Worker (EXP-1584/1585, 2026-10-19):**
EXP-1584 усилила prompt конкретным helper-шаблоном, который отклоняет bool через
`type(value) is not int`, и тестами контракта prompt. Старый неиспользованный
gate EXP-1448 отозван; EXP-1585 зарегистрирован как новая credential-free
локальная попытка, но остаётся DRAFT до точного свежего gate. Worker, snapshot,
Ollama, Docker и сеть в этой подготовке не запускались. Это не подтверждает,
что модель исправит target; последняя успешная Worker→target→same-host
verifier→stage цепочка остаётся EXP-1269. R2/MVP остаются OPEN.

**Локальная попытка экспорта verifier-образа (EXP-1586—1588, 2026-10-19):**
EXP-1586 остановилась при импорте wrapper-а до Docker. EXP-1587 исправила
запускной путь, но один offline запуск вернул
`CLEANUP_FAILED|resources=verifier_tag`. Read-only запрос EXP-1588 подтвердил
отсутствие точного tag; наличие untagged image и успешность archive validation
не установлены. Повторов, диагностики image metadata или cleanup не было.
Portable candidate не принят, production pin и проверка verifier не менялись.
R2/MVP остаются OPEN.

**Обновление локального verifier-export (Batch AKBK, EXP-1590/1591,
2026-10-19):** новый одноразовый wrapper прошёл focused tests. Единственная
offline Buildx попытка прошла exact local preflight, но вернула фиксированный
`BUILD_FAILED` (exit 14); task-specific tag отсутствовал на bounded cleanup
query, dependency-copy container был удалён штатно. Ошибка не диагностировалась,
повтора не было. Portable archive всё ещё не подтверждён; latest successful
Worker→target→same-host verifier→stage остаётся EXP-1269. Следующий шаг — не
повторять тот же эксперимент, а пересмотреть способ offline export или
классификацию существующих synthetic evidence отдельной карточкой. Independent
verifier trust, digest-bound approval, controlled PR, критерии 13/14 и R2/MVP
остаются OPEN/PARTIAL. Batch-end full offline suite: 1,992 теста, 26 skipped;
`git diff --check` прошёл.

**EXP-1592/1593:** дальнейшая попытка под новым tag использовала bounded
allowlisted Buildx-failure classification, не раскрывая stderr. Результат:
`BUILD_FAILED|reason=unknown|exit=125|stderr_bytes=109`; no retry or diagnostic.
Batch-end suite: 1,995 tests, 26 skipped. Portable verifier archive and
independent verifier/approval/publication evidence remain unconfirmed; the
earlier same-host EXP-1269 evidence remains the latest successful run. R2/MVP
remain OPEN.

**EXP-1585/1594/1595:** точное разрешение на один credential-free Worker run
получено, но preflight exact target/verifier image ID/platform завершился
`PINNED_IMAGES_FAILED`; до quota request, Ollama, snapshot, DB или inference
карточка остановилась. Повтор не выполнялся. EXP-1594 добавила и синтетически
проверила ограниченный inspector этих двух exact pins; EXP-1595 остаётся DRAFT
до отдельного разрешения на read-only inspect. Worker, независимый verifier,
approval и PR evidence не изменились. Batch-end full suite: 2,000 tests,
26 skipped; `git diff --check` прошёл. R2/MVP остаются OPEN.
