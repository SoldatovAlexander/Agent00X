# Статус реализации и доказательств

Статус: единственный оперативный статус проекта

Версия: 1.1

Дата сверки: 2026-10-19

**Оперативный checkpoint (Batch AKCJ → EXP-1633, 2026-10-19):** EXP-1632
подтвердила один локальный portable verifier candidate:
manifest/image ID `sha256:f49397ccfb59beefa21161c86379e17ae754acee810cedd3fc5de4f5494d913f`,
config ID `sha256:cb5c068a474164060b27942d764304fed521d267a0eb83fdfa530cc90bc249d9`,
code digest `sha256:705c3803ca36374ee0ab0bef80fb4d77b3211dd60e8168a7729a3fed46c7a2c7`.
Изменены только verifier pins; target pin сохранён. Это локальное archive
evidence, не remote import и не independent-host verification. EXP-1631
научила bounded проверку legacy gzip layers сверять DiffID по распакованному
содержимому. После обновления pins EXP-1633 синхронизировала локальный
host-bundle digest `3dcb0413950d005d56e96e39d65b214f466f7ec80e09aec688c73e56b00a9459`
(34 members; 566,893 source bytes; 604,160 archive bytes), а также config и
deterministic profile ожидания. Batch AKCI сначала выявил 4 stale assertions;
после локального исправления Batch AKCJ full offline suite прошёл: 2,068 tests,
26 skipped. Текущий вычисленный profile digest
`sha256:8dc575b00533f5bd6d64a72153438a7f5aa1f49673b267c42166a9f742faf070`
— только локальная идентичность, не enrollment или host-trust evidence.
Remote transfer не выполнялся; его старые image/config/code pins не обновлялись.
EXP-1634 одним read-only inspect подтвердил тот же containerd image ID,
linux/amd64, size 48,857,362 bytes, девять упорядоченных DiffID и единственный
tag `agent00x-verifier:exp-1632`; дополнительных Docker-запросов не было.
Batch AKCK full offline suite passed: 2,072 tests, 26 skipped.
EXP-1635 ran exactly one bounded in-memory `docker image save` by immutable ID;
its safe result was `archive_bytes=48871936|repo_tags=tagless|layers=9`. This
only characterized the legacy manifest header, not the full archive content;
no remote import occurred. Batch AKCL full offline suite passed: 2,077 tests,
26 skipped. EXP-1636 refreshed the dormant transfer helper's local/remote
identity tuple and gate using the accepted local candidate facts; 13 focused
tests and the Batch AKCM full suite passed (2,077 tests, 26 skipped). It did
not run Docker or SSH. EXP-1637 remains DRAFT because one remote image-store
import requires a fresh exact user confirmation. EXP-1638 added explicit
tagless legacy archive validation while preserving exact-tag checks (52 focused
tests). EXP-1639's single by-ID save then passed the full bounded parser:
`oci+docker-legacy`, bound manifest, config/platform/nine DiffIDs verified,
48,871,936 bytes, no RepoTags. Batch AKCN full suite passed (2,083 tests,
26 skipped). No remote import occurred.
Последняя успешная реальная цепочка Worker→target→verifier→stage остаётся
EXP-1269; независимый remote verifier trust, authenticated digest-bound
approval, controlled real PR, provider recovery и критерий R5 остаются открытыми.
R2/MVP остаются OPEN.

**Исторический checkpoint (Batch AKCC → EXP-1621, 2026-10-19):** последняя
успешная цепочка с реальным локальным Worker — EXP-1269: pinned public
snapshot → restricted Worker → target tests → same-host verifier → exact stage
readback. EXP-1498 повторно проверила сохранённый stage и получила `fresh_pass`,
но не запускала Worker и не доказывает независимый verifier. Последующие
попытки не закрыли новый сквозной проход: EXP-1303 завершилась ошибкой target,
а EXP-1585 остановилась на pin preflight до Worker/model. Полный прогон в конце
Batch AKBO завершился ошибкой (2,007 tests, 26 skipped, 6 failures and 1 error).
EXP-1602 исправила verifier source closure и обновила source/code digest до
`sha256:705c3803ca36374ee0ab0bef80fb4d77b3211dd60e8168a7729a3fed46c7a2c7`;
deterministic host bundle —
`sha256:519090b97923be43f6e1a9f868fe1711069cd14b2ac4fc05f52de6fe2dc432d5`
(34 members). EXP-1603 подготовила helper и прошла focused suite (25 tests).
Единственная отдельно подтверждённая попытка EXP-1604 завершилась
`BUILD_FAILED|reason=unknown|exit=125|stderr_bytes=109`; archive не принят,
production image pins не менялись. Возможное состояние task tag не
проверялось и остаётся неизвестным; inspect/cleanup не выполнялись. Текущий manifest/config image pair
`sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2` /
`sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`
ещё не подтверждён как соответствующий текущему code digest. Карточка EXP-1604
BLOCKED после этой попытки; её gate повторно не использовать. Полный suite
после неё выявил один stale profile-digest assertion; EXP-1605 обновила
только тестовое ожидание, не runtime profile/trust records. Batch AKBR suite
после правки прошёл: 2,011 tests, 26 skipped. Текущий вычисленный verifier
profile digest —
`sha256:1ee01a5df3f1310de885ffbbb8cc17c825974fb0cc001ba2a3fda9c4e6f9ff78`;
это локальное вычисление, не доверенное enrollment/host evidence.
Независимый remote verifier trust, authenticated digest-bound approval,
controlled real PR, recovery на provider и критерий R5 остаются незакрытыми;
R2/MVP OPEN. EXP-1606 ran its one filtered tag-presence query: exit code 0,
empty stdout, so `agent00x-verifier:exp-1603` was absent at query time. This
does not exclude an untagged partial image or establish any image identity.
EXP-1607 prepared a fresh, task-unique tag; EXP-1608 then returned the same
sanitized Buildx failure marker (`exit=125`, 109 diagnostic bytes). The full
offline suite passed (2,014 tests, 26 skipped), but no archive or pin update was
accepted. The possible new-tag/untagged image state was not queried.
EXP-1610's unnamed inspect, EXP-1611's formatted builder list, and EXP-1612's
version command failed under isolated config. EXP-1613 found exactly one
executable at a fixed standard path and invoked it directly; exit was zero,
but the output was not retained because it failed the version parser. EXP-1614
adds only a unique user-local plugin link inside the temporary config. EXP-1615
then resolved `docker buildx version` as `v0.27.0-desktop.1` through that
isolated setup. This confirms a plugin-discovery fix for the credential-isolated
CLI path; it does not prove that this caused the prior build failure or establish
builder/image identity. Batch AKBZ full suite passed (2,044 tests, 26 skipped).
EXP-1616 prepared a fresh candidate tag; its focused suite passed (35 tests).
EXP-1617 returned `ARCHIVE_INVALID` and EXP-1619 refined that to the safe
allowlisted `stage=archive-validation`; neither archive was accepted nor pins
changed. The latest task tag state remains unqueried. Batch AKCB full suite
passed (2,052 tests, 26 skipped). EXP-1620 added safe attribution to manual
archive checks and a fixed EXP-1621 wrapper; its focused suite passed (44
tests) and `git diff --check` passed. The one self-confirmed EXP-1621 attempt
returned `ARCHIVE_INVALID|stage=daemon-config-digest-mismatch`; no candidate
was accepted and production image pins did not change. The new task tag may
remain; it was not queried or cleaned. Batch AKCC full offline suite passed
(2,056 tests, 26 skipped), and `git diff --check` passed. R2/MVP remain OPEN.
EXP-1622 adds a fixed, allowlisted config-name/content relation fact to the
safe mismatch marker; focused suite passed (46 tests) and `git diff --check`
passed. EXP-1623 returned
`ARCHIVE_INVALID|stage=daemon-config-digest-mismatch|fact=config-name-mismatches-content`.
The fact expresses only literal filename/content-hash equality; Docker's
archive spec describes `manifest.json.Config` as a file reference and does
not make that equality a requirement. The underlying daemon/config digest
mismatch remains unexplained. No pins changed; the tag may remain and was not
queried or cleaned. Batch AKCD suite passed (2,058 tests, 26 skipped) and
`git diff --check` passed. R2/MVP remain OPEN.
EXP-1624 adds only fixed archive-format and legacy/OCI-config-to-daemon
identity facts to the mismatch marker; it does not change acceptance or pins.
Focused candidate suite passed (48 tests), and `git diff --check` passed.
EXP-1625 returned
`ARCHIVE_INVALID|stage=daemon-config-digest-mismatch|fact=config-name-mismatches-content|archive=oci+docker-legacy|legacy-config=daemon-mismatch|oci-config=daemon-mismatch`.
Both archive config views mismatch the daemon ID; this does not establish the
root cause. No pins changed; the tag may remain and was not queried or cleaned.
Batch AKCE full suite passed (2,060 tests, 26 skipped) and `git diff --check`
passed. EXP-1626's single redacted read-only query classified the Docker
storage backend as `containerd`; it did not inspect images or mutate state.
EXP-1627 adds only a safe comparison of OCI manifest digest to daemon `.Id`.
Focused tests (53 across the related modules) passed, with no Docker call for
EXP-1627. EXP-1628 returned
`ARCHIVE_INVALID|stage=daemon-config-digest-mismatch|fact=config-name-mismatches-content|archive=oci+docker-legacy|legacy-config=daemon-mismatch|oci-config=daemon-mismatch|oci-manifest=daemon-match`.
For this candidate, daemon `.Id` matches the OCI manifest digest, not config
digest. This is an observed local backend behavior, not a universal Docker
contract. No pin changed; the task tag may remain and was not queried or
cleaned. Batch AKCG full offline suite passed (2,065 tests, 26 skipped) and
`git diff --check` passed.
EXP-1629 changes candidate validation to accept a daemon `.Id` only when it
equals the archive's fully validated config digest (classic) or OCI manifest
digest (containerd); unrelated IDs remain rejected. Synthetic suites passed
(99 combined, then 50 candidate tests), with no Docker operation. EXP-1630
passed the new image-ID binding and then returned
`ARCHIVE_INVALID|stage=docker-layer-diff-id-mismatch`. In parser order, OCI
layers had already passed; the legacy compatibility-layer check failed. No
verifier pins changed; the task tag may remain and was not queried or cleaned.
Batch AKCH full offline suite passed (2,066 tests, 26 skipped) and
`git diff --check` passed.

**Исторический baseline (Batch AJI, 2026-10-19):** EXP-1269 остаётся
последней принятой цепочкой реального local Worker → target tests → same-host
verifier → stage. Её отдельный WAL-aware snapshot принят по EXP-1483. EXP-1498
один раз воспроизвёл сохранённый candidate через текущий публичный snapshot,
`network=none` target и текущий локальный same-host verifier с `fresh_pass`;
verified contents byte-identical, но это не новый Worker run и не независимый
verifier. Новый staged digest —
`sha256:14e3118b49eff4ff57dd56218dcb5aaa610bb8c3ecf9e5de55fbb71ca47d0809`,
verification digest —
`sha256:ab3f36bfd902ae9064b8dab3e13996093113a919dc08e47670ad84db6e1d1579`;
Observer остаётся partial на cursor 87. EXP-1500 подтвердил, что approval
request fail-closed отклоняется при отсутствии verifier provenance trust;
request/signature/provider action не создавались. Текущие независимые verifier
artifacts подготовлены локально: image/manifest
`sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`,
code `sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`,
classic-store config
`sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`,
source bundle
`sha256:d0d51e4a37ba0dc86cd649acf79e7bab3c790dc680bd0ea81df5291782b0f35f`.
EXP-1493 и EXP-1494 — отдельные DRAFT transfer/import gates; оба помощника
пока не запускались. `RUN EXP-1468 ONCE` и позднее подтверждение для
EXP-1465 не применялись: соответствующие карточки BLOCKED и ссылаются на
устаревшие pins/scope. Следующий remote replay потребует принятия актуальных
transfer/import gates и новой карточки с отдельным свежим разрешением.
Кроме того, текущий verifier profile digest
`sha256:95187a75559f945fdaf40b194f5d8815da21baa6c8f165efc16cded68b57c758`
не совпадает с profile digest
`sha256:603f0e674e131ef795f115f099cdeb514452a82def41e5b5853f84f62d7ff281`,
жёстко разрешённым в `scripts/exp1383_macos_keychain_signer.swift`; этот signer
также ограничен EXP-1383. Текущая авторизация на Keychain/signing не
распространяется на новый replay. Keychain не читался; требуется отдельное
решение о новом signer scope/источнике, прежде чем готовить live trust-signing
карточку.
EXP-1503 прошёл локальный synthetic REST-to-signed-mock-receipt composition
test: synthetic REST transport, verifier/authority/approver keys и local mock
publisher; receipt остался `external_write=false` и
`identity_authenticated=false`. EXP-1505 проверил, что synthetic
`identity_authenticated=true` claim блокируется до provider configuration,
token minter и publication journal. Это подтверждает только локальную synthetic
композицию и refusal gate, а не доверие к независимому verifier, реальную approval подпись,
provider write или публикацию. Независимый verifier, digest-bound approval,
controlled PR и MVP остаются OPEN. Последний полный offline suite после Batch
AJI прошёл: 1,896 тестов, 25 пропущено за 77.443 секунды; это regression
evidence, не сквозное подтверждение MVP.

**Актуальный delta к baseline, Batch AKD (2026-10-19):** EXP-1521 локально
собрала текущий verifier-кандидат `agent00x-verifier:exp-1521-e6fb28b`
(`linux/amd64`, config ID
`sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b`,
code digest `sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e`)
и прошла один synthetic контейнерный запрос. Этот локальный кандидат не заменил
production pins и не доказывает portable/remote identity. EXP-1526 попыталась
связать один локальный save с известными daemon facts, но ограниченный маркер
результата не сохранился; попытка inconclusive, повтор не делался. EXP-1527
добавила bounded incremental save-output capture; EXP-1528 ограничила
распакованный суммарный размер слоёв. Их синтетические/regression suites прошли,
без нового Docker/save запуска. EXP-1529 остановилась до Docker из-за прямого
import-path. EXP-1530 один раз выполнила save, но returned
`PORTABLE_IMAGE_CHAIN_INVALID`; последующая локальная проверка обнаружила, что
ожидаемый config digest в runner был неверной длины (61 hex-символ вместо 64),
и parser отказал на проверке expected facts до разбора архива. Portable identity
этим не установлена, архив не сохранён, повтор по EXP-1530 не выполнялся.
EXP-1531 исправила tuple: единственная save-попытка дошла до `archive-members`.
EXP-1532 добавила безопасные directory entries; EXP-1533 — согласованную
проверку OCI+legacy metadata; EXP-1534/1535/1536 уточнили OCI ref binding.
EXP-1537 изменила проверку OCI ref-name по спецификации: принимает только
короткую точную tag-компоненту или полный RepoTag; 28 focused tests и полный
suite (1,925 тестов, 26 skipped) прошли. Единственный новый bounded save вернул
`PORTABLE_IMAGE_CHAIN_INVALID|stage=docker-layers`. До него прошли OCI index,
manifest/config, platform, RepoTag и ordered DiffID metadata; broad marker пока
не отличает member-read, size-limit и layer DiffID mismatch. EXP-1538 разделила
их; 28 focused tests, 1,925 тестов полного suite (26 skipped) и `git diff
--check` прошли. Один bounded save уточнил результат до
`docker-layer-diff-id-mismatch`: legacy member присутствует и проходит limit,
но digest bytes не равен ожидаемому DiffID. EXP-1539 добавила bounded ordinal;
29 focused tests, 1,926 тестов полного suite (26 skipped) и `git diff --check`
прошли. Единственная save-попытка показала `layer_index=0`; архив, слой и
digest не сохранялись, повтора не было. Это не доказывает ошибку OCI chain:
OCI DiffID определён как hash несжатого tar, а Docker image-save отдельно
содержит legacy `layer.tar`; EXP-1540 добавила memory-only extraction OCI
subset и synthetic test на несовпадающий legacy слой. 31 focused tests, 1,928
тестов полного suite (26 skipped) и `git diff --check` прошли. Единственный
bounded save вернул `OCI_SUBSET_INVALID|stage=daemon-facts`: OCI chain была
проверена, но не совпал по крайней мере один закреплённый факт. Архив и raw
значения не сохранялись/не выводились; повтора не было. EXP-1541 разделила
config digest, platform и DiffID pin failure в фиксированные маркеры; 32
focused tests и полный suite (1,929 тестов, 26 skipped) прошли. Единственная
попытка вернула `daemon-config-digest-mismatch`: OCI DAG целостен внутри save,
но config ID не совпал с закреплённым. EXP-1542 read-only сверила local tag:
config ID, linux/amd64 и все девять ordered DiffIDs совпадают с pin; focused
test и полный suite (1,930 тестов, 26 skipped) прошли. Следовательно, tag не
сдвинут, а OCI save representation сообщает иной config digest. EXP-1543
добавила вывод только проверенных config digests; 35 focused tests, полный
suite (1,932 теста, 26 skipped) и `git diff --check` прошли. Одна save-попытка
сообщила expected Docker config
`sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b` и
observed OCI config
`sha256:8fd288eaae140b2ba5acbf70aa3e18db0d54c724c0a20e5a65080d214966eaeb`.
Archive и config JSON не сохранялись, повтора и pin mutation не было. Поэтому
OCI config не признан идентичным Docker image config. EXP-1544 изучила
`containers/verifier/Dockerfile` и экспортные скрипты: Dockerfile использует
digest-pinned Python 3.11 slim, копирует разрешённые runtime/source/schema
файлы и запускается под UID 65532. `command -v` нашёл Docker CLI, но не
`skopeo`, `umoci` или `buildctl`; `docker buildx version` вернул
`BUILDX_UNAVAILABLE` без daemon/network/build. EXP-1546 проверит локальную
загрузку только проверенного OCI subset под новым непересекающимся tag
`agent00x-verifier:exp-1546-oci-candidate`; исходный tag не меняется. Batch
AKX прошёл 37 focused tests, полный suite (1,934 теста, 26 skipped) и
`git diff --check`. Один `docker image load` завершился без ошибки, но inspect
по новому tag вернул `POST_LOAD_INSPECT_FAILED`; archive не сохранялся, tag
не менялся после load, image не удалялся. Возможен untagged образ
`sha256:8fd288eaae140b2ba5acbf70aa3e18db0d54c724c0a20e5a65080d214966eaeb`.
EXP-1547 прошла 38 focused tests, полный suite (1,935 тестов, 26 skipped) и
`git diff --check`. Единственный inspect exact ID вернул `IMAGE_ID_NOT_FOUND`;
общий список образов не запрашивался. EXP-1548 также вернула
`CANDIDATE_TAG_NOT_FOUND` для выделенного tag. Docker image load завершился с
успехом, но ни exact OCI ID, ни candidate tag в image store не обнаружены;
никаких других образов не перечисляли. EXP-1549 синтетически подтвердила
конверсию OCI в Docker archive (41 focused tests, полный suite 1,938/26), но
одна bounded save остановилась до `docker load`: decompressed слои превышают
128 MiB save cap, хотя разрешённый layer expansion cap — 512 MiB; кроме того,
ошибка выявила отсутствующий fixed-marker helper. Archive не сохранялся и
image load не выполнялся. EXP-1550 разделила лимиты и добавила helper; 42
focused tests, полный suite (1,939/26) и `git diff --check` прошли. Одна новая
save/convert/load попытка завершилась `DOCKER_LOAD_FACTS_MISMATCH` после
успешного inspect нового tag; фактические поля не выводились. EXP-1551 прошла
43 focused tests, полный suite (1,940/26) и diff-check; exact candidate tag
содержит config ID `sha256:f9352ed122050abfa42526544c101a713f4724271e0aa044fb92e56972a0ae38`,
linux/amd64, все девять ожидаемых DiffIDs, user `65532:65532` и ожидаемый
entrypoint. Docker при load переписал config ID относительно OCI source
`8fd2…`, но runtime tuple и filesystem layers совпали. EXP-1552 прошла 45
focused tests, полный suite (1,942/26) и diff-check; одна synthetic container
попытка вернула только `SYNTHETIC_VERIFIER_FAILED`, без stderr/details; adapter
прибрал container. Повтора нет. Поскольку launcher привязывается к
`/var/run/docker.sock`, EXP-1553 проверяет только наличие этого Unix socket и
его permission bits. Локальная изоляция/verifier ещё не подтверждена.
Portable identity текущего образа по-прежнему не подтверждена. Transfer/import cards EXP-1493/1494 ссылаются
на более старые pins и остаются непригодными для текущего кандидата. EXP-1448
superseded; EXP-1585 остаётся DRAFT за точным gate `RUN EXP-1585 ONCE`; новый
Worker/model run не выполнялся. Независимый verifier, human-authenticated digest-bound approval и
real controlled PR по-прежнему отсутствуют; R2/MVP остаются OPEN.

EXP-1571 checked standalone executable names and `docker image save`, but did
not check the Docker CLI plugin namespace. EXP-1572 corrected that audit:
`docker buildx version` reports `v0.27.0-desktop.1`; `docker buildx ls` reports
two running local Docker-driver builders with BuildKit v0.23.2. Official Docker
documentation describes `--output type=docker,dest=-` as a single-platform
Docker image-spec tarball exporter, also OCI-compatible. This supplies a
candidate offline export route, not proof that this project's exact artifact
matches the pinned runtime. No build, export, image mutation, network or remote
operation was run; no pin or credentials changed. EXP-1540—1543's config-ID
mismatch remains unresolved, so `b2bf…` is not promoted. EXP-1573 added a
gated Buildx candidate exporter with in-memory archive validation and fixed
synthetic tests (9 passed), including valid legacy-archive parsing, rejection
of tag/layer mismatches, and cleanup-failure precedence. Its single local
build/export returned only
`EXPORT_FAILED`; the no-retry rule was followed. No image load, tag, pin update,
transfer or publication occurred. Temporary-container cleanup was invoked but
its outcome was not surfaced by the original runner path, so it remains
unverified and was not queried again. The runner's local failure reporting was
corrected; the build was not repeated. Final batch-end offline suite passed (1,956
tests, 26 skipped). R2/MVP remain OPEN.

EXP-1575 attempted to clarify the local Buildx environment without repeating
the export. Its gated, credential-isolated, read-only version/default-builder
probe returned only `PROBE_UNCLASSIFIED` (exit 12), which does not identify
which of the two outputs could not be parsed. No image was inspected or invoked;
no retry or diagnostic was run. The installed Buildx driver/version therefore
remain unknown from this probe, and EXP-1573's archive failure is unresolved.
Focused synthetic tests passed (5); batch-end full suite passed (1,961 tests,
26 skipped); `git diff --check` passed. No MVP criterion changes; R2/MVP remain
OPEN.

EXP-1576 improved the local probe to preserve separate version and default
builder facts, then ran it once. It returned
`BUILDX_PROBE|version=unclassified|builder=unclassified` (exit 12). The marker
does not distinguish command failure from output-format mismatch, so neither
capability is established. No raw output, retry, export, image operation or
credential access occurred. Six focused tests and the batch-end offline suite
(1,962 tests, 26 skipped) passed; R2/MVP remain OPEN.

EXP-1577 used EXP-1572's accepted Buildx v0.27.0-desktop.1 / Docker-driver
BuildKit v0.23.2 evidence and made one bounded offline Docker archive export
attempt against the exact target runtime and digest-pinned Python base. The
marker was `EXPORT_FAILED|reason=unknown` (exit 14); raw output was discarded,
and no retry or extra diagnosis followed. The runner did not report failure
while removing its own temporary container. No archive identity was validated,
no image was loaded/tagged/pushed, and no verifier was invoked. The portable
candidate remains unqualified; no production pin changed. Focused tests passed
(12); batch-end full offline suite passed (1,965 tests, 26 skipped). R2/MVP
remain OPEN.

EXP-1579 distinguished the Buildx process result from an internal runner error.
One fresh local offline export emitted only
`EXPORT_FAILED|reason=unclassified_stderr|exit=125|stderr_bytes=109` (wrapper
exit 14). The process produced bounded stderr, but its cause was not in the
allowlist; raw text was discarded and no retry/diagnostic followed. The exact
temporary container cleanup did not report failure. No archive identity was
validated and no image was loaded/tagged/pushed or verifier invoked. The
candidate remains unqualified and pins unchanged. Focused tests passed (13);
batch-end full offline suite passed (1,966 tests, 26 skipped). R2/MVP remain
OPEN.

EXP-1580 tried the distinct Buildx `--load` then `docker image save` route with
the exact local target/base pins and a task-unique tag. It returned
`CLEANUP_FAILED` (exit 22), which does not reveal whether the exact temporary
dependency-copy container or the newly owned image tag resisted cleanup. The
archive was not accepted; no verifier ran and no production pin changed. A
separate exact read-only tag-presence card is pending; no container query or
cleanup retry is authorized by EXP-1580. R2/MVP remain OPEN.

EXP-1581 made one exact filtered read-only presence query for tag
`agent00x-verifier:exp-1580`; it returned `EXP1580_TAG_ABSENT`. No verifier image
tag remains in the local store. This does not establish whether the earlier
dependency-copy container cleanup succeeded, because its ID was not retained
in the fixed marker/evidence
and no container query was authorized. No follow-up cleanup or broader Docker
listing occurred. R2/MVP remain OPEN.

**Уточнение модели Worker (2026-10-19, EXP-1512/1513):** EXP-1512 сначала
ошибочно заключила, что pinned Ollama v0.40.3 не поддерживает digest-reference
для inference. Повторная сверка официального `server/model_resolver.go`,
`manifest/paths.go` и route `/v1/chat/completions` показала, что локальный
reference `sha256-<64 hex>` разрешается к точному manifest blob, а OpenAI-
compatible route проходит через общий chat handler. EXP-1513 изменила канал:
после metadata preflight он отправляет digest-reference
`sha256-dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`, а
не изменяемый tag `qwen2.5-coder:7b`; synthetic tests проверяют точное поле
запроса и отказ на ответ с чужим model reference. Это закрывает известный
TOCTOU между tag-check и последующим name resolution на поддерживаемом
локальном API path, но пока является unit-test evidence: Ollama, Worker и модель
не запускались. Основание: [resolver](https://github.com/ollama/ollama/blob/v0.40.3/server/model_resolver.go),
[manifest digest lookup](https://github.com/ollama/ollama/blob/v0.40.3/manifest/paths.go)
и [chat route](https://github.com/ollama/ollama/blob/v0.40.3/server/routes.go).
EXP-1585 остаётся DRAFT и требует точного gate; независимый verifier, approval,
publication и MVP остаются OPEN. Целевые тесты EXP-1513: 9 passed; полный
offline suite batch: 1,896 tests, 25 skipped (77.525 seconds); `git diff
--check` passed.

EXP-1515 registered the exact local one-shot CLI tuple for EXP-1448
(`RUN EXP-1448 ONCE`, process `process-exp-1448-local-001`, task
`task-exp-1448-local-001`) with the fixed public snapshot origin and
`local-ollama` backend. The profile is only a gate mapping; it did not grant
permission to run and was later retired by EXP-1584. EXP-1585 now remains DRAFT
until its fresh exact user gate, and no
preflight, quota request, Ollama process, Worker or model ran in EXP-1515.
Focused CLI tests passed (53); Batch AJQ full offline suite passed (1,897 tests,
25 skipped in 77.488 seconds); `git diff --check` passed. R2/MVP remain OPEN.

EXP-1516 closes the Observer run only on known-success local mock-publication
completion in `signed_mock_publication.py` and the stage-approval CLI: append
`run_finished` after `agent_finished` and mock receipt/confirmation readback.
Bad signature/pending publication and mock failure cases remain without
`run_finished`. Focused tests and batch-end suite evidence are recorded with
the EXP-1516 card. This does not cover real GitHub publication or prove complete
collection/durability; criteria 13/14 remain PARTIAL and R2/MVP OPEN.

EXP-1518 adds an optional Observer to the signed GitHub publication API. The
synthetic fake-transport path records `Publication.dispatch`; a clean validated
receipt closes the run only after publication-journal/readback checks. A
dispatch exception is recorded as `outcome_unknown`, and a failed, unknown, or
unavailable Observer terminal leaves the run open. A recovered receipt does
not override a non-success Observer dispatch event. Tests use only fake
provider transport and temporary SQLite files; they do not exercise GitHub,
credentials, or a live publication. This is bounded lifecycle instrumentation,
not full collection or evidence of a real provider outcome; criteria 13/14 and
R2/MVP remain PARTIAL/OPEN.

EXP-1518's Observer runtime change also changes the verifier source bundle and
hashed runtime context. EXP-1519 refreshes their local source digests and
bundle metadata only (runtime source digest
`sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e`;
bundle `sha256:da8e4b2925b9cf32582dc81ed3347d6c43e87dcc59f2a2f88e11630cca50d13b`,
33 members, 566,513 source bytes, 604,160 archive bytes). It leaves the prior Docker image/config IDs
unchanged and does not build or inspect an image; therefore the new
source-digest/image-ID pair is not evidence that the existing image contains
the changed Observer code and is not qualified for verifier execution or
enrollment. EXP-1521 below records a separate fresh local build; it does not
qualify the old production pin or prove independent-host trust.
EXP-1520 refreshed only the derived current local profile fingerprint to
`sha256:95187a75559f945fdaf40b194f5d8815da21baa6c8f165efc16cded68b57c758`;
profile policy inputs were unchanged. Batch AJV's full offline suite passed
(1,902 tests, 25 skipped, 74.876 seconds). Batch AJT and AJU retain their
historical failed-closure records; the corrective successor path through AJU
and AJV passed its final closure.
These remain local regression/source-pin results, not verifier or publication
evidence. R2/MVP remain OPEN.

EXP-1521 built a fresh verifier image locally, with `--pull=false` and
`--network=none`, from the current verifier context and the already pinned
target dependency image. Exact retained tag:
`agent00x-verifier:exp-1521-e6fb28b`; config ID
`sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b`,
platform `linux/amd64`; source code digest
`sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e`.
One synthetic `VerifierInput` returned `PASS` through that image with matching
identity. This is local same-host container evidence only; no live GitHub,
credentials, external verifier, host independence, or isolation was tested.
Production pins remain unchanged pending review of the image/code/config tuple.
The one ordinary Batch AJW full offline suite passed (1,903 tests, 26 skipped,
76.483 seconds); `git diff --check` passed. R2/MVP remain OPEN.

EXP-1522's one local portable-image audit did not produce facts; it returned a
sanitized Python failure and did not retain the archive. EXP-1523's separate
format-only save attempt returned `IMAGE_ARCHIVE_FORMAT_UNKNOWN` without raw
diagnostics or saved bytes. EXP-1524 confirmed that the tag still exists in the
Docker store at config ID `sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b`,
`linux/amd64`, size 48,857,037 bytes, with nine ordered DiffIDs. Thus the local
container works, but its portable manifest identity remains unknown.
EXP-1525 adds synthetic-only parsing/validation for both OCI and legacy Docker
archive formats. Its focused tests passed (9); Batch AKA's offline suite passed
(1,906 tests, 26 skipped, 76.201 seconds). The parser has not yet been run
against this image's save stream: EXP-1526's one permitted attempt terminated
without a preserved bounded result marker, so no conclusion can be drawn and
no retry or further Docker operation was performed. EXP-1527 made future saves
incremental and bounded (128 MiB / 60 seconds; stderr discarded; terminate and
reap on timeout/overflow); its 13 focused tests and full suite (1,910 tests,
26 skipped) passed. EXP-1528 capped aggregate expanded layer data at 512 MiB
across OCI and legacy archives, with incremental gzip hashing; 16 focused tests
and the full suite (1,913 tests, 26 skipped) passed. No Docker/image-save was
run in EXP-1527/1528. Portable image identity is still unknown; there is still
no independent-host or remote-verifier evidence. R2/MVP remain OPEN.

Test cadence decision (2026-10-19): для новых batch полный offline suite
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` запускается
один раз по завершении всех карточек batch. Между карточками остаются целевые
проверки изменённого компонента и локальные проверки; batch не принимается до
успешного итогового полного прогона. Исторические результаты ниже сохраняют
свой первоначальный объём и не пересчитываются.

Batch AAF / EXP-1225 authorized exactly one transfer of verifier image
`sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`
to the `testdev` Docker image store. The transfer helper showed the exact
`RUN EXP-1225 ONCE` gate; after that single run it returned only
`REMOTE_LOAD_IDENTITY_UNCONFIRMED` (exit 18), not `IMAGE_IMPORT_CONFIRMED`.
The image may have loaded partially or fully, but there is no accepted evidence
of its remote identity. Per the card, no retry, remote diagnosis or cleanup was
performed. EXP-1225 is BLOCKED and any further testdev action requires a new
exact card and authorization. R2/MVP remain OPEN.

Batch AAG / EXP-1226 was blocked before tests because its card named a nonexistent
unittest class. Batches AAH–AAI / EXP-1227–1228 were blocked before Docker
execution because copied verifier-digest values did not match the active
profile; the opt-in guard skipped the composition. Batch AAJ / EXP-1229 then
passed the verifier-context digest preflight and one current-pin local synthetic
Docker composition (2.574s) using target image
`sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187` and
verifier image `sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`.
The receipt remains `external_write=false`, `identity_authenticated=false`.
This is same-host synthetic evidence, not a public snapshot/real Worker run,
independent verifier host, authenticated approval, recovery or real PR. No
network, credential, model, SSH/testdev or provider write was used. R2/MVP remain
OPEN.

Remote verifier image identity follow-up (2026-10-16): EXP-1347 found the exact
config digest present in the testdev image store; EXP-1348 reported an opaque
tuple mismatch. The separately authorized, single EXP-1349 field-facts inspect
reported `id=match|platform=match|size=mismatch|layers=match` (exit 11), with no
raw metadata exposed. Thus ID, platform and ordered layers match the local pin,
but the image size differs. EXP-1349 is BLOCKED; its one-shot permission is
consumed. No retry, remote diagnostics, container/service launch, import,
cleanup or other remote action occurred. This discrepancy does not establish
verifier readiness or independent host trust; R2/MVP remain OPEN.

Local portable-image audit (2026-10-17): EXP-1350's single opt-in, in-memory
`docker image save` returned `PORTABLE_IMAGE_CHAIN_CONFIRMED`. The exact pinned
OCI index target hashes to its manifest; that manifest's config descriptor and
bytes hash to the config ID observed on testdev; platform, nine ordered DiffIDs,
each layer blob hash and each uncompressed layer DiffID match the pin. Five
focused synthetic tests cover broken manifest/config links, corrupt config,
platform and layer mismatch, the opt-in guard and redacted save failure. The
full offline suite ran 1,806 tests (25 skipped) successfully; the scoped diff
check was clean. Under
the [OCI image configuration specification](https://github.com/opencontainers/image-spec/blob/main/config.md),
the config digest addresses image configuration and ordered uncompressed layer
hashes. Moby's [image inspect type](https://github.com/moby/moby/blob/master/api/types/image/image_inspect.go)
defines `.Size` as storage usage that, with containerd, includes local image
content and unpacked snapshot data. Therefore size mismatch alone does not
invalidate the content digest/DiffID evidence; the exact cause of this host's
size discrepancy remains unmeasured. This is a Control Plane inference from
the local chain and EXP-1349's bounded remote facts, not a verified remote
service or independent host trust attestation. R2/MVP remain OPEN.

Publication and Worker preparation (2026-10-17): EXP-1351 now requires an
authority-signed approver-key enrollment, verified against an out-of-band
digest-pinned public authority-key set, before preview or any GitHub App
provider configuration. Missing/invalid enrollment fails without Broker,
journal or provider effect; the fake-provider success path still binds the
exact staged digest and reports `identity_authenticated=false`. Nine focused
tests and the full 1,810-test offline suite (25 skipped) passed. This verifies
key enrollment, not human identity or a live PR. EXP-1352 registers a distinct
EXP-1354 local-Ollama Worker profile; it has no permission to run the Worker.
Its 50 focused CLI tests and the full 1,812-test offline suite (25 skipped)
passed. The profile preserves the fixed public snapshot and local target/
verifier/model pins but does not refresh the expired execution authorization.
No readiness request, model, Docker, credential, SSH/testdev or provider write
occurred in these local preparations. The separate EXP-1354 authorization then
used one anonymous Control Plane readiness GET (HTTP 200, remaining 60), one
runner readiness check and exactly one local Ollama model-channel call. It
stopped at `target-test-malformed-status-level-bool` before verifier PASS or
stage/readback; observer cursor 76 records one pending/ok model-channel pair.
Both retained evidence DBs passed `quick_check` and have mode 0600. The owned
Ollama daemon was stopped, with no TCP 11434 listener. No approval, provider
write, PR or retry occurred. EXP-1354 is BLOCKED and spent; reuse the accepted
EXP-1269 successful stage for downstream work instead of repeating Worker.
R2/MVP remain OPEN.

EXP-1445 retired the static `EXP-1425` authorization profile after its recorded
one-shot Worker attempt was spent. The card ID is absent from the CLI's profile,
snapshot-origin and model-backend maps; tests cover all three. This prevents
reusing the old phrase/profile, but does not provide a replacement Worker
authorization or change the failed attempt's evidence. R2/MVP remain OPEN.

The complete offline suite after EXP-1445 passed 1,874 tests with 25 skipped;
the count is lower by one because the obsolete positive EXP-1425 profile test
was removed. Focused CLI tests passed (52). This is regression evidence only;
no Worker/model/network/DB or external action occurred. A new exact card and
fresh authorization are required for any future Worker attempt.

EXP-1446 retired EXP-1354's static authorization profile after its one
authorized Worker/model attempt was spent. The ID is absent from all three CLI
authorization maps, and argument parsing rejects it. Focused CLI tests passed
(51); full offline suite passed (1,873 tests, 25 skipped). No runtime or
external action occurred. EXP-1425 and EXP-1354 are both spent; no replacement
profile is registered, and a fresh exact card/authorization is required for
another Worker attempt. R2/MVP remain OPEN.

EXP-1447 clarifies the next Worker task after comparing the strict-bool failure
with `backend/routes.py` at pinned commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`: the baseline converts all five
numeric fields with `int(data.get(...))` before SQL, so JSON `true` becomes `1`
before any later strict-type check. The prompt now explicitly deletes those
conversions, gives exact raw reads/defaults, requires `HTTPException` import,
and forbids coercion on the changed path. Focused CLI tests passed (51); full
offline suite passed (1,873 tests, 25 skipped); `git diff --check` passed. This
is prompt-contract evidence only; EXP-1354's candidate was not retained or
inspected, and no new Worker/model attempt was made. Fresh authorization is
still required before a future attempt; R2/MVP remain OPEN.

Verifier-host critical path (EXP-1353, updated 2026-10-17): use the existing
one-shot user-process HTTPS launcher on testdev rather than requiring systemd
privileges. EXP-1363 transferred the exact 33-member source bundle once to
`/home/alex/.local/share/agent00x/verifier-host/exp-1363`; its receiver emitted
`BUNDLE_TRANSFER_CONFIRMED` only after validating the pinned archive, canonical
manifest and member hashes. This proves bounded transfer, not runtime readiness.
The launcher binds remote loopback and exits after one request; any SSH forward
must carry only routing while the client verifies fixed
`https://testdev.local/v1/verify`, TLS SAN and caller-pinned CA. A separate
Control Plane-governed authority must enroll the ephemeral signer and issue a
host-trust decision tied to both host IDs and out-of-band separation evidence.
Neither the remote bootstrap nor image/content identity establishes that trust.
Runtime/dependency preflight and authority custody are not yet confirmed; no
remote service or verifier request was run. Local `--help` import smoke for the
exact launcher passed (exit 0). The separately authorized EXP-1371 remote
`--help` import smoke also returned its exact success marker; it verifies only
Python import readiness on the host, not service/runtime readiness.
EXP-1364 was superseded because it targeted the previous bundle. EXP-1368
transferred the refreshed source pin once to
`/home/alex/.local/share/agent00x/verifier-host/exp-1367`; the receiver emitted
`BUNDLE_TRANSFER_CONFIRMED` after validating the pinned archive, canonical
manifest and member hashes. This confirmed file transfer only; at that point no
remote import smoke, Docker/container, service, tunnel or verifier request had
run. The streamer targets a unique directory for this source pin;
`sha256:5536709798de2a5756a62be351b839598b763025ac4c45635a6f7f272cbdaacd`
is now present at the transfer target. EXP-1371's one separately authorized
strict-host-key SSH command returned exit 0 and the exact marker
`VERIFIER_IMPORT_SMOKE_OK` while invoking only the bundled launcher's
side-effect-free `--help`. This confirms remote Python imports for this bundle;
it does not confirm Docker/image readiness, service startup, bootstrap, verifier
behavior, host trust or MVP completion. No verifier-host execution card is
READY. R2/MVP remain OPEN.

Detached authority signing (EXP-1365/1369/1372, 2026-10-17): both verifier enrollment
and host-decision modules expose canonical domain-separated signing messages
and detached-signature assembly, allowing a separate signer to operate without
passing its private key into these modules. EXP-1369 adds a public-only
stdin/stdout CLI to prepare messages for a separately governed signer; output
is explicitly `trust=unestablished`, and the CLI cannot sign or verify. Existing
validators remain the trust boundary; assembly alone is untrusted. Nineteen
trust-module tests and four CLI tests passed. EXP-1366 refreshed the dependent
local bundle pin; 49 focused bundle/streamer/trust/CLI tests and the full
offline suite passed at that point (1,845 tests, 25 skipped). EXP-1372 adds a
local bounded stdin/stdout CLI that assembles an external detached signature,
checks its caller-pinned authority key-set digest and every expected deployment
binding, and emits the signed artifact only after verification. It accepts only
public signature material and never signs or contacts a service. Its fixed
result explicitly keeps `independent_host_trust_established=false`; authority
signature validity does not verify deployment or OOB host-separation evidence.
EXP-1373 extends the success evidence with the complete verified binding tuple
and signed validity interval, and README now documents the handoff envelope and
local operator sequence. Focused tests: 5 passed. The current full offline
suite passed (1,850 tests, 25 skipped). Two in-memory bundle builds match at
`sha256:5536709798de2a5756a62be351b839598b763025ac4c45635a6f7f272cbdaacd`
(33 members, 552,056 source bytes; 593,920 archive bytes).
No private key, signature from a real authority, SSH or remote action was used.
No MVP trust criterion is promoted; R2/MVP remain OPEN.

EXP-1374 executes the documented verifier CLI as a separate local Python
process using only synthetic enrollment/signature/key-set data. Both the
successful JSON evidence output and wrong-pin fail-closed marker are covered;
there is no stderr on success and no stdout on rejection. Six focused tests
passed; current full offline suite: 1,851 tests, 25 skipped. This confirms the
operator entrypoint only, not a real authority signature or remote trust.

EXP-1375 requires and revalidates the signed enrollment artifact before
accepting a host-trust decision, checks the same complete deployment binding
tuple and caller-pinned enrollment digest, and reports that exact bound digest.
Missing, tampered and substituted enrollment records fail before output.
Focused suite: 7 passed; full offline suite: 1,852 tests, 25 skipped. Both
signatures and the authority key are synthetic; host separation remains
unestablished.

EXP-1377 verifies that the local verifier launcher's `--help` exits before
calling verifier, signer, TLS-identity or server factories; an actual local
subprocess emits usage only. Launcher suite: 9 tests (7 passed, 2 skipped);
full offline suite: 1,854 tests, 25 skipped. This supports the safety
precondition for EXP-1371 but does not prove imports on testdev, service
readiness or remote verifier behavior.

EXP-1379 rebuilt the verifier-host bundle in memory and matched the exact
EXP-1368 pin (`sha256:5536709798de2a5756a62be351b839598b763025ac4c45635a6f7f272cbdaacd`,
593,920 archive bytes, 33 source members, 552,056 source bytes), then extracted
only regular safe-path members in a temporary directory and ran that pinned
bundle's launcher `--help`. The exact-pin import succeeded with usage output and
no stderr. Focused test: 1 passed; current full suite: 1,854 tests, 25 skipped.
This verifies the local archive, not the transferred copy on testdev; EXP-1371
subsequently verified the transferred copy's import path only. Remote runtime
readiness and trust remain unproven.

Public bootstrap preflight (EXP-1356, 2026-10-17): a new local read-only parser
and CLI bind the one-shot launcher's exact canonical JSON bytes to a
caller-supplied SHA-256 digest, the fixed endpoint/loopback port, current
BrainBooster verifier profile/key ID, CA certificate/hash and Ed25519 public
key/hash. It rejects duplicate or extra fields, noncanonical or oversized
input, symlink/non-regular files and pin mismatches while emitting only a
bounded public-digest marker with `trust=unestablished`; the returned object
also contains no raw CA or signer key. Seven focused tests,
including the real launcher serializer without starting a server, passed;
the full offline suite passed 1,819 tests (25 skipped). No real bootstrap,
credential, key, SSH/testdev, service, enrollment, host decision or verifier
request was used. A caller pin obtained from the same remote bootstrap would
not be out-of-band trust. Independent verifier readiness remains OPEN.

Host-bundle local refresh (EXP-1357, 2026-10-17): two sequential in-memory
builds matched byte-for-byte at
`sha256:98a8432f7d6eb48f9079d30979b8887daa3ea4358958e5c062ca83b6a285ae67`
(32 source members; 540,864 source bytes). The focused bundle suite passed 15
tests. The earlier EXP-1300 digest covered 31 members and is stale. The new
digest describes this dirty worktree only; the expanded import closure has not
yet been independently audited at this checkpoint and this was not an approved
deployment pin.
No archive file, SSH, service or remote change occurred. R2/MVP remain OPEN.

EXP-1358 audited the 32-member archive against its manifest: exact names,
sizes and SHA-256 values matched; 15 focused import-closure tests passed.
Compared with EXP-1301's recorded 31-member list, the only new member is the
data-only `verifier_image_pin.py` with public image/code digests. No concrete
credential reader or secret-bearing path entered the bundle. This source audit
does not approve deployment. It exposes a separate runtime address gap:
`create_brainbooster_verifier_runner` passes the manifest digest to Docker run,
whereas the classic image store on testdev was observed by config digest.
The service could fail before verification; no remote run has tested it.

EXP-1359 locally addressed that classic-store runtime gap with a fixed
BrainBooster-only adapter. The one-shot launcher now checks only the exact
config image ID and `linux/amd64` via a Docker inspect before each
container run, runs by that config ID, and rebinds to the pinned manifest/code
identity only after the existing verifier returns its config-bound result.
There is no tag or caller-selected alias fallback. The host-bundle builder now
follows the launcher's static package imports, so its extracted launcher
imports successfully. Five focused adapter tests, seven launcher tests (two
skipped), sixteen bundle tests and the full offline suite (1,826 tests, 25
skipped) passed. Two in-memory builds matched at
`sha256:40ceed704632b41b0e9a170e170e0e4b78aefe60ea60f5378458dfd46c1b16b2`
(33 source members, 545,538 source bytes). The config-to-manifest bridge is a
Control Plane inference from EXP-1349/1350 evidence, not host attestation.
No real Docker invocation, testdev service, verifier request, key, enrollment
or host-trust decision occurred. R2/MVP remain OPEN.

EXP-1360 subsequently audited the exact 33-member in-memory archive: two
builds matched byte-for-byte, all manifest names/sizes/SHA-256 matched source
members, and the member set was exactly EXP-1301's 31 accepted names plus
the public image-pin module added in EXP-1358 and the fixed classic-store
adapter added in EXP-1359. Review found no new concrete credential reader,
secret-bearing path, dynamic image alias or provider capability in the changed
files. Sixteen bundle tests and `git diff --check` passed. This is local source
evidence only, not a deployment authorization or verifier-host trust decision.

EXP-1361 hardened the inspect path to use the tested streaming collector:
stdout is capped at 256 bytes, stderr at 4,096 bytes, and the child deadline is
15 seconds with kill/reap on cap or timeout. Synthetic tests assert one exact
Popen, pipes, sanitized environment and failure before container invocation.
The full offline suite passed 1,826 tests (25 skipped). Two in-memory builds
matched at
`sha256:63813cbc6666e543c6b15250631f94689242fd04113c0a544126d2d868b03a86`
(33 members, 545,795 source bytes); all manifest names, sizes and hashes match,
and names equal the prior audited 31-member set plus the two fixed public
modules. This supersedes the EXP-1359/1360 archive digest. No Docker or remote
operation occurred. Local dirty-worktree evidence only; R2/MVP remain OPEN.

EXP-1362 added an import-inert local CLI to stream this pinned source bundle
once. Before opening SSH it rebuilds in memory and requires the reviewed
archive digest, byte size, member count and source-byte count. EXP-1363 was
authorized separately and returned `BUNDLE_TRANSFER_CONFIRMED` after the
receiver validated the archive digest, canonical manifest and every source
hash, then created only the unique target directory with files mode 0600. No
follow-up SSH, Docker, service launch or verifier request occurred. The next
remote preflight needs a new exact card and fresh confirmation. Host trust and
R2/MVP remain OPEN.

Local Control Plane result (2026-10-16): EXP-1340's bounded inspect requesting
both `.Id` and `.Descriptor.Digest` failed before saving. EXP-1341 independently
reported `containerd_snapshotter=true`, but the same descriptor-formatted inspect
returned a fixed failure marker without raw diagnostics. EXP-1342 then queried
only `.Id` and returned `LOCAL_IMAGE_ID_CONFIRMED`, establishing that the exact
pin remains addressable locally; it does not identify the descriptor digest or
explain the template failure. EXP-1343 used `{{json .Descriptor}}` and returned
`LOCAL_DESCRIPTOR|present=true|digest_matches_pinned_id=true`. The local image
ID therefore equals its descriptor digest, consistent with Moby's containerd
backend implementation. This supports, but does not prove, a cross-backend
identity mismatch: the pinned local ID may be a manifest digest while a classic
image store identifies the loaded image by config digest. The exact config
digest has not yet been emitted. No archive save or remote action occurred in
EXP-1340—1343. EXP-1344 is limited to one local save and emission of that public
content digest plus bounded layer checks. Remote exact-ID presence remains
absent per EXP-1334; R2/MVP remain OPEN.

Batch AAK / EXP-1230 added a fresh one-shot local-Ollama CLI identity and made
the credential-free choice explicit as `--credential-source not-applicable`.
Local mode continues to pass no credential source, construct no keyring/env/
terminal source and emit `credential_input=none`; DeepSeek rejects
`not-applicable`. The focused CLI suite passed 37 tests; the full offline suite
passed 1,702 tests with 25 skipped. No model, network, Docker, credential or
external action occurred. This only prepares a new local run; it is not Worker
evidence. R2/MVP remain OPEN.

Batch AAL / EXP-1231 made one anonymous verified-TLS `/rate_limit` request and
returned `READINESS|200|35|1791988401` (exit 0), reset
2026-10-14 17:33:21 Europe/Moscow. Remaining 35 is below the required 36, so no
snapshot, Ollama process or model call was made. No response body or credential
was read. A fresh post-reset readiness result is required before any new
public-snapshot Worker card is eligible. R2/MVP remain OPEN.

Batch AAM / EXP-1232 registered a distinct future profile EXP-1233 for one
credential-free local-Ollama attempt: exact phrase/process/task IDs, public
snapshot origin and `local-ollama` backend. Focused CLI suite: 37 passed; full
offline suite: 1,702 tests, 25 skipped, exit 0. No Worker, model, network,
Docker or credentials were used. EXP-1233 still requires its own execution card;
the latest quota gate is below threshold. R2/MVP remain OPEN.

Batch AAN / EXP-1233 used a fresh post-reset readiness result
`READINESS|200|60|1791992019`, matching local target/verifier images, and one
credential-free local-Ollama request against the pinned public snapshot. Target
tests returned `target-test-malformed-status`; no verifier PASS or verified stage
was established, approval was not created, and publication was not attempted.
Ollama was stopped and both experiment databases passed `quick_check=ok` at mode
0600. Candidate, source, model output, and raw test command/output were not read.
EXP-1233 is BLOCKED and will not be retried. Batch AAO / EXP-1234 then made one
anonymous GET of the pinned public `backend/routes.py` (HTTP 200): the save route
accepts a generic dict and applies direct `int(...)` conversions to five numeric
fields, with no explicit range/schema validation or conversion-error-to-422
mapping in that route. EXP-1235's local source trace found that the fixed probe
expects HTTP 422 for booleans, fractions, numeric strings, and signed-64-bit
overflow, and the safe marker mapper projects an invalid-case status mismatch to
`target-test-malformed-status`. This narrows the failure to an invalid-input
status mismatch but does not reveal which case failed because candidate code
was not read. EXP-1236 clarified the Worker task instruction to require JSON
integer tokens without coercion and added prompt contract assertions; focused
CLI tests passed (37), full suite passed (1,702, 25 skipped), and scoped
`git diff --check` passed. EXP-1237 registered distinct profile
`RUN EXP-1238 ONCE` / `process-exp-1238-local-001` /
`task-exp-1238-local-001`; synthetic CLI coverage confirms `local-ollama`,
`pinned-docker`, `restricted-container`, and `not-applicable` with zero
credential lookups. Focused suite passed 38 tests; full suite passed 1,703 with
25 skipped; scoped `git diff --check` passed. AAT / EXP-1239 refreshed the six
R2 exit-matrix gates to current evidence on 2026-10-14 without promoting any
synthetic or failed result. Through AAT: 39 batches, 29 accepted, 8 blocked,
1 superseded, 1 draft. AAU / EXP-1240 confirmed the local Ollama channel and
restricted Worker perform at most one model request, with no retry after
connection/HTTP failure; a fake connection-failure regression passed. EXP-1238
remains gated on the quota reset/readiness result. Independent verifier trust,
authenticated digest-bound approval, recovery, and controlled PR remain
unproven. AAV / EXP-1241 refreshed section-10 criteria 1, 2, 7, 10, and 13 with
the bounded EXP-1233 outcome; criterion 16 is unchanged. AAW / EXP-1242 records
the canary scan included in EXP-1229's current-pin synthetic composition.
Through AAW: 42 batches, 32 accepted, 8 blocked, 1 superseded, 1 draft.
EXP-1243 makes Python's exact-integer type check and pre-write signed-64
bounds explicit in the Worker task instruction; focused and full offline suites
passed. Through AAX: 43 batches, 33 accepted, 8 blocked, 1 superseded,
1 draft. AAY / EXP-1244 pins the Worker CLI and contract-test source hashes in
EXP-1238 for reproducibility. Through AAY: 44 batches, 34 accepted, 8 blocked,
1 superseded, 1 draft. EXP-1245 adds a profile-level regression proving the
EXP-1238 runtime Worker receives the pinned strict-integer contract; the test
source fingerprint is refreshed in its card. Through AAZ: 45 batches,
35 accepted, 8 blocked, 1 superseded, 1 draft. EXP-1238's post-reset readiness
returned HTTP 200 with remaining 35 (<36); no service, snapshot, model or Worker
ran, and that one-shot card is spent. EXP-1246 registers a fresh credential-free
profile. Through ABA: 46 batches, 36 accepted, 9 blocked, 1 superseded. EXP-1247
passed one fresh readiness gate but failed target tests with
`target-test-malformed-status`; run `run-fe793efd813b45fa859eeaf9ea615cc0`,
cursor 74, partial. Ollama was stopped; both DBs are `quick_check=ok`, mode
0600. Through ABB: 47 batches, 36 accepted, 10 blocked, 1 superseded, 0 draft.
EXP-1248 refreshed affected criteria and the R2 matrix with the bounded EXP-1247
failure; no candidate output was read and no event/checkpoint count was inferred.
Through ABC: 48 batches, 37 accepted, 10 blocked, 1 superseded, 0 draft.
EXP-1249 now gives the Worker explicit per-field invalid classes, HTTP 422
before DB access, and exact valid/invalid row outcomes; EXP-1250 is a fresh
profile. Focused suite: 40 passed; full offline suite: 1,706 tests, 25 skipped.
Through ABD: 49 batches, 38 accepted, 10 blocked, 1 superseded, 0 draft.
EXP-1251 passed its post-reset readiness gate (`READINESS|200|60|1791999646`)
and made one exact-gated local-Ollama request against the pinned snapshot. Target
tests failed with `target-test-malformed-status`; run
`run-5cde42df8f474fa39d3dcb188b1ed096`, cursor 74, partial. No verifier PASS,
verified stage/readback, approval or publication. Candidate/source/model output
was not read; owned Ollama was stopped and the listener is absent. Both DBs
returned `quick_check=ok`, mode 0600. EXP-1251 is BLOCKED and not retried.
Through ABE: 50 batches, 38 accepted, 11 blocked, 1 superseded, 0 draft.
Batch ABF / EXP-1252 adds finite field/class/phase detail to the target-probe
failure marker without changing the oracle or exposing candidate/model output.
The verifier source change invalidated the old image pin; image
`sha256:ada0c0c0bc91e418582231a002e90b3bf1a3cdeaa52efc43cd2ee2c946940959`,
code digest
`sha256:2c1cdcc3dd64132e04f8a626ca7c2e5e0ab254363e657a5add9a11075af1e0db`,
was rebuilt offline and inspected as `linux/amd64`; two synthetic container
tests passed. Focused suites: 103 tests, 8 skipped; pinned target-contract suite:
10 tests, 1 skipped; full offline suite: 1,706 tests, 25 skipped; `git diff
--check` passed. Through ABF: 51 batches, 39 accepted, 11 blocked, 1 superseded,
0 draft. Historical EXP-1233/1247/1251 aggregate failures remain unlocalized;
R5 stays closed as preregistered, R2/MVP remain OPEN.
Batch ABG / EXP-1253 registered a distinct one-shot local profile with
`RUN EXP-1253 ONCE`; focused suite: 41 passed, full suite: 1,707 tests,
25 skipped, and scoped `git diff --check` passed. EXP-1254 passed exact image,
profile and database preflights; its sole readiness result was
`READINESS|200|35|1791999670`. Below 36, so no Ollama, snapshot or model ran;
the one-shot card is BLOCKED and not retried. Through ABG: 52 batches,
39 accepted, 12 blocked, 1 superseded, 0 draft.
Batch ABH / EXP-1255 registered a distinct post-gate local profile; focused
suite 42 passed, full suite 1,708 tests / 25 skipped, `git diff --check` passed.
EXP-1256 passed readiness (`READINESS|200|60|1792003470`) and made one local
model call. The new bounded marker was `target-test-malformed-status-level-bool`
for the `level=true` case expecting HTTP 422; run
`run-0d35d6f0298642088ab531bf51abad69`, cursor 74, partial. No candidate output
was read; no verifier PASS, stage/readback, approval or publication. Ollama
stopped, listener absent, both DBs `quick_check=ok`, mode 0600. EXP-1256 is
BLOCKED and not retried. Through ABH: 53 batches, 39 accepted, 13 blocked,
1 superseded, 0 draft.

Batch ABI / EXP-1257 registers a fresh credential-free local profile and
includes only the bounded EXP-1256 `level=true` → HTTP 422 diagnostic in the
task prompt. Tests confirm exact profile and prompt wiring, restricted worker,
and zero credential lookups: focused suite 43 passed; full suite 1,709 tests /
25 skipped; `git diff --check` passed. Source hashes are pinned in the task
card. EXP-1258 is READY for exactly one post-reset anonymous readiness gate
after 2026-10-14 21:44:30 Europe/Moscow; a miss stops before daemon/snapshot/model
with no retry. Through ABI: 54 batches, 39 accepted, 13 blocked, 1 superseded,
1 ready, 0 draft. R2/MVP remain OPEN.

Batch ABK / EXP-1260 registers a fresh transfer confirmation profile after the
spent EXP-1225 gate. Synthetic tests prove stale/wrong phrases dispatch no
transfer and the exact `RUN EXP-1261 ONCE` phrase dispatches the mocked runner
once. Focused suite: 13 passed; full suite: 1,710 tests / 25 skipped;
`git diff --check` passed. Corrected runner/test hashes and the exact EXP-1261
scope are pinned in the task card. At the ABK checkpoint EXP-1261 was DRAFT;
the later one-shot outcome is recorded below. Through ABK: 56 batches, 40
accepted, 13 blocked, 1 superseded, 1 ready, 1 draft. R2/MVP remain OPEN.
EXP-1261's local read-only exact image inspect then confirmed the pinned ID,
sole tag, `linux/amd64`, size and nine ordered DiffIDs; no remote query was made.

Batch ABL / EXP-1262 built the current verifier-host source bundle twice,
sequentially, with archive stdout discarded. Both bounded metadata reports
matched: digest `sha256:5dffc70360b50678b5ee722cc05f5fb6bfa9384dde6ffb82f240f012ed76ae8d`,
81 members, 1,282,712 source bytes. No archive file, SSH or network operation
occurred. This is a reproducibility pin only, not remote-host or service-trust
evidence. Through ABL: 57 batches, 41 accepted, 13 blocked, 1 superseded,
1 ready, 1 draft. R2/MVP remain OPEN.
EXP-1258's local pre-reset preflight on 2026-10-14 20:52:31 Europe/Moscow
matched both exact `linux/amd64` image pins; the verifier closure/digest test
passed; Ollama client 0.40.3 is installed, no listener is running, and both
new DB paths are absent/non-symlinks. No quota request, daemon, snapshot, model
or Worker ran.

Batch ABM / EXP-1263 reconciles the R2 exit matrix to evidence through ABL.
The matrix distinguishes the local transfer fix and source-bundle pin from
remote import/service readiness, and records EXP-1258's single pending quota
gate, latest Worker failure, and absence of verified stage/approval/real PR.
No evidence was upgraded to independent-host trust. Through ABM: 58 batches,
42 accepted, 13 blocked, 1 superseded, 1 ready, 1 draft. R2/MVP remain OPEN.

Current Control Plane update (2026-10-14): EXP-1258's sole readiness request
returned `READINESS|200|35|1792003499`, below the required 36; it stopped before
daemon, snapshot, model or Worker. After fresh exact user authorization,
EXP-1261 ran once through its visible gate and emitted `REMOTE_INSPECT_FAILED`
(exit 16). The exact remote image tuple is unconfirmed; the image may have been
imported. No retry, remote diagnostic or cleanup was run. Current ledger: 58
batches, 42 accepted, 15 blocked, 1 superseded, 0 ready, 0 draft. R2/MVP remain
OPEN.

Control Plane update (2026-10-15): EXP-1264 added a separately gated,
read-only, one-SSH exact-image inspector with bounded markers and fake tests.
Focused tests: 5 passed; full offline suite: 1,715 tests / 25 skipped;
`git diff --check` passed. It was not run against testdev. EXP-1265 is DRAFT
pending fresh exact authorization for one read-only inspect; no remote image
identity is established. Current ledger: 60 batches/cards, 43 accepted, 15
blocked, 1 superseded, 0 ready, 1 draft. R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1266 registered a fresh one-shot
profile for the existing restricted-container local-Ollama Worker path, keeping
the exact numeric-validation prompt and acceptance oracle unchanged. Focused
CLI suite: 44 passed; full offline suite: 1,716 tests / 25 skipped;
`git diff --check` passed. No model or snapshot request ran. EXP-1267 is
prepared for one public pinned-snapshot attempt, contingent on exact preflight
and a single anonymous readiness response with remaining >=36. Current ledger:
62 batches/cards, 44 accepted, 15 blocked, 1 superseded, 0 ready, 2 draft.
R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1267 passed one anonymous readiness gate
(`READINESS|200|60|1792082595`) and verified the exact public commit/tree/content
digest, then its sole restricted local-Ollama Worker attempt failed the first
target probe: `target-test-malformed-status-level-bool`. The observed value was
not echoed or persisted in evidence; no verifier or stage was reached, approval
was not created, and publication was not attempted (`external_write=false`).
Observer run `run-3b6bad10579d4a8697aaab7fd0c09c20` is partial through cursor 74;
both SQLite files passed `quick_check` and mode 0600 checks. The owned Ollama
process stopped and left no listener. No retry. At this checkpoint: 62
batches/cards, 44 accepted, 16 blocked, 1 superseded, 0 ready, 1 draft.
R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1268 sharpened the fail-fast Worker
instruction with an explicit type/range validation order and registered a new
one-shot profile. Focused CLI suite: 44 passed; full suite: 1,716 tests,
25 skipped; `git diff --check` passed. No model call ran. EXP-1269 remains DRAFT
until the next recorded GitHub rate reset (`1792082595`, 2026-10-15 19:43:15
Moscow). Current ledger: 64 batches/cards, 45 accepted, 16 blocked,
1 superseded, 0 ready, 2 draft. R2/MVP remain OPEN.

Control Plane preflight (2026-10-15 18:56 MSK): EXP-1269's exact local
preflight passed (12 transport tests, 1 pinned-command contract test, both
exact Docker image IDs/platforms, Ollama client 0.40.3 with no listener, both
database paths absent, scoped diff check clean). The scheduled rate reset had
not occurred, so the card remains DRAFT; no readiness request, daemon, snapshot
or model call ran.

Control Plane recheck (2026-10-15 19:15 MSK): the exact local transport and
pinned-command contract suites passed again (12 and 1 tests); both current image
IDs/platforms matched (`linux/amd64`), Ollama reported client 0.40.3 with no
running server/listener, both EXP-1269 database paths remain absent, and
`git diff --check` passed. Reset `1792082595` was still in the future. No
readiness request, daemon, snapshot or model call ran; EXP-1269 remains DRAFT.

Control Plane regression revalidation (2026-10-15 19:21 MSK): the standard
offline suite passed on the current worktree (1,715 tests, 25 skipped). No
network, Docker, Ollama, model, provider or publication action ran; this is
regression evidence only.

Control Plane update (2026-10-15): EXP-1270 consolidated the repeated Worker
numeric-validation prompt into one ordered helper recipe without changing the
acceptance matrix. Focused CLI tests: 44 passed; full offline suite: 1,716 tests,
25 skipped; `git diff --check` passed. No model call ran. EXP-1269 is still
DRAFT pending reset `1792082595` and exact preflight. Current ledger: 65
batches/cards, 46 accepted, 16 blocked, 1 superseded, 0 ready, 2 draft.
R2/MVP remain OPEN.

Batch ABJ / EXP-1259 removes an unnecessary dependency on Docker CLI prose from
the verifier-image transfer runner: after successful `docker image load`, it
discards output and accepts only an exact remote inspect tuple (image ID,
platform, size, ordered DiffIDs, empty RepoTags). Fake tests cover six load
output variants, failed load before inspect, exact inspect mismatch and redacted
no-retry behavior. Focused suite: 11 passed; full suite: 1,708 tests / 25
skipped; `git diff --check` passed. No SSH or live transfer ran; EXP-1225's
remote state is still unknown and its one-shot remains spent. Through ABJ: 55
batches, 40 accepted, 13 blocked, 1 superseded, 1 ready, 0 draft. R2/MVP remain
OPEN.

Batch AAS / EXP-1238 is BLOCKED: its one post-reset readiness marker was
`READINESS|200|35|1791992064`, below the required 36. No daemon, snapshot,
model or Worker ran; its one-shot card is not retried. Exact target/verifier
image IDs and `linux/amd64` were confirmed locally; the verifier-context digest
test passed; Ollama client is 0.40.3. Batch ABA / EXP-1246 registers a new
credential-free profile with its own one-shot phrase and explicit prompt wiring.
Batch ABB / EXP-1247 passed readiness `READINESS|200|60|1791996011`, made one
restricted local model request on the exact snapshot, then failed target tests
with `target-test-malformed-status`. No verifier PASS, verified stage/readback,
approval or publication occurred. Observer run `run-fe793efd813b45fa859eeaf9ea615cc0`
is partial through cursor 74; its candidate/source/model output was not read.
The owned Ollama process is stopped; both DBs passed `quick_check=ok`, mode
0600. This does not establish independent verifier trust. R2/MVP remain OPEN.

EXP-1243 further clarifies the EXP-1238 task instruction: Python `bool` is a
subclass of `int`, so the requested exact check is `type(value) is int`, not
`isinstance`; signed-64 bounds must be checked before a database call, and
existing defaults for omitted fields must be preserved. This is preventive
prompt precision only; EXP-1233's precise failing input remains unknown because
candidate output was not read. Focused CLI suite: 38 passed; full offline suite:
1,704 tests, 25 skipped, OK. No model or external action occurred. R2/MVP remain
OPEN.

Batch ZG / EXP-1200 attempted one current-pin local Ollama Worker run after its
preflight and exact one-shot gate. The runner stopped at
`github-readiness-ineligible` (`provider_attempts=0`, observer cursor 4,
partial run); no repository snapshot, model inference, Worker, target test or
verifier ran. The one owned loopback Ollama server was stopped. The observer DB
passed integrity check and was retained at mode 0600; no stage DB was created.
EXP-1200 is exhausted and will not be retried. This leaves the previous
EXP-990 composition as the strongest successful local Worker evidence; R2/MVP
remain OPEN. EXP-1201 addresses secure creation permissions for new local
observer/stage SQLite files. Any change to the observer store also changes the
verifier source-context digest, so the current verifier image must be rebuilt
and revalidated under a separate card before it can be used again.

Batch ZH / EXP-1201 created new writable observer and stage SQLite databases
exclusively with POSIX mode 0600 before SQLite opens them. Reopening preserves
existing file modes; no existing evidence DB was chmod-ed. Focused store tests:
76 passed; verifier source-context digest test: 1 passed; full offline suite:
1,699 tests, 25 skipped, OK; scoped `git diff --check` passed. The declared
verifier context digest is now
`sha256:c1f02c1f6548c6edf1f3d6ea0bdb5ead061d25c0c38efbfbcfc801f7eea18135`,
while image `sha256:f9cf14612cd0632eb20e42d6a78f91e7b1b73b09d7947c2edd67fc23e9dfcbc2`
was built for the previous digest and must not be used until rebuilt and
revalidated. Existing permissive databases are not repaired; Windows ACL
privacy remains unverified. No Docker, network, SSH, credentials, live model,
provider, approval, publication or commit was used. R2/MVP remain OPEN.

EXP-1202 then built one local verifier image offline from the exact target
runtime and updated source closure; the helper returned image
`sha256:49a7d7d14e0545069be45246d5184e3547d50a3a5fae521f17d433b4ea89bb14`
and the expected context digest
`sha256:c1f02c1f6548c6edf1f3d6ea0bdb5ead061d25c0c38efbfbcfc801f7eea18135`.
Its single post-build inspect command failed at Docker template rendering, so
image platform/size/tag remain unverified, the profile remains on the old image
ID, and no container ran. No retry or cleanup occurred; EXP-1203 is a separate
read-only inspection of only this exact image ID. R2/MVP remain OPEN.

EXP-1203's corrected single read-only inspect confirmed that rebuilt image as
`sha256:49a7d7d14e0545069be45246d5184e3547d50a3a5fae521f17d433b4ea89bb14`,
`linux/amd64`, 48,850,700 bytes, sole tag
`agent00x-verifier-exp466:036dbb36501340cc8e3957e4506c0d04`. The profile now
binds this image to source-context digest
`sha256:c1f02c1f6548c6edf1f3d6ea0bdb5ead061d25c0c38efbfbcfc801f7eea18135`.
Runtime tests have not yet run; EXP-1204 is prepared for two synthetic,
network-none container cases only. No external action occurred.

EXP-1204 then passed exactly two opt-in synthetic verifier-container tests on
the refreshed image in 1.209 seconds. Assertions cover UID 65532, read-only
root, absent Docker socket, network-none execution and a 220,064-byte synthetic
snapshot. This is current same-host runtime evidence only; no target repository
or independent host was used. The transfer pin was subsequently refreshed in
EXP-1205; any remote import still requires a fresh exact card and user
authorization.

EXP-1205 refreshed `scripts/stream_pinned_verifier_image.py` to the rebuilt
image and fake-tested the transfer contract. The pin binds the exact image ID,
sole tag, platform, size, nine ordered layer DiffIDs, and a 48,864,256-byte
memory-only stream guard. Focused fake-runner suite: 12 passed; full offline
suite: 1,699 tests, 25 skipped, OK. The real transfer runner was not invoked.
EXP-1206 is DRAFT for one exact image-store import to `alex@192.168.88.101` and
requires fresh user authorization for the current image; previous approvals
refer to other image IDs. No remote verifier trust, service, approval, or PR is
established. R2/MVP remain OPEN.

Batch ZP / EXP-1209 used a fresh local identity and the EXP-1203/1204 verifier
pin, but again stopped after one anonymous readiness request with
`github-readiness-ineligible` (`provider_attempts=0`, observer cursor 4). No
snapshot, local model inference, Worker, target tests or verifier ran. The
observer journal is mode 0600 and integrity-valid; no stage DB was created.
The owned Ollama process/listener is stopped. EXP-1209 is exhausted and not
retried. EXP-1210 is a single anonymous header-only readiness diagnostic; a
future Worker attempt is not prepared unless a bounded quota preflight passes.

EXP-1210 returned bounded marker `READINESS|200|10|1791984759`; the anonymous
GitHub core quota resets at 2026-10-14 16:32:39 Europe/Moscow. Remaining 10 is
below the preflight threshold, so no additional Worker/readiness attempt should
run before reset. EXP-1211 is a local offline synthetic-canary retest on the
refreshed verifier image and does not consume public quota.

EXP-1213 made one fresh anonymous header-only request at 2026-10-14 16:11
Europe/Moscow and returned `READINESS|200|10|1791984759` (exit 0). This was
before the reported 16:32:39 reset, so quota remained below the 36-request
eligibility threshold. No repository content or Worker request ran; any later
quota observation requires a separate card after reset.

EXP-1215 ran the standard offline suite against the current worktree:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` returned
0 with 1,699 tests in 80.611 seconds and 25 skipped. This is local regression
evidence only; it does not establish remote verifier trust, a current
public-snapshot Worker run, authenticated approval, recovery, or real PR
publication.

EXP-1216 corrected a readiness-policy mismatch: current task cards require at
least 36 anonymous GitHub requests remaining, while the runtime permit had
accepted 25. `src/app_contracts/worker_cli.py` now requires 36; regressions
prove 35 is denied and 36 accepted. Focused `tests.test_worker_cli`: 62 tests,
2 skipped. Full offline suite: 1,700 tests in 80.663 seconds, 25 skipped,
exit 0. EXP-1213's observed remaining=10 was still before reset; no Worker or
repository-content request was made. This raises the local quota guard but
does not itself create readiness or authorize a run.

EXP-1217 adds a fresh fixed CLI identity for the next local-Ollama attempt:
`RUN EXP-1218 ONCE`, process/task `process-exp-1218-local-001` /
`task-exp-1218-local-001`, snapshot origin `github_rest_api_claim`, backend
`local-ollama`. Focused CLI suite: 37 passed; full offline suite: 1,700 tests
in 80.832 seconds, 25 skipped, exit 0. No model call was made by EXP-1217.
EXP-1218 passed the post-reset local preflight and one fresh readiness gate,
then made exactly one successful loopback local-Ollama POST. The CLI returned
`remote-execution-pipeline-failed` (exit 1), run
`run-15ae81252ff042fc98aa0abafdc6d082`; the redacted observer report is partial
(75 events/37 checkpoints) and indicates a `tool_failed` event at cursor 72.
Observer/stage DBs have mode 0600 and `quick_check=ok`; owned Ollama is stopped
and listener absent. Target-test PASS, current verifier PASS and a verified
stage were not established; no retry is permitted. EXP-1218 is BLOCKED, and
an allowlisted read-only query classifies the failed event as
`sandbox-command-nonzero`; the exact command identity/output and verifier status
remain unknown. No candidate/source/model content was read. EXP-1219 accepted
this bounded diagnosis without retrying the run. EXP-1220 queried only the
allowlisted action label at cursor 72 and returned `FAILED_ACTION|unclassified`;
the query was not broadened and no payload or stage database was read. A
separate immutable query correlated the failed terminal event with its exact
causal request by event ID, run and adjacent sequence; the fixed action label
was `SandboxSession.run.target-tests`. The target-test command and output were
not inspected, so its cause remains unknown; EXP-1218 is not retried. The
At the preceding AAB checkpoint, series ZH–AAB had 21 batches: 17 accepted,
3 blocked and 1 DRAFT (EXP-1206 authorization).

EXP-1222 added a typed target-test failure carrying only one fixed category from
the existing safe marker allowlist. The executor maps it to an exact finite
`target-test-*` code; CLI evidence still rejects unrecognized values and never
includes child output. EXP-1223 refreshed the verifier closure pin after those
code changes and rebuilt the local image offline: image
`sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`,
`linux/amd64`, 48,850,944 bytes; code digest
`sha256:5227a5cfa1c4da78ff9f62809a6f7737c5d6d5a8a6e3e562ec9993e6fa533e5e`.
Two synthetic verifier-container tests passed. Focused suites passed (41
repository-process, 71 executor, 63 CLI / 2 skipped); full offline suite passed
1,702 tests / 25 skipped. EXP-1218 was not retried; the new category code has
not yet been observed on a fresh Worker run. The prior EXP-1206 remote-import
card referred to the previous image ID and does not authorize transfer of this
rebuilt image; it is now SUPERSEDED. EXP-1224 refreshed the fake-tested transfer helper to the new
ID, tag, nine ordered DiffIDs and 48,864,768-byte in-memory stream; 12 fake
tests and the full suite passed. The runner was not invoked. EXP-1225 is a new
exact-image import DRAFT awaiting fresh user authorization. Current series
ZH–AAF: 25 batches, 20 accepted, 3 blocked, 1 SUPERSEDED, 1 DRAFT (EXP-1225).

The older R2 exit-matrix rows below retain their dated historical pins. For
current image status, EXP-1203/1204 supersede EXP-1191/1192; EXP-1198's
end-to-end composition used the previous verifier source pin and has not been
repeated against the EXP-1201/1203 closure. EXP-1211 repeated the local
synthetic credential-canary composition on the refreshed verifier and passed
in 2.921 seconds after exact image/platform and source-digest preflight. It
scanned the listed output, SQLite, approval/trust/report and receipt surfaces;
the receipt still states `external_write=false` and
`identity_authenticated=false`. This is same-host synthetic evidence only,
not the public-snapshot/live-Worker composition or independent remote trust.

Этот документ отвечает на вопрос «что существует и что подтверждено сейчас».
План работ находится в [документе 24](24-mvp-final-plan.md); замысел широкого
продукта — в документах 00 и 23. При расхождении этот документ имеет приоритет
для утверждений о реализации и проверках.

Control Plane update 2026-10-14, Batch XR / EXP-1056: свежий локальный
preflight совпал со всеми pin-значениями; после точного gate
`RUN EXP-1056 ONCE` выполнен один импортный запуск через guarded runner.
Результат — `REMOTE_INSPECT_FAILED` (exit 16): `docker image load` принял
ожидаемый tag, но последующий inspect exact image ID не подтвердил metadata.
Следовательно, образ мог попасть в Docker image store testdev, но его
удалённая идентичность не доказана. Повторов, второго SSH, диагностики и
cleanup не было; локальные файлы/commit не изменялись. EXP-1056 BLOCKED;
продолжение на testdev требует отдельной точной карточки и разрешения.
Service readiness, независимый verifier trust, authenticated approval,
controlled publication и MVP этим результатом не установлены; R2/MVP остаются
OPEN.

Control Plane update 2026-10-14, Batch YM / EXP-1180: `git diff --check`
прошёл; gate был введён, но до SSH обнаружена неоднозначность двойного
экранирования `printf`. OpenCode предложил отличающуюся от карточки команду;
Control Plane отказал её shell permission. Ни SSH, ни Docker, ни удалённый
запрос не выполнялись. Gate израсходован; EXP-1180 BLOCKED. Batch YN / EXP-1181
подготовлен как новая read-only проверка с newline-free fixed markers; её
preflight и gate ещё не выполнены. Удалённая metadata, readiness и verifier
trust остаются неподтверждёнными.

Control Plane update 2026-10-14, Batch YN / EXP-1181: gate
`RUN EXP-1181 ONCE` был введён Control Plane; выполнена одна read-only SSH
проверка точного verifier tag. Результат — `PINNED_TAG_METADATA_MISMATCH`:
Docker разрешил tag, но tuple image ID/OS/architecture/size отличается от
ожидаемого локального pin. Полные фактические metadata не выводились. OpenCode
shell UI добавил локальные `echo` после SSH, поэтому показанный `EXIT=0` не
сохранил SSH exit status; точный fixed marker остаётся bounded evidence, без
повтора или дополнительной диагностики. EXP-1181 закрыта с процедурным
отклонением; EXP-1056 import и точная удалённая identity остаются
неподтверждёнными. Image mutation, service readiness, independent verifier
trust, approval/publication и MVP этим не подтверждены; R2/MVP остаются OPEN.

Control Plane update 2026-10-14, Batch YO / EXP-1182: после `git diff --check`
(exit 0), точного gate `RUN EXP-1182 ONCE` и одноразового shell permission
выполнена одна read-only SSH-инспекция ровно заданного verifier tag на
`testdev`. Получена bounded tuple
`sha256:b39a3df140d9e00a5dc31f2ef53629c1f52c397aa414314be6cd052ebf0851c6|linux|amd64|135701718`;
ожидался локальный pin
`sha256:321c268a841de8cc354125ae25113b38835208f0e0f766f443514b63f1167b0c|linux|amd64|48849495`.
Tag разрешается в иной image ID и размер; локальный pin на testdev не
подтверждён. Команда выполнена один раз без локальных echo/обёрток; вывода
ошибки инструмента не было, отдельный числовой SSH exit status не записан.
Повторов, диагностики, импорта или иных remote changes не было. Это не
подтверждает provenance, verifier service/readiness, independent trust,
approval/publication или MVP; R2/MVP остаются OPEN.

Control Plane update 2026-10-12, Batch VA / EXP-980: пять pinned preflight
прошли; после точного видимого gate `RUN EXP-980 ONCE` Control Plane разрешил
один запуск guarded runner. Он вернул `REMOTE_INSPECT_FAILED` (exit 16). По
контракту runner это означает, что удалённый `docker image load` завершился
успешно, но последующая инспекция не подтвердила точные pinned metadata.
Следовательно, image мог попасть в image store testdev, но точная удалённая
идентичность не подтверждена. Никаких повторов, cleanup, диагностики или
второго SSH не было; карточка BLOCKED. Не выполнять новую запись или удалённую
проверку без отдельной карточки и gate. Это не доказывает запуск verifier,
trust, approval/publication chain или достижение MVP.
До карточных preflight OpenCode также выполнил локальные read-only
`git status`/`git log` и поиск/чтение карточек; эти действия не меняли файлы
или remote. Для следующего шага подготовлена отдельная read-only карточка
EXP-981: один exact-image inspect на testdev; до её выполнения текущее наличие
образа и последующая verifier-service/trust chain остаются неподтверждёнными.

Control Plane update 2026-10-12, Batch VB / EXP-981: `git diff --check` прошёл;
после точного видимого gate `RUN EXP-981 ONCE` выполнена ровно одна разрешённая
read-only SSH-команда. Вывод — только `PINNED_IMAGE_INSPECT_FAILED` (exit 0),
один из fixed outcomes карточки. Docker CLI и daemon отвечают, но exact
`docker image inspect` не подтвердил pinned metadata. Маркер не различает
отсутствие image и другую причину сбоя inspect; наличие/отсутствие образа не
утверждается. Файлы и remote state не менялись; повторов и диагностики не было.
EXP-981 принят как ограниченная диагностика, не как доказательство отсутствия
образа. Подготовлена новая независимая read-only карточка EXP-982: проверить
только точное членство image ID в bounded Docker image list, без вывода списка
и без иных remote-операций. Ни эта карточка, ни результат EXP-981 не доказывают
service readiness, независимый trust, approval/publication или MVP; R2/MVP
остаются OPEN.

Control Plane update 2026-10-12, Batch VC / EXP-982: единственный local
preflight `git diff --check` прошёл; после точного видимого gate
`RUN EXP-982 ONCE` выполнена ровно одна разрешённая read-only SSH-команда.
Вывод — только `EXACT_IMAGE_ID_NOT_LISTED` (exit 0): pinned ID не перечисляется
в Docker image list на testdev. Это не устанавливает причину ошибки inspect из
EXP-981; полный список ID не раскрывался. Файлы executor и remote state не
менялись; повторов, диагностики и дополнительных подключений не было. Карточка
принята как ограниченная диагностика. Metadata/content образа, service
readiness, независимый trust, approval/publication и MVP остаются
неподтверждёнными; R2/MVP остаются OPEN. Новая удалённая проверка или изменение
testdev требует отдельной карточки и свежего gate.

Подготовлена Batch VD / EXP-983 (R2 local batch #498): уточнить локальный
fail-closed transfer runner, чтобы он не считал успешный exit `docker image
load` достаточным, а продолжал к exact-ID inspect только при точном совпадении
вывода загрузки с закреплённым image ID. Задача ограничена runner и его offline
fake-runner tests; Docker, SSH, network и testdev запрещены. Это адресует
неоднозначность `REMOTE_INSPECT_FAILED` из EXP-980 и исторически наблюдавшееся
несовпадение ID при загрузке; live-передача потребует отдельной карточки и
нового точного подтверждения.

Control Plane result 2026-10-12, Batch VD / EXP-983: принят после локальной
реализации и независимой проверки. Runner сравнивает полный stdout `docker
image load`, включая единственный завершающий LF, с закреплённой строкой до
exact-ID inspect; mismatch выдаёт только `REMOTE_LOAD_IDENTITY_UNCONFIRMED`.
Offline shell-fake tests покрывают точный путь, wrong ID, дополнительную
строку, дополнительный пустой line, отсутствующий LF, load/inspect failure,
redaction и отсутствие повторов. Focused suite — 10 tests; полный suite — 1,518
tests (25 skipped); `git diff --check` чист. Docker, SSH, network и testdev не
запускались; commit не создавался. Это не доказывает удалённый image import,
service readiness, independent verifier trust, authenticated approval или PR;
R2/MVP остаются OPEN.

Актуальное обновление 2026-10-12: продолжение достигло Batch #489.
EXP-957/958/959/961 приняты; EXP-960 остановлен до snapshot/model на единственной
ошибке readiness fetch (без повтора). У карточки EXP-960 не был задан срок
действия; попытка не считается conforming external-read evidence. Полный
offline suite прошёл: 1,508 tests, 25 skipped.
EXP-959 повторил публичный pinned snapshot на текущих target/verifier pins с
synthetic Worker channel и local-mock receipt; это не заменяет EXP-851's
credential-free local-Ollama Worker run и same-host verifier evidence.
EXP-956 подтверждён точной фразой в OpenCode, но команда SSH-передачи была
заблокирована effective `external_directory` policy до запуска; SSH-сессий и
переданных байт — 0. Подтверждение потрачено, EXP-956 теперь BLOCKED; обход или
повтор не выполнялся. EXP-953 остаётся DRAFT. Независимый verifier trust,
authenticated digest-bound approval и controlled real PR отсутствуют; R2/MVP
остаются OPEN.
EXP-962 не запускался: инспекция OpenCode показала effective
`external_directory: * deny` (исключения — только внутренние tool-output и
temp-output пути). Project-local allow не переопределяет эту политику; фраза
`RUN EXP-962 ONCE` не предъявлялась и не израсходована. EXP-962 заблокирован.
EXP-963 добавил opt-in no-overwrite сохранение quiescent observer SQLite журнала
с digest и reopened event/checkpoint readback. Synthetic REST pipeline прошёл
полную цепочку до mock receipt и сохранил/перечитал 51 событие того же run;
реальный public snapshot retention run ещё не выполнялся. Полный offline suite:
1,508 tests, 25 skipped.
Batch #479 / EXP-964 добавил отдельный local-Ollama профиль и тесты его
привязки (focused CLI: 34 tests; полный suite повторно: 1,508 tests,
25 skipped). Попытка блокирована до live-authorization prompt: OpenCode не
может удержать требуемый foreground Ollama server с сессионным handle для
параллельной проверки модели/listener. Предложенный background/redirected
вариант отвергнут; server не запускался. Prompt `RUN EXP-964 ONCE` не
показывался и не вводился; GitHub readiness/snapshot, model, Worker и verifier
вызовы — 0. Изменения профиля/тестов локальные, без commit. Нужна новая карточка
с поддерживаемым foreground-session механизмом; обход или повтор по EXP-964
не разрешены.
Batch #480 / EXP-965 принят. После трёх успешных preflight OpenCode предъявил
точный prompt; Control Plane ввёл `RUN EXP-965 ONCE` в той же сессии. Публичный
pinned snapshot → synthetic restricted Worker → текущие pinned target/verifier
→ local-mock receipt завершился: 1 test, 25.279s, OK. Использовано 27 HTTPS
exchanges в лимите 28 (readiness 1, commit 1, tree 1, blobs 23, raw commit 1);
snapshot commit/tree/23-file digest совпали с pins. Receipt:
`external_write=false`, `identity_authenticated=false`, completeness `partial`;
staged digest `sha256:a6fbdc59e5121d6438124093cbe32df5a2f56d29b994e760c37ef9370c362341`.
No-overwrite observer copy содержит 95 событий и 47 checkpoints того же run,
151552 bytes, SHA-256
`0e43eeb257fe837a7be52d2036c989324f18b417907826855960ef43d4b661d1`;
Control Plane проверил read-only SQLite integrity (`ok`), файл mode 600.
Повторных запросов не было; source и stage DB не сохранялись. Артефакт
`EXP-965-observer.sqlite3` — локальный content-bearing файл, не коммитить; его
содержимое не сертифицировано как secret-free. R2/MVP остаются OPEN:
independent verifier trust, authenticated digest-bound approval и controlled
real PR не доказаны.
Batch #481 / EXP-966 остановлен как BLOCKED на последнем read-only preflight:
SSH DNS lookup сообщил `hostname testdev.local could not be resolved`. Три
предшествующие локальные preflight-команды прошли; prompt `RUN EXP-966 ONCE`
не показывался и не вводился, архив не создан, SSH-передача и удалённые
изменения — 0. Карточка запрещает retry и IP/alias fallback. Следующий шаг —
новая карточка с заранее проверенным разрешённым способом разрешения имени и
доступа к назначенной цели; сервис, listener, trust-enrollment и публикация
этим результатом не затронуты.

Batch #482 / EXP-967 BLOCKED на read-only mDNS preflight:
`/usr/bin/dns-sd -G v4 testdev.local` завершился `NO_MDNS_A_RECORD` (exit 1),
поэтому SSH не запускался; точный prompt/одноразовое подтверждение отсутствовали,
архив, передача и remote changes — 0. User-designated `.local` hostname и адрес
не менялись; нужен внешний client-side mDNS/DNS repair before verifier-host
setup can resume. Для read-only preflight 2–4 executor добавил вывод exit-кода;
до корректной инструкции были только `git status`/`git log` и поиск карточки,
а запрос `ls` был отклонён. Файлы не менялись. Полный offline suite после этой
проверки: 1,508 tests, 25 skipped, OK; внешние provider calls и testdev
operations из suite — 0.
Batch #483 / EXP-968 принят: `scutil --dns` показывает `resolver #2`, `domain: local`,
`Request A records`; launchd state projection выдала `MDNSRESPONDER_STATUS_UNAVAILABLE`;
`git diff --check` чистый. Batch #484 / EXP-969 также принят: локальный
`mDNSResponder` и membership группы `224.0.0.251` присутствуют, `git diff --check`
чистый. OpenCode до карточки сделал внеплановый read-only `git status`/`git log`;
первая команда 1 с дополнительным `echo` была отклонена и не выполнялась,
дословная повторная команда прошла. Никаких файлов/внешнего состояния не меняли.
Эти локальные маркеры не подтверждают объявление или достижимость `testdev`.
Batch #485 / EXP-970 принят: единственный TCP connect к назначенному
`192.168.88.101:22` вернул `TESTDEV_SSH_TCP_OPEN`; payload/SSH authentication не
отправлялись. Batch #486 / EXP-971 принят по одной прямой strict SSH-сессии
`alex@192.168.88.101`: pre-existing host key проверен строго, public-key auth
успешна, удалённая команда только `true`; `git diff --check` чистый. Файлы и
`known_hosts` не менялись. Процедурное отклонение: отдельный OpenCode permission
prompt в видимом окне не появился (предположительно, сохранилось разрешение
предыдущего запуска), поэтому нельзя утверждать, что был отдельный UI approval.
Перед следующим testdev SSH вызовом необходимо обеспечить наблюдаемое
одноразовое подтверждение; EXP-971 не повторять. Host identity/authentication
ещё не равны verifier enrollment или независимому trust. Batch #487 / EXP-972
принят: в новой OpenCode-сессии показан и однократно разрешён точный SSH prompt;
результат `PINNED_VERIFIER_IMAGE_ABSENT_OR_UNAVAILABLE`, `git diff --check`
чистый, image/host не менялись. Маркер не различает отсутствие образа и
недоступность Docker CLI/daemon. Batch #488 / EXP-973 принят: Docker CLI и daemon
на testdev доступны, точный verifier image отсутствует; `git diff --check` чистый,
других операций не было. Локальный inspect повторно подтвердил image ID
`sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`,
`linux/amd64`, size 51,052,429 bytes и девять pinned DiffIDs; `docker image save`
поток без файла — 51,071,488 bytes. Batch #489 / EXP-974 прошёл все четыре
read-only preflight: metadata и `51071488`-byte stream совпали с pins, strict
SSH вернул `EXACT_IMAGE_ABSENT`, `git diff --check` чистый. OpenCode предъявил
точный prompt `Type RUN EXP-974 ONCE to continue:`; shell permission prompts
для перечисленных проверок Control Plane разрешил ровно по одному разу.
Передача/import не выполнялись: для единственной записи image store всё ещё
нужна отдельная свежая точная фраза пользователя `RUN EXP-974 ONCE` в чате.
Independent verifier trust, authenticated digest-bound approval и controlled
real PR остаются открытыми; публикация не разрешена этим checkpoint.

Control Plane update, 2026-10-12: Batch UV / EXP-975 прошёл четыре read-only
preflight (pinned image metadata/DiffIDs exact, stream `51071488` bytes,
testdev `EXACT_IMAGE_ABSENT`, `git diff --check` clean). После видимого prompt
и ограниченной пользовательской делегации точная фраза `RUN EXP-975 ONCE` была
введена Control Plane один раз; post-confirmation stream/load команда была
разрешена в OpenCode один раз и исполнена один раз. Единственный видимый
bounded output: `Error response from daemon: No such image:
sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`.
Exit status в интерфейсе не показан; источник ошибки не классифицирован.
Повторной/диагностической команды и второго remote-вызова не было; состояние
image на testdev после попытки unknown. EXP-975 теперь BLOCKED, его одноразовое
подтверждение потрачено; не повторять. EXP-953 остаётся DRAFT. Следующее
продолжение требует отдельной новой карточки с ограниченной безопасной
идентификацией текущего remote image state до любой новой записи.
Это не подтверждает запуск verifier, независимый trust, digest-bound approval,
controlled PR или завершение MVP.

Batch UW / EXP-976, 2026-10-12: одна read-only SSH-команда в свежей OpenCode-
сессии вернула `EXACT_IMAGE_ABSENT` для точного pinned verifier image. OpenCode
не показал отдельный exit status. Команда была разрешена одноразовым shell
prompt, но Control Plane ввёл gate `RUN EXP-976 ONCE` уже после выполнения;
это процедурное отклонение, поэтому EXP-976 остаётся BLOCKED и не считается
conforming accepted card. Другой SSH-сеанс, диагностика и изменение состояния
не выполнялись. Фактическое наблюдение всё же показывает, что pinned image не
инспектировался как присутствующий на testdev на момент этой команды.
Отдельная Batch UX / EXP-977 была подготовлена как замена EXP-975: четыре
свежих preflight прошли; `RUN EXP-977 ONCE` был введён Control Plane до
единственной передачи/загрузки, а точный shell prompt разрешён один раз.
Post-command вернула bounded output `Error response from daemon: No such image:
sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`;
exit status и источник ошибки в интерфейсе неизвестны. `git diff --check`
прошёл с дополнительным безопасным status-print wrapper. Попытка остановлена
без повторов, удаления, диагностики или второго remote-вызова; image store на
testdev после неё unknown. EXP-977 теперь BLOCKED и её одноразовое подтверждение
израсходовано. Никаких дальнейших remote-проверок или записей не выполнять по
этой карточке. EXP-953 остаётся DRAFT; verifier service/trust, approval,
publication и MVP открыты.

Control Plane local regression check, 2026-10-12: after recording the EXP-977
bounded failure, the standard suite
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` passed:
1,508 tests, 25 skipped, 94.428s. `git diff --check` also passed. This is
local regression evidence only; it does not classify the EXP-977 error or prove
testdev image state, verifier service/trust, authenticated approval, controlled
PR publication or MVP completion.

Следующий последовательный transfer smoke подготовлен как Batch UR / EXP-953,
пока DRAFT до принятия EXP-974. Текущий fixed-allowlist host bundle дважды
собран идентично: `sha256:64769adc992eb20ececdd142904587c08563188ac407c0217c0f8df66e972977`,
76 members, 1,206,401 source bytes; no-file archive stream — 1,280,000 bytes.
Focused suite `tests.test_verifier_host_bundle`: 12 tests passed. Устаревший
digest в DRAFT заменён; передача на testdev не выполнялась.
Текущий DRAFT повторно прошёл exact expected-digest preflight: поток ровно
1,280,000 bytes; focused suite снова прошёл (12 tests), `git diff --check`
чистый. Архив не сохранялся; сеть/SSH не использовались.
Code inspection of `serve_ephemeral_signed_verifier_https.py` shows a one-shot
user-process design: it binds only `127.0.0.1` and generates TLS/signing private
keys in process memory. This may avoid root/systemd and persistent credentials
for a bounded verifier experiment, but the testdev Python/Docker runtime,
forwarded request, signed enrollment and independent-host trust have not been
verified; Batch UR's read-only preflight will test the first runtime prerequisites.
Trust bootstrap inspection: `SignedVerifierClient.from_trust_enrollment` also
requires a caller-pinned authority key set and a distinct authority-signed
host-trust decision bound to the enrollment digest, endpoint, verifier profile/
key, both host IDs and host-separation evidence. Generating an authority key
alongside the enrollment would be circular trust, not independent-host evidence.
No current non-synthetic authority-key source or OOB host-trust decision is
approved for this host; none was generated and no verifier request was made.

Control Plane verification 2026-10-12: на текущем рабочем дереве повторно
выполнен стандартный offline suite
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`:
1,508 tests, 25 skipped, OK (86.849s). Это локальное regression evidence;
оно не заменяет независимый verifier trust, digest-bound human approval или
controlled real PR. README test-count summary is older and should be synced in
a separate documentation task.

Batch VE / EXP-984: immutable local-Ollama CLI mapping and a dedicated test
confirmed the local profile constructs no credential source and reports
`credential_input=none`; focused CLI tests passed (35), full suite passed
(1,519 tests, 25 skipped), both pinned images matched exact IDs/platforms,
evidence DB paths were absent and `git diff --check` was clean. The single
card-authorized foreground Ollama startup failed immediately (`$HOME is not
defined`), before obtaining a process session handle. No model listing, GitHub
readiness/snapshot, confirmation gate, Worker or verifier call occurred; no
retry was made. EXP-984 is BLOCKED and cannot be retried. R2/MVP remain OPEN.

Batch VF / EXP-985 followed EXP-984 with explicit `HOME`, cloud-disabled
loopback Ollama and a retained foreground session. The local model digest and
loopback listener matched. OpenCode then ran the exact worker command once;
its shell stdin was EOF, so the runner displayed the exact one-shot gate but
returned cancelled (exit 3) before receiving the phrase. No public readiness,
snapshot, inference, Worker or verifier request occurred; evidence DB paths
remain absent. The phrase was not entered, but EXP-985 is BLOCKED and cannot be
retried. Both spent CLI profiles EXP-984/985 are revoked and tested as rejected
before preflight. A future card must use a retained interactive PTY/terminal or
another supported confirmation channel. R2/MVP remain OPEN.

Batch VG / EXP-986 used a retained Control Plane interactive PTY. Exact gate
was visible and `RUN EXP-986 ONCE` was entered once; the runner returned the
fixed `github-readiness-fetch-failed` marker. Observer SQLite integrity is
`ok`, but the journal contains only initial `agent_started` at cursor 0 and no
checkpoints or `GitHubReadiness.fetch` tool event. The GET dispatch is gated
after checkpoint/intent persistence, so no public readiness request is
evidenced or claimed. No snapshot, inference, Worker or verifier call occurred.
The stage DB is absent; observer DB is mode 0600. Ollama was stopped and the
spent EXP-986 profile revoked. R2/MVP remain OPEN.

Batch VH / EXP-987 narrows CLI readiness-failure evidence using the already
available observer cursor delta, without modifying the observer runtime or its
pinned verifier-code digest. Fixed markers distinguish transport construction
failure, cursor-unchanged pre-dispatch refusal, a one-event post-dispatch
unknown outcome, typed transport failures and arbitrary fetch failure. Fake
tests prove no transport call on pre-dispatch refusal, exactly one call with no
retry on unknown outcome, no Worker/runtime continuation, and redaction. Focused
CLI suite: 37 tests; full offline suite: 1,521 tests, 25 skipped; `git diff
--check` passed. No network, Ollama, Docker, SSH, credentials, Worker or
verifier operation ran. This diagnosis does not explain the specific EXP-986
cursor-0 failure by itself. EXP-988 was a separate fresh card/run: after the
exact gate and one delegated confirmation it returned
`observer-readiness-pre-dispatch-failed` at cursor 0, proving readiness
dispatch was not entered. No GitHub request, snapshot, model inference, Worker,
target test or verifier ran. Ollama was stopped, stage DB is absent, and the
mode-0600 observer DB is integrity-valid with only `agent_started` and zero
checkpoints. EXP-988's profile was revoked after the attempt; the card remains
BLOCKED and must not be retried. R2/MVP remain OPEN.

Batch VK / EXP-989 fixed the identity mismatch responsible for EXP-988's
pre-dispatch refusal: the CLI now supplies the selected authorization profile's
process ID to both journaled readiness and execution-permit gates instead of
the legacy module-level EXP-634 ID. The observer integration regression test
uses non-default EXP-851 process/task identities and verifies readiness intent,
permit issue/consume, and snapshot-pin events on one run. Focused CLI suite:
37 tests; full suite: 1,521 tests, 25 skipped; `git diff --check` passed. No
network, credential, Ollama, Docker, Worker or verifier call ran; verifier-code
digest is unchanged. EXP-988 remains BLOCKED and cannot be retried; any new
current-pin run requires its own card and one-shot gate. Independent verifier
trust, authenticated digest-bound approval and controlled real PR remain
unproven; R2/MVP remain OPEN.

Batch VL / EXP-990 then completed one fresh credential-free current-pin run
after the EXP-989 process-identity fix. The exact gate was shown in retained
PTY `98363`, and Control Plane entered its one-shot phrase once. Evidence:
`status=verified`, `external_write=false`, `approval=not_created`,
`publication=not_attempted`; staged-change digest
`sha256:b55af83fe251f2276240f0ec6679e70d8115409b38db479011180f116dc3f87c`.
The observer DB is integrity-valid with 81 events and 40 checkpoints for one
run; it records 27 bounded anonymous HTTPS GET exchanges (readiness, commit,
tree, 23 blobs and raw commit), one local model Worker proposal, target-test
pass and pinned same-host Docker verifier completion. The raw pinned commit
object hash and snapshot/tree/file digest matched. Both local Ollama and the
model are credential-free; the model used one loopback completion request.
Stage and observer SQLite files are mode 0600, with no payload text printed.
The stage DB includes a 2,007-byte canonical patch field as the requested
stage artifact; this is a disclosed scope interpretation, and future cards
must explicitly permit or forbid canonical stage payload retention. EXP-990's
one-shot profile was revoked; focused/full postflight passed (37 tests; 1,521
tests, 25 skipped). This is same-host verifier/local-mock evidence only, not
independent verifier trust, authenticated approval or a real PR. R2/MVP remain
OPEN.

Control Plane recheck 2026-10-12: тот же стандартный offline suite повторён на
текущем рабочем дереве после проверки статуса Batch UQ / EXP-974; 1,508 tests,
25 skipped, OK (85.123s). Изменений файлов во время прогона не выполнялось.
Это подтверждает локальную регрессию, но не меняет статус EXP-974 и не закрывает
независимый verifier trust, authenticated digest-bound approval или controlled
real PR.

Control Plane source audit 2026-10-12: static review of
`src/app_contracts/executor.py`, `signed_verifier_client.py`,
`publication_seed.py` and `controlled_publication.py` confirms the local gates
remain fail-closed: an attested response without a verified host-trust decision
does not produce a verified execution; publication-seed construction checks
decision/enrollment/verifier bindings; the enrolled publication coordinator
accepts only the in-memory mock GitHub endpoint. This is code-path review backed
by the passing offline suite, not evidence of a real testdev authority root,
human identity, verifier operation or GitHub PR.

Control Plane local preflight 2026-10-12: the still-DRAFT EXP-953 verifier-host
bundle was rebuilt against its exact expected digest. It matched
`sha256:64769adc992eb20ececdd142904587c08563188ac407c0217c0f8df66e972977`,
76 members, 1,206,401 source bytes and a 1,280,000-byte stdout stream; the
focused bundle suite passed 12 tests. No archive file or network/SSH operation
was used. EXP-953 remains DRAFT until the verifier image is present and its own
authorization is handled separately.

Предыдущий checkpoint 2026-10-11: продолжение достигло Batch #376. EXP-851
создал свежий verified stage после pinned public snapshot, restricted Worker,
target tests и pinned same-host Docker verifier; staged digest
`sha256:a034c79c6552b5ebc4a2a788d439c579d0024f178675415e586192d0b4403209`.
EXP-856 подтвердил на quiescent-копии этого stage, что approval CLI fail-closed
отказывает без caller-pinned verifier provenance и не меняет DB. EXP-857
делает отказ для активных SQLite `-wal`/`-shm` sidecars понятным, не ослабляя
quiescence gate. Focused approval suite: 12 tests. После EXP-857 полный offline
suite прошёл: 1468 tests (22 skipped). EXP-859 добавил optional TCP port
override для маршрута на unprivileged SSH loopback tunnel, не меняя pinned
HTTPS endpoint, SNI, Host header или CA/host trust. Focused suites: 62 tests;
последний полный offline suite: 1469 tests (22 skipped); `git diff --check`
чист. MVP всё ещё OPEN: verifier не развернут/не доверен на testdev,
authenticated digest-bound approval и реальное controlled PR evidence
отсутствуют. EXP-859 был проверен только на локальном synthetic TLS endpoint;
SSH tunnel и удалённый HTTPS verifier ещё не запускались. EXP-860 добавил
loopback-only HTTPS listener для уже существующего bounded one-request сервиса,
с server-side TLS 1.2+ и sanitized fail-closed startup; fake/synthetic loopback
exchange прошёл. Это всё ещё только слушатель: startup с эфемерными ключами,
testdev service и tunnel не реализованы/не запускались. Focused suite: 12 tests;
последний полный offline suite: 1470 tests (22 skipped); `git diff --check` clean.
Verifier-host follow-up: after an earlier SSH timeout on 2026-10-11, the exact
read-only EXP-858 preflight connected once and exited 0. It confirmed hostname
`testdev`, systemd 255, no non-interactive sudo, no `systemd-creds encrypt --user`
support, and `testdev.local` resolution on the host. This matches EXP-812's
2026-10-09 findings; the unprivileged systemd-user credential route is not
available. No host state changed. Client-side `.local` resolution remains a
separate issue and was not checked by EXP-858.
EXP-851's CLI limitation list remains explicit: snapshot source is not
authenticated by the CLI; verifier trust depends on injected authority and host
decision; production durability is not established. The new stage is not an
approval or publication artifact.

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

### Сверка критериев Thin Vertical Slice из документа 24, раздел 10 (2026-10-19; обновлено через EXP-1593)

Статусы ниже относятся к требуемому сквозному evidence, а не к наличию
отдельного класса или unit-теста. `Частично` означает только локальные,
synthetic/fake или same-host доказательства; это не закрывает production gate.

**EXP-1500/1503/1505 delta (2026-10-19):** EXP-1500 confirmed that approval
request construction refuses when verifier provenance trust is unavailable.
EXP-1503 exercised the positive synthetic REST → verifier proof → digest-bound
mock approval → mock receipt composition; the receipt explicitly remains
`external_write=false` and `identity_authenticated=false`. EXP-1505 separately
verified that a synthetic `identity_authenticated=true` claim is rejected
before provider configuration, token minter or publication journal. These
checks strengthen local allow/deny composition evidence only. They do not
establish an independent verifier, authenticated human, real approval, provider
write, PR, or MVP completion; affected criteria remain OPEN/PARTIAL.

Уточнение к строкам 1 и 10: EXP-1349 завершён одним разрешённым inspect и
находится в BLOCKED, а не DRAFT. Его bounded result: image ID, platform и
ordered layers совпали; размер storage отличается; разрешение израсходовано.
Текущее обновление также учитывает EXP-1363 (перенос предыдущего source
bundle), EXP-1368 (передача нового pin подтверждена, но удалённый import/runtime
не проверен), EXP-1369 (публичная заявка на подпись) и EXP-1372—1375
(локальная caller-pinned проверка синтетической detached signature, вывод
проверенных bindings/time window, CLI subprocess smoke и привязка host-decision
к точному проверенному enrollment), EXP-1380 (одноразовый запуск loopback
listener и выдача недоверенного публичного bootstrap) и EXP-1381 (локальная
сборка signing request, остающаяся `trust=unestablished`). EXP-1391 локально
проверила одноразовые authority-signed enrollment/host-decision, но ключ создан
самим Control Plane, срок записей истёк, а host evidence ограничено двумя
fingerprint; это не внешний authority source и не независимый trust. EXP-1392
сверила pinned commit/tree metadata; EXP-1393 проверила полный pinned public
snapshot и raw commit object, но не authorship. Verifier HTTP request по-прежнему
не отправлялся. EXP-1395 добавила локальный `trusted-https` backend для replay
сохранённого stage без повторного Worker/model: он принимает только caller-pinned
trust records, сохраняет их digests и fixed host/profile bindings, но не доказывает
управление authority, разделение хостов или deployment. Replay не запускался.
Эти события не закрывают критерий независимого verifier. EXP-1435 создала
отдельный EXP-1383 v2 Ed25519 item в назначенном пользователем macOS Keychain;
его public key-set digest
`sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`
закреплён пользователем 2026-10-19. Пользователь выбрал ограниченное
in-process использование signer-процесса; это не hardware-backed или
non-exportable гарантия и не разрешение на реальную подпись. EXP-1436 обновила
fingerprint-only comparison отдельным artifact digest
`sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`:
локальный Mac и `testdev` дали разные SHA-256 fingerprints, remote hostname/OS
совпали с `testdev`/`Linux`. Пользователь принял evidence только в этой
ограниченной области; date-only observation precision не доказывает текущие
deployment, runtime или isolation. EXP-1453 была выполнена один раз по
отдельному разрешению: точные bounded queries не нашли совпадающих systemd
unit, Docker container или listener на TCP 49231. Это не исключает иной
механизм развертывания и не доказывает отсутствие verifier вне заданных
запросов, runtime identity или isolation. Поэтому критерии независимого
verifier, approval и PR остаются открытыми.

Обновление EXP-1447 к критерию 2: local-ollama CLI требует exact
Ollama version/model/digest preflight после readiness permit и до snapshot/
Worker runtime. EXP-1447 отдельно исправила инструкцию для найденного
`int(data.get(...))` pre-validation coercion в целевом `/save-session`:
кандидат должен валидировать исходные JSON значения, не преобразовывая bool в
int. Synthetic prompt-contract tests и полный offline suite проходят, но не
являются live Worker evidence и не меняют `Частично` статус. EXP-1441
superseded до запуска; EXP-1448 остаётся DRAFT, поэтому новая модельная
попытка не выполнена.

Publication-path source review, 2026-10-19: `signed_github_publication.py`
rejects an approval result unless `identity_authenticated` is exactly `false`,
and its successful receipt also reports `identity_authenticated: false`.
`tests/test_signed_github_publication.py` exercises the gate only with a fake
GitHub transport. This is intentionally explicit evidence that the current
approver enrollment binds a signing key, not a verified human identity; it is
not authenticated-human-approval or provider-write evidence. Before a live PR
can satisfy the plan's authenticated approval/publication gate, the identity
binding contract needs a separate design and implementation card. The focused
publication suite was rerun and passed (9 tests); all provider interactions in
that suite use fake transport. EXP-1450 now makes the separate approval signer
fail closed unless stdin is a real TTY, before it reads repository metadata,
verifier trust inputs, displays review, or creates the lazy signer source.
Synthetic CLI tests prove that even an exact phrase supplied by a pipe is
refused without callback or seed access; the TTY exact-phrase path still signs
once and a wrong phrase still avoids seed access. Focused approval-signer tests
passed (8); full offline suite passed (1,874 tests, 25 skipped). This closes a
piped-input bypass, not human-identity authentication; keep
`identity_authenticated=false` until a separately reviewed identity binding
exists.

EXP-1449 Control Plane identity decision (2026-10-19): distinguish the
authority enrolling an approver key, the key holder signing one exact staged
digest, and the GitHub App principal performing a provider write. Current
enrollment/signature evidence establishes key possession and request binding;
`approver_id` remains a declared label. TTY presence and a fresh user decision
in the Control Plane are operational consent signals, not independently
verifiable application identity assertions. No supported identity provider or
signed subject-to-key binding is configured. Keep all protocol fields and
receipts at `identity_authenticated=false`; do not infer personhood from a
signature, terminal, or GitHub App installation. A future `true` claim requires
an independently pinned signed binding of subject, approver key, exact digest,
operation, audience and single-use nonce, with expiry and revocation checks.
Exact-digest signature and fresh user authorization remain distinct gates; this
decision authorizes no publication. The plan's authenticated-human-approval
criterion remains OPEN until such a binding is implemented and verified.

EXP-1451 added fake-only non-TTY regression cases for the existing GitHub
publication and read-only reconciliation CLIs. Publication displays only its
validated digest preview, then refuses before provider configuration, input,
journal creation or transport. Reconciliation displays one bounded journal
state, then refuses before provider configuration, input, token mint or GET;
the observed journal record fields remain unchanged. Both focused suites passed
(18 tests), and the full offline suite passed (1,876 tests, 25 skipped). No
provider transport ran. These tests pin existing terminal-confirmation gates;
they do not authorize or evidence provider reads/writes or human identity.

**EXP-1498 delta to the R2 matrix (2026-10-19):** the retained EXP-1269
candidate was replayed once from its standalone mode-0600 stage through the
current pinned public snapshot, target `network=none` sandbox, and current local
same-host verifier. It returned `fresh_pass`; the new stage's `verified_contents`
were byte-identical to the source stage and still declare only
`backend/routes.py`. New staged digest is
`sha256:14e3118b49eff4ff57dd56218dcb5aaa610bb8c3ecf9e5de55fbb71ca47d0809`,
verification digest
`sha256:ab3f36bfd902ae9064b8dab3e13996093113a919dc08e47670ad84db6e1d1579`; the
observer run is partial at cursor 87. This is not a new Worker/model execution,
independent verifier result, signed approval, or publication. R2/MVP remain OPEN.

**Current R2 matrix delta (EXP-1498/1500, 2026-10-19):** rows 1, 7, 10 and 13
must distinguish EXP-1498's fresh stored-candidate replay from EXP-1269's
successful Worker run. EXP-1498 verifies the retained bytes through the current
local same-host verifier and records a partial Observer run; it does not add
independent-verifier trust or approval eligibility. EXP-1500 then supplied
direct local fail-closed evidence for row 1: without trusted verifier
provenance, approval-request construction refuses before creating a request.
No key signature, provider action or publication was attempted. Rows 1, 7, 10
and 13 therefore remain OPEN/PARTIAL as previously classified; EXP-1493/1494
are separate DRAFT gates, not evidence of transfer, import or runtime readiness.

| № | Критерий | Текущее evidence | Статус / что ещё требуется |
|---|---|---|---|
| 1 | PR из одобренного staged digest | EXP-1269 remains the latest successful restricted Worker→target tests→same-host pinned verifier→exact stage/readback pass: staged digest `sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0`, verification digest `sha256:2d228a9e9a6faa35b2024a9dc5f19db1db068f8c8b6e0f2b4845eb81ffd0465`; observer `run-dacc14f7789d4d35aafca58cfe5cf8d1` is partial at cursor 88. Later Worker attempts EXP-1303 and EXP-1354 failed before verifier/stage. EXP-1347 confirmed presence of the exact verifier config ID on testdev; EXP-1349's one authorized field-facts inspect matched ID/platform/ordered DiffIDs but found a storage-size mismatch. EXP-1350 linked the local portable manifest to that config and layer chain. EXP-1363 transferred the previous verifier-host source bundle; EXP-1368 transferred the refreshed bundle and returned `BUNDLE_TRANSFER_CONFIRMED`; the one authorized EXP-1371 `--help` smoke returned `VERIFIER_IMPORT_SMOKE_OK`, proving remote Python imports only. EXP-1369 prepares public signing messages only; it does not establish verifier or approver trust. | **Открыт:** no independently trusted remote verifier, authenticated approval or real PR receipt. The field-facts inspect found a storage-size mismatch; Docker/image readiness, service behavior, host trust and provider publication remain unconfirmed. |
| 2 | Worker без GitHub network path и credential | EXP-678/693 cover the pinned target image's `network=none`, synthetic parent-environment exclusion and resource limits; EXP-781/802 cover restricted Worker composition. EXP-1269 used one credential-free local Ollama request through the restricted Worker against a pinned public snapshot, passed target tests and reached the same-host verifier/stage; the Worker container remains separated from repository/provider egress. Later EXP-1303 and EXP-1354 each journaled one local model call but failed target tests before verification/stage; EXP-1310 stopped at readiness 31, before snapshot/model. EXP-1240 establishes a one-request/no-retry local channel boundary. | **Частично:** EXP-1269 is still the latest successful Worker execution. No independent remote verifier trust or provider-enforced spend cap is proven. Existing canary scans are bounded to enumerated surfaces and synthetic secrets; they do not prove every possible surface or a real-credential run. Explicit legacy host-process mode has no network isolation and remains outside the security gate. |
| 3 | Canary credential отсутствует на проверяемых поверхностях | EXP-802's historical opt-in Docker composition exercised the restricted Worker and pinned Docker verifier with a synthetic credential canary. EXP-957 re-ran that composition against then-current target `sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187`, verifier `sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`, and code `sha256:3b48eb35f4abb55a539aed008c6c2ded93df006b6dab2da3c9e541a7ab73c7b3`; both image inspections matched (`linux/amd64`) and the exact opt-in test passed in 3.699s. That composed test scans worker/approval/publication stdout and stderr, stage and observer SQLite bytes, approval/signature/trust/enrollment/authority files, observer report and mock receipt; EXP-674 scans terminal stage-review output, EXP-675 covers a fake composition, and EXP-676 bounds traversal and fails closed on unscannable surfaces. EXP-1196 repeated the exact synthetic composition on target `sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187` and verifier `sha256:f9cf14612cd0632eb20e42d6a78f91e7b1b73b09d7947c2edd67fc23e9dfcbc2`, code digest `sha256:33502d811d02277d7f3ff9f385faf575b4f851c06fb7b2f99722dc3ddb6791bb`; exact `linux/amd64` inspections and the single opt-in test passed. EXP-1211 repeated the composition on refreshed verifier `sha256:49a7d7d14e0545069be45246d5184e3547d50a3a5fae521f17d433b4ea89bb14` and source digest `sha256:c1f02c1f6548c6edf1f3d6ea0bdb5ead061d25c0c38efbfbcfc801f7eea18135`; exact target/verifier `linux/amd64` inspections and the one opt-in composition passed in 2.921s, scanning output, SQLite, approval/trust/report and receipt surfaces. EXP-1229 extends the current-pin evidence: target `sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187`, verifier `sha256:75513217594db5ef5001048e643db581bc9e6188ca045c9c784e5054473def07`, source digest `sha256:5227a5cfa1c4da78ff9f62809a6f7737c5d6d5a8a6e3e562ec9993e6fa533e5e`; the exact synthetic Docker composition passed. Its canary scan covers Worker/approval-request/publication stdout and stderr, stage and observer database bytes, approval request/signature/trust-profile/approver-enrollment/authority-key-set files, observer report and local mock receipt. | **Частично:** current-pin synthetic canary coverage passed for the listed runtime/persisted surfaces. EXP-1229 used synthetic in-memory Worker inputs and a synthetic canary, with no real credential, model/API, SSH, testdev or provider write. This does not prove every possible runtime surface is collected or that a real provider credential/model run is safe. Content-pattern checks remain heuristic. |
| 4 | Изменение digest отзывает approval | Approval и intent привязаны к digest; mutation/неверная подпись отклоняются локальными policy regressions (EXP-547, EXP-553/554, EXP-558). | **Частично закрыт локально:** повторить как gate реального staged approval и signer enrollment. |
| 5 | Повтор intent не создаёт второй side effect | Idempotency и lost-response reconciliation покрыты mock/fake provider тестами (EXP-537/538, EXP-550/551). | **Частично закрыт локально:** нет подтверждённого recovery после реального provider side effect. |
| 6 | Недоступная policy запрещает publication | Composed mock-chain и fast/slow/degraded policy paths имеют fail-closed regression coverage (EXP-247/248 и последующие gateway/broker suites). | **Частично закрыт локально:** нет production policy service/runtime evidence. |
| 7 | Audit восстанавливает цепочку без секрета | SQLite journal and observer store verify local event causality/reopen; synthetic compositions link snapshot/Worker/verifier/stage/mock receipt. EXP-1269 is the latest successful restricted Worker→target→same-host verifier→stage/readback run: observer `run-dacc14f7789d4d35aafca58cfe5cf8d1`, cursor 88, `completeness=partial`; both databases passed `quick_check=ok` and mode 0600. EXP-1289, EXP-1303 and EXP-1354 persisted bounded model-channel intent/completion evidence, but the attempts failed target tests before verifier/stage. EXP-1310 produced only a bounded readiness result and no observer DB. Candidate/source/model output was not read. | **Частично:** latest successful stage is still EXP-1269 and observer completeness is partial; the later attempts prove only model-call journaling/failure metadata. This does not prove complete secret-free collection, full-history restoration, independent verifier trust, or operational durability. |
| 8 | Crash recovery не делает слепой повтор | Unknown/lost outcomes переходят в reconciliation; fake GitHub и SQLite reopen cases не повторяют подтверждённый side effect. | **Частично закрыт локально:** нет production crash/recovery evidence против provider. |
| 9 | Personal пользователь понимает действие до approval | EXP-629/630 дают bounded read-only preview точного stage и patch; EXP-673 adds a colorless terminal view with all three exact digests and escaped patch text while retaining JSON by default. | **Частично:** readable CLI evidence exists, but no usability study or authenticated human approval has validated the operator experience. |
| 10 | Эксперт через CLI видит identity, policy, evidence и receipt | CLI emits bounded stage/verifier/approval/publication evidence and fixed-schema trust metadata (EXP-552/558/563/573/682/683/781/798/959). EXP-1269 emitted `status=verified` with exact staged and verification digests plus observer run/cursor; no approval or publication was attempted. EXP-1344/1345 established the local OCI manifest/config identity distinction; EXP-1347 confirmed config-ID presence; EXP-1349's bounded inspect matched ID/platform/ordered DiffIDs but found a storage-size mismatch. EXP-1365 adds detached-signature message APIs; EXP-1369 prepares public signing requests; EXP-1372/1373 verify detached signatures against caller-pinned public keys and expose the checked binding tuple/time window; EXP-1374 runs the CLI subprocess; EXP-1375 validates enrollment before its linked host-decision; EXP-1381 prepares an untrusted enrollment request from a pinned public bootstrap. EXP-1395 adds a credential-free stored-stage replay mode using the caller-pinned trusted-HTTPS verifier backend; it records public trust digests and host bindings but was not run. These trust CLI tests use synthetic authorities/signatures. On 2026-10-19 the user pinned the current public authority key-set digest and accepted EXP-1436 only as date-precision fingerprint-separation evidence; this does not establish current testdev deployment identity, verifier runtime or host isolation. | **Частично:** local trust-signature preparation and verification paths exist, but there is no real authority signature, authenticated remote verifier result, human approval, provider receipt or real PR identity. EXP-1436 is accepted only for its stated fingerprint scope; current runtime/deployment/isolation evidence remains missing. |
| 11 | MVP технически отключает неготовые возможности | Fixed CLIs ограничивают target, operation, endpoint и повтор; unapproved write paths требуют отдельного permit/approval. | **Частично:** нет доказательства единого production deployment, где все незакрытые функции невозможно включить/обойти. |
| 12 | Записаны время и затраты | EXP-723's public-read-only fake-worker integration test took about 24 seconds; EXP-745 took 21.516 seconds and EXP-748 23.124 seconds; EXP-781 took 17.127 seconds; EXP-802's restricted-default Docker composition took 2.037 seconds. No provider/model call or write occurred in EXP-802. EXP-634's one-call USD 1 ceiling is user-set, not account-enforced. | **Открыт:** no live end-to-end model time/cost or provider-enforced spend cap. |
| 13 | Checkpoint каждого решения/вызова записан до исполнения | EXP-643—647 and subsequent composition cards cover Worker/verifier/test/replay/stage gates. EXP-1269 records the successful current local Worker→target→same-host verifier→stage sequence in observer `run-dacc14f7789d4d35aafca58cfe5cf8d1`, cursor 88. EXP-1283 adds opt-in pre-dispatch and terminal events for the model channel, without request/response payload. EXP-1289, EXP-1303 and EXP-1354 each persisted a model-call intent/completion pair; all failed at target-test execution before verifier/stage. EXP-1305 adds only exact allowlisted failure-code evidence; EXP-1310 stopped at readiness before observer startup. | **Частично:** current local instrumentation has one successful end-to-end record (EXP-1269) and later bounded model-call/failure records, but observer completeness and production durability remain unproven. No independent remote verifier, authenticated approval or publication trace exists; earlier replay reports remain partial/local-unattested. |
| 14 | Observer восстанавливает сохранённую историю и показывает пробелы | EXP-642/653/668 provide bounded reports and explicit gap markers; EXP-687/693/699/703 prove synthetic same-run continuity; EXP-723 validates public snapshot-intake events linked through fake Worker, target/verifier, stage and mock receipt; EXP-730/731 resolve content-addressed event and declared checkpoint refs from an optional local SQLite store; EXP-740 validates a referenced workspace manifest and materializes bounded file bytes in memory for a complete simulation checkpoint. Local report updates add timezone-aware `recorded_at` and `occurred_at` views, mark late-recorded events, and expose timestamp/checkpoint/artifact availability gaps. Report facts also identify the journal kind/trust/scope, causal event IDs, and artifact references or resolved digest/size metadata; free-text rationale/content is intentionally omitted. | **Частично:** timestamp views rely on an unauthenticated local journal; source metadata and references are not authenticated explanatory evidence; historical artifact/checkpoint availability, state/workspace execution, external-state reconciliation and collector completeness remain unproven; output remains partial/local-unattested. Focused report suite: 13 passed (2026-10-14). |
| 15 | Учебная ветка не меняет историю и не повторяет effects | EXP-665 adds a metadata-only branch declaration; EXP-740 materializes a complete simulation workspace read-only; EXP-950 binds an in-memory alternative replacement to the exact correction ID/version/digest, source manifest and file preimage digests. EXP-958 ran the exact correction against a synthetic target test in two separate current-pinned Docker sandbox sessions: baseline failed and alternative passed, with unchanged source workspace/host fixture and `network=none`. | **Частично:** one synthetic correction is now target-tested in a local sandbox, but branch outputs are not persisted as a replayable run, transfer to new cases/regressions is unevaluated, and broader isolation/durability remains unproven. |
| 16 | Оценены функция, вклад организации данных и перенос корректировки | EXP-706/707 preregistered design; EXP-1090—1179 dispatched the exact 100-ID schedule and retained only bounded outcome/reason metadata. Final join to casebook scenario/arm labels is recorded in docs/33 §16. | **Эксперимент исполнен, гипотеза не подтверждена:** functional pass 0/40 по S1/S2; ни одна arm не дала положительного functional outcome. Process-control evidence: S3 `needs_input` 4/20 (все C), S5 `denied` 1/20 (C); S4 fixed timeout был control input, не model-visible tool invocation. Correction transfer по per-case бинарным оценкам восстановить нельзя из агрегированного ledger. Counts: 29 UNKNOWN, 10 blocked, 2 denied, 55 failed, 4 needs-input. Никакой статистической значимости или широкой переносимости не заявляется. |

**Delta through EXP-1569 (2026-10-19):** EXP-1562's pass is limited to
converted same-host candidate `f935…`, not the configured classic-store pin
`4bc…`; EXP-1563/1565 did not confirm that configured ID in the local store.
EXP-1566 found a separate offline-built `linux/amd64` candidate `b2bf…`;
EXP-1567's substring-filtered attempt had one failure and is not accepted.
EXP-1568 pinned `--platform=linux/amd64`; three explicitly named synthetic
container cases then passed against `b2bf…`. EXP-1569 restored consistency of
the local verifier-host bundle pin (`6e2e…`, 33 members, 566543 source bytes,
604160 archive bytes); the full offline suite passed (1947 tests, 26 skipped).
These local results do not produce a new Worker run or independent verifier
result. Accordingly the 16 criterion classifications do not advance: the
independent verifier, authenticated-human approval, provider publication and
real-PR evidence remain missing; observer completeness and production recovery
remain partial/open. R2/MVP remain OPEN.

Обновление критериев 2, 7, 10 и 13 по EXP-1247: свежий exact-pin запуск сделал
один credential-free local model request, затем завершился фиксированной
ошибкой `target-test-malformed-status` до verifier/stage. Ограниченное CLI
evidence содержит run `run-fe793efd813b45fa859eeaf9ea615cc0`, cursor 74 и
`completeness=partial`; обе SQLite DB после остановки Ollama прошли
`quick_check=ok`, mode 0600. Candidate/source/model output не читался, число
events/checkpoints из этого запуска не утверждается. Approval/publication не
создавались/не вызывались. Статусы критериев остаются открытыми/частичными;
эта запись не является Worker, verifier, approval или publication PASS.

Дополнение к критериям 1, 7, 10 и 13 после Batch #480 / EXP-965:
один публичный pinned snapshot был проведён через synthetic restricted Worker,
актуальные target/verifier pins, stage и local-mock receipt; тот же run observer
journal сохранён и read-back проверен (95 events, 47 checkpoints, SQLite
integrity `ok`, mode 600). Это обновляет прежнее замечание таблицы, где
retention evidence ограничивалось EXP-963/синтетическим REST-run. Результат
остаётся частичным: Worker synthetic, receipt local mock, verifier same-host;
content-bearing journal не сертифицирован как secret-free. Независимый verifier,
аутентифицированное digest-bound approval и real PR не доказаны.

Обновление Control Plane от 2026-10-15 к критериям 1, 2, 7, 10 и 13:
EXP-1267 ранее завершился на target-test probe до verifier/stage; его run
`run-3b6bad10579d4a8697aaab7fd0c09c20` сохранил 75 events/37 checkpoints до
cursor 74, обе SQLite DB прошли `quick_check=ok`, mode 0600. Последующий
EXP-1269 устранил этот конкретный execution gap: один current-pin public
snapshot прошёл credential-free restricted local Worker, target tests,
same-host Docker verifier и exact stage/readback. Это не меняет ограничения
на independent-host trust, approval и publication, описанные ниже.

EXP-1272 завершил разрешённую передачу с неоднозначным `REMOTE_INSPECT_FAILED`
(exit 16); EXP-1274 и EXP-1277 каждый завершили по одному отдельно
авторизованному read-only inspect маркером `REMOTE_INSPECT_FAILED` (exit 11).
Эти маркеры не подтвердили remote image tuple; повторов, диагностики или
cleanup не было. EXP-1277 BLOCKED. Поэтому latest local Worker→same-host
verifier→stage evidence не становится evidence независимого remote verifier.
EXP-1275 закрыл только current-pin synthetic canary regression для перечисленных
поверхностей; это не real credential/model evidence и не доказывает полноту
сбора всех поверхностей.

Последующее обновление критериев 1, 2, 7, 10 и 13 после EXP-1269:
новая credential-free попытка на том же закреплённом public snapshot прошла
restricted Worker и target tests, current pinned Docker verifier и точное
stage/readback; bounded CLI вернул `status=verified`, stage digest
`sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0`,
verification digest `sha256:2d228a9e9a6faa35b2024a9dc5f19db1db068f8c8b6e0f2b4845eb81ffd0465`.
Observer run `run-dacc14f7789d4d35aafca58cfe5cf8d1` достиг cursor 88,
`completeness=partial`; SQLite integrity/mode прошли. Сервер был ограничен
loopback и запущен с `OLLAMA_NO_CLOUD=1`; его owned process остановлен после
одного вызова, listener отсутствует. Snapshot origin остался
`github_rest_api_claim`, verifier — same-host Docker, approval не создан,
publication не запускалась. Поэтому current live execution/stage gap закрыт
локально, но independent-host trust, authenticated signer/approval, complete
audit, real PR и отсутствие provider-enforced cost cap остаются OPEN.

Дополнение по критерию 3 после EXP-1275: существующий opt-in synthetic Docker
composition test прошёл на текущем target/verifier pin (1 test, 2.568s).
In-memory synthetic snapshot, fake Worker, generated test-only signing keys и
local-mock receipt проверялись без live model/API или real credential; canary
assertion покрывает только явно перечисленные output, temporary SQLite и
receipt surfaces. Это закрывает регрессионный разрыв по image pin для данного
теста, но не доказывает collection completeness или отсутствие реального
credential во всех средах.

Control Plane update after EXP-1276: the read-only image inspector now emits
separate fixed markers for local SSH-client launch exceptions, SSH-client exit
255 and other remote inspect failures, while preserving the exact tuple check,
single-call gate and output redaction. Focused tests passed (5); current full
offline suite passed (1,715 tests, 25 skipped); `git diff --check` passed. The
separately authorized EXP-1277 inspect ran once and returned only
`REMOTE_INSPECT_FAILED` (exit 11); remote image identity remains unconfirmed.
No retry or diagnostic SSH followed. EXP-1277 is BLOCKED; remote verifier
trust/readiness, authenticated approval and real PR remain OPEN.

EXP-1278 prepared a bounded, fixed-marker testdev probe and fake-runner tests.
The local suite passed (6 focused tests, including `/bin/sh -n` without
execution; 1,721 full offline tests, 25 skipped;
`git diff --check` clean). No SSH/network/Docker ran. EXP-1279 is a separate
DRAFT for one read-only check of Docker CLI availability, daemon access and the
exact pinned image tuple. Remote execution still requires fresh authorization;
the prior EXP-1277 attempt remains BLOCKED and is not retried. R2/MVP remain
OPEN.

EXP-1280 narrowed the verifier-host bundle from all 77 `app_contracts` modules
to the 27-module static local import closure of the HTTP/service roots, plus
four fixed launcher/dependency/schema files. The launcher imports successfully
from the extracted archive without starting the service. Two sequential
in-memory builds matched at digest
`sha256:31ca7d3df0ad03bd64e0924d34b107f1f25a6157fecbd132d7b4a4e50875a3c4`
(31 members, 541,323 source bytes). Focused suite: 13 passed; full suite:
1,721 tests, 25 skipped; `git diff --check` clean. This is a smaller,
reproducible package from the current dirty worktree, not a clean/reviewed
deployment pin, service runtime proof, or independent trust. R2/MVP remain OPEN.

EXP-1281 extracted `CredentialSource` and `CredentialSourceError` into a narrow
contract-only module; legacy `credential_source` imports re-export those exact
type objects, while `signer_key_source` imports the narrow module. The real
verifier bundle contains `credential_protocol.py` and omits `credential_source.py`,
which contains unused systemd-file, terminal-prompt and native-keyring readers.
Compatibility/type-identity and package-exclusion tests pass (57 focused tests;
bundle subset 14). Two sequential in-memory builds match at
`sha256:261fce4785b2b0fd17c369d3faf9c53873a8319af66d7ec03abacc32eda3e791`
(31 members, 533,249 source bytes). Full offline suite: 1,723 tests,
25 skipped; `git diff --check` clean. This reduces the secret-reading capability
surface shipped to the host, but does not authenticate that host, validate
runtime deployment, or make the dirty source an approved release. R2/MVP remain
OPEN.

**Итог на 2026-10-15:** ни один из 16 критериев не доказан целиком на
сквозном production-уровне. Локальные/синтетические доказательства частично
поддерживают пункты 2—6, 8—11 и 13—15; пункты 1, 7 и 12 остаются открытыми.
Критерий 16 исполнен по preregistered R5 расписанию, но исследовательская
гипотеза не подтверждена: functional pass 0/40, положительных functional
outcome нет, перенос correction по per-case оценкам восстановить нельзя.
R2 остаётся открытым: current local Worker→same-host verifier→stage путь
прошёл в EXP-1269, однако independent remote verifier identity/readiness/trust
не подтверждены (EXP-1272/1274/1277), authenticated digest-bound approval и
controlled real PR отсутствуют. Audit completeness и production durability
также не доказаны. Критерии 14—15 имеют ограниченные local/synthetic
возможности, но не полное исполнение, replay, transfer или production evidence.
Эта сверка не меняет исторические карточки и не является закрытием MVP.

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

### R2 exit matrix (evidence refreshed 2026-10-19, through EXP-1577)

**Current delta through EXP-1577:** EXP-1574 adds only the missing failed-run
terminal after a known local mock refusal; unresolved/unknown work remains open
and criteria 13/14 remain PARTIAL. EXP-1575/1576 did not establish current
Buildx capabilities; EXP-1572's accepted version/driver evidence remains the
operative tooling evidence. EXP-1577's one bounded local archive export returned
`EXPORT_FAILED|reason=unknown`; no validated portable candidate or changed pin
resulted. No remote transfer, independent verifier request/runtime, authenticated
human approval, provider receipt or controlled PR evidence was added. Existing
criterion classifications stay unchanged; R2/MVP remain OPEN.

EXP-1442 adds a synthetic-tested exact Ollama version/model/digest gate before
local snapshot/Worker runtime. EXP-1447 corrects the Worker instruction to
remove the target's pre-validation integer coercions. Both are code-path and
prompt-contract improvements only; EXP-1448 is still DRAFT and no new Worker
execution or model inference is evidenced.

| Gate | What current evidence demonstrates | Evidence still required for R2 exit |
|---|---|---|
| Fixed remote repository snapshot | EXP-1269 and the fresh EXP-1392/1393 evidence bind the public repository to commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, tree `2007066217aadafd9887fb3e3069220333b4fddb`, 23 files and snapshot digest `sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`. EXP-1393 matched the archive-derived Git tree/content and raw commit object OID/tree OID. | Content/object IDs are verified, but commit signature and authorship are not. This remains anonymous public-read evidence only; it grants no provider write or credential access. |
| Worker change | EXP-1269 made one credential-free local-Ollama request through the restricted Worker against that exact snapshot; target tests passed. EXP-1289's later one-shot attempt reached a journaled model call but exited nonzero at the target command before verifier/stage; EXP-1294 added bounded return-code evidence. EXP-1299 stopped before snapshot/model due to readiness 35 (<36). EXP-1302 registered a new exact-gated profile; EXP-1303 then passed post-reset readiness, consumed the pinned public snapshot and completed one local model call, but its target-test command failed with bounded return code 1 before verifier/stage. EXP-1304 found the fixed probe already emits one of 57 bounded failure markers. EXP-1305 implements exact allowlist persistence and bounded report projection; focused and full offline suites pass. EXP-1306's verifier image omitted the profile import; EXP-1307 added it but exposed a self-referential image/code pin. EXP-1308 fixes that pin design and passes local verifier-container/full-suite gates; it did not run or retry the Worker. EXP-1309 registers distinct profile EXP-1310. Its sole authorized readiness GET returned remaining 31 (<36); EXP-1310 is BLOCKED before CLI readiness/snapshot/Ollama/model, with no retry. EXP-1311 registers fresh profile EXP-1312; its one-shot run remains DRAFT until after reset and separate fresh authorization. EXP-1354 later used one fresh readiness permit and one local model call, then failed the target command before verifier/stage; its authorization is consumed and no retry followed. A read-only check confirms EXP-1303 predates the failure marker and contains only bounded return-code metadata; no raw output was read. The diagnostic marker remains untrusted and cannot affect approval/publication. Earlier EXP-1233/1247/1251/1256 attempts failed before verification and remain historical failures, not evidence against EXP-1269. | One successful Worker change is evidenced, but not repeated under the latest observer/model channel. No provider-enforced spend cap or separately governed Worker host is proven. Canary scans remain bounded to listed surfaces and synthetic values. |
| Bounded execution and test | EXP-1269 used target image `sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187`, ran the restricted-container Worker and target tests, then passed the current pinned Docker verifier on the same host. Stage/readback matched the exact staged digest. EXP-1303 used the current fixed target image but the target-test command returned 1; verifier/stage were not reached, and the empty stage was confirmed. Thus EXP-1269 remains the latest successful Worker→target→same-host verifier→stage run; EXP-1295's verifier pin is still not exercised by a successful end-to-end run. | The verifier is on the same host, so this does not establish an independent verifier trust domain. Production isolation, provider-enforced spend limits and production recovery remain unproven. |
| Independent verification | EXP-1269 remains the latest accepted Worker→target→same-host verifier→stage result; no independent verifier result has been accepted. Current local verifier artifacts are manifest/image `sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`, code `sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`, classic-store config `sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`, and deterministic source bundle `sha256:d0d51e4a37ba0dc86cd649acf79e7bab3c790dc680bd0ea81df5291782b0f35f`. EXP-1483 preserved the accepted EXP-1269 stage in a separate mode-0600 standalone SQLite snapshot with matching staged digest and `integrity_check=ok`. EXP-1493 (source bundle transfer) and EXP-1494 (image import) are the current DRAFT cards; neither has been run. The user-pinned v2 authority key-set and accepted EXP-1436 fingerprint comparison are bounded inputs only: they do not prove current deployment identity, runtime, or isolation. | Current bundle/image are not on testdev; no current independent verifier request/result exists. Still required: separately authorized artifact transfer/import, evidence of the actual verifier runtime, a signed verifier result under accepted trust inputs, and evidence sufficient to bind verifier host/deployment. Same-host verification and fingerprint difference alone are insufficient. |
| Durable stage and human approval | EXP-1269 produced staged digest `sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0` and verification digest `sha256:2d228a9e9a6faa35b2024a9dc5f19db1db068f8c8b6e0f2b4845eb81ffd0465`; exact-digest readback passed. Both SQLite databases passed `quick_check=ok` and mode 0600. Observer run `run-dacc14f7789d4d35aafca58cfe5cf8d1` remains partial at cursor 88. Signed/enrolled mock approval plumbing exists. | No authenticated human approval or production/cross-host durability evidence exists. The partial observer does not prove full audit completeness. Synthetic trust/signing inputs do not authorize publication. |
| Controlled Pull Request publication and recovery | Fake-only GitHub App composition binds the verified manifest to seed and journals before branch/file effects; EXP-1021/1022 exercise process-exit recovery against a durable SQLite mock provider. Mock receipts remain `identity_authenticated=false`, `external_write=false`. EXP-1269 explicitly did not create approval or attempt publication. | No real PR receipt exists. Missing: real/OOB signer enrollment, fresh exact provider authorization, approved provider identity, real PR evidence, independently trusted verifier, and crash recovery against the approved provider without blind retry. No power-loss, cross-host, real-provider durability, or multi-file atomicity claim. |

EXP-1301 independently audited the current EXP-1300 dirty-worktree verifier-host
bundle in memory: two builds matched the pinned digest/member/byte tuple;
manifest hashes matched every source member; AST-derived local imports had no
unresolved members. No concrete credential-reading implementation or
secret-bearing path is included. The closure does include the opaque
`CredentialSource` protocol and an Ed25519 adapter that consumes an injected
source, but does not implement credential storage/injection. Focused bundle
tests passed (14); full offline suite passed (1,736 tests, 25 skipped). This is
source-closure evidence only, not a clean/reviewed deployment pin or remote host
trust. EXP-1297's one authorized read-only remote inspect failed with fixed
marker `REMOTE_INSPECT_FAILED` (exit 11); remote image identity remains unknown.

EXP-1029 / Batch UZ expanded the fixed offline HTTP/DB target probe to cover
the preregistered 5-field × 5-invalid-class matrix (boolean, fractional,
numeric string and both SQLite signed-64 overflow boundaries), resetting the
disposable DB before every case, while preserving the non-finite rejection and
exact valid-row control. Focused and offline suite results are recorded in the
queue. This changes the acceptance oracle only: no candidate or target was run,
so it provides no Worker/verifier PASS evidence and does not close R2.

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

Результат 2026-10-12: **1496 тестов запущено, 24 пропущены; suite завершился
успешно за 117.198 секунды** (`OK`, exit 0). Пропуски соответствуют условиям
skip в тестах; Docker sandbox integration остаётся opt-in через
`RUN_DOCKER_SANDBOX_TESTS=1`. Это подтверждает только свойства, покрытые
offline-тестами на текущей машине, и не является доказательством testdev,
независимого verifier trust, live Worker, authenticated approval или PR.

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

Актуальная граница R2 дана в оперативном checkpoint в начале документа и в
строке `Independent verification` выше. Исторические подробности о старых
verifier image pins ниже не являются текущими transfer/deployment pins; на
момент Batch AIX актуальные локальные pins и незапущенные transfer gates
перечислены в этих двух оперативных местах.

| Этап из плана 1.1 | Статус | Ближайший проверяемый результат |
|---|---|---|
| R0: наблюдение и память | Концепция готова | JSON Schema, валидаторы и негативные тесты ObservationEvent/Checkpoint/LearningCorrection/MemorySummary |
| R1: целостность и фиксация действий | Частично проверено | Нарушения 1–2 закрыты локальными regression; composed local harness, gateway-before-broker enforcement, deterministic workspace interleaving, pre-`prepare_change` checkpoints для `WorkerProposal.validate` (EXP-1185), `PreparedChange.validate-binding` (EXP-1186), записи proposal в workspace (EXP-1187) и `SandboxSnapshot.validate-binding` (EXP-1190) приняты. Collector остаётся частичным; production orchestration, real concurrent-writer evidence и external proof отсутствуют |
| R2: сквозной исполнитель | EXP-1269 is the latest successful full local run: pinned public snapshot → restricted-container Worker → target tests → same-host Docker verifier → exact stage/readback (staged digest `sha256:511feb6a6d66d8f3f89bc03f106f99a3bf768dfe26ddefa03739d61dfc9287a0`, verification digest `sha256:2d228a9e9a6faa35b2024a9dc5f19db1db068f8c8b6e0f2b4845eb81ffd0465`, observer partial at cursor 88). EXP-1289's later journaled local-model attempt failed at the target command before verifier/stage; EXP-1294 added bounded return-code evidence but no safe target diagnostic/output. EXP-1295 rebuilt the current local verifier image `sha256:8caa34a8e516f9be31a54f0271ccabee3b088ecc7f3ce9c2dad49f3fe42c133f` from code digest `sha256:223fd6f35c73892c1a5d4e43b2294da7f7ef7a9d6004181ab16c954f62e79d18`; synthetic runtime tests pass. EXP-1286/1287 import/inspect attempts on the prior image did not establish remote identity; EXP-1299 readiness stopped below quota. EXP-1296's authorized transfer returned `REMOTE_INSPECT_FAILED` (exit 16) and EXP-1297's separately authorized inspect returned `REMOTE_INSPECT_FAILED` (exit 11); remote image identity remains unknown. EXP-1303 passed post-reset readiness and completed one journaled local model call, but the target command failed with return code 1 before verifier/stage; the stage remained empty and no retry followed. Durable/process-crash recovery is verified only against a local SQLite mock (EXP-1021/1022), and composed approval/publication evidence is mock-only. No independently trusted remote verifier, authenticated digest-bound approval, or real PR receipt exists. | **OPEN:** independent-host verifier trust, authenticated digest-bound approval, real controlled PR and provider crash recovery remain unproven. |
| R3: исторический Observer | Частично реализован: local SQLite journal/reopen, bounded structural reports with gap markers, content-addressed artifact resolution/materialization (EXP-642/653/668, EXP-730/731/740), and selected same-run event instrumentation. | **Частично:** collector is not comprehensive, journal/artifact origin and access control are not production-trusted, and the report does not restore and replay a full execution environment. |
| R4: учебная ветка | Частично реализована: metadata-only branch declaration (EXP-665), strict in-memory materialization (EXP-740), correction-ID/version/digest- plus preimage-bound in-memory alternative patch step (EXP-950), and one baseline-fail/corrected-pass target test in separate current-pinned `network=none` Docker sandboxes (EXP-958). | **Частично:** one synthetic correction is target-tested locally, but branch outputs are not persisted as replayable runs, transfer to new cases/regressions is unevaluated, and broader isolation/durability remains unproven. No historical permissions/effects are replayed. |
| R5: эксперимент | EXP-1090—1179 dispatched the fixed 100-ID casebook against the pinned public snapshot and local Ollama runtime. Final ledger has 100 terminal IDs; bounded scenario/arm and outcome summary is in docs/33 §16. | **Исполнен с отрицательным/неубедительным результатом:** primary functional pass 0/40; no positive organization-effect or correction-transfer signal. 29 UNKNOWN, 10 blocked, 2 denied, 55 failed, 4 needs-input; stage empty. No repeats/replacements are authorized by the completed preregistration. Criterion 16 is not confirmed. |

Batch WO / EXP-1018 added `snapshot_wal_stage.py` and a local helper that
copies a stable SQLite DB/WAL/SHM file set into a private temp directory, verifies
source fingerprints before/after, then uses SQLite backup API to produce a
standalone mode-0600 DELETE-journal database with exact staged-artifact readback.
The original stage, WAL and SHM files are never opened by SQLite or modified;
the existing byte-identical copy and approval CLI still fail closed on
sidecars. Five focused tests and the full offline suite passed (1,539 tests,
1,514 passed, 25 skipped); `git diff --check` passed. Tests use synthetic stages
only; the real EXP-990 artifact was neither opened nor copied. This is a local
consistency snapshot, not production durability or independent verifier trust.

Batch WR / EXP-1021 adds one true local process-boundary recovery regression:
the child process performs one effect against a durable SQLite mock provider,
then terminates via `os._exit(86)` after the effect and before journal receipt
completion. A new journal connection recovers the exact idempotency/repository/
base-branch-bound receipt, and repeated reconciliation leaves provider call and
effect counts at one. Focused suite: 28 tests; full offline suite: 1,540 tests
(1,515 passed, 25 skipped), with no ResourceWarning; `git diff --check` clean.
This strengthens only local mock-process-crash evidence; power-loss, filesystem,
cross-host and real-provider durability remain unproven, so R2 stays OPEN.

Batch WS / EXP-1022 adds the complementary abrupt-exit case: the child persists
`attempting` and dies before invoking the durable SQLite mock provider. Restart
reconciliation stores `reconciliation_required`; a repeated check stays blocked
with zero mock calls and receipts. Focused suite: 29 tests; full offline suite:
1,541 tests (1,516 passed, 25 skipped), without ResourceWarning;
`git diff --check` clean. Together, EXP-1021/1022 exercise both sides of this
uncertain crash boundary across an actual OS-process exit, but only with local
SQLite and a test double; this is not power-loss, filesystem, cross-host or
real-provider durability evidence. R2 remains OPEN.

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

Batch NW / EXP-794 locally enables `.local` HTTPS verifier endpoints with an
optional caller-pinned custom PEM CA bundle (SHA-256 required, maximum 1 MiB),
while preserving certifi/default trust, TLS hostname verification and the
bounded one-shot request contract. A loopback TLS integration with a synthetic
`testdev.local` SAN certificate passes; wrong hostname, missing trust and CA
digest mismatch fail before HTTP. This does not establish DNS/mDNS availability,
remote TLS termination, signer-key injection, host separation or independent
verifier trust. EXP-793 is READY for read-only testdev preflight; its exact
commands still require confirmation in OpenCode for macOS. No remote
connection/change has occurred. Focused client suite: 29 tests; full suite at
that checkpoint: 1416 tests, 20 skipped. R2/MVP remain OPEN.

EXP-795 adds a Linux systemd `LoadCredential` consumer for the verifier signing
seed, selected explicitly by the operator CLI. It reads the one fixed name from
`CREDENTIALS_DIRECTORY` only at signer use, rejects symlinks/non-regular and
oversized files, and keeps errors/diagnostics opaque. Synthetic source and CLI
tests pass; no credential was provisioned and no unit/service was started.
Combined focused source/service tests: 27 passed; full suite: 1421 tests, 20
skipped; `git diff --check` clean.

Batch NX / EXP-796—797 closes two local integration gaps for the chosen
`.local` verifier. Signed enrollment and host-decision validation now accept
`testdev.local`; the pinned runtime can use a `SignedVerifierClient` only with
the exact endpoint/profile and a verified OOB host decision bound to expected
host IDs, with both signed records still within their validity windows. An
audit-only or expired client is rejected before DB creation, Worker credential
lookup, runtime entrypoint or network. Focused tests: 99 (2 skipped), using
synthetic signatures and no transport calls. This does not create actual host
separation evidence or independent trust; no runtime CLI live run or provider
call was made. Full offline suite: 1424 tests, 20 skipped; `git diff --check`
clean. R2/MVP remain OPEN.

Batch NY / EXP-798 exposes the `.local` signed verifier in the operator CLI via
an explicit trusted-HTTPS backend. All public trust inputs require caller-pinned
SHA-256 digests; the CA/TLS configuration is checked before readiness, prompt,
or runtime, and invalid trust stops fail-closed. Synthetic tests show the
validated client reaches `run_remote_snapshot_with_runtime` with expected host
IDs and no verifier Docker preflight; pinned Docker remains the default. Full
offline suite: 1427 tests, 20 skipped. The host has not been contacted or
configured and no signer credential, actual OOB trust evidence, Worker call,
provider operation, or deployment exists. R2/MVP remain OPEN.

Batch NZ / EXP-799 closes a credential-source liveness defect found by a
bounded synthetic FIFO probe: opening the fixed systemd credential name with
blocking `O_RDONLY` could wait forever before the later regular-file check.
`SystemdCredentialSource` now requires and uses `O_NONBLOCK` together with
`O_NOFOLLOW`, failing before `open` if either safe flag is unavailable. A
subprocess regression test rejects a FIFO promptly without printing its path or
contents. Focused tests: 19 passed; full offline suite: 1429 tests, 20 skipped;
`git diff --check` clean. No real credential or host was accessed. R2/MVP remain
OPEN.

Batch OA / EXP-800 reconciles the user-facing README with EXP-794—799 evidence
and the 1429-test baseline. It documents the explicit trusted-HTTPS backend,
fixed `testdev.local` URL and digest-pinned public trust inputs, the systemd
credential-source option, and the unconfigured/unverified state of the remote
host and OOB trust. This documentation-only batch made no runtime, Docker,
network or credential calls; `git diff --check` passed. R2/MVP remain OPEN.

Batch OB / EXP-801 changes the pinned operator CLI default from a host-process
proposal worker to the existing restricted `ContainerProposalWorker`; the
legacy host-process backend now requires an explicit option. The fixed runtime
and observation wrapper preserve the selected worker instance. Synthetic CLI
and runtime tests cover default selection, lazy host-side channel wiring,
construction failure before prompt/readiness, and explicit legacy selection.
The synthetic remote-snapshot composition harnesses now explicitly request
that legacy backend where they inject their host-process fake. Focused suite:
82 tests, 2 skipped; remote-snapshot suite: 29 tests, 8 skipped; full offline
suite: 1432 tests, 20 skipped; `git diff --check` clean. No Docker, model,
provider, host, verifier network, or publication
operation occurred. This selects the existing container adapter but does not
establish live end-to-end Worker isolation. R2/MVP remain OPEN.

Batch OC / EXP-802 corrects the prior synthetic pipeline harness to select the
host-process backend only when running its non-Docker fakes. Its opt-in Docker
composition leaves the backend flag absent, proving the CLI default instantiates
the pinned `ContainerProposalWorker`; a one-shot synthetic Chat Completions
channel supplies the model result from Worker context and records exactly one
credential-source read of a synthetic canary. One run completes the container
Worker, Docker target tests, pinned Docker verifier, exact SQLite stage/readback,
synthetic enrolled approval and local-mock receipt under one observer run ID.
The test asserts no canary in output and receipt `external_write=false`,
`identity_authenticated=false`. Exact command from Batch OC passed in 2.037s;
full offline suite passed 1432 tests with 20 skipped, and `git diff --check` is
clean. This is a synthetic same-host composition, not live model spend,
independently trusted remote verifier, authenticated human approval or real PR.
R2/MVP remain OPEN.

Batch OD / EXP-803 completed one exact anonymous public-read-only attempt after
both caller-pinned local Docker image preflights. The pinned snapshot for
`SoldatovAlexander/brainbooster_full_v11` at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` (tree
`2007066217aadafd9887fb3e3069220333b4fddb`, 23 files, content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`)
passed through the operator CLI's default restricted Worker with one synthetic
channel response, pinned target tests, pinned verifier PASS, exact SQLite
stage/readback and enrolled local-mock receipt. Retained stage digest
`sha256:871ee8ad2ede91232e5f32272265c5e6d74a433aaa06566782737ccf8f736101`,
observer run `run-9851f08d0cec4452afac4f5f3360807d`; counts: readiness 1, commit
1, tree 1, blobs 23, raw commit fetch 1, runtime 1. Test: 21.437s, `OK`.
Receipt remains mock-only (`external_write=false`,
`identity_authenticated=false`, `completeness=partial`). No live model,
credential, remote verifier trust, human approval, actual PR, provider write,
deployment or host configuration occurred. R2/MVP remain OPEN.

Batch OE / EXP-804 adds an opt-in retained-stage destination to the guarded
public integration test. Absolute new paths, parent type and SQLite sidecars
are checked before GitHub transport construction; only a fully successful
composition copies the exact stage database through the existing digest-bound
no-overwrite copier. A fixed-schema metadata line reports staged/artifact/database
digests, byte size and `overwrite=false`, omitting path and content. Focused
tests passed (37, 8 skipped); the full offline suite passed (1433, 20 skipped);
`git diff --check` passed. No second public run has used this facility yet. A
retained stage would contain synthetic local verifier trust and is review
material only—not approval-eligible evidence or independent-host proof. R2/MVP
remain OPEN.

Batch OF / EXP-805 completed both local Docker image inspections, then made
exactly one allowed GitHub readiness request. It returned HTTP 200 with
remaining 33 (minimum 35); the guarded test stopped before any snapshot GET,
container, Worker or stage creation. No retry occurred and the retained
destination remains absent. This is a quota-gate stop, not new end-to-end
evidence. R2/MVP remain OPEN.

EXP-793 / Batch NV completed read-only testdev metadata discovery from
OpenCode: hostname `testdev`; systemd 255; `systemd-creds` installed;
`command -v` produced no output for `avahi-daemon`, `caddy` or `nginx`; the
primary interface is `enp2s0` at `192.168.88.101/24`. One malformed canceled
sibling session repeated only `hostnamectl --static`, so the seven-command
preflight had one read-only duplicate; no other remote action occurred. A
post-run local git-status request was denied. No host mutation, secret/config
read, service action, key/certificate creation or deployment occurred. This
supports exact setup planning only; independent trust is still unproven. R2/MVP
remain OPEN.

EXP-806 / Batch OG completed one read-only SSH session. testdev reports Python
3.12.3 and Docker 29.1.3; both caller-pinned verifier images are absent. Cached
Ubuntu package candidates are available for `avahi-daemon` 0.8-13ubuntu6.2 and
Caddy 2.6.2-6ubuntu0.24.04.3; TCP ports 80 and 443 are free. No package, image,
service, file, credential or network configuration changed. The task's SSH
command was followed only by a local exit-status echo; no other SSH call was
made. Host setup still needs a separate exact card and user confirmation; the
card must include a pinned verifier image transfer before service startup.
R2/MVP remain OPEN.

EXP-807 / Batch OH completed one read-only SSH session: `sudo -n true` returned
`SUDO_EXIT=1` (`sudo: a password is required`); Python cryptography 41.0.7
imports; systemd-creds reports systemd 255 and documents stdio encryption with
named credentials and host/TPM key selection. No files, credentials or unit
configuration were read; no host changes occurred. The current SSH identity
cannot perform privileged setup. Await a user-provided elevation path; do not
route around it via Docker. EXP-812 / Batch OM confirmed `testdev.local` resolves
on testdev to link-local IPv6, but the local macOS resolver returned no record.
Host-side Docker metadata is `linux/x86_64`; `sudo -n` remains unavailable.
Both macOS `dscacheutil` and application-level `socket.getaddrinfo` failed to
resolve `testdev.local`. No DNS/TLS/service setup occurred. Client-side `.local`
resolution and the verifier service remain undeployed; the endpoint in
application code is not deployment evidence. The latest offline suite passed
1445 tests (21 skipped). R2/MVP remain OPEN.

EXP-808 / Batch OI rechecked both exact cached Docker image IDs successfully,
then performed exactly one anonymous readiness GET. GitHub again reported
`remaining=33`, below the required 35, so no snapshot REST request, raw commit
fetch, container, Worker or stage was produced. The retained destination and
SQLite sidecars were confirmed absent; no retry or provider write occurred.
Before the integration, the executor also made an unlisted filtered local
`/private/tmp` metadata check; no filenames were emitted and no contents or
files were read or changed. A later unfiltered listing request was denied.
The quota gate is still the immediate blocker for this public composition;
deployed independent verifier/trust and authenticated publication remain
separate OPEN gates. R2/MVP remain OPEN.

EXP-809 / Batch OJ adds a local-only operator utility for generating one fresh
Ed25519 signer seed, piping only its canonical hex form to fixed systemd-creds
stdin encryption, and atomically publishing validated ciphertext with
no-overwrite semantics and mode 0600. Only public enrollment fields and
bounded SHA-256 metadata are emitted. No live systemd-creds, host key, Linux
host, testdev, verifier deployment or authority
enrollment was used. The root-only guard is tested before entropy/tool use.
Eleven focused tests and the full offline suite (1444 tests, 20 skipped) passed;
`git diff --check` is clean. The utility cannot by itself establish signer
identity, independent host trust or an approval-eligible receipt. R2/MVP remain
OPEN.

EXP-810 / Batch OK completed one fresh quota-gated public snapshot composition.
The exact pinned commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` (tree
`2007066217aadafd9887fb3e3069220333b4fddb`, 23 files, content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`)
passed through one restricted Docker Worker runtime, target PASS, pinned
independent verifier PASS, exact stage/readback and local-mock receipt under
staged digest
`sha256:086e5abcd1c6d4f4bcf0c968ddc4dcd59c53cbe3d9ec36d813ccc6449ca6b489`.
Counts were readiness=1, commit=1, tree=1, blobs=23, raw commit=1,
runtime=1; test time 26.059s. Retained stage metadata reports 462848 bytes,
database SHA-256
`0b5ab3bc9b69e3b61d00b937a39b6bd29ea2913bb0bf3214eaab3fc7f4f84360`, and
no-overwrite artifact digest
`sha256:69b9c70dcd06acda82939a215716f23609dc44f921981500286f84901c7ac432`.
Receipt remains `mock_published`, `external_write=false`,
`identity_authenticated=false`; observer completeness is partial. No live
model/provider, credential, deployed `.local` verifier, human approval, provider
write, branch/PR, push, deployment or commit occurred. This does not close R2.

EXP-811 / Batch OL adds a second opt-in retained-stage approval CLI check for
the exact EXP-810 artifact. With synthetic repository metadata, the real CLI
returned exit 2, empty stdout and the fixed unavailable-verifier-provenance
diagnostic; exact pre/post database bytes and SHA-256 matched. The focused test
passed once; full offline discovery passed 1445 tests (21 skipped), including
the expected opt-in skip. No credential, network, approval artifact, signature
or provider action occurred. This proves a fail-closed boundary for this stage,
not trusted verifier provenance or authenticated approval. R2/MVP remain OPEN.
The successful mock approval-request path in the integration used a
test-generated verifier authority key set confined to that run's temporary
directory; it was not retained as caller-pinned out-of-band trust. Thus the
saved stage plus its local mock receipt is still not eligible for approval.

EXP-819—821 / Batches OT—OV resolved the base-image architecture discrepancy
without building or contacting testdev. The old Python 3.11.16 manifest pin
resolved locally to `linux/arm64`, so EXP-818 stopped before build. One bounded
public metadata request identified the version-pinned tag's OCI index digest
`sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e` and
amd64 child `sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761`.
The target-runtime and verifier Dockerfiles plus runtime references pin the
immutable index. EXP-825 built target image
`sha256:cc32f8cd0d05f92082b9e796ff28e3ea4567426844755b09650a6c37e83acce5`
as `linux/amd64`; its first verifier image lacked the transitive observer import
closure and the one request failed closed. EXP-827 added the missing modules
and updated the source-derived verifier code digest to
`sha256:5a8cec6b880c085d047b28043502ad75a309cb3c2773f3797670844dce6b2714`.
The rebuilt verifier image is `sha256:8e9452efd0f24c0db4bd64dc90fee9ed173b6d4c7f4cf08696ac2d3f5168bc74`
(`linux/amd64`), but its one synthetic request and one direct import smoke
failed closed with exit 1; sanitized output does not expose the startup cause.
No trust enrollment or transfer occurred. Testdev image enrollment and `.local`
host DNS/TLS/service setup remain open. `sudo -n` still cannot perform
privileged host setup, so no host mutation has been attempted. R2/MVP remain
OPEN.

EXP-831 adds the exact two observation schemas loaded during verifier startup
to the immutable verifier image context and includes their content in the
source-derived code digest
`sha256:3b48eb35f4abb55a539aed008c6c2ded93df006b6dab2da3c9e541a7ab73c7b3`.
The focused verifier/target suite passed (35 tests, 4 skipped); full offline
suite passed (1446 tests, 21 skipped). EXP-832 built verifier image
`sha256:6c0426fd6aee71ffdd119a98f6699d3958d01e1798dc8773185211c42e9b5574`
(`linux/amd64`) from the completed import/schema context; its one synthetic
network-none non-root request passed. Profile identity is aligned to this image
and the EXP-831 code digest, but the image remains local-only. No testdev
enrollment, host trust, DNS/TLS/service setup or remote request occurred.

EXP-833 pins the inspected amd64 target/verifier IDs and the matching
source-derived verifier code digest in the active profile. Focused tests passed
(65 tests, 3 skipped); full suite passed (1446 tests, 21 skipped). EXP-834 is a
single quota-gated anonymous public-read-only snapshot run through the updated
images into a local mock receipt. It does not authorize provider writes or
deployment and remains ineligible as authenticated approval evidence.

The one EXP-834 run passed the pinned public snapshot through the updated amd64
target/verifier and local mock receipt path. It read 23 pinned blobs, verified
the same staged digest on readback, and retained the SQLite artifact (SHA-256
`a70abe067529c5ca8ce836d08e33395e555211c9dc6de32905a29e6bbe6c816a`). The
receipt remains mock-only: `external_write=false`,
`identity_authenticated=false`; observer completeness is `partial`. This is not
evidence of testdev host trust, real approval, or a provider write.

EXP-835 exercised the actual approval-request CLI against the EXP-834 retained
database with no caller-pinned verifier trust. It returned exit 2, emitted no
request, reported the fixed missing-provenance diagnostic, and did not mutate
the stage. This is a fail-closed regression, not positive approval evidence.
The full offline suite passed (1447 tests, 22 skipped).

EXP-836 joins the synthetic systemd credential source to one signed verifier
HTTP exchange on loopback; the expected public key validated the PASS response,
and the seed was not in the response. Focused test passed; full suite passed
(1448 tests, 22 skipped). This remains local synthetic evidence. `systemd-creds`,
the testdev systemd unit, remote TLS/`.local` resolution, host separation and
out-of-band trust have not been exercised.

EXP-837 removes the replay tool's stale requirement that a saved candidate
already have the current verifier image/code ID. The exact EXP-548 source stage
was independently opened read-only and validated as candidate input; its prior
verifier result is not promoted. The replay must still execute and bind the
current pinned target/verifier in its new output stage. Synthetic replay test
passed, full offline suite passed (1449 tests, 22 skipped), and `git diff
--check` passed. The actual pinned snapshot replay is still pending.

EXP-838 completed one read-only pinned snapshot/raw-commit replay of the
historical live-Worker candidate with the current profile, then stopped at the
expanded target boundary (`target-test-sqlite-range-status`). The verifier was
not reached and no output stage was created; retry was not attempted. Retained
observer metadata shows 67 events/33 checkpoints with `completeness=partial`.
The candidate predates the signed-64-bit SQLite-range requirement and must be
updated before a fresh verification run. No model/credential, approval,
publication, or host deployment occurred.

EXP-839 adds explicit provenance labels to successful replay evidence:
`source_stage_verifier_result=not_carried_forward` and
`current_verification_status=fresh_pass`. The regression confirms a candidate
with a different historical verifier ID is freshly run through the current
verifier, and the output stage binds only the current ID. Focused replay suite:
20 tests passed; full offline suite: 1449 tests, 22 skipped; `git diff --check`
passed. This is evidence-format clarity, not trust promotion or a repair of the
failed EXP-838 candidate.

EXP-840 adds optional `--verifier-connect-address` to the trusted HTTPS CLI.
It changes only the TCP destination; URL, TLS SNI/hostname validation and
authority-signed host trust remain bound to `testdev.local`. A real loopback TLS
regression skipped DNS and accepted only a certificate with the matching SAN;
invalid address shapes fail before readiness/prompt/Worker, and the chosen IP
is included in CLI preflight JSON. Focused suites: 57 passed; full offline suite:
1451 tests, 22 skipped. No testdev request or host configuration occurred. This
does not establish a remote verifier or independent-host trust.

EXP-841 restricts the optional dial address to explicit local IPv4 ranges,
loopback, and IPv6 ULA; global/documentation/reserved/multicast/unspecified and
IPv6 link-local values are rejected. The override cannot be combined with an
injected connection factory. Real loopback TLS confirms a trusted but
wrong-host SAN is rejected before HTTP while the `testdev.local` SAN succeeds.
Focused client suite: 30 passed; full offline suite: 1451 tests, 22 skipped;
`git diff --check` passed. No live endpoint was contacted; remote service,
out-of-band host trust, approval and publication remain unverified.

EXP-842 adds a credential-free local model option to the pinned Worker CLI. The
fixed `qwen2.5-coder:7b` endpoint is `http://127.0.0.1:11434/v1/chat/completions`;
the host-side transport performs at most one bounded request with no
Authorization header, while the proposal Worker remains in the existing
network-none container. CLI authorization is isolated under EXP-842 and rejects
DeepSeek-card/local-backend and EXP-842/DeepSeek mismatches before Docker
inspection, confirmation or readiness. Synthetic offline tests prove transport
bounds, response validation and that no credential source is constructed or
queried. EXP-843 preparation installed Ollama and pulled the single approved
model, but its exact confirmation was entered at an unrelated shell prompt; that
card is blocked. EXP-844 was confirmed at its visible CLI prompt and made
exactly one local model request. Ollama aborted cold loading and returned HTTP
499 after 30.273 seconds; no model output, candidate, approval or publication
exists. The fresh stage database remains integrity-valid with zero staged
artifacts, and the server was stopped without retry. EXP-845 adds a 180-second
timeout profile only for the local model path; remote DeepSeek remains capped at
30 seconds. EXP-846 made exactly one local Ollama request, which returned HTTP
200 after about 58.1 seconds (624 generated tokens), but the CLI emitted only
the sanitized `remote-snapshot-execution-failed` marker. Its fresh SQLite stage
passed integrity check and contains zero staged artifacts. Ollama was stopped
without retry; no proposal, verifier PASS, approval or publication exists. The
generic pipeline failure is not diagnosed. Focused EXP-845 tests passed (75
tests, 1 skipped); full offline suite passed (1465 tests, 22 skipped), and
`git diff --check` is clean. EXP-847 adds fixed sanitized markers distinguishing
unexpected snapshot-preparation failures from execution-pipeline exceptions;
HTTP and allowlisted execution-result mappings are preserved. Synthetic canary
tests confirm exception text is redacted. CLI suite passed (59 tests, 2
skipped); full offline suite passed (1467 tests, 22 skipped). This does not
retroactively identify EXP-846's failure. Remote verifier setup and trust remain
open gates.
EXP-848 stopped with `pinned-worker-runtime-failed` before Ollama recorded any
POST; its stage path remained absent. EXP-849 adds fixed sanitized readiness
failure codes and a new one-shot profile. Its readiness attempt stopped with
`github-readiness-ineligible` and `provider_attempts=0`; response status and
remaining quota are not available, so the cause is not claimed. No snapshot,
model call or stage followed. Focused CLI suite passed (31 tests); no retry,
credential or provider write occurred. R2/MVP remain OPEN.
Focused EXP-842 suites passed: 93 tests, 2 skipped; full offline suite passed:
1461 tests, 1439 passed, 22 skipped; `git diff --check` passed. No model,
GitHub, verifier or host service was contacted by this implementation batch.

EXP-861 / Batch QJ implements a one-shot loopback HTTPS server with a generated
`testdev.local` CA/leaf and in-process Ed25519 signer; TLS key material is
loaded through sealed Linux memfd descriptors, with no persistent-file or
environment fallback. The public bootstrap contains only the CA, signer
identity/fingerprints and bound port. Focused macOS suite passed (4 tests, 1
Linux-only skip). The exact pinned verifier image passed inspection, but its
single authorized Linux test run stopped before discovery because the image
lacks `cryptography`; no package/image changes or retry occurred. The full
offline suite ran 1474 tests (23 skipped) with one timing-sensitive failure in
an unrelated DeepSeek HTTP timeout test; that test passed in isolation.
`git diff --check` passed. At that checkpoint, Linux memfd/TLS behavior was
unverified and EXP-861 was temporarily BLOCKED. No testdev/SSH/tunnel,
credential, provider, deployment, or commit occurred. Process-memory erasure is
not guaranteed, another local testdev principal could race the unauthenticated
one-shot listener, and separate out-of-band trust enrollment is still required.
The subsequent Linux run and final acceptance are recorded below; R2/MVP remain
OPEN.

EXP-861 is reopened only for one network-isolated Linux verification after the
pinned verifier image was found to lack the declared `cryptography` dependency.
The revised card pins the three public PyPI wheel hashes, allows a temporary
read-only wheelhouse mount, and installs dependencies into the container's
bounded tmpfs for one test run. No image build/pull or testdev operation is
authorized; acceptance still requires the Linux test result and clean local
verification. The first wheel-enabled container invocation installed the
verified wheels but failed importing the native extension because tmpfs defaulted
to noexec; no test case ran. The card now permits one corrected run with
explicitly executable bounded tmpfs, still with network disabled and read-only
workspace/wheel mounts. That corrected request did not create a container: the
pinned raw image ID was not resolved by `docker run`, although read-only image
inventory shows the exact same ID cached under `agent00x-verifier:exp832-amd64`.
The card now requires tag-to-ID preflight and permits one `--pull=never` test
through that cached immutable ID. No image pull/build or testdev action is
authorized. The cached-tag test installed the three hash-pinned wheels, then
stopped at module import because `certifi` is also a declared project dependency
and is absent from that image; no test case ran. A final card amendment permits
only the host runtime's `certifi==2026.5.20` wheel with its PyPI hash, installed
from the read-only wheel mount into bounded tmpfs for one retest. That exact
cached-tag run passed all 4 focused Linux tests, including actual sealed-memfd
TLS-key loading and the signed loopback HTTPS exchange. Four wheels matched
PyPI SHA-256 metadata and were installed only into container tmpfs; the host
wheelhouse was then removed. Focused macOS tests passed (4, 1 skipped), the full
offline suite passed (1474, 23 skipped), and `git diff --check` passed. EXP-861
is ACCEPTED for local implementation/evidence only. No testdev, remote trust
enrollment, provider operation, deployment, publication, or commit occurred;
R2/MVP remain OPEN.

At the prior checkpoint, EXP-862 was READY for one fresh, strictly read-only
testdev metadata check (Python/cryptography/Docker and the exact verifier
image), pending `RUN EXP-862 ONCE` confirmation in OpenCode. It could not
transfer an image or launch a service, and prior image observations were stale.

EXP-862 was subsequently confirmed and completed once in the visible OpenCode
session. Its single read-only SSH result refreshed testdev metadata (Python
3.12.3, cryptography 41.0.7, Docker 29.1.3, UID 1000, `os.memfd_create`
available) and showed the exact pinned verifier image absent. No remote state
changed. The local Docker Desktop exposes that immutable image ID as
`linux/amd64` (51,052,447 bytes); the old convenience tag is absent.

EXP-863 / Batch QL then received the exact fresh OpenCode confirmation and ran
its one permitted pinned-image stream command. The local ID/platform preflight
matched, but the pipeline exited 1 with Docker `No such image`; the output does
not identify whether local `docker image save` or remote `docker image load`
reported the error, and no post-load inspection was produced. No retry or
cleanup occurred, so testdev's image-store state is unknown. EXP-863 is BLOCKED,
not accepted. Batch QM / EXP-864 then performed one separately confirmed,
strictly read-only inspection of only that exact ID; testdev's Docker daemon
returned its exact-image-not-found error (SSH succeeded, exit 1), confirming the
image is absent. No remote state changed. Batch QN / EXP-865 is READY for one
local-only `docker image save` diagnostic with output discarded, to isolate
whether the local source daemon can serialize the pinned image. No container,
service, verifier request, trust enrollment, approval, or publication occurred;
R2/MVP remain OPEN.

EXP-865 was added as a local-only diagnostic to separate source `docker image
save` from the remote failure, but its exact command exited 2 in the Codex shell
before the save stage and emitted no output. EXP-866 then confirmed the active
Docker context resolves through a local Unix socket and inspected the exact
pinned image successfully as `linux/amd64`; no non-local endpoint was contacted.
Thus EXP-865's failed command/preflight is not evidence that the source image
is absent; the empty output does not distinguish inspect failure from identity-
comparison mismatch. EXP-867 then saved the exact pinned image locally to `/dev/null` once
with `save_exit=0`, proving local serialization only. Batch QQ / EXP-868 is
READY for a separate freshly-confirmed one-session stream to testdev; unlike
EXP-863, it retains remote `docker image load` output before the exact-ID inspect
to make the result observable. No container/service/verifier request or trust,
approval, publication, or deployment operation occurred. R2/MVP remain OPEN.

Fresh Control Plane verification after EXP-868's local preflight: the standard
offline command `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s
tests -q` passed all 1474 discovered tests (23 skipped); `git diff --check`
passed. This validates the current local tree only and does not accept EXP-868
or prove any remote transfer. The visible OpenCode session still shows
`Type RUN EXP-868 ONCE to continue:` with an empty input; no SSH connection or
image transfer has occurred. The exact fresh OpenCode confirmation remains the
next gate. R2/MVP remain OPEN.

Deployment-scope audit: `containers/verifier/Dockerfile` copies the pinned
stdin/stdout verifier runtime and starts
`app_contracts.verifier_container_entrypoint`; it does not package the HTTPS
listener or `scripts/serve_ephemeral_signed_verifier_https.py`. That launcher
currently imports the host-side `src/app_contracts` tree and uses the host
Docker CLI to invoke the pinned verifier image. Therefore EXP-868, if later
completed, establishes only the child verifier image in testdev's image store;
it cannot by itself start the HTTPS endpoint. Before any endpoint startup, a
separate local, digest-pinned host-launcher bundle and an exact scoped testdev
transfer/start card are required. EXP-869 implements and accepts that local
packaging step: a deterministic archive was emitted to `/dev/null` with digest
`sha256:5c9e9a1c51528406cffa80bf7a7066b6ea75bd64462829c586646503ff371ceb`
(75 source members, 1,181,102 bytes); 9 focused tests, including extraction
and launcher import smoke, and the full offline suite (1483 run, 23 skipped)
passed, as did `git diff --check`. This is packaging evidence only: no launcher
code was transferred and no service was started.
This distinction does not change EXP-868's acceptance criteria or authorize
remote action. EXP-870 adds a pre-stream expected-bundle-digest check; the
fixed SHA-256 pin passed, malformed/extra arguments and digest mismatch emit no
archive bytes, and the real CLI does not ignore process arguments. Focused suite:
12 passed; full offline suite: 1486 run, 23 skipped; `git diff --check` clean.
This remains local packaging evidence only; no remote transfer/service or trust
promotion occurred. DRAFT EXP-871 specifies one digest-checked source-bundle
transfer and import-only smoke; it does not start the endpoint. The bundle still
requires an exact fresh OpenCode confirmation before any testdev write. R2/MVP
remain OPEN.

Fresh local preflight for the previously retained EXP-851 approval input: the
original `/private/tmp/agent00x-exp851-stage.sqlite3` still has WAL/SHM sidecars,
so it is not the approval CLI input. Its separate `VACUUM INTO` review copy
`/private/tmp/agent00x-exp851-approval-vacuum.sqlite3` was opened with SQLite
`mode=ro&immutable=1`; integrity is `ok`, and it still contains exactly staged
digest `sha256:a034c79c6552b5ebc4a2a788d439c579d0024f178675415e586192d0b4403209`
with artifact digest
`sha256:9bf03da33a2a311d8024055078fdbd8c9b9131169007dbb03e3483cbf3240796`.
No database was changed. This is same-host stage evidence only; it does not
substitute for independent verifier provenance or authorize approval.

EXP-872 also removes the fixed-port collision assumption from the one-shot
launcher: `--port 0` asks the OS for a loopback port, and the bootstrap reports
the actual validated unprivileged port. Fixed-port compatibility remains.
Focused suite: 5 run (4 passed, 1 Linux-only skip); full offline suite: 1487
run, 23 skipped; `git diff --check` clean. This remains local evidence and does
not establish a testdev service, tunnel, verifier trust, approval or publication.

EXP-868 was confirmed in the visible OpenCode session. Its displayed command
ran one stream; `docker image load` reported ID
`sha256:8a4b48afb7d51692ca4581a8acb0abeb570c0e8140561a8316a26ff2eaec7fbe`,
then inspection of the original pinned ID failed with `No such image` (exit 1).
The acceptance condition requiring the exact pinned ID and platform was not met.
Separately, a Codex shell invoked the same exact command and returned exit 2 with
no output; that result does not reveal whether it stopped at local preflight or
opened another SSH session. Therefore the card's exactly-one-session property
cannot be established and a duplicate stream cannot be ruled out. No further
remote command, retry, or cleanup is permitted under EXP-868. EXP-868 remains
BLOCKED, not accepted. EXP-873 then failed its local-only source-image preflight:
OpenCode's Docker daemon returned `No such image` for the original pinned ID.
Per the card, it stopped before displaying a confirmation gate; no SSH or remote
inspection occurred. EXP-873 is now BLOCKED. The source image's availability in
the executor Docker context must be recovered/re-established before a new exact
card can compare it with the load-reported remote ID. R2/MVP remain OPEN.

A subsequent read-only `docker image inspect` in the Codex shell could not find
the local pinned ID. This is consistent with the earlier exit-2 preflight, but
does not prove what that Docker context returned at the time of the separate
command; the successful OpenCode preflight and current Codex-shell result may
reflect different daemon contexts or changed local state. Docker describes
image IDs as content-addressable SHA-256 identities ([image pull reference](https://docs.docker.com/reference/cli/docker/image/pull/)),
so the different reported IDs are not attributed to storage-driver differences
without evidence. EXP-873's local preflight in OpenCode also returned
exact-image-not-found, so its remote inspection gate was never presented.
Content equivalence and the testdev image's platform/runtime metadata remain
unproven. No further SSH action has been run.

EXP-874 checked the previously accepted `agent00x-verifier:exp832-amd64` tag in
the fixed local Docker socket/config context; it also returned `No such image`
(exit 1). `git diff --check` passed; no Docker state changed. EXP-874 is BLOCKED.
EXP-875 is READY for a separately confirmed, single SSH read-only inspect of
only the `sha256:8a4b48…` ID reported by the EXP-868 load output. It can report
remote platform/layers/runtime fields but cannot establish equivalence to the
missing local source image. No remote verification has yet been run.

Batch QY / EXP-876 closes a local time-of-use gap in `SignedVerifierClient`:
when an authority-verified verifier-host decision is attached, the client now
rechecks enrollment and decision expiry immediately before the one-shot
transport call and again after signed-response verification, before marking the
attestation independently trusted. Synthetic regressions demonstrated both
failures before the fix: an already-expired decision dispatched, and a decision
expiring in-flight still promoted the signed result. Now the former fails before
transport and the latter fails after exactly one transport call; clients without
host-trust decisions remain explicitly audit-only. Focused client suite: 32
tests passed; full offline suite: 1489 tests (23 skipped); `git diff --check`
passed. No network, Docker, SSH, credentials, provider action, or commit was
used. This prevents expiry across the local verifier call only; revocation,
clock synchronization, independent host evidence, authenticated approval and
publication remain open. EXP-875 remains READY pending the exact user-entered
OpenCode confirmation; no remote inspect has run. R2/MVP remain OPEN.

EXP-877 / Batch QZ (#393) attempted one local read-only inspection of the
previously accepted target-runtime build input in the fixed Docker context. The
tag `agent00x-target-runtime:exp825-amd64` is absent (exit 1); `git diff --check`
passed. No fallback context, registry, pull/build, container or remote action
was used. EXP-877 is BLOCKED. Restoring the verifier source will require a new
exact card that re-establishes the public pinned build inputs and rebuilds
locally; this does not alter or retry EXP-868/875. The signed remote inspect
EXP-875 remains a separate user-confirmed gate. R2/MVP remain OPEN.

EXP-878 attempted a local-only preflight for offline rebuild from the accepted
15-wheel EXP-815 wheelhouse and plugin-only Docker config. Those filesystem and
plugin predicates passed, but the exact pinned base reference
`python:3.11.16-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e`
was absent in the fixed Docker context. No pull, build, container, or directory
creation occurred. EXP-878 is BLOCKED and requires a separately scoped anonymous
read-only fetch card before the offline rebuild. This is distinct from the
testdev inspection gate EXP-875. R2/MVP remain OPEN.

EXP-879 performed the one-card-approved anonymous pull of the exact public
Python base index digest with `--platform linux/amd64`. Docker reported the
digest as up to date, but the exact post-pull inspect returned
`ID=sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
OS=linux ARCH=arm64` (repo digest was the same e416 index). The card's amd64
criterion failed; no retry, alternate digest, build, or additional network
action was performed. EXP-879 is BLOCKED because it did not satisfy the
amd64 criterion. The immutable child digest previously accepted in EXP-820/821
was used directly in the separate EXP-880 card; no registry metadata retry was
needed. This does not affect the separate user-confirmed testdev inspect gate
EXP-875; R2/MVP remain OPEN.

EXP-880 used the child digest previously accepted by EXP-820/821, not the
parent OCI index that resolved locally as arm64 in EXP-879. After the fixed
wheelhouse/plugin preflight passed, one anonymous Docker Hub pull of
`python:3.11.16-slim@sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761`
completed. Local inspect confirmed the same image ID and RepoDigest with
`OS=linux ARCH=amd64`; `git diff --check` passed. No build, container, source
change, credentials or remote host operation occurred. EXP-880 is ACCEPTED.
The earlier EXP-878 remains terminally BLOCKED; only a new exact offline
rebuild task can consume this recovered local input. R2/MVP remain OPEN.

EXP-881 attempted the exact offline amd64 target rebuild from the accepted
wheelhouse and previously accepted child base digest. The temporary Dockerfile
copy was rewritten to that child digest; the project Dockerfiles were not
changed. The build exited 0 and produced image
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`
(`linux/amd64`), which differs from previously accepted target ID
`sha256:cc32f8cd0d05f92082b9e796ff28e3ea4567426844755b09650a6c37e83acce5`.
The card therefore stopped before verifier build or synthetic request. Its
temporary context was used read-only in EXP-882 and later for the verifier
build in EXP-883, then removed after success; the generated target image
remains local. No registry, credentials or remote host action occurred.
EXP-881 is BLOCKED. R2/MVP remain OPEN.

EXP-882 compared the retained EXP-881 context and image read-only. The copied
lockfile matched the current source exactly; the only Dockerfile difference was
the documented parent-index to accepted amd64-child substitution. The new
target image's four base rootfs layers matched the inspected amd64 child, and
its history showed the expected pip install and target copy. The prior accepted
`cc32…` image's layer/config metadata is no longer local, so the ID mismatch
cause remains unknown; no rebuild or image mutation occurred.

EXP-883 used the new local target candidate
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`
and built verifier image
`sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`
(`linux/amd64`) offline from the exact source/schema allowlist and its installed
dependencies. One synthetic request passed the existing network-none/non-root
verifier profile. The temporary export container and task context were removed
after success; images remain local. This is new same-host candidate evidence,
not proof of previous image identity, independent testdev trust, or approval.
EXP-886 aligned `brainbooster_target_profile.py` to the two images inspected
and exercised in EXP-881/883: target
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2` and
verifier
`sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`.
The verifier code digest `sha256:3b48eb35f4abb55a539aed008c6c2ded93df006b6dab2da3c9e541a7ab73c7b3`,
snapshot, candidate and authority settings were unchanged. Full offline suite:
1489 tests, 23 skipped. This enables local use of the new same-host candidate
pair; the old target image-ID discrepancy is still unexplained, and no
testdev enrollment, independent trust, approval or publication is proven.
R2/MVP remain OPEN.

EXP-887 repeated the single anonymous public-read-only pinned snapshot path
with the EXP-886 profile and new local target/verifier pair. One readiness,
commit, tree and runtime call, 23 blob GETs and one raw commit fetch completed;
the 23-file snapshot matched the fixed commit/tree/content digest. Target and
verifier passed, and stage digest
`sha256:4db19a974060e24ba88b5ff9298de255802c7c43c4917c6d90ac5256c8353926`
was read back and bound to a retained local mock receipt. The 462848-byte
SQLite artifact has SHA-256
`72e8f58ea40ebb759706aee5c86f95ebce591fd81175ab6d32db71f9fee83d62`.
Receipt remains `external_write=false`, `identity_authenticated=false`; observer
completeness is `partial`. This confirms the refreshed local pair across the
mock vertical slice, not a live Worker, independent remote verifier trust,
human approval, or real PR publication. R2/MVP remain OPEN.

EXP-888 rebuilt the target with the byte-identical project Dockerfile and lock,
without cache, pull, or build network, selecting `linux/amd64`. The build
completed but produced
`sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`,
not profile target ID
`sha256:9a6f710330d538514bc07f71cdfef2a7fdafaa266acbcb93039f892e0de217d2`.
The task stopped before verifier build. The new image/context remain local for
a separate candidate-verifier check; this increases evidence of an image-ID
reproducibility/configuration mismatch. R2/MVP remain OPEN.

EXP-889 built verifier image
`sha256:4025f0542be43cd1b58ef582c1a3a22a277b5cb8aab6f489cdf51013ba1ec2a4`
(`linux/amd64`) with the byte-identical project verifier Dockerfile, exported
dependencies from EXP-888 target `sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`,
and no-cache/no-pull/network-none build. One synthetic non-root/network-none
verifier request passed. Both images are local candidates; the active profile
still references the previous child-pinned pair pending repeat-build evidence.
No testdev trust, live Worker, approval or publication is established.
R2/MVP remain OPEN.

EXP-890 repeated the target build from the same byte-identical project
Dockerfile/lock, verified 15-file wheelhouse, and locally available amd64 base
child, with no cache, pull, or network. It succeeded but returned
`sha256:fc76bf3f55111ca1382975359add565c94c92a2d8c983d07d2ff0e59249f2903`,
different from EXP-888's `sha256:8e2316dfe6666d0a8acaa5042180a84c6bdefb8feb38ee038fe9c89a2c3ddbac`.
The task stopped before verifier build or synthetic request; the context and
image remain local. Source image reproducibility is therefore unproven, and
R2/MVP remain OPEN.

EXP-891 compared the two target image records without starting containers.
The first five rootfs layers match, while the final dependency layer differs;
bounded image config fields match and Created timestamps differ. The EXP-890
Docker-history query failed because the daemon reported the layer snapshot
missing. No retry was made. The local image-ID mismatch is narrowed to the
final copied dependency layer, but its file-level cause and daemon snapshot
health remain unverified. R2/MVP remain OPEN.

EXP-892 compared `/opt/target-python` copied from stopped EXP-888/890
containers. Hundreds of generated `__pycache__/*.pyc` files differ while
package source files were not reported as different. The source Dockerfile
does not pass pip's `--no-compile`; timestamp-bearing bytecode is the likely
cause of final-layer/image-ID drift. This is a cause hypothesis, not yet a
verified fix or reproducible build. R2/MVP remain OPEN.

EXP-893 added pip `--no-compile` in the target dependency install. The full
offline suite passed (1489 tests, 23 skipped). No Docker image was built in
that task, so image reproducibility and the resulting runtime profile remain
unverified. R2/MVP remain OPEN.

EXP-906 built two no-cache/no-pull/network-none target images from the current
Dockerfile; IDs differed (`sha256:e03c5d3e…` and `sha256:0b11293e…`). Both
were amd64, and no verifier was built. EXP-907 found `/workspace` metadata
identical (mtime `1791572324`, mode 755, owner/group 501:0, size 64), ruling it
out. EXP-908 checks whether remaining rootfs layers or only config metadata
differ. R2/MVP remain OPEN.

EXP-908 found first-five-layer DiffIDs match, while the final layer differs
(`sha256:5ec03402…` vs `sha256:79d88056…`); image Created timestamps differ.
EXP-909 compared `/tmp`: both contain only the same metadata for `/tmp`
(mtime `1789689600`, mode 777, owner/group 501:0, size 64); no mountpoint
remains. EXP-910 checks the final `/opt` subtree. R2/MVP remain OPEN.

EXP-894 performed two no-cache/no-pull/network-none builds from one
byte-identical source context after `--no-compile`. Both targets inspected as
amd64 but IDs differed: `sha256:c7017777…` versus `sha256:4134ac8f…`. No
verifier was built; rootfs-layer and image-config differences are not yet
separated. The task context and images are retained. R2/MVP remain OPEN.

EXP-895 inspected rootfs layer digests for both images. The first five layers
match; the final dependency layer differs (`sha256:ebb0bf8c…` vs
`sha256:590cc335…`), as do image Created timestamps. This rules out config
timestamp alone as the image-ID cause. File content versus metadata in the
copied dependency tree remains to be determined. R2/MVP remain OPEN.

EXP-896 copied `/opt/target-python` from stopped containers and compared the
trees. `diff -qr` found identical paths and file bytes despite different final
layer digests, locating the residual difference to filesystem/tar metadata.
No container was started. The exact metadata field and a deterministic fix
remain unverified. R2/MVP remain OPEN.

EXP-897 compared path, mtime, mode, owner/group and size for all dependency
entries. Mode, owner/group, size and paths matched; every exported entry's
mtime differed by exactly five seconds (`1791743424` versus `1791743429`).
This identifies pip install's build-time mtimes as the remaining layer drift.
A deterministic normalization and repeated image-ID check remain pending.
R2/MVP remain OPEN.

EXP-898 added `find /opt/target-python -exec touch -h -d '@0' {} +` after
successful pip installation; `--no-compile` and both pinned base references
remain. The full offline suite passed (1489 tests, 23 skipped). Repeated image
IDs are not yet demonstrated. R2/MVP remain OPEN.

EXP-899 ran two no-cache/no-pull/network-none target builds with the normalized
Dockerfile. Both inspected as amd64 but IDs differed:
`sha256:1f05d8e7…` versus `sha256:33a67335…`. No verifier build occurred; the
context and images are retained. Rootfs-layer versus image-config drift is
not yet isolated. R2/MVP remain OPEN.

EXP-900 found matching first five rootfs layers but different final-layer
digests (`sha256:9e7b5924…` vs `sha256:cc74aa46…`) and Created timestamps for
EXP-899. Builder-stage mtime normalization did not make the final COPY layer
identical. Final filesystem metadata still needs inspection. R2/MVP remain
OPEN.

EXP-901 found matching metadata for entries copied from inside
`/opt/target-python`; however, the copy form omitted the directory entry
itself. The result cannot establish whether the root directory mtime causes
the residual layer drift. EXP-902 checks that entry directly. R2/MVP remain
OPEN.

EXP-902 inspected the actual copied `/opt/target-python` directory: both images
report mtime 0, mode 755, owner/group 501:0 and size 1088. Child metadata and
file content also match, while the final layer digests do not. The remaining
cause may be tar/layer serialization or unmeasured metadata; no cause is yet
established. R2/MVP remain OPEN.

EXP-903 saved the two normalized images and confirmed differing final layer
tar hashes (`d15f46f6…` vs `81ac1c91…`). Sorted verbose listings exceeded the
output limit, preventing a reliable comparison. The visible `opt/` parent
entry carries build-time date; EXP-904 checks that directory's exact metadata.
R2/MVP remain OPEN.

EXP-904 measured `/opt` from both final images. Mtime was `1791743701` versus
`1791743708` (the seven-second build interval), while mode, owner/group and
size matched. This identifies the residual variation: builder-stage
normalization omits the parent directory that the final COPY creates. A
deterministic source/copy adjustment and repeat build remain pending. R2/MVP
remain OPEN.

EXP-905 changes the builder normalization root to `/opt` and replaces final
`COPY` with a read-only BuildKit bind mount plus `cp -a` and runtime mtime
normalization in one RUN layer. The full offline suite passed (1489 tests,
23 skipped). No Docker build was run; image reproducibility remains
unverified. R2/MVP remain OPEN.

EXP-915 established that the distinct final-layer DiffIDs match the SHA-256 of
the respective uncompressed TAR streams; the first difference is the `root`
directory header mtime (`1791744099` vs `1791744104`). EXP-916 had an invalid
preflight architecture expectation and ran no build/test. EXP-917 normalized
`/` mtime and passed 1489 offline tests (23 skipped), but two offline amd64
builds still differ only in the final RootFS layer (`sha256:e8d69095…` vs
`sha256:e07e674c…`). EXP-918 found the exported `root` TAR entry still has
wall-clock mtime (`1791744745` vs `1791744751`) despite the Dockerfile
`touch /`; `/opt` remains epoch-normalized. EXP-919 tests BuildKit's
`SOURCE_DATE_EPOCH` plus image exporter `rewrite-timestamp=true`, but the
first build was rejected because the option conflicts with `--load`; no image
was produced. EXP-920 runs image export without `--load` and compares recorded
digests, but failed with the same conflict because exporter storage still
unpacks by default. EXP-921 explicitly sets `store=false`. Runtime profile
remains unverified and R2/MVP remain OPEN. EXP-921 produced differing top-
level OCI index digests, with metadata showing per-build provenance refs.
EXP-922 disables provenance attestations and compares the image manifest
digests only; both exports matched the same linux/amd64 Docker manifest digest
`sha256:1274d036…`. EXP-923 removed the ineffective Dockerfile `touch /` and
passed the full offline suite (1489 tests, 23 skipped). EXP-924 repeated the
fixed-epoch export from a fresh context copied from the cleaned Dockerfile;
both no-cache offline builds produced identical linux/amd64 Docker manifest
digest `sha256:95410961…`. EXP-925 checks the OCI archive output path. No image
is loaded or run, so the runtime profile and testdev verifier remain
unverified; R2/MVP remain OPEN. EXP-925 produced byte-identical OCI archives
(SHA-256 `4c80035f…`) with matching manifest, config, six compressed layers,
six DiffIDs and linux/amd64 platform. EXP-926 loaded the archive locally;
Docker reported its manifest digest as image ID, not the config digest.
EXP-927 verified that exact ID is linux/amd64 with matching six RootFS DiffIDs.
EXP-928 passed one non-root, read-only, network-none dependency import check
(FastAPI 0.142.2, Pydantic 2.13.5, Uvicorn 0.54.0). EXP-929 pinned this image
ID in the target profile and passed the full offline suite (1489 tests, 23
skipped). EXP-930 passed the existing local Docker sandbox security test:
network/DNS blocked, read-only snapshot/root, non-root, zero capabilities,
resource bounds, and synthetic API/host canaries excluded. EXP-931 checks for
the exact pinned target snapshot locally before app-level container testing.
EXP-932 fetched one commit-pinned public archive and confirmed the 23-file
mode-aware tree digest matches the profile value; the distinct content-only
digest does not, despite the profile field name. EXP-933 ran the HTTP/DB probe
once in the pinned sandbox and failed at malformed-status. Read-only source
inspection found unchecked integer coercions in the target endpoint; the
probe did not reach the valid-write assertion and was not retried. A separate
disposable-copy remediation is assigned as EXP-934 without changing the
pinned snapshot. EXP-934 passed the same HTTP/DB probe on that disposable
candidate (`malformed=5`, `overflow=1`, `sqlite_range=10`, `valid=1`); this is
not evidence of upstream change, and its integer-only rule could break numeric
string inputs accepted by the base route. EXP-935 passed one fresh codeload →
containerized synthetic Worker → bounded target probe → pinned Docker
verifier → exact stage save/readback → preview → same-digest local-mock receipt
composition in 11.551s. It records one Worker channel call, no credentials or
provider calls, `external_write=false`, and no authenticated approval or PR.
The mock receipt does not establish independent host trust. EXP-936 verified
one ASCII-integer-string session payload over loopback HTTP against the
EXP-935 candidate, returning 200 and one exact SQLite row; only disposable-
candidate compatibility is proven. EXP-875 testdev verification remains
open; R2/MVP remain OPEN.
EXP-937 additionally passed the fresh public REST/raw-commit Docker
composition through synthetic Worker, pinned verifier, signed verifier
attestation, digest-bound synthetic approval and enrolled local-mock receipt
(32.766s; readiness=1, commit=1, tree=1, blobs=23, raw commit=1, runtime=1).
Receipt remains `identity_authenticated=false`, `external_write=false`, and
observer completeness `partial`; no stage retention or real publication.
The full offline suite after this continuation passed 1489 tests, 23 skipped;
`git diff --check` passed. EXP-938 renamed the internal Python pin to
`PINNED_SNAPSHOT_TREE_DIGEST` while preserving `PINNED_CONTENT_DIGEST` as a
backward-compatible alias; canonicalization and wire fields are unchanged.
The full offline suite after EXP-938 passed 1490 tests, 23 skipped.

EXP-939 found that the previously pinned verifier-host bundle digest became
stale after included project sources changed. Two bounded local builds using
the current expected digest both succeeded with
`sha256:13b6c68db8dee5ee8a8e61825ce95b1ca76fb183d02709a7bcc8342b77f0f643`,
75 members and 1,182,276 source bytes; the focused bundle suite passed (12
tests), as did `git diff --check`. No bundle artifact was saved and no network,
SSH, remote state, credential, or service was used. Do not use EXP-871's stale
bundle pin; any transfer/start requires a new exact card and fresh user
confirmation. EXP-875 remains pending that visible OpenCode confirmation;
independent verifier trust, authenticated approval, and real controlled PR
publication remain open, so R2/MVP remain OPEN.

EXP-940 confirmed via one exact local read-only Docker inspect that the
profile-pinned verifier image `sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`
is present in the fixed local context as `linux/amd64`, with nine rootfs
layers, the expected verifier entrypoint, user `65532:65532`, and workdir
`/work`. `git diff --check` passed. No image mutation, container, network,
SSH, or remote action occurred. The local image can be used to prepare a new
explicit transfer card, but no testdev presence, independent host trust,
approval, or PR publication is proven. EXP-875 was superseded because it
targeted the stale image reported by the failed EXP-868 transfer; EXP-941 is
the current exact-pin read-only testdev inspection and awaits fresh user
confirmation in visible OpenCode.

EXP-943 adds a Linux-only test for the actual one-shot HTTPS launcher composed
with its ephemeral TLS identity and one signed synthetic verifier response.
Its single Docker attempt stopped before discovery because the pinned image
lacks `cryptography` (`linux/amd64` image on `linux/arm64/v8` host); no test
executed and no image/dependency/network state changed. `git diff --check`
passed. A new task must explicitly provide hash-verified dependencies in
bounded tmpfs and set the platform before this behavior can be accepted. This
does not change the separate testdev/independent-host gate.
EXP-944 used the retained hash-verified wheels in one exact pinned
`linux/amd64`, network-none Docker run. The integration test reached the
launcher but returned 2 because the test sent a one-file `fixture/repository`
input to the launcher's fixed 23-file production profile. No host/external
state changed; EXP-944 is blocked and will not be retried. EXP-945 changes only
the test invocation to use one consistent synthetic profile for server,
client, and request, and permits one local rerun from the retained wheelhouse.
Independent verifier-host trust and the testdev gate remain open.
EXP-945's single separate local run passed the profile-compatible synthetic
launcher integration in the exact pinned `linux/amd64`, network-none Docker
image (1 test, 0.255s). The test asserts valid response signature, one
verifier/request, HTTP 200, bounded closure, and
`independent_host_trust_established=false`; production profile defaults are
unchanged. Dependencies came only from the retained four hash-verified wheels
and were installed into container `/tmp`. No external network, SSH, host
installation, credential, provider, approval, or publication was used.
`git diff --check` passed. This is local launcher evidence, not independent
verifier-host trust; EXP-941 and the approval/publication gates remain open, so
R2/MVP remain OPEN.
The supplemental full offline suite after EXP-945 passed 1491 tests with 24
skipped in 81.305s (`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover
-s tests -q`, exit 0); `git diff --check` remained clean.
On 2026-10-12 a stale OpenCode session for superseded EXP-875 reports one
execution of its historical read-only SSH inspect after the exact
`RUN EXP-875 ONCE` phrase. It exited 1 with
`template parsing error: template: :1:140: executing "" at <.Config.Cmd>: map has no entry for key "Cmd"`;
no image metadata fields were captured and no retry/follow-up occurred. This
does not establish image presence or identity and is not EXP-941 evidence.
At this historical checkpoint EXP-941 was the current READY gate for pinned
image `sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`;
the subsequent result is recorded below. Independent verifier-host trust,
authenticated approval, and controlled PR publication remain unproven.

Control Plane checkpoint before EXP-941 execution on 2026-10-12: the queue's stale `READY` labels for
EXP-892, EXP-909, EXP-910 and EXP-911 were synchronized to `ACCEPTED` using
their already-recorded acceptance evidence; EXP-941 is now the sole `READY`
card. A fresh visible OpenCode session reread the card and `AGENTS.md`, passed
`git diff --check`, and displayed its exact `Type RUN EXP-941 ONCE to continue:`
gate. At that checkpoint no matching response had been entered and no SSH or
testdev command had run. The stale EXP-875-session input was not reused. The
subsequent exact confirmation and one read-only inspect are recorded below.
Independent verifier-host trust and runtime evidence, authenticated
digest-bound human approval, and controlled PR publication remain OPEN.

Supplemental local evidence 2026-10-12: the retained EXP-851 stage database
still exists at `/private/tmp/agent00x-exp851-stage.sqlite3` (16 KiB); a
read-only SHA-256 check returned its recorded digest
`261fd8e4a45b6dc427e75b6e5731bc20ee3e37f01b543aad147d42750297ef8a`.
The database was not opened or modified. This establishes byte-identity with
EXP-851 evidence, not independent verifier trust; EXP-852's separate
approval-request attempt remains blocked and is not retried.

Local change 2026-10-12 adds `--as-of-recorded-at` and
`--about-occurred-at` historical report selectors. The first limits rows to
what the journal recorded by the cutoff and does not resolve current artifact
store contents. The second includes events that occurred by the cutoff even
if they were recorded later, marks those events, and may resolve current
artifact metadata while flagging historical availability as unknown.
Checkpoints in the latter view are limited by trigger-event and `created_at`
timestamps, but their journal-availability time is unknown and reported as a
gap. Both cutoffs normalize to UTC and remain local, unattested timestamps.
Focused observer-report suite: 13 tests passed; full offline suite: 1493 tests
(1469 passed, 24 skipped); `git diff --check` passed.
This improves historical query behavior but does not authenticate time,
establish collector completeness, or restore an executable workspace. At this
point EXP-941's fresh OpenCode confirmation was still pending; its later result
is recorded below. Independent verifier trust, authenticated approval,
controlled PR publication, and R2/MVP remain OPEN.

EXP-941 result, 2026-10-12: after the delegated Control Plane approval was
entered exactly in the visible OpenCode session, its single strict SSH
read-only inspect returned `Error response from daemon: No such image:
sha256:7ec5a8948515b187ca0761998235ecaf98747a83da12e5eda877ececcb70f61a`
(`SSH_EXIT=1`). The exact local image therefore is not present on testdev;
remote metadata comparison was impossible. `git diff --check` passed
(`DIFF_CHECK_EXIT=0`). No retry, remote-state change, cleanup, commit, or push
occurred. EXP-941 is accepted as a completed negative inspection; EXP-942's
image-present dependency is unmet. Transfer/import needs a new exact card and
fresh confirmation. Independent verifier-host trust, runtime evidence,
authenticated approval, controlled PR publication, and R2/MVP remain OPEN.

EXP-946/947 local follow-up, 2026-10-12: one `docker image save` of the exact
local verifier image produced a retained 51,071,488-byte archive at
`/private/tmp/agent00x-exp946-verifier-image.tar` (SHA-256
`6d9326c9c4f6741aa51e5df74c0af0129b8de1ae56158192963f75abe9a24879`). Its
config digest (`sha256:3dd6042857a58aaefd3210bc7c787ff96e1fb7929426efb4b8120f1e83368034`)
differs from Docker's pinned image ID; EXP-946's equality criterion did not
pass. EXP-947 confirmed one manifest, nine layers, and config `rootfs.diff_ids`
matching the nine EXP-940 values, but raw layer-tar hashes did not match those
DiffIDs; the cause remains unresolved. The official image spec defines DiffID
as SHA-256 of the uncompressed layer tar, so the mismatch was not dismissed as
normal serialization. No retry, extraction, network, or remote operation.
EXP-949 then performed one local Docker load of the retained archive: Docker
returned the exact pinned image ID, and a subsequent inspect matched
`linux/amd64` plus all nine ordered EXP-940 RootFS DiffIDs. This is local
archive-load evidence, not remote presence/trust. EXP-948's local preflight
passed, but its exact SSH command was blocked twice by OpenCode's local
permission rules before execution. No SSH session, bytes transferred, or
testdev change occurred. EXP-948 is BLOCKED pending an explicit narrowly
scoped OpenCode permission and a new card/fresh confirmation; do not retry or
route around the permission layer. Independent verifier-host trust, runtime
service evidence, authenticated approval, controlled PR publication, and
R2/MVP remain OPEN.

Current stage review 2026-10-12: the retained EXP-851 vacuum review copy
`/private/tmp/agent00x-exp851-approval-vacuum.sqlite3` remains readable in
read-only mode (database SHA-256
`31f4ce1e3d1aa64558bf7e606c0e847541ca2c4424a21d52d1797688963f6e0e0`). The
exact stage `sha256:a034c79c6552b5ebc4a2a788d439c579d0024f178675415e586192d0b4403209`
revalidated to artifact digest
`sha256:9bf03da33a2a311d8024055078fdbd8c9b9131169007dbb03e3483cbf3240796`,
verified-content digest
`sha256:2831b3a117cbed4b370c157255681bcb00532db98fa18c09362a9d4d82f9cfce`,
and verifier verdict `pass`. The verifier ID is the pinned local Docker image
and code digest; preview reports `signed_evidence_available=false`,
`verifier_trust.status=not_recorded`, `approval=not_created`, and
`publication=not_attempted`. This is current local review evidence only and
does not qualify the stage for authenticated approval or controlled PR
publication.

EXP-950 local R4 result, 2026-10-12: one strict declarative replacement
applied to a workspace produced by the actual read-only artifact materializer.
The step bound the exact `LearningCorrection` ID, version and canonical digest,
source manifest digest, and file preimage/replacement digests. It modified only
a separate in-memory result; source workspace bytes and metadata stayed
unchanged. The deterministic result digest and content-free evidence include
no file contents. Wrong correction ID/version/content/checkpoint/status,
source/preimage/replacement digest, malformed schema/base64,
unsafe/missing/case-variant/duplicate paths, no-op, oversized and
credential-like replacements failed closed. Focused simulation suite passed 14
tests; the full offline suite passed 1496 tests with 24 skipped in 117.198s;
`git diff --check` passed. A disposable SQLite fixture in `TemporaryDirectory`
fed the existing read-only materializer and was removed automatically; no
persistent/project database was written. No restored code was executed, no
target tests were run, and no network/remote effect occurred. This advances
only the R4 in-memory alternative-step representation; it does not establish
sandbox replay isolation, learning transfer or any R2 verifier-trust/approval/
publication gate.

Control Plane follow-up 2026-10-12: EXP-948's blocked transfer was superseded
by Batch TV / EXP-951. OpenCode's project config now allows external-directory
access only to `/private/tmp/agent00x-exp946-verifier-image.tar`; other external
paths remain denied, direct read/edit of that archive is denied, and `bash`
remains ask-gated. A new OpenCode session ran EXP-951's local preflight only:
archive size 51,071,488 bytes and SHA-256 matched, local inspect returned the
expected image ID, `linux/amd64`, and nine RootFS layers; `PREFLIGHT_EXIT=0`.
`git diff --check` passed and the 58-entry worktree count was unchanged. The
session now visibly waits at `Type RUN EXP-951 ONCE to continue:`. No SSH,
transfer or testdev mutation occurred; the task remains READY pending that
fresh user confirmation. Current full offline suite was re-run after this
worktree state: 1496 tests, 24 skipped, exit 0 in 102.685s. This validates
local contracts only; it does not establish remote verifier availability or
trust, authenticated approval, or controlled PR publication. R2/MVP remain
OPEN.

Batch TW / EXP-952 local follow-up 2026-10-12: after subsequent source changes,
the fixed 75-member verifier-host bundle reproducibly builds twice with digest
`sha256:66a6dd3ac322f98ea1d2f64ae3a624e625068c70ad4bbf92bad002230ff23046`
and 1,196,954 source bytes. The focused bundle suite passed 12 tests and
`git diff --check` passed. Archive bytes went only to `/dev/null`; nothing was
saved or transferred. EXP-939's previous digest
`sha256:13b6c68db8dee5ee8a8e61825ce95b1ca76fb183d02709a7bcc8342b77f0f643` is
stale. No testdev image or bundle, independent verifier trust, authenticated
approval, or controlled PR publication is established; R2/MVP remain OPEN.

Control Plane follow-up 2026-10-12: the user entered the fresh exact
`RUN EXP-951 ONCE` confirmation in the visible OpenCode session, but the
executor-level `external_directory: deny` blocked the archive access before the
SSH command started. There were zero SSH sessions, zero transferred bytes, and
no testdev change; EXP-951 is now BLOCKED and that confirmation is spent. To
honor the user's instruction that Codex may authorize scoped OpenCode
experiments, the executor agent now permits only the exact retained archive
path for external-directory access; direct read/edit remain denied, all other
external paths remain denied, and shell commands still require OpenCode
approval. The official [OpenCode agent permissions
documentation](https://opencode.ai/docs/agents/) confirms that path-pattern
rules can be set per agent; the [permissions documentation](https://dev.opencode.ai/docs/permissions/)
confirms that external path access is separately gated. Replacement EXP-954 is
READY with a new exact confirmation and one-shot scope; EXP-953 remains DRAFT
until EXP-954 is accepted. No new OpenCode run or remote action has started.
This permission exception is experimental and does not establish verifier
availability/trust, authenticated approval, controlled PR publication, or
R2/MVP completion.

Control Plane check after that update, 2026-10-12: OpenCode UI still showed the
previous malformed `-954` session, not the exact EXP-954 confirmation prompt.
A new executor request was canceled when UI text entry corrupted its task ID;
only repository status and task-directory listing were run, and a follow-up
queue grep was denied. No EXP-954 local preflight, SSH, transferred bytes or
testdev change occurred. Do not enter a confirmation in the malformed session.
The corrected EXP-954 card remains READY for a clean OpenCode session; its
`RUN EXP-954 ONCE` token has not been requested or consumed.

EXP-954 Control Plane local preflight, 2026-10-12: the exact card command was
run read-only outside OpenCode and exited 0. The retained archive matched its
regular-file/non-symlink, byte-size and SHA-256 pins; local Docker inspect
returned the expected image ID, `linux/amd64`, and nine ordered RootFS DiffIDs.
`git diff --check` passed. This establishes local transfer readiness only;
OpenCode has not yet presented the fresh confirmation prompt, no SSH or remote
change occurred, and EXP-954 remains READY. Independent verifier-host trust,
service operation, authenticated approval and controlled PR publication are
still unproven; R2/MVP remain OPEN.

EXP-954 OpenCode attempt, 2026-10-12: the user supplied the fresh exact phrase
after the visible prompt in that session. The exact local preflight passed
(`PREFLIGHT_EXIT=0`) and `git diff --check` passed. OpenCode then rejected the
single card command before execution because the active session's effective
`external_directory` policy denied the retained archive path; there were zero
SSH sessions, zero bytes transferred, and no testdev changes. The exact-path
allow exists in current repository configuration, so the observed discrepancy
is between that configuration and the old session's effective rules. The
phrase is spent and EXP-954 is BLOCKED; no workaround or retry was attempted.
Batch TZ / EXP-955 is a local-only permission check in a fresh executor session.
Independent verifier-host trust, service operation, authenticated approval,
controlled PR publication, and R2/MVP remain OPEN.

EXP-955 was accepted 2026-10-12 after a fresh OpenCode executor session ran
the exact EXP-954 read-only local preflight (`PREFLIGHT_EXIT=0`) and
`git diff --check` (`DIFF_CHECK_EXIT=0`). The pinned archive and Docker image
identity/platform/nine ordered RootFS DiffIDs matched local EXP-940 evidence.
No SSH, network, remote read/write, file change, or commit occurred. This
confirms only read-only path access in a fresh session; it does not authorize
transfer. Batch UA / EXP-956 is READY with a new exact one-shot confirmation
requirement for the bounded testdev image import. R2/MVP and independent
verifier trust, authenticated approval, and controlled publication remain OPEN.

Control Plane local verification, 2026-10-12: the standard offline suite
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q` completed
successfully: 1,497 tests run, 25 skipped in 97.306 seconds. This validates the
current local test suite only; it does not perform or substitute for EXP-956's
separately confirmed testdev image import, nor close the verifier-trust,
approval, or publication gates. EXP-956 remains READY in the fresh OpenCode
executor session `ses_ecff710f0ffeAB3vfhlNjx645Z` (2026-10-12). Its exact local
preflight returned `PREFLIGHT_EXIT=0`; local Docker inspect matched the pinned
image ID, `linux/amd64`, and nine ordered DiffIDs. `git diff --check` returned
`DIFF_CHECK_EXIT=0`. OpenCode visibly presents `Type RUN EXP-956 ONCE to
continue:` in that same session. The remote SSH transfer has not started; zero
bytes were sent and testdev was not contacted. No remote operation may start
until the user enters the exact phrase in that OpenCode session. R2/MVP remain
OPEN.

Control Plane queue correction, 2026-10-12: the DRAFT Batch TX / EXP-953
prerequisite was updated from blocked EXP-954 to require replacement EXP-956
acceptance. EXP-956 is still READY and awaiting its exact one-shot confirmation;
EXP-953 remains DRAFT until the image is confirmed present on testdev. It will
require its own fresh `RUN EXP-953 ONCE` confirmation and will not inherit
EXP-956 permission or approval. `git diff --check` passed.

EXP-959 / Batch UD was accepted 2026-10-12 after the public pinned-snapshot
integration executed once against the current target and verifier image pins.
It produced a same-run local mock receipt for staged digest
`sha256:154a44496a14d971dd2068bb65a6a902d0379306b4d2784f193320fc3b3ef88b`;
the receipt explicitly has `external_write=false`,
`identity_authenticated=false`, and partial observer completeness. This is
current-pin local composition evidence only: no live model, trusted remote
verifier, authenticated approval, or provider publication was involved. The
full offline suite was rerun after this evidence and passed as recorded above;
R2/MVP remain OPEN.

EXP-960 / Batch UE, 2026-10-12: a fresh profile and CLI mapping were added for
one credential-free local-Ollama run on the current pinned snapshot. The
focused CLI suite passed (32 tests), Docker image IDs/platforms matched, and
the locally installed model was confirmed without downloading. The one-shot
run stopped at its single anonymous readiness fetch with
`github-readiness-fetch-failed`; no snapshot/model/Worker/verifier request or
stage creation followed, and no retry was made. The resulting observer DB is
integrity-valid but has cursor 0. This is a bounded failure, not new Worker
evidence; the full offline suite result above predates this profile-only edit.
Post-attempt review found the task card omitted a required explicit expiration,
so this attempt is not treated as conforming external-read evidence. The
EXP-960 runtime profile was revoked to prevent reuse; this card must not be
retried and any future attempt needs a complete replacement card. The focused
CLI suite passed again (32 tests) after revocation, including rejection of the
spent profile before preflight; `git diff --check` passed.

EXP-961 / Batch UF, 2026-10-12: readiness transport exceptions now map to
closed-set failure categories for timeout, TLS, DNS, connection, HTTP protocol,
system network, invalid TLS trust/response and already-used readiness. Operator
evidence emits only typed allowlisted categories and falls back to the generic
marker for arbitrary or mutated values; raw exception messages remain redacted.
Observer failure events retain their existing generic code. Focused suites
passed (46 tests), full offline suite passed (1,501 tests, 25 skipped), and
`git diff --check` passed. No live HTTP or external operation ran.

Control Plane refresh, 2026-10-12: EXP-953's prior verifier-host bundle digest
became stale after EXP-961 changed an included module. Two local builds matched
at `sha256:10b62b27be5281f56c5e9d2f99e8bc12aa0e2fc8c21be45b20954d53e1341920`
(75 members; 1,199,304 source bytes); the focused bundle suite passed (12
tests). The DRAFT card now pins that digest and destination. No archive was
saved or transferred; EXP-953 remains DRAFT pending successful image import
and its own fresh confirmation. In the OpenCode EXP-956 session, local
preflight and `git diff --check` passed and the exact `RUN EXP-956 ONCE` was
accepted. The transfer command was then denied before execution by the active
session's effective `external_directory` policy: zero SSH sessions, zero
bytes, no testdev precheck or state change. The confirmation is spent;
EXP-956 is BLOCKED, with no retry or alternate route attempted. A future
transfer requires a separately reviewed permission/configuration change and a
replacement card. For EXP-991, local preflight passed (10 focused tests; 1,521
full-suite tests, 25 skipped; `git diff --check` clean; exact image pin and
runner hash matched). The visible `RUN EXP-991 ONCE` gate was confirmed once in
the same OpenCode session. Its sole stream attempt returned
`REMOTE_LOAD_IDENTITY_UNCONFIRMED` (exit 18), so import success is unconfirmed
and remote image-store state is unknown. No retry, cleanup, remote diagnostics
or second SSH occurred; another check needs a replacement card and fresh gate.
R2/MVP remain OPEN. Local diagnosis for EXP-992: the exact pinned local image
has RepoTag `agent00x-verifier:exp883-amd64`; Docker documents that tagged
archives produce `Loaded image: <tag>` output, whereas the previous runner only
accepted `Loaded image ID: <digest>`. The runner now requires that exact tag
line and then exact pinned remote inspect metadata. Focused tests (10), the full
offline suite (1,521 tests, 25 skipped), `git diff --check`, local image pin and
runner SHA-256 all pass. EXP-992's one newly gated import nevertheless returned
`REMOTE_LOAD_IDENTITY_UNCONFIRMED`, not `IMAGE_IMPORT_CONFIRMED`. The shell tool
did not expose the runner exit status; a subsequent `$?` read returned `0` but
is unreliable and does not meet the acceptance contract. No retry, cleanup,
remote diagnostics or second SSH occurred. Remote image-store state remains
unknown. EXP-993's one newly gated read-only check returned only
`IMAGE_NOT_VERIFIED` / wrapper exit 22; this cannot distinguish SSH/Docker
failure or timeout, and no retry or further diagnosis occurred under that
card. EXP-994's single freshly gated read-only SSH check returned
`PINNED_IMAGE_NOT_INSPECTABLE` (wrapper exit 26). SSH and Docker daemon
responded, but Docker could not inspect the pinned ID; the fixed marker does
not distinguish an absent image from another inspect failure. No retry,
diagnosis, cleanup, or additional SSH occurred. EXP-994 is now BLOCKED, and its
gate is spent. Any further testdev contact requires a replacement card and a
fresh gate. This result does not prove image absence, verifier readiness,
independent host trust, authenticated approval, publication, or MVP completion;
R2/MVP remain OPEN.

EXP-995 did not run: after its exact gate was entered, OpenCode's shell
permission prompt appended a local `echo` not listed in that card. Control
Plane denied the mismatched command; there was no SSH/Docker invocation. Its
gate is spent and the card is BLOCKED. Replacement Batch VR / EXP-996 explicitly
included that local exit echo in its scope. A fresh preflight passed and, after
the exact `RUN EXP-996 ONCE` gate, one read-only SSH invocation ran
`docker image ls --no-trunc --quiet`. The sanitized result was
`PINNED_IMAGE_ID_NOT_LISTED` (wrapper exit 0): the exact pinned verifier image
ID is not present in Docker's image-ID list on testdev. The query suppressed
all image IDs and did not establish why prior imports failed, nor whether an
image with another ID is tagged under the expected name. No retry, inspect,
repair, or further remote operation occurred. EXP-996 is accepted as this
limited diagnostic only. The standard offline suite passed 1,521 tests with 25
skipped; it does not replace verifier-host trust, authenticated approval, or
controlled PR publication evidence. R2/MVP remain OPEN.

Batch VS / EXP-997 was a separate one-command read-only check after EXP-996:
`docker image ls --no-trunc --quiet agent00x-verifier:exp883-amd64`. After its
fresh preflight and exact `RUN EXP-997 ONCE` gate, the sanitized result was
`VERIFIER_TAG_NOT_LISTED` (wrapper exit 0). Therefore neither the pinned image
ID nor the expected repository:tag is listed in Docker's image store on
testdev. This does not diagnose prior transfer failures or prove there is no
other image/content outside Docker's image-ID listing. No IDs were revealed;
there was no retry, inspect, import, or host modification. EXP-997 is accepted
as a limited diagnostic. Any further testdev operation requires a replacement
card and fresh gate. R2/MVP remain OPEN.

Batch VT / EXP-998 resolved the local transfer-runner mismatch without another
remote call. A read-only local `docker image save` by the pinned image ID
produced a manifest with no `RepoTags`; saving by the exact tag produced an
archive whose manifest listed `agent00x-verifier:exp883-amd64` and whose size
matched the runner's `51071488`-byte guard. The actual prior remote load output
remains suppressed and unknown, so tag loss is the local mechanism explaining
the marker, not direct evidence of the remote stdout. The runner now saves by
the exact tag and includes exact RepoTags in both local and remote identity
checks. Focused transfer tests passed (10); the full offline suite passed
(1,521 tests, 25 skipped). Exact local Docker inspect matched ID, tag,
platform, size, and ordered DiffIDs. No SSH, credentials, provider access, deployment or
publication occurred. README's latest suite summary is synchronized. This is
local runner evidence only; testdev still lists neither the pinned image ID nor
its expected tag, and no image import is now authorized. R2/MVP remain OPEN.

Scope note: EXP-996 and EXP-997 used the previously authorized public-key SSH
identity for read-only Docker-list checks on testdev. That is credential-based
authentication, even though no API secret was read or transmitted. The current
MVP objective says not to use credentials; to avoid widening that scope, no
further key-authenticated testdev contact is authorized until the user
explicitly confirms that this existing SSH identity may be used for the
separately carded image import.

Batch VV / EXP-1000 closes one local packaging gap for the experimental verifier
host: its source bundle now carries `requirements-verifier-host.txt` with the
exact `cryptography==50.0.2` runtime dependency imported by the fixed service.
The file is part of the bundle allowlist and a regression asserts the exact
pin. Two sequential in-memory builds matched at
`sha256:76a748fa0013528fb1d9c3d33edb519e8b39f8379f45c375f54ec464afb864bf`
(77 members, 1,206,422 source bytes; 1,280,000 archive bytes). This makes the
dependency declaration reproducible, not the remote installation or host
runtime: no dependency was installed, no bundle was saved/transferred, and no
SSH, credential, service, or publication action occurred. Independent verifier
trust, authenticated approval and controlled PR remain OPEN.

R5 local-runtime preflight / EXP-1001: Ollama 0.40.3 was started for a single
metadata-only check bound to `127.0.0.1:11434`; `ollama list` reported the
already-installed `qwen2.5-coder:7b` model (ID prefix `dae161e27b0e`, 4.7 GB).
The CLI's observed requests were only local `/` health and `/api/tags` metadata;
no inference, prompt, Worker run, provider credential, Docker or repository
access was used. However, Ollama reported cloud support enabled and outbound
sockets were not monitored, so this preflight does not prove absence of
background public traffic. The foreground server was stopped immediately, and
a follow-up process/port check found no listener. This confirms local runtime
availability for planning a zero-provider-cost R5 card, not a model result or
any R5 outcome. R5 and criterion 16 remain unfulfilled.

EXP-1002 attempted one metadata-only local Ollama check with
`OLLAMA_NO_CLOUD=1`. Version 0.40.3 logged `Ollama cloud disabled: true` and
listened on `127.0.0.1:11434`. The one bounded loopback `/api/tags` parser
returned only `MODEL_METADATA_UNAVAILABLE`; the cause was not inspected and no
retry occurred. The server was stopped and follow-up process/port checks found
no listener. No inference or model digest was obtained. This verifies the
installed build's cloud-disable setting, but is not an OS-level egress fence;
R5/criterion 16 remain OPEN.

Batch VY / EXP-1003 added a bounded R5 source-fact inventory for the pinned
`backend/routes.py`. The exact public raw file at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e` was read at
https://raw.githubusercontent.com/SoldatovAlexander/brainbooster_full_v11/2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e/backend/routes.py.
The inventory distinguishes direct source observations from a bounded
source-level inference, records line references, and does not embed source code.
Its SHA-256 is `sha256:4acd322f55b1e08194a6cc83406f2652d82a1af42f7dd57f1684768aad17d594`;
three offline integrity tests passed. This does not verify commit signature,
authorship, full snapshot digest, or runtime HTTP/SQLite outcomes; R5 and
criterion 16 remain OPEN. The full offline suite then passed: 1,524 tests,
25 skipped; `git diff --check` passed. No model/Worker run or external write.

EXP-1004 / Batch VZ added a pure deterministic renderer for the EXP-1003 fact
inventory. Structured and flat layouts preserve the same six fact objects,
source metadata, scope note, and fixed security limits; the exact preregistered
LearningCorrection appears only in correction arms. Focused tests passed (4),
the full suite passed (1,528 tests, 25 skipped), and `git diff --check` passed.
The four in-memory contexts have stable hashes, but byte lengths differ:
structured/no-correction 2,298; flat/no-correction 2,165; structured/correction
3,218; flat/correction 3,085. Their digests, in the same order, are
`sha256:efed341aa79c9ac4adcd6ea16e40ebdd57db0764932a288784e9970698524a5a`,
`sha256:29049dbbac62774e73ed7210da25b3bdbd33d84786ae703b90d73efdae895a96`,
`sha256:1e3fea0abee4319854aa386e4c3f43f80167fedcbb12f2dcdb2bf2e98f9f67a0`,
and `sha256:a354541438e7d2c1130c2f8cdcd24172b24b555ba22f465ce289e0a7b7a27778`.
`tokenizer_status=not_measured`; these are not yet valid R5 stimuli because
the exact model tokenizer and protocol's 1% token
balance have not been established. No context package persisted and no model or
Worker ran. R5 and criterion 16 remain OPEN.

EXP-1005 / Batch WA was stopped before its sole metadata request. The existing
Ollama process was confirmed bound only to `127.0.0.1:11434`, but its detached
startup output could not be checked for the required `cloud disabled: true`
marker. The gate therefore failed closed: no `/api/tags` request, retry,
diagnosis, or inference occurred. The exact process was interrupted and follow-up
process/listener checks found none. The model digest remains unknown; the card is
BLOCKED and spent. A replacement card is required for any further attempt.
R5 and criterion 16 remain OPEN.

EXP-1006 / Batch WB measured the four EXP-1004 context byte strings with the
tokenizer embedded in the local Qwen2.5-Coder GGUF model layer
`sha256:60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463`,
using the bundled llama.cpp commit `631109b34da437a3c4a5ebd75091d677671392e3`
and four loopback-only `/tokenize` requests (no generation). Counts were A=579,
B=549 (5.1813%) and C=1,300, D=1,270 (2.3077%); both preregistered structured/
flat pairs exceed the 1% limit. The contexts are therefore not eligible R5
stimuli. The exact server process was stopped and no listener remained. Any
format-balancing change must be specified in a replacement preregistration
before further tokenization or Worker runs; R5/criterion 16 remain OPEN.

EXP-1007 tested the preregistered format-only trailing-LF method for flat arms
with the exact local GGUF tokenizer. No shared padding count from 1 through 256
met both A/B and C/D's 1% bound. The server was stopped; no renderer source was
changed and no Worker/model completion ran. The padding method is rejected for
these contexts; original and padded candidates remain ineligible. A compact
structure-only renderer redesign would need its own pre-run card and fresh token
measurement. R5 and criterion 16 remain OPEN.

EXP-1008 tested a compact nested-array representation in memory with the exact
GGUF tokenizer. Counts were A=605, B=598 (1.1570%) and C=1,326, D=1,319
(0.5279%). The correction pair meets 1%; the no-correction pair narrowly fails.
Per card, no source changes were made. The local server was stopped and no
listener remained; there was no generation or Worker run. R5 inputs remain
ineligible pending a replacement preregistered design; criterion 16 remains
OPEN.

EXP-1009 was invalidated before interpreting its measurements: the in-memory
candidate builder retained legacy `fact_groups` and also added nested `facts`,
duplicating all six structured facts. Four tokenizer requests occurred, but
their results are discarded and no experimental count/digest is recorded. No
renderer source was changed; the server was stopped with no listener remaining.
No generation or Worker ran. Any replacement must verify exact one-time fact
objects and equality across layouts before its first tokenizer call. R5 remains
OPEN.

EXP-1010 stopped at its mandatory in-memory integrity gate with
`CONTEXT_INTEGRITY_REJECTED`. Per card, no diagnosis or tokenizer request
followed. No renderer/test source changed; the local server was stopped with
no listener. No model result or Worker run exists. A separate offline
candidate-builder implementation/test is needed before another measurement.
R5/criterion 16 remain OPEN.

EXP-1011 added the separate pure `render_blinded_context` candidate
(`agent00x-r5-blinded-context/v1`) while preserving EXP-1004 output byte-for-
byte. It omits the arm label, shares category labels/order/metadata, and keeps
each full fact object exactly once; focused tests passed (7), full suite passed
(1,531 tests, 25 skipped), and `git diff --check` passed. No tokenizer, model,
Worker, network, or external operation ran. Its token balance is still unknown;
the candidate is not yet an eligible R5 stimulus. R5/criterion 16 remain OPEN.

EXP-1012 stopped at the required integrity gate with
`CONTEXT_INTEGRITY_REJECTED`; zero tokenizer requests were sent. The local
server was stopped and port 18080 has no listener. No source change, generation,
or Worker run occurred. A separate offline diagnostic is needed to reconcile
the runtime preflight with EXP-1011's passing unit tests before retrying token
measurement. R5/criterion 16 remain OPEN.

EXP-1013 added `render_blinded_context_bundle`, a pure offline A/B/C/D bundle
builder. It verifies exact one-time fact objects, category assignment, ID-sorted
semantic equality, shared metadata and correction control before returning any
bytes. The previous runtime-gate mismatch was due to requiring global ID order
after category grouping; the bundle now compares objects in ID order while
separately checking each category. Focused tests passed (9), full suite passed
(1,533 tests, 25 skipped), and `git diff --check` passed. No tokenizer/model,
Worker, network or external operation ran; token parity remains unmeasured and
all R5 stimuli remain ineligible.

EXP-1014 tokenized the integrity-checked blinded bundle using the exact local
Qwen2.5-Coder GGUF layer and llama.cpp build. Context-only counts: A=601,
B=594 (1.1647%) and C=1,322, D=1,315 (0.5295%). The correction pair passes,
but A/B fails the preregistered 1% threshold; the contexts remain ineligible.
All four context digests and counts are in the queue card. The same loopback
server was stopped with no listener remaining. No generation, Worker, network,
or code change occurred. The full frozen scenario prompt was not included in
this context-only measurement; if protocol interpretation requires total input,
it needs a separate pre-run card and exact prompt composition. R5/criterion 16
remain OPEN.

EXP-1015 attempted to compare complete model-facing inputs after applying the
exact local chat template, but the command output was truncated before per-arm
counts or a completed-request total could be retained. The server process was
stopped and port 18080 has no listener. No model inference or Worker call
occurred. The card prohibits retries, so this run is inconclusive: it does not
establish token parity or eligibility. A separately reviewed replacement card
is required for any new measurement. R5/criterion 16 remain OPEN.

EXP-1016 repeated the complete-input comparison under a separately reviewed
one-shot card with bounded aggregate output; all 20 `/apply-template` and 20
`/tokenize` responses succeeded against the pinned local GGUF and llama.cpp
commit. Counts A/B/C/D: S1 701/694/1422/1415 (AB 0.998573%, CD 0.492264%);
S2 699/692/1420/1413 (1.001431%, 0.492958%); S3 711/704/1432/1425
(0.984529%, 0.488827%); S4 680/673/1401/1394 (1.029412%, 0.499643%); S5
671/664/1392/1385 (1.043219%, 0.502874%). Three of ten comparisons fail the
1% bound, so all stimuli remain ineligible under the all-comparisons gate.
Exact context digests are recorded in the queue card. The same server was
stopped and no listener remains. No inference, Worker or source change occurred;
R5/criterion 16 remain OPEN.

EXP-1017 tested an in-memory v2 compact organization encoding: all arms carried
the same six fact objects in category-grouped order, while structured arms alone
carried `group_sizes: [2,2,2]`. The independent integrity gate passed and exactly
20 `/apply-template` plus 20 `/tokenize` responses succeeded against the pinned
local tokenizer. Complete-input counts A/B/C/D: S1 703/694/1424/1415 (AB
1.280228%, CD 0.632022%); S2 701/692/1422/1413 (1.283880%, 0.632911%); S3
713/704/1434/1425 (1.262272%, 0.627615%); S4 682/673/1403/1394 (1.319648%,
0.641483%); S5 673/664/1394/1385 (1.337296%, 0.645624%). All five AB pairs
fail the 1% bound, while CD pass. The candidate is ineligible and was not
implemented. Server stopped with no listener; no inference or Worker ran. R5
and criterion 16 remain OPEN.

EXP-1019 applied that helper once to the existing EXP-990 WAL stage, producing
`/Volumes/DATA/Agent00X-local-evidence/exp990-stage-review.sqlite3` with exact
stage digest `sha256:b55af83fe251f2276240f0ec6679e70d8115409b38db479011180f116dc3f87c`.
The helper reported source unchanged and no overwrite; read-only postflight
verified the 20,480-byte destination, mode 0600, no sidecars and SQLite integrity
`ok`. Destination file SHA-256 is
`7bdb5975c514bf7b57b75a941ce1c1e420d4664cb0f73fe7c9e88ebe8d97d7a8`. No
approval request was attempted: EXP-990 contains same-host verifier evidence,
not caller-pinned trusted provenance. The copied DB is content-bearing, outside
Git and not certified secret-free.

EXP-1031 / Batch VB added an exact `agent00x-worker-result/v2` envelope for
patch, clarification, blocked and denied Worker results, preserving legacy v1
patch parsing. Observer stores only the fixed terminal outcome enum; executor
returns before target tests, verifier or stage, and CLI emits a fixed status
plus reason code. Focused offline suites passed (216 tests: 212 passed, 4 skipped).
The first full run caught a stale verifier code digest: Observer code and schema
are members of the verifier identity. EXP-1032 rebuilt one local pinned verifier
image from the existing pinned target image using Docker `--network=none` and
`--pull=false`; exact image ID is
`sha256:34069c176da27372d66a7a358eb12b977d920735ab3eb27d6bdfe7b1cc5f77e8`,
and the independently recomputed source/schema digest is
`sha256:e4d53a6b617da7265f74087ef3c8ab4a5ddbe882113d53312a18c0d1d2660fca`.
The pinned code-identity test passed; the full offline suite passed 1,553 tests
total (1,528 passed, 25 skipped), and `git diff --check` passed. No model inference, target probe,
GitHub, testdev, credential, approval or provider action occurred. The new image
is local-only and does not establish independent-host trust or testdev presence;
R5, criterion 16 and R2/MVP remain OPEN.

EXP-1034 reviewed the current verifier-host preparation prototype. The deterministic
bundle builder has a fixed source allowlist, bounded regular-file reads, symlink
rejection, canonical manifest and stable archive metadata. The systemd credential
provisioner is covered only with synthetic seed bytes and a fake `systemd-creds`
runner; no real credential was generated or read. The one-shot HTTPS launcher is
covered by fake-server tests; its Linux-only sealed-memfd integration was skipped
on macOS. Focused suites: 29 tests (27 passed, 2 skipped); the full offline suite:
1,553 tests (1,528 passed, 25 skipped); `git diff --check` passed. This is local
packaging and synthetic behavior evidence only: no host bundle was transferred,
no testdev service/key was provisioned, and no independent verifier trust or
production credential custody is established. R2/MVP remain OPEN.

EXP-1035 attempted the Linux-only memfd HTTPS integration test in a network-none,
read-only container using the exact pinned verifier image. The image ID/platform
preflight matched, but its runtime lacked `cryptography`; Python failed before
test discovery and no integration test ran. The one-shot card forbade retries.
This confirms that the minimal verifier image is not a suitable TLS host test
image; it does not indicate a TLS test failure. A replacement requires a
separately pinned offline Linux test image with the locked dependency. No
credentials, service, host, or external endpoint were used; independent verifier
trust and R2/MVP remain OPEN.

EXP-1036 downloaded only the official PyPI `cryptography==50.0.2` CPython 3.11
Linux/ARM64 wheel and verified its published SHA-256 before mounting it
read-only into the pinned Python base image. The one network-disabled test
container stopped before discovery because the wheel was mounted as
`cryptography.whl`, which pip rejected as a noncanonical wheel filename. No test
ran and the one-shot card forbade retries. A separate replacement card may use
the retained hash-verified wheel under its complete platform filename; R2/MVP
remain OPEN.

EXP-1037 reused the retained wheel only after the same SHA-256 and image
preflight. Pip installed it under its canonical platform filename into tmpfs,
but loading its native extension failed because the container's `/tmp` mount
was `noexec`; test discovery never began. The one-shot card forbade retries.
This is an execution-policy mismatch, not a TLS test result. A separate card
may allow executable mapping only on the ephemeral tmpfs containing the exact
hash-pinned wheel; R2/MVP remain OPEN.

EXP-1038 repeated the isolated Linux test with the canonical wheel filename,
but omitting an explicit tmpfs `exec` option did not make the filesystem
executable. The native extension again failed to map before test discovery; no
test ran and the one-shot card forbade retries. This remains a test-container
mount configuration issue, not an integration outcome. R2/MVP remain OPEN.

EXP-1039 used the canonical, hash-verified cryptography wheel in a network-none,
read-only Linux/ARM64 container running as a non-root UID with executable
ephemeral tmpfs. Cryptography installation succeeded, but importing it failed
before test discovery because the `_cffi_backend` extension was absent after
installing only that wheel with `--no-deps`. No test ran; the one-shot card
forbade retries. The observed blocker is an incomplete offline dependency set,
not a TLS integration failure. A separate exact card pins `cffi` and its
`pycparser` dependency from official PyPI artifacts. R2/MVP remain OPEN.

EXP-1040 installed the hash-pinned cryptography, cffi, and pycparser wheels in
the same network-none, read-only Linux/ARM64 container. Import advanced into
the test module but stopped before discovery because the client imports
`certifi`, which the test environment had not installed. No test ran; the
one-shot card forbade retries. This is an incomplete test dependency manifest,
not an integration result. EXP-1041 separately pins the observed direct import
set, including certifi; R2/MVP remain OPEN.

EXP-1041 installed all four exact, hash-verified wheels in the isolated
container, but its card's pre-test assertion expected certifi's wheel release
string (`2026.7.22`) to equal the module's normalized `__version__`
(`2026.07.22`). The assertion stopped execution before unittest discovery; no
tests ran. This is a test-card formatting defect, not a dependency or TLS
result. EXP-1042 corrects only the assertion's normalized string; R2/MVP remain
OPEN.

EXP-1042 ran the Linux-only `test_ephemeral_signed_verifier_https.py` suite in
the pinned Python 3.11 Linux/ARM64 container with networking disabled, a
read-only repository mount, non-root UID, dropped capabilities, and executable
ephemeral tmpfs. All four official dependency wheels matched their pinned
SHA-256 values; all 6 tests passed with 0 skipped, including both sealed-memfd
HTTPS integration tests. The temporary wheel files were removed. This is
targeted local Linux integration evidence only; it does not establish
independent verifier trust, testdev deployment, provider behavior, or MVP
completion. R2/MVP remain OPEN.

EXP-1043 corrected the verifier-host source-bundle requirements manifest to
declare all four observed runtime pins: `cryptography==50.0.2`,
`cffi==2.1.1`, `pycparser==2.22`, and `certifi==2026.7.22`. A regression now
parses the real project manifest, rejects malformed, duplicate, or unexpected
pins, and verifies that the deterministic bundle preserves its exact bytes.
The executor reported 13 focused tests passing and a full offline suite of
1,554 tests with 25 skipped; `git diff --check` exited 0. I reviewed the two
allowed files. They were already untracked before the card, so Git's ordinary
diff check does not inspect them; their current contents were inspected
directly. No packages were installed, and no network, Docker, credential,
external host, publication, or commit was used. This improves local bundle
reproducibility only; it does not establish installation on testdev, independent
verifier trust, authenticated approval, controlled PR publication, or MVP
completion. R2/MVP remain OPEN.

Control Plane follow-up after EXP-1043: the current verifier-host source bundle
was built in memory once and returned
`sha256:7c8df7dfcd49eff4240a5122a7d198a57a5298eb8d6786cd1749c1bf9b9e1901`
(78 members, 1,226,299 source bytes, 1,300,480 archive bytes). This is the
current source-state digest and supersedes EXP-1000's earlier bundle digest for
future planning. The archive was neither saved nor transferred; no remote
installation or external action occurred. R2/MVP remain OPEN.

EXP-1046 pinned the installed local Ollama runtime metadata without inference:
the 0.40.3 server reported cloud disabled and listened only on
`127.0.0.1:11434`; one bounded GET each to `/api/version` and `/api/tags`
returned model `qwen2.5-coder:7b` digest
`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`.
The foreground process was stopped and its listener disappeared. No model
inference, Worker, tokenizer, target, Docker, credentials or external action
occurred. Socket snapshots and Ollama's cloud-disable flag are not OS-level
egress attestation. This only pins local model metadata; R5 criterion 16 and
R2/MVP remain OPEN.

EXP-1047 used one explicitly authorized read-only SSH command with strict host
key checking and BatchMode. SSH identity/authentication and Docker daemon access
on `testdev` succeeded, but `docker image inspect` returned `No such image` for
the current local verifier image ID
`sha256:34069c176da27372d66a7a358eb12b977d920735ab3eb27d6bdfe7b1cc5f77e8`.
The same exact ID exists locally as `linux/arm64` (49,144,208 bytes), but remote
presence is now disproved for that ID; no fallback tag lookup or remote mutation
occurred. Import/deployment requires a separate exact task card and fresh user
confirmation. Independent verifier readiness/trust, authenticated approval,
controlled PR publication, R5 criterion 16 and R2/MVP remain OPEN.

EXP-1049 checked the Docker daemon itself on `testdev` with one strict,
read-only SSH call: it reports `linux/x86_64` (exit 0). This does not match the
current local verifier image from EXP-1032 (`linux/arm64`). The proposed image
stream in EXP-1048 is therefore invalidated and was not run; no emulation or
remote mutation is evidenced. A platform-compatible verifier artifact and a
freshly authorized transfer/deployment card are still required. R2/MVP remain
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

Batch XV / EXP-1060—1063 adds offline-only R5 preparation: an exact blinded
selector for `R5-001`—`R5-005`, a caller-path append-only SQLite no-repeat
ledger, a wrapper over the existing pinned remote-snapshot execution spine, and
a sequential five-attempt coordinator that creates a fresh one-shot Worker for
each ID. Fake tests cover terminal outcomes, exact ordering, crash/unknown stop,
restart without replay and redacted metadata. No production ledger, model
inference, Worker, Docker, target, verifier, external network or provider action
occurred. Batch XV's final full offline suite passed 1,583 tests (1,558 passed,
25 skipped); `git diff --check` is clean.

The coordinator is not yet an operational CLI: it does not construct the
anonymous pinned full snapshot, local model channel, Docker target sandbox,
verifier, durable stage and observer together. No live R5 invocation command is
supported. The tokenizer GGUF pin used for EXP-1059 is not the model pin of the
production local Ollama adapter (`qwen2.5-coder:7b`). A read-only Control Plane
`ollama --version` probe reported client 0.40.3 but no running daemon; this was
an unscoped procedural deviation after EXP-1063, not model/runtime eligibility
or an egress-fence proof. No HTTP request or inference occurred. A separate
bounded CLI/preflight task is next; live Worker runs need a later exact card and
fresh local model/image/snapshot checks. R5/criterion 16 and MVP remain OPEN.

Batch XW / EXP-1065—1068 completes the local-first operational wiring for one
five-attempt R5 batch. EXP-1065 binds the accepted public snapshot adapter;
EXP-1066 adds a bounded GET-only loopback Ollama metadata preflight;
EXP-1067 constructs fixed target/verifier adapters and per-attempt journal-
bound Workers around explicitly supplied SQLite stores; EXP-1068 adds the CLI,
preflight ordering, redacted summary, and exact interactive `RUN <card-ID> ONCE`
gate. If snapshot/model/image preflight fails, no operational DB is created;
refusing the gate closes and removes only invocation-owned empty DB files.
Focused tests: 3 + 5 + 4 + 7 passed. Full offline suite: 1,602 tests (1,577
passed, 25 skipped); `git diff --check` clean. The CLI was not invoked; no
GitHub, Ollama, Docker, Worker, target, verifier, operational DB, provider,
credential or publication operation occurred.

EXP-1066's expected Ollama server version `0.40.3` is provisional: historical
local metadata showed that version, but the latest client-only probe could not
connect to a server. The prior model digest and Docker image IDs are also not
fresh evidence. EXP-1070 is therefore DRAFT, not an execution authorization.
Before any first-five model run, refresh server/model/snapshot/image pins, check
disk headroom, and explicitly bound whole-batch elapsed time; per-call timeouts
alone do not cap total runtime. R5 outcome evidence, criterion 16 and MVP remain
OPEN. This local path does not prove OS-level egress isolation or independent
verifier trust.

Batch XX / EXP-1071—1075 refreshed execution readiness without inference.
Ollama `/api/version` was unavailable on one bounded loopback request; no daemon
was started, no `/api/tags` request followed, and no model digest is current.
Both local Docker images match their exact profile IDs by two read-only
inspections. The anonymous public snapshot still matches the exact pinned
commit/tree/content digest and all 23 files; the raw commit object was
hash-verified. The workspace volume has 330,895,228,928 free bytes and the
three proposed EXP-1070 database destinations are absent. EXP-1070 remains
DRAFT because current Ollama metadata is missing and the CLI still lacks an
enforced whole-run deadline. Batch XY / EXP-1076—1080 is the follow-up: bounded
deadline, enforced disk gate, temporary metadata-only local server readiness,
fake-only gate composition, and evidence reconciliation. No model inference,
Worker, target, verifier, operational database or provider action occurred;
R5/criterion 16 and MVP remain OPEN.

Batch XY / EXP-1076—1080 closes the readiness gaps for the first R5 sample.
EXP-1076 adds a 2,400-second POSIX one-shot execution cutoff and tested
no-retry/UNKNOWN behavior, with a documented deviation: this is not a hard
process-group kill guarantee. EXP-1077 enforces a 500 MiB disk gate before
external preflight or database creation. EXP-1078 refreshed loopback Ollama
metadata (server 0.40.3, `qwen2.5-coder:7b`, digest
`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`) using two
GETs and stopped its owned server process. EXP-1079's fake integration tests
confirm gate ordering and that no Worker is constructed before exact operator
confirmation. Fresh disk/path check: 330,895,167,488 bytes free and all three
EXP-1070 database paths absent. Snapshot and Docker pins match their accepted
same-day evidence. Focused Batch XY integration tests pass; full offline suite
passes 1,618 tests (1,593 passed, 25 skipped); `git diff --check` is clean.

EXP-1070 is IN PROGRESS, gated on a failed pre-dispatch `snapshot` phase. Three
supervised CLI invocations stopped before the summary/confirmation gate. The
first two used the old generic error; the third used fixed phase diagnostics
and identified `snapshot`. Their precise preflight progress is unknown where no
phase was recorded. No invocation reached inference, target, verifier or
operational database creation. The public snapshot/fetch stage is the only
identified current blocker; EXP-1084 records it and further execution is held
until read-only diagnosis succeeds. The five-attempt sample is not MVP
completion; R5 outcome evidence, criterion 16 and MVP remain OPEN. No OS-level
egress isolation or independent verifier trust is established.

## Control Plane update — Batch YA, 2026-10-13

The earlier IN PROGRESS snapshot status above is superseded by EXP-1089. One
bounded codeload archive read plus one hash-verified raw Git commit-object read
revalidated the 23-file pinned snapshot and exact commit/tree/content digest;
the recorded origin is `github_codeload_archive`. Metadata-only local Ollama
preflight matched version 0.40.3, `qwen2.5-coder:7b`, the pinned model digest
and one installed model. Exact same-day target/verifier image evidence matched
the profile IDs and verifier code digest. The three EXP-1070 DB paths were
absent and the volume had >500 MiB free. Owned Ollama server cleanup was
verified; no inference occurred. EXP-1070 is READY and EXP-1090 authorizes one
interactive first-five run. The exact confirmation has not yet been entered;
there is still no R5 attempt outcome. This readiness does not prove OS-level
egress isolation or independent verifier trust, and does not complete MVP.

## Control Plane update — R5-001 pre-worker stop and provenance correction, 2026-10-13

EXP-1098 matched the redacted source/model/image/disk summary and passed the
one-shot gate. The ledger durably records R5-001 as `UNKNOWN` with fixed reason
`pipeline-error`, input digest only; R5-002—005 remain `PENDING`. Stage contains
zero artifacts; Observer contains one event and zero checkpoints. No event or
candidate content was read. Source tracing proves the failure occurred in
`run_r5_attempt` provenance validation before `run_remote_snapshot_execution`;
the local model channel sends a request only when its Worker is asked to
`propose`. Thus there was no inference, target or verifier execution. The ID is
non-retryable and remains UNKNOWN.

The pre-registered casebook and WorkerInput had retained the old
`github_rest_api_claim` metadata while the accepted snapshot reader correctly
reported `github_codeload_archive` with a hash-verified commit/root-tree proof.
Batch YE updates this metadata binding and execution guard. The casebook digest
is now `bf27eb21434f6a8f099871b2608459c5a7dbae04be6186490d053fe7f07a8fe5`;
the task prompts, schedule, contexts, source bytes and model-visible payloads
are unchanged (verified across all 100 inputs). Exact origin mismatch still
fails closed before collaborators. This does not complete a five-attempt batch,
criterion 16, independent verifier trust or MVP.

## Control Plane update — R5 Worker timeout contract, 2026-10-13

EXP-1112—1115 localized the four terminal Worker failures to startup before
`ready`; EXP-1115 confirmed that the container's stdin/stdout are FIFOs. Source
inspection then found the concrete mismatch: the R5 runtime configures a
60-second Worker timeout, while both IPC channel constructors accepted only
exactly 30 or 180 seconds. The child therefore rejected 60 seconds after
`network-probes-blocked` and before advertising `ready`. EXP-1117 now validates
configured channel maxima as finite positive values bounded by the existing
180-second local cap. Both constructors accept the 60-second profile; invalid
and over-cap values remain rejected, and the 30-second default is unchanged.
Focused IPC/Worker/runtime tests passed (29 tests, one skipped); the full suite
passed (1,643 tests, 25 skipped). No Docker Worker or model was run after this
fix, so runtime recovery and any R5 inference remain unproven. EXP-1118 then
ran one exact pinned Worker container with frozen R5-006 input and an
in-memory fake channel; the fake channel was called once and raised a fixed
error, proving the container reached the host-channel boundary after the
60-second configuration. No model request or attempt-ledger claim occurred.
The four failed IDs remain terminal; only still-pending preregistered IDs may be selected for a
new, separately gated run. R5 criterion 16, independent verifier trust,
authenticated approval, controlled PR publication and MVP remain OPEN.

## Control Plane update — bounded R5 continuation controls, 2026-10-13

Batch YH / EXP-1119—1123 fixes the offline continuation path. The execution
spine now validates a selected ID against the full frozen 100-ID schedule, not
only the original first five. The runner stops after a durably recorded
`outcome=failed`, while `verified`, `needs_input`, `blocked`, and `denied` remain
distinct experimental outcomes. For a resumed ledger, future IDs require an
explicit `--extend-allowed-attempts` flag plus `--attempt-ids`; only the exact
next contiguous range is shown in the pre-gate summary and appended after the
matching one-shot confirmation. The selected set is rechecked PENDING before
adapter construction. Temporary-DB composition proved that a failed R5-006 is
recorded once, R5-007—010 remain PENDING, and a later invocation is rejected
before gate/dispatch without mutating the stores. Focused tests passed (41); the
full suite passed (1,650 tests, 25 skipped). No operational EXP-1070 store,
model, Docker, target or verifier was used in this batch. A new local R5-006—010
run remains a separate READY card/gate; no post-fix inference is yet evidenced.
R5 criterion 16, independent verifier trust, authenticated approval, controlled
PR publication and MVP remain OPEN.

## Control Plane update — snapshot summary gate correction, 2026-10-13

EXP-1125 adds the validated pinned snapshot tree OID and content digest to the
R5 CLI's pre-gate summary. Exact-value regressions pass in the CLI and deadline
summary tests; the full offline suite passes 1,650 tests (1,625 passed, 25
skipped). `git diff --check` is clean. The first batch execution card,
EXP-1124, remains blocked because its summary omitted these identity fields; it
was stopped before confirmation, ledger extension or inference and was not
reused. EXP-1126 was a separate bounded local run for R5-006—010. The exact
one-shot gate was entered; the local Ollama log records one chat-completions
request. R5-006 is durably `COMPLETED/failed/execution-failed`, so the runner
stopped and R5-007—010 were not dispatched. Postcheck: all three databases pass
`quick_check`; stage has zero artifacts; Observer has 36 events/15 checkpoints;
the owned Ollama process exited and the listener is absent. No event, prompt or
candidate content was inspected. The experiment produced one local model
outcome but no verified target change. R5 outcome evidence, criterion 16,
independent verifier trust, authenticated approval, controlled PR publication
and MVP remain open.

## Control Plane update — bounded R5 failure evidence, 2026-10-13

EXP-1127 fixes a loss of diagnostic metadata in the preregistered R5 runner.
Previously every ordinary failed execution was recorded as generic
`execution-failed` even though the executor provided fixed `failure_code`
markers. The runner now projects only an explicit set of 18 fixed categories
into the append-only ledger and includes that projected reason in the result
digest. Missing or unrecognized values remain generic; arbitrary error text is
never persisted. Distinct fixed reason categories produce distinct digests.
No-retry and stop-on-failure behavior is unchanged. Focused runner/ledger suites
pass (22 tests); full offline suite passes 1,654 tests (1,629 passed, 25 skipped);
`git diff --check` is clean. EXP-1126 remains a
terminal failed attempt with its original generic reason; it cannot be
retroactively diagnosed, and R5-007—010 remain unexecuted. This improves future
failure evidence but is not R5 outcome success or MVP completion.

## Control Plane update — explicit continuation after failed R5 outcomes, 2026-10-13

EXP-1128 makes continuation after a terminal `failed` outcome available only
through `--continue-after-failed`, with resume and an explicit attempt-ID list.
The default still stops on failure; completed IDs are not replayed; unknown,
claimed, preflight and deadline states still stop. The exact opt-in appears in
the pre-gate summary, and a fully dispatched sample containing a failed result
is labeled `complete-with-failures`. Targeted suites pass (40 tests); the full
offline suite passes 1,658 tests (1,633 passed, 25 skipped); `git diff --check`
is clean. EXP-1129 was stopped before summary/gate because the CLI only allowed
an extension when all selected IDs were new. No inference or store extension
occurred. EXP-1130 fixes this with a test proving existing pending IDs may be
batched with only the exact next contiguous new suffix; 41 targeted tests pass.
The full suite passes 1,659 tests (1,634 passed, 25 skipped).
EXP-1131 was then run under its own one-shot gate. R5-007 is durably
`COMPLETED/failed/worker-failed`; R5-008 is durably `UNKNOWN/pipeline-error`, so
R5-009—011 were not dispatched. The Ollama terminal capture was truncated, so
exact request count is unavailable; at most two requests were possible for the
two dispatched IDs. Postcheck: ledger, stage and Observer integrity pass, stage
has zero artifacts, Observer is 50 events/21 checkpoints, and the owned
listener is absent. No event/prompt/candidate content was inspected. EXP-1132
then dispatched only R5-009, which became `UNKNOWN/pipeline-error`; the local
Ollama log confirms one chat-completions request. R5-010—013 were not
dispatched. Postcheck: all stores pass `quick_check`, stage has zero artifacts,
Observer is 59 events/25 checkpoints, and the owned listener is absent. EXP-1133
then dispatched only R5-010, which became `UNKNOWN/pipeline-error` after one
local chat-completions request; R5-011—014 remain unexecuted. Postcheck: all
stores pass integrity checks, stage is empty, Observer is 68 events/29
checkpoints, and the owned listener is absent. EXP-1134 is READY for R5-011—015
and excludes terminal IDs 007—010. EXP-1134 then completed R5-011 as
`blocked/worker-blocked`, R5-012 as `blocked/worker-blocked`, R5-013 as
`failed/worker-failed`, and R5-014 as `UNKNOWN/pipeline-error`; it stopped before
R5-015. Postcheck: all databases pass integrity checks, stage remains empty,
Observer is 98 events/42 checkpoints, and the owned listener is absent. The
sample remains incomplete. MVP remains open.
EXP-1135 then dispatched R5-015 (`blocked/worker-blocked`) and R5-016
(`UNKNOWN/pipeline-error`), stopping before R5-017—019. Postcheck: all databases
pass integrity, stage has zero artifacts, Observer is 114 events/49 checkpoints,
and the owned listener is absent. Exact chat request count was not recoverable
from the truncated Ollama terminal output; at most two were possible. EXP-1136
is READY for R5-017—021, excluding terminal IDs 007—016. No R5 positive verified
change or MVP completion is established. EXP-1136 then dispatched R5-017
(`blocked/worker-blocked`), R5-018 (`failed/worker-failed`), and R5-019
(`UNKNOWN/pipeline-error`), stopping before 020—021. Postcheck: all database
integrity checks pass, stage empty, Observer 137 events/59 checkpoints, owned
listener absent. The sample has no verified result yet. EXP-1137 then recorded
R5-020 `denied/worker-denied`, R5-021 `blocked/worker-blocked`, and R5-022
`UNKNOWN/pipeline-error`; it stopped before R5-023—024. Postcheck: integrity
passes, stage empty, Observer 160 events/69 checkpoints, owned listener absent.
The sample has no verified change. EXP-1138 then dispatched only R5-023, which
became `UNKNOWN/pipeline-error`; one local chat-completions request was logged.
R5-024—027 were not dispatched. Postcheck: integrity passes, stage empty,
Observer 169 events/73 checkpoints, listener absent. EXP-1139 then recorded
R5-024 as `needs_input/worker-clarification` and R5-025 as
`UNKNOWN/pipeline-error`, stopping before R5-026—028. The initial CLI process
was stopped before gate when its PTY handle was unavailable; a fresh retained
PTY was used for the sole confirmed run. Ollama output was truncated, so the
request count is bounded by at most two for the two dispatched attempts.
Postcheck: integrity passes, stage empty, Observer 185 events/80 checkpoints,
owned listener absent. EXP-1140 is READY for pending R5-026—030, appending only
029—030 and excluding terminal IDs 001—025. EXP-1140 then dispatched only
R5-026, which became `UNKNOWN/pipeline-error`; the local Ollama log confirms
one chat-completions POST. R5-027—030 were not dispatched. Postcheck: integrity
passes, stage empty, Observer 192 events/83 checkpoints, owned listener absent.
EXP-1141 is READY for R5-027—031, appending only 031 and excluding terminal IDs
001—026. EXP-1141 then dispatched only R5-027, which became
`UNKNOWN/pipeline-error`; the owned local server logged one chat-completions
POST. R5-028—031 were not dispatched. Postcheck: integrity passes, stage empty,
Observer 201 events/87 checkpoints, listener absent. EXP-1142 then recorded
R5-028 as `needs_input/worker-clarification` and R5-029 as
`UNKNOWN/pipeline-error`, stopping before R5-030—032. The owned server logged
one chat-completions POST; captured output was truncated, bounding the request
count to at most two. Postcheck: integrity passes, stage empty, Observer 217
events/94 checkpoints, listener absent. EXP-1143 then recorded R5-030 as
`needs_input/worker-clarification` and R5-031 as `UNKNOWN/pipeline-error`,
stopping before 032—034. One local POST was logged. Postcheck: integrity passes,
stage empty, Observer 233 events/101 checkpoints, listener absent. EXP-1144 then
recorded R5-032 as `failed/worker-failed` and R5-033 as `UNKNOWN/pipeline-error`,
stopping before 034—036. Captured server output was truncated; at most two
requests were possible for the two dispatched IDs. Postcheck: integrity passes,
stage empty, Observer 249 events/108 checkpoints, listener absent. EXP-1145 then
dispatched only R5-034, which became `UNKNOWN/pipeline-error`; one local POST
was logged. R5-035—038 were not dispatched. Postcheck: integrity passes, stage
empty, Observer 258 events/112 checkpoints, listener absent. EXP-1146 then
recorded R5-035 as `blocked/worker-blocked` and R5-036 as
`UNKNOWN/pipeline-error`, stopping before 037—039. One local POST was logged.
Postcheck: integrity passes, stage empty, Observer 274 events/119 checkpoints,
listener absent. EXP-1147 then recorded R5-037 as `blocked/worker-blocked` and
R5-038 as `UNKNOWN/pipeline-error`, stopping before 039—041. One local POST was
logged. Postcheck: integrity passes, stage empty, Observer 290 events/126
checkpoints, listener absent. EXP-1149 added a fixed R5 adapter classification
for the four exact proposal-validation errors: those known returned invalid
proposals become `FAILED/worker-proposal-invalid`; all other exceptions remain
sanitized UNKNOWN. This is a future diagnostic path only and does not
reclassify prior attempts. Focused R5 suites passed (22 tests); full offline
suite passed (1,662 tests, 25 skipped); `git diff --check` is clean. An
intermediate direct edit to `executor.py` exposed its inclusion in the pinned
verifier code digest; it was removed, and no verifier image or pin changed.
EXP-1148 then dispatched only R5-039, which became `UNKNOWN/pipeline-error`
after one local request; R5-040—043 remain pending. The new fixed invalid-
proposal classification did not match this attempt, so it does not explain this
UNKNOWN or any earlier one. Postcheck: all databases pass integrity, stage is
empty, Observer has 299 events/130 checkpoints, and the owned listener is
absent. EXP-1150 then dispatched only R5-040, which became
`UNKNOWN/pipeline-error`; 041—044 were not dispatched. Postcheck: all stores
pass integrity, ledger has 44 IDs, stage remains empty, Observer has 306
events/133 checkpoints, and the owned listener is absent. EXP-1151 then
dispatched only R5-041, which also became
`UNKNOWN/pipeline-error`; 042—045 were not dispatched. Its first pre-gate
attempt was rejected because the metadata inspection had left two unheld stage
sidecars; only those zero-byte-WAL/transient files were removed before a fresh
matching preflight. Postcheck: all stores pass integrity, ledger has 45 IDs,
stage remains empty, Observer has 315 events/137 checkpoints, and the owned
listener is absent. EXP-1152 is READY for offline, redacted phase diagnostics
before another model attempt. EXP-1152 added fixed `input-validation-error`,
`executor-uncaught-error` and `result-validation-error` codes to newly recorded
UNKNOWN outcomes; `pipeline-error` remains the fallback, and historical records
were not changed. Focused R5 suites passed (36 tests); the full offline suite
passed (1,665 tests, 25 skipped). This does not explain R5-040/041. EXP-1153
then dispatched only R5-042, recorded as `UNKNOWN/executor-uncaught-error`;
043—046 were not dispatched. The CLI initially rejected that code while
formatting final JSON, although it was durably present in the ledger. EXP-1154
added the three fixed phase codes to the CLI evidence allowlist while preserving
rejection of arbitrary strings; 30 focused tests and the full suite (1,666
tests, 25 skipped) passed. EXP-1155 then dispatched only R5-043, also
`UNKNOWN/executor-uncaught-error`; 044—047 were not dispatched. The updated CLI
successfully reported this fixed reason. Postcheck: all stores pass integrity,
ledger has 47 IDs, stage is empty, Observer has 333 events/145 checkpoints, and
the owned listener is absent. EXP-1156 extended the diagnostic boundary to exact
fixed executor error markers and seven static boundary reason codes; unknown
markers keep the safe fallback, and the four invalid-proposal mappings stay
FAILED. The original message is never stored. 67 focused R5/CLI tests and the
full offline suite (1,667 tests, 25 skipped) passed. EXP-1157 then completed
R5-044—046 as `failed/worker-failed` and R5-047 as
`UNKNOWN/executor-uncaught-error`; R5-048 was not dispatched. Four local model
calls were made. Postcheck: all stores pass integrity, ledger has 48 IDs, stage
remains empty, Observer has 363 events/158 checkpoints, and the owned listener
is absent. EXP-1158 added the fixed `executor-marker-unmapped` code for an exact
but unmapped `ExecutionError`, while non-ExecutionError failures retain
`executor-uncaught-error`. Focused R5/CLI tests passed (68); full offline suite
passed (1,668 tests, 25 skipped). No operational stores or live services were
used. EXP-1159 then dispatched only R5-048, which became
`UNKNOWN/executor-uncaught-error`; 049—052 were not dispatched. The new
`executor-marker-unmapped` path implies this was a non-ExecutionError type, but
its type/text were not examined. Postcheck: ledger has 52 IDs, stage is empty,
Observer has 372 events/162 checkpoints and the owned listener is absent.
EXP-1160 maps six exact built-in exception types to static codes while retaining
the generic fallback for subclasses and unlisted types; messages and class names
remain private. 70 focused R5/CLI tests and the full suite (1,670 tests, 25
skipped) passed. No operational stores or live services were used. EXP-1161
then dispatched only R5-049, which became `UNKNOWN/executor-uncaught-error`;
050—053 were not dispatched. Exact built-in types were not classified, and the
exception metadata was not inspected. Postcheck: ledger has 53 IDs, stage is
empty, Observer has 381 events/166 checkpoints, and the owned listener is absent.
EXP-1162 maps the exact remote workspace lease exception to
`executor-workspace-error`; other ValueError subclasses remain in the generic
fallback. 71 focused R5/CLI tests and the full suite (1,671 tests, 25 skipped)
passed. No operational stores or live services were used. EXP-1163 then
dispatched only R5-050, which became `UNKNOWN/executor-uncaught-error`; 051—054
were not dispatched. The workspace-specific mapping did not apply. Postcheck:
ledger has 54 IDs, stage is empty, Observer has 390 events/170 checkpoints,
and the owned listener is absent. Static path review identifies
`ContractValidationError` from the preparation contract as another uncaught
typed boundary. EXP-1164 maps only that exact class to
`executor-contract-invalid`; 71 focused tests and the full offline suite (1,671
tests, 25 skipped) passed. No operational stores or live services were used.
EXP-1165 dispatched R5-051 and R5-052 only: the former completed as a known
worker failure and the latter remained UNKNOWN with a fixed contract-validation
reason. Ledger has 55 IDs, stage has zero artifacts, and Observer has 406
events/177 checkpoints. EXP-1166 maps only the exact fixed target-test failure
marker to `FAILED/target-tests-failed`; all other contract validation failures
remain UNKNOWN. Focused tests passed (64); the full offline suite passed (1,673
tests, 25 skipped). EXP-1167 is READY for pending R5-053—057, appending only
056—057, subject to exact fresh preflight and one-shot confirmation. EXP-1167
then completed all five attempts: 053—055 `failed/target-tests-failed`, 056
`failed/worker-failed`, 057 `needs_input/worker-clarification`. Ledger has 57
IDs; stage remains empty; Observer has 447 events/195 checkpoints; owned server
is stopped. EXP-1168 completed 058—062 as `failed/target-tests-failed`; ledger
has 62 IDs, stage remains empty, Observer has 492 events/215 checkpoints and
the owned server is stopped. There are now eight target-test failures among the
newly classified attempts, but the safe category suffix was not retained.
EXP-1169 adds only a fixed one-to-one mapping from the existing safe category
allowlist to static reason codes, leaving historical outcomes unchanged. 65
focused R5/CLI tests passed; the full offline suite passed (1,674 tests, 25
skipped). EXP-1170 completed 063—067: two `failed/worker-failed` and three
`failed/target-test-malformed-status`. Ledger has 67 IDs; stage remains empty;
Observer has 533 events/233 checkpoints; the owned server is stopped. The fixed
category means the bounded target probe failed an expected HTTP 422 check for a
malformed value; the exact field/value/status and candidate were not retained.
EXP-1171 completed 068=`failed/worker-failed`,
069=`failed/target-test-malformed-status`, 070=`failed/target-test-readiness-exit`,
and stopped on 071=`UNKNOWN/executor-contract-invalid`; 072 remains pending.
Ledger has 72 IDs, stage remains empty, Observer has 565 events/247 checkpoints,
and the owned server is stopped. EXP-1172 adds exact, redacted classification
for selected known preparation-contract markers; focused tests passed (66), and
the full suite passed (1,675 tests, 25 skipped). Historical outcomes are
unchanged. EXP-1173 completed 072—076: four
`failed/target-test-malformed-status`, one `failed/worker-failed`. Ledger has 76
IDs; stage remains empty; Observer has 608 events/266 checkpoints; owned server
is stopped. EXP-1174 completed 077—081 as five
`failed/target-test-malformed-status`. Ledger has 81 IDs; stage remains empty;
Observer has 653 events/286 checkpoints; owned server is stopped. Because the
fixed test order evaluates the boolean value for `level` first, this category
means `level=true` did not produce the expected HTTP 422; actual status and
candidate were not retained. EXP-1175 completed 082=`denied/worker-denied`,
083=`failed/target-test-malformed-status`, 084/086=`failed/worker-failed`, and
085=`blocked/worker-blocked`. Ledger has 86 IDs; stage remains empty; Observer
has 690 events/302 checkpoints; owned server is stopped. EXP-1176 completed
087=`failed/worker-proposal-invalid`, 088=`failed/target-test-readiness-exit`,
and 089—091=`failed/target-test-malformed-status`. Ledger has 91 IDs; stage
remains empty; Observer has 733 events/321 checkpoints; owned server is stopped.
EXP-1177 completed 092/093/095=`failed/target-test-malformed-status` and
094/096=`blocked/worker-blocked`. Ledger has 96 IDs; stage remains empty;
Observer has 774 events/339 checkpoints; owned server is stopped. EXP-1178
reached its pre-gate summary, which reported a fixed maximum of five model
requests despite selecting four attempts. The gate was not entered and no
model request was made; postcheck confirmed unchanged stores and no Ollama
listener. The CLI summary now derives the request maximum from the selected
attempt count (21 focused tests passed). EXP-1178 is BLOCKED and must not be
reused. EXP-1179 completed the final preregistered R5-097—100 with an exact
four-request summary cap: 097/098
`failed/target-test-malformed-status`, 099 `failed/worker-failed`, and 100
`failed/target-tests-failed`. The schedule now has 100 registered IDs, but this
does not establish a verified change. Aggregate ledger metadata across all 100
contains 29 UNKNOWN, 10 blocked, 2 denied, 55 failed, and 4 needs-input; stage
remains empty. The pinned study has no successful/verified result. R5 outcome
review and the independent verifier, authenticated approval, and controlled-PR
gates remain OPEN; MVP is not complete. Scenario-by-arm counts and the bounded
interpretation are recorded in §16 of `docs/33-r5-experimental-protocol.md`.
Local verifier-host bundle build also passes (81 members, 1,270,548 source
bytes, 1,351,680 archive bytes; in-memory digest
`sha256:34896bf8d06163f3dd6fa1c585f1883d2351c36a6279da8098c93afb505a02c2`;
two fresh in-memory builds were byte-identical; 13 bundle tests and 18 one-shot
HTTPS/service tests (2 skipped) passed. The workspace is broadly dirty, so this
bundle digest is only a current-worktree measurement, not a deployment-approved
source pin; no bundle was saved or transferred. Relative to HEAD
`52adc5b300d94a5168d7664b592cf8e3b84f3280`, its 81 members include 21 modified
tracked files and 8 untracked files; only 52 match the committed tree. Its
fixed host launcher and dependency manifest are among the untracked files, so
the service source is not currently reproducible from HEAD; a later service
setup must first pin/review that source bundle and authorize its transfer
separately. The manifest lists 77 `app_contracts` Python modules and four fixed
launch/requirements/schema files;
there are no named `.env` or key-material files (two credential-related source
modules are included as code, not credential values). This is a filename-level
package-boundary check, not a content scan or secret-leak proof.
An additional synthetic regression now places `.env`, SSH-key, signer-seed and
PEM-named files beside the bundle source and confirms they are absent from the
archive; no real credential values are used. The focused bundle suite passes
13 tests and the full offline suite passes 1,675 tests (25 skipped).

EXP-1183 (Batch YP) changed only `scripts/stream_pinned_verifier_image.py` and
`tests/test_stream_pinned_verifier_image.py`: the transfer now saves the pinned
archive by immutable `IMAGE_ID`
(`sha256:321c268a841de8cc354125ae25113b38835208f0e0f766f443514b63f1167b0c`)
instead of the conflicting remote tag, and accepts only
`Loaded image ID: <IMAGE_ID>` from `docker image load`. The local preflight
still requires the exact sole RepoTag
`["agent00x-verifier-exp466:8e26180bde4749438988170f85b395da"]`, while the
remote inspect runs by exact ID and is accepted only when it matches the same
ID/platform/size/ordered DiffIDs with an empty `RepoTags` list (`…|[]`), so the
conflicting remote tag is never rewritten. Memory-only stream, the
48,863,232-byte guard, SSH options, timeouts, output redaction and
single-attempt fail-closed no-retry markers are unchanged. Fake-runner tests
prove the save receives `IMAGE_ID` and not the tag, that tag/foreign-ID/extra
load output and load/inspect failures are rejected before success, that remote
inspect must show `RepoTags=[]`, and that no raw private output reaches the
marker evidence. Checks, each run exactly once and only against fake runners:
focused suite `Ran 12 tests … OK`; full offline suite
`Ran 1677 tests … OK (skipped=25)`; `git diff --check` exit 0. No real Docker,
SSH, network or testdev command ran; no commit, import, publication or
configuration change occurred. This is local contract/test evidence only: it
does not establish a remote copy of the pinned image, verifier
service/readiness, independent host trust, approval or publication; R2/MVP
remain OPEN.

Control Plane result for EXP-1188 (2026-10-14): after the visible one-time
`RUN EXP-1188 ONCE` gate, the exact read-only SSH inspection command ran once
and returned `PINNED_IMAGE_ID_UNAVAILABLE` (exit 0), an allowed bounded marker.
No second SSH, import, pull, tag mutation, diagnosis, or cleanup occurred. The
inspection does not distinguish an absent image from unavailable Docker CLI.
The separate user authorization for one EXP-1184 import does not permit a
repeat: that import attempt was already consumed and its remote identity
remains unconfirmed. R2/MVP remain OPEN.

Control Plane revalidation (2026-10-14): the current worktree's standard offline
suite completed successfully: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
discover -s tests -q` → 1,692 tests, 25 skipped, OK (83.472s). `git diff --check`
also exited 0. This is evidence for the current dirty worktree, not a clean
checkout/reproducible-release proof. EXP-1189 is DRAFT / SUPERSEDED because the
current verifier source closure changed; no new image import or other testdev
operation has been authorized or run.

EXP-1190 (Batch YW) now records the observed executor's sandbox-to-pin binding
decision through `SandboxSnapshot.validate-binding` before Worker dispatch.
The journal captures only fixed `ok`/`denied` outcomes; checkpoint refusal or
unknown terminal evidence prevents Worker invocation, while mismatch preserves
the prior fixed execution error. Resume preserves the one-shot guard. Tests
cover decision ordering, redaction, mismatch, journal refusal, lost terminal and
resume. The current verifier code closure hashes to
`sha256:33502d811d02277d7f3ff9f385faf575b4f851c06fb7b2f99722dc3ddb6791bb`,
matching the profile pin. Focused executor/observer tests: 54 passed; pinned
snapshot pipeline suites: 42 tests, 9 skipped, OK. Full offline suite: 1,696
tests, 25 skipped (1,671 passed), OK. `git diff --check` on task-allowed paths
passes. No Docker, SSH, network, credentials, live Worker/model, provider,
approval, branch/PR, push, deployment, testdev or commit ran. Collector
completeness and production durability remain unproven; R1 is still partial and
R2/MVP remain OPEN.

EXP-1191 rebuilt the verifier image locally from the current declared source
closure after EXP-1190. New profile image pin:
`sha256:f9cf14612cd0632eb20e42d6a78f91e7b1b73b09d7947c2edd67fc23e9dfcbc2`,
`linux/amd64`, size `48850488`, tag
`agent00x-verifier-exp466:70812b76c54447578c209bca7bf000f5`; code digest remains
`sha256:33502d811d02277d7f3ff9f385faf575b4f851c06fb7b2f99722dc3ddb6791bb`.
The build used only the pinned target runtime, with pull/network disabled; its
temporary dependency container was removed. The offline full suite passed 1,696
tests (25 skipped) and the exact context-digest test passed. No verifier
container runtime test, image save/export, SSH, testdev operation, or remote
transfer was performed. Historical runtime evidence for image
`sha256:321c268a...` does not transfer to this rebuilt image. EXP-1189 remains
superseded; current-image runtime validation and transfer metadata need separate
local cards before any newly authorized remote transfer. R2/MVP remain OPEN.

EXP-1192 then inspected the exact refreshed image tuple (ID above, `linux/amd64`,
48,850,488 bytes, exact sole tag) and ran the two named synthetic Docker verifier
tests. Both passed in 1.545 s with `--pull=never` and `--network=none`; assertions
covered synthetic PASS, UID 65532, read-only root, absent Docker socket,
restricted environment, and a 220,064-byte synthetic snapshot. This establishes
local same-host runtime behavior only. It does not establish independent-host
trust, service readiness, or testdev image identity. No image export, SSH,
testdev, remote operation, credential, model/Worker, provider, approval,
publication or commit occurred. A further local card is needed to refresh and
fake-test the transfer helper's exact image metadata before considering a new
remote import card; the old EXP-1184/1056/1189 approvals and runner pins cannot
authorize or identify this image. R2/MVP remain OPEN.

EXP-1193 refreshed the in-memory transfer helper to the current validated
verifier image. Exact metadata: ID
`sha256:f9cf14612cd0632eb20e42d6a78f91e7b1b73b09d7947c2edd67fc23e9dfcbc2`,
`linux/amd64`, size `48,850,488`, sole tag
`agent00x-verifier-exp466:70812b76c54447578c209bca7bf000f5`, nine ordered
DiffIDs. Exact-ID image-save stream measured `48,864,256` bytes in memory only;
no archive file was created. The helper's immutable identity, stream guard,
layer sequence and fake-runner expectations now match. Focused suite: 12 passed;
full offline suite: 1,696 tests, 25 skipped, OK; allowed-path diff check passed.
No real helper run, SSH, testdev, remote operation, credential, model/Worker,
provider, approval, publication or commit occurred. A new exact one-import card
and fresh user authorization are still required before any remote image-store
mutation; previous approvals refer to old cards/images. R2/MVP remain OPEN.

EXP-1196 re-ran the synthetic credential-canary composition on the current
target/verifier pins. Both exact local image inspections returned their pinned
IDs with `linux/amd64`; the one exact opt-in integration test passed in 2.724s.
The synthetic run scans the listed Worker/approval/publication stdout and
stderr, stage/observer SQLite, approval/trust inputs, observer report and local
mock receipt; receipt fields remain `external_write=false` and
`identity_authenticated=false`. No real credential, model/API, SSH, testdev or
provider write was used. This closes the prior-image gap for this particular
synthetic scan only; collection completeness, all possible surfaces, separate
host trust, authenticated approval and real publication remain unproven.
R2/MVP remain OPEN.

EXP-1198 exercised one current-pin public snapshot composition: one rate-limit
readiness request passed the `remaining >= 35` gate, followed by exactly 25
repository GETs (commit, tree, 23 blobs) and one raw-commit-source invocation.
The exact commit/tree/content digest and 23-file snapshot matched the pin.
One synthetic candidate was derived from fetched `backend/routes.py`, then
target tests, current pinned verifier, exact-digest stage/readback, and synthetic
signed/enrolled local-mock receipt passed. The receipt remained
`external_write=false`, `identity_authenticated=false`. The test used no real
model inference, credential or provider write; actual rate-limit remaining was
not emitted. This is current same-host composition evidence, not an independent
verifier, authenticated human approval or real PR. R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1271 refreshed the one-shot transfer
helper to the current local verifier pin
`sha256:ada0c0c0bc91e418582231a002e90b3bf1a3cdeaa52efc43cd2ee2c946940959`
and changed its gate from spent `RUN EXP-1261 ONCE` to fresh
`RUN EXP-1272 ONCE`. Current exact image tuple and stream-size checks, 13 focused
tests, one verifier-context contract test, and the 1,716-test offline suite pass
(25 skipped). EXP-1272's one freshly authorized import attempt returned only
`REMOTE_INSPECT_FAILED` (exit 16); remote image identity remains unconfirmed
and the image may have imported. No retry, separate diagnostic or cleanup ran.
A new exact card and fresh authorization are required for a read-only check.
Remote verifier readiness/trust, verified stage, authenticated approval and
real PR remain unproven; R2/MVP OPEN.

Control Plane update (2026-10-15): EXP-1272's single authorized transfer ended
`REMOTE_INSPECT_FAILED` (exit 16). The fixed marker means remote `docker image
load` returned status 0, but exact-ID inspect failed; remote identity is not
confirmed.
EXP-1273 retired the spent transfer entrypoint and repinned the separate
read-only inspector to the current image with gate `RUN EXP-1274 ONCE`. Focused
fake suites passed (12 transfer, 5 inspector); full suite passed 1,715 tests,
25 skipped. EXP-1274 is DRAFT pending fresh exact authorization for one SSH
inspect. No retry, diagnostic SSH, cleanup, provider action or publication ran.
Remote identity/readiness/trust, verified stage, authenticated approval and real
PR remain open; R2/MVP OPEN.

Control Plane update (2026-10-15): the separately authorized EXP-1274
read-only inspection was invoked once after the exact visible gate. It returned
only `REMOTE_INSPECT_FAILED` (exit 11), a marker that does not distinguish SSH
unavailability from a Docker inspect failure; the expected exact image tuple
was not confirmed. No retry, diagnostic SSH, cleanup, service start, provider
action, publication or commit followed. EXP-1274 is BLOCKED; remote image
identity and verifier readiness/trust remain unproven, and R2/MVP remain OPEN.

Control Plane result (2026-10-15): EXP-1277 received fresh exact authorization;
its gate was entered once and its sole read-only SSH invocation returned only
`REMOTE_INSPECT_FAILED` (exit 11). The expected image tuple was not confirmed;
the marker does not distinguish SSH unavailability from Docker inspect failure.
No retry, diagnostic command, cleanup, service start, remote mutation, provider
action, publication or commit followed. EXP-1277 is BLOCKED. Remote image
identity and verifier readiness/trust remain unproven; R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1284 rebuilt the verifier image offline
after the observer source-closure change. Exact local image pin is
`sha256:76a3d7da42cd26f00d145379c6b3467a480f4d0cba48f0e499ea3140bc79e5a1`,
source digest `sha256:e9b018828f24eea5aa1b50a65720587c1fcb7905baeff9f3c7c8fe599f997c2f`,
`linux/amd64`, size 48,851,536, nine ordered layers; both bounded synthetic
verifier-container tests and the 1,727-test offline suite passed (25 skipped).
EXP-1285 refreshed exact local transfer pins and fresh-gate contracts. EXP-1286
ran once after fresh authorization and returned `REMOTE_INSPECT_FAILED`
(exit 16): remote `docker image load` reported success, but exact-ID inspect
failed. EXP-1287 then ran once after separate fresh authorization and returned
`REMOTE_INSPECT_FAILED` (exit 11). Remote image presence/identity remains
unknown. No retry, diagnostic SSH or cleanup followed.
EXP-1288 registers the fresh local-Ollama profile
EXP-1289. Its one readiness GET passed (`200|60`); the one gated run logged one
model-call event pair, but exited 1 at a restricted sandbox command before
verification/staging. Observer DB is healthy (77 events, 38 checkpoints, cursor
76, mode 0600); stage DB is healthy but empty. EXP-1290 classified the sole
failure as `sandbox-command-nonzero`; the failed assertion is still unknown.
Ollama was stopped; no retry, approval, or publication occurred. R2/MVP remain
OPEN.

EXP-1291 pins local Ollama sampling at temperature 0 and seed 42; caller
overrides are rejected, leaving the DeepSeek payload untouched. This is a
repeatability control, not evidence that sampling caused EXP-1289's failed
target command. EXP-1292 registers fresh local profile EXP-1293. Its source and
tests pass; the full offline suite is 1,730 tests (25 skipped). EXP-1293 is
BLOCKED: its one readiness check returned `READINESS|200|35|1792090084`, below
the required 36. It stopped before snapshot, Ollama startup and model inference;
the exact gate was not entered and the card must not be retried. A new profile
and card are required after reset. R2/MVP remain OPEN.

EXP-1294 adds a strictly bounded `safe_parameters.sandbox_return_code` for
sandbox terminal events and projects only that numeric field for allowlisted
sandbox run operations. Synthetic tests confirm return-code validation and
that command output is absent from SQLite/report; this does not classify the
failed assertion from EXP-1289. EXP-1295 rebuilt the verifier after the shared
schema-validator change, refreshed the exact local image/code/transfer pins and
one-shot gates, and prepared fresh DRAFT EXP-1296/1297 remote cards. The current
full offline suite passes 1,735 tests (25 skipped). No new Worker/model attempt
or remote image action occurred; R2/MVP remain OPEN.

EXP-1298 registered a distinct one-shot local-Ollama profile EXP-1299 after
EXP-1293's below-threshold readiness stop; EXP-1293 remains blocked and will
not be reused. EXP-1299's one readiness GET returned HTTP 200 / remaining 35
(<36); it stopped before daemon, snapshot or Worker and must not be retried. A
new profile/card is required after reset. The full offline suite passes 1,736
tests (25 skipped). No new Worker run occurred; R2/MVP remain OPEN.

EXP-1296's fresh user-authorized one-shot image transfer returned
`REMOTE_INSPECT_FAILED` (exit 16): the script reports remote `docker image load`
status 0, but the subsequent exact-ID inspect failed. Remote image presence is
possible; identity remains unknown. No retry, diagnostics, separate inspect or
cleanup followed. EXP-1297 remains DRAFT pending separate fresh authorization.
The current verifier is not established on testdev, and no service/trust,
authenticated approval or PR evidence exists; R2/MVP remain OPEN.

EXP-1300 refreshed the deterministic verifier-host source bundle after the
observation-event schema changed. Two in-memory builds matched at
`sha256:d8c8e2a40975d0ebcfe05210d98f2779bc032f975d6def84909d93e9313ec8de`
(31 members, 536,278 source bytes); the old EXP-1281 pin is stale. This digest
comes from the current dirty worktree and is not a reviewed deployment artifact.
Focused bundle tests: 14 passed; full suite: 1,736 tests (25 skipped). No SSH,
Docker, credentials or service action occurred; R2/MVP remain OPEN.

Control Plane update (2026-10-15): EXP-1317 re-enabled the one-shot,
fixed-marker read-only verifier-host probe under fresh exact gate
`RUN EXP-1318 ONCE`. The probe checks only Docker CLI availability, daemon
availability and the exact current verifier image identity. Its one fresh
user-authorized invocation returned `REMOTE_IMAGE_INSPECT_FAILED` (exit 12):
the fixed protocol passed CLI and daemon checks, but did not confirm the image.
The result does not prove the image is absent. No retry or further remote action
occurred. Focused tests pass (6); the full offline suite passes (1,744 tests,
25 skipped). Testdev verifier image identity, service/readiness/host trust,
authenticated approval and real PR remain unproven; R2/MVP remain OPEN.

Control Plane result (2026-10-15): EXP-1314's one freshly authorized transfer
returned `REMOTE_INSPECT_FAILED` (exit 16). The helper reports remote
`docker image load` status 0 but failed to confirm the exact immutable image
tuple. The image may be partly or fully present; identity remains unconfirmed.
No retry, diagnostics, separate inspect or cleanup occurred. EXP-1315 is a
separate read-only inspect and still requires fresh user authorization. The
independent verifier host and R2/MVP gates remain OPEN.

Control Plane result (2026-10-15): EXP-1315's one separately authorized
read-only SSH inspect returned `REMOTE_INSPECT_FAILED` (exit 11). SSH exit 255
is distinguishable, but the fixed marker does not prove whether the remote
Docker command or image inspect failed. The current verifier image identity
remains unconfirmed; no retry or further remote operation occurred. No
independent verifier service/readiness, authenticated approval or real PR is
established; R2/MVP remain OPEN.

EXP-1319 added an exact-ID-only read-only Docker image-presence probe after the
EXP-1314 transfer and EXP-1315 inspect both failed to confirm image identity.
Its helper never emits the host's image inventory; the exact gate is
`RUN EXP-1320 ONCE`. Focused tests passed (4); full offline suite passed (1,748
tests, 25 skipped). No remote request has been made. EXP-1320 remains DRAFT
pending fresh user authorization; verifier service/readiness/trust, approval
and real PR remain OPEN.

Control Plane reconciliation (2026-10-15; supersedes matrix evidence cutoff at
EXP-1313): EXP-1318 confirmed Docker CLI and daemon availability but did not
confirm the image. EXP-1314's one import reported `docker image load` status 0,
then failed exact-ID inspect; EXP-1315's separate read-only inspect also failed.
EXP-1319 adds only a local helper/test for redacted exact-ID presence checking;
EXP-1320 is still DRAFT. These results do not prove remote image presence or
absence. The independent verifier service, authenticated host trust, approved
digest-bound human approval and real controlled PR remain unproven. No MVP
criterion is promoted; R2/MVP remain OPEN.

Control Plane update (2026-10-15): after fresh exact user authorization,
EXP-1320's `RUN EXP-1320 ONCE` gate was entered once. The only remote query
checked whether the exact pinned verifier image ID
`sha256:babefaa38e0e068f3af35b9f00d0ff0ea319a69e3a13697fe471b3e01a2cdf6a`
appeared in Docker's image-ID list; it returned the fixed marker
`REMOTE_IMAGE_ID_ABSENT` (exit 10). Thus the exact image was absent at the time
of this check. No image import, inspect, tag change, container/service start,
retry, diagnostic action, cleanup or other remote operation followed. This is
not evidence of a verifier service, independent-host trust/readiness,
authenticated approval or real PR. R2/MVP remain OPEN; no criterion is promoted.

R1 local consolidation (2026-10-15, EXP-1324): six focused digest/manifest
regressions passed. They reject invalid or reordered verified-file manifests
before loader/broker effects, staged-content digest substitution before gateway,
broker, journal or mock effects, swapped actuator request digest, tampered
approved-intent digest, and coordinated request/intent substitutions. The full
offline suite also passed (1,748 tests, 25 skipped), including the pre-dispatch
journal tests that refuse dispatch when checkpoint/intent persistence fails.
This supports local fail-closed behavior only: it does not establish complete
subagent checkpoint coverage or operational journal durability. No MVP criterion
is promoted; R1 remains partial and R2/MVP remain OPEN.

EXP-1326 revalidated the current local verifier pin: the read-only inspect
matched image `sha256:babefaa38e0e068f3af35b9f00d0ff0ea319a69e3a13697fe471b3e01a2cdf6a`
(`linux/amd64`, 48,854,834 bytes, nine expected ordered DiffIDs, sole pinned
RepoTag), and the source-closure test confirmed code digest
`sha256:f63ecc2359fe0c9dcd51893d55d831bacb33daa0b289a3b87d0b6a65de1d660f`.
Both exact-pin synthetic verifier-container tests passed, including the bounded
large-snapshot case. The initial local inspect happened before its card was
written; it was read-only and was not repeated. This is local synthetic evidence,
not remote image presence, independent-host trust/readiness, authenticated
approval, or a real PR. No R2/MVP criterion is promoted; both remain OPEN.

EXP-1327 audited the local approval route. `create_approval_request.py` reads
one exact quiescent stage through SQLite read-only mode, emits an unsigned
review request and canonical Ed25519 signing bytes, and binds both the staged
change and approved intent digests. The 23 approval-request and signed-mock
publication tests passed, including an in-memory signing round-trip, tampered
intent rejection and exact-digest mock receipt. This is synthetic key-possession
evidence only: no trusted human signer enrollment was exercised; the mock CLI
explicitly reports `identity_authenticated=false` and `external_write=false`.
Real digest-bound approval and controlled real PR remain open; no criterion is
promoted, and R2/MVP remain OPEN.

EXP-1328 adds `sign_approval_request.py` and `approval_signer.py`. Before key
access, the signer re-reads one exact stage in SQLite read-only mode, rebuilds
and canonical-compares the complete approval request, checks expiry, displays
the bounded action/patch, and requires an exact digest-specific confirmation.
Only then does it resolve the fixed `AGENT_APPROVER_SIGNING_SEED` through the
process-environment credential source once and emit a signed envelope to stdout;
it writes no file and has no provider adapter. Seven focused synthetic tests
passed, including tamper/expiry/gate refusal before credential lookup, a
confirmation-time expiry boundary, exact-signature verification, and unchanged
stage bytes. The existing request/mock suites plus signer suite passed (30
tests). No live seed was read or approval artifact created. This grants no human
identity authentication and no real publication capability; approver enrollment
and external write gates remain open. The full offline suite passes 1,755 tests
(25 skipped). R2/MVP remain OPEN.

EXP-1329 adds a fresh, independently named gate wrapper for a possible new
transfer of the pinned verifier image. Two offline tests passed: prior/inexact
phrases do not dispatch, while `RUN EXP-1330 ONCE` dispatches the bounded
transfer exactly once. Full offline suite: 1,757 tests (25 skipped);
`git diff --check` passed. No Docker, SSH, network, credentials, service or
provider action occurred. EXP-1330 remains DRAFT for a single fresh user
authorization; it would load only the exact image into Docker's image store and
inspect the exact tuple. It cannot establish service readiness, independent
host trust, authenticated approval or real PR. R2/MVP remain OPEN.

Control Plane result (2026-10-15): EXP-1320's authorized exact-ID presence
check had returned `REMOTE_IMAGE_ID_ABSENT`. EXP-1330 then received separate
fresh authorization and ran once through `RUN EXP-1330 ONCE`. Local image
preflight matched the pinned ID, tag, platform, size and nine ordered DiffIDs;
15 focused gate/transfer tests, the 1,757-test offline suite (25 skipped), and
`git diff --check` passed. The only remote run returned
`REMOTE_INSPECT_FAILED` (exit 16): `docker image load` reported status 0, but
the exact-ID inspect failed. Whether the image is now present is unknown. No
retry, separate inspect, diagnostic, cleanup or service/container action
followed. A fresh exact card and user authorization are required for any next
remote check. Independent verifier readiness/trust, authenticated
digest-bound approval and real PR remain unproven; R2/MVP stay OPEN.

Control Plane result (2026-10-15): EXP-1338's single local in-memory audit of
the pinned `docker image save` payload returned `CONFIG_ID_MISMATCH` (exit 23)
and bounded facts: `config_hash_matches_pin=false`,
`config_filename_stem_matches_hash=true`, `diff_ids_match_pin=true`, and
raw layer-member bytes did not hash to DiffIDs. EXP-1339 corrected the layer
comparison for gzip encoding: one further authorized local audit found all nine
layers gzip-compressed, raw member hashes unequal to DiffIDs, but streamed
uncompressed hashes equal to the expected ordered DiffIDs. The earlier claim
that layer contents mismatched is withdrawn. The config hash still differs from
the pinned image ID even though its filename stem matches its own content hash
and its embedded DiffIDs match the pin. No raw archive was retained. No remote
operation, rebuild, retag or pin change occurred. The saved export remains
unsuitable for transfer under the existing pin until config-ID discrepancy is
explained and resolved; R2/MVP remain OPEN.

EXP-1331 prepared a distinct one-shot, read-only image-inspect gate; seven
focused wrapper/inspector tests and the full 1,759-test suite (25 skipped)
passed. EXP-1332 is DRAFT for one SSH `docker image inspect` of the exact pinned
ID and complete metadata tuple on testdev. It does not authorize import or any
service action; fresh user authorization is still required. R2/MVP remain OPEN.

Control Plane result (2026-10-15): EXP-1332's one freshly authorized
read-only exact-tuple inspection returned `REMOTE_INSPECT_FAILED` (exit 11).
This does not establish whether the image is absent or the remote inspect
failed; no follow-up command was issued. EXP-1333 prepares a distinct
exact-ID-only read-only presence check for EXP-1334. Its six focused tests and
the full offline suite (1,761 tests, 25 skipped) passed; `git diff --check`
passed. EXP-1334 ran once after fresh exact user authorization and returned
`REMOTE_IMAGE_ID_ABSENT` (exit 10). The exact verifier ID is absent from the
Docker image store on testdev at this check time, following EXP-1330's
load-status-0 / inspect-failed outcome. The query did not expose other image
IDs and made no changes. This establishes current absence, not the cause of the
earlier discrepancy; no retry or diagnostic action followed. A new import path
must be justified and separately authorized. Verifier deployment/trust,
authenticated digest-bound approval and real PR remain unproven; R2/MVP stay
OPEN.

Local Control Plane result (2026-10-16): EXP-1344 emitted the exact public
config digest from one local saved-image archive:
`sha256:abead7559044e2f44369eed75ccfc56c5079cb5df08809e4c29f855d98bedfb3`.
The config filename matched its content hash; embedded ordered DiffIDs matched
the verifier profile; all nine gzip-compressed layer members matched those
DiffIDs after streaming decompression. The config digest did not equal the
local `.Id`/descriptor digest, while descriptor digest did equal that image ID.
This yields a portable content identity candidate but does not establish
testdev presence, trust or verifier service readiness. No archive was retained
and no remote operation occurred. EXP-1345 then verified that the archive's
single OCI index target digest equals the local image ID and that its manifest
blob hash matches the descriptor. The serialized export therefore preserves
the source manifest identity; the prior testdev absence is more likely due to
target image-store/import behavior or an incomplete load. EXP-1346 received
fresh exact user authorization for one read-only config-digest inspect on
testdev. Its sole SSH run returned only
`REMOTE_IMAGE_IDENTITY_MISMATCH` (exit 11); the redacted marker cannot
distinguish an absent image from a mismatching tuple. No remote diagnostics,
retry or follow-up action occurred, and the one-shot authorization is consumed.
Resolving this requires a newly scoped card and fresh permission. R2/MVP remain
OPEN. EXP-1347's one freshly authorized exact-ID-only SSH query returned
`REMOTE_CONFIG_IMAGE_ID_PRESENT` (exit 0): the config digest is addressable in
testdev's Docker image store. EXP-1348 then received separate exact
authorization; its one tuple inspect returned
`REMOTE_CONFIG_IMAGE_TUPLE_MISMATCH` (exit 11), without revealing raw metadata
or the mismatching field. No retry or remote diagnostics followed. The local
tuple wrapper's three focused tests and full offline suite passed: 1,801 tests,
25 skipped. EXP-1349 is a DRAFT boolean-only field-facts inspect; its wrapper's
three tests are included in the 1,801-test suite and require separate fresh
authorization before remote use.

The focused synthetic composition
`RemoteSnapshotPipelineTests.test_remote_seed_approval_and_mock_publication_share_exact_digest`
also passes on the current tree. It exercises a synthetic snapshot fixture, a
fixed-response Worker, local-process sandbox, local subprocess verifier,
SQLite stage persistence and local mock receipt under one digest. It does not
use the selected BrainBooster repository, a live model, restricted container,
independent verifier host, signed approval or GitHub publication.

EXP-1381 добавил `prepare_pinned_verifier_enrollment_request.py`: он принимает
ровно две bounded canonical JSON-строки (bootstrap и operator bindings),
сверяет caller-supplied bootstrap SHA-256, повторно использует строгую проверку
public bootstrap и локальный verifier image/code pin, затем строит существующий
domain-separated signing request. Закрытые ключи, подпись, файлы, сеть и signer
не используются; вывод явно сохраняет `trust=unestablished`. Пять synthetic
tests проверяют точный message binding, неверный pin, повреждённый bootstrap,
дополнительные/дублирующие поля и отсутствие частичного stdout при ошибке.
Digest, вычисленный из того же SSH bootstrap, остаётся только проверкой
целостности, не independent/OOB trust.

EXP-1380 выполнила один отдельно подтверждённый запуск переданного launcher на
testdev: получена ровно одна публичная bootstrap-запись с endpoint
`https://testdev.local/v1/verify`, профилем
`sha256:603f0e674e131ef795f115f099cdeb514452a82def41e5b5853f84f62d7ff281`,
CA digest `sha256:2b71c9af388839648a033fde0f4886928b569010b8364531a6587bac7a90a949`
и verifier public-key digest
`sha256:1544ec9b493e8289705e945e93d5ffc9ea02530c4442eaf010982f913344d52e`.
SSH-сессия оставлена ждать максимум один запрос до idle timeout 900 секунд;
запрос не отправлялся. Это подтверждает запуск listener и выдачу его публичного
bootstrap, но не независимый host trust, verifier behavior или end-to-end
readiness. Сессия позже закрылась с кодом 2 без дополнительного вывода;
launcher использует этот код, если единственный запрос не дал HTTP 200. Так как
карточка запрещала запрос, а idle timeout был ожидаемым, это только ограниченное
завершение без verifier-response, не проверка поведения verifier. Control Plane
подтвердил, что authority-key-set/signer source пока отсутствует; EXP-1383
остаётся DRAFT, поэтому доверие не установлено и verifier-запрос не разрешён.
Полный offline suite после EXP-1381: 1,859 тестов (1,834 прошли, 25 пропущено);
R2/MVP остаются OPEN.

Актуальное дополнение на 2026-10-18: EXP-1394 выполнила ровно один отдельно
подтверждённый strict-host-key SSH-запуск ephemeral loopback verifier и
сохранила свежий публичный bootstrap для `https://testdev.local/v1/verify`,
port 49231, profile
`sha256:603f0e674e131ef795f115f099cdeb514452a82def41e5b5853f84f62d7ff281`, CA
`sha256:405c545a5f927036a1cb6a93de9121e06590d18abaace6dbe7887122acf462cc`,
verifier public-key digest
`sha256:f7e44e01375646c11d9d5203204a883f862b59c32d26f6c4c6df02133b58c7ec`.
Локальный strict parser принял точный byte-pinned файл и вывел
`trust=unestablished`. Verifier HTTP request/response, подпись, authority source,
host-separation proof, approval и provider write отсутствуют; истечение
ephemeral listener не проверялось. EXP-1383 остаётся DRAFT; R2/MVP остаются
OPEN. Это подтверждает получение публичных bootstrap-фактов, но не доверие,
готовность сервиса после one-shot запуска или сквозной runtime.

EXP-1407: полный локальный offline suite на текущем worktree завершился успешно:
1,867 тестов, 1,842 passed, 25 skipped, 79.781 секунды. Запуск был без Docker
opt-in, сети, credentials, Worker/model и удалённых действий. Это только свежее
регрессионное evidence; доверие, R2 и MVP остаются OPEN.

EXP-1408 (2026-10-18): an anonymous public `git ls-remote` with Git credential
helpers and extra HTTP auth headers disabled resolved both upstream `HEAD` and
`refs/heads/master` for `SoldatovAlexander/brainbooster_full_v11` to
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, matching the EXP-1393 pinned
snapshot. No content was fetched. The check only confirms the public ref pointer
at this time; it does not establish authorship, immutable branch state, target
behavior or any R2/MVP gate.

EXP-1410 provisioned one Ed25519 Control Plane key into the user-designated
macOS Keychain item for EXP-1383. The private key was not written to a project
file or emitted. The key is stored as a Keychain generic-password item; the
unrun `--sign` path currently retrieves its raw representation into process
memory to construct a CryptoKit key. This is not a Secure Enclave or
non-extractable-key guarantee. The EXP-specific Swift signer passed its in-memory synthetic
self-test for enrollment and host-decision signatures and rejected an endpoint
mismatch. Public key-set file `control-plane-authority-keys-exp1383.json` has
digest `sha256:6e1491662c6e108ff8952f6d42cd15e2f69259a91975aee920471c6edb8701b8`.
The user must pin this digest through the separate chat channel before any real
trust-message signature. No real message was signed. Existing EXP-1385/1386
host-fingerprint evidence has digest
`sha256:82a1c8915d819c5c71fa395a411575a1268b72ecb96efeaed8c235305e6fb941`; it
records distinct local-Mac/testdev fingerprints but references a disposable
EXP-1386 key-set and does not prove deployment, runtime or isolation. User
review/acceptance (or separately authorized fresh evidence) is pending.
EXP-1383 remains DRAFT; R2/MVP remain OPEN.

EXP-1412 aligned the EXP-1383 macOS signer timestamp parser with the existing
Python trust contracts: only canonical UTC timestamps with whole seconds and a
terminal `Z` are accepted. Its in-memory self-test still verifies both
signature kinds and now rejects fractional-seconds and offset spellings, as
well as a wrong endpoint. `swift scripts/exp1383_macos_keychain_signer.swift
--self-test` passed; the full offline suite passed (1,867 tests, 25 skipped).
The self-test did not access Keychain, and no real trust signature or remote
operation occurred. This is protocol-compatibility evidence only; EXP-1383
remains DRAFT pending user pin and review/acceptance of the existing
fingerprint-only evidence or a separately authorized refresh. R2/MVP remain
OPEN.

EXP-1413 makes the EXP-1383 signer require explicit command-line pins for the
expected public-key-set digest and reviewed host-separation evidence digest.
It checks request canonicality and evidence-digest equality before reading
Keychain, then checks the retrieved key's public-set digest before signing.
The self-test covers matching and mismatching synthetic pins. These checks
enforce binding consistency only; they cannot prove that the user actually
pinned the key-set out of band or reviewed the evidence. Swift self-test and
full offline suite passed (1,867 tests, 25 skipped); `git diff --check` passed.
No Keychain access, actual signature, or remote operation occurred. Before
running `--sign`, clarify that process-memory use is consistent with the user's
instruction not to export the private key; EXP-1383 remains DRAFT and R2/MVP
remain OPEN.

EXP-1414 validated the existing `verifier-host-separation-exp1385.json` bytes:
879 bytes, exact SHA-256
`sha256:82a1c8915d819c5c71fa395a411575a1268b72ecb96efeaed8c235305e6fb941`, schema
`agent00x-host-separation-evidence/v1`, scope
`host-fingerprint-separation-only`, observed at `2026-10-17T18:33:56Z`. The
worker Mac and testdev Linux fingerprints are distinct. Its embedded authority
key-set digest is the expired disposable EXP-1386 key-set
`sha256:d00f8caf1d14623f675edde06b0c44567183e9dc5ca725d14eb155ed9590efbe`, not
the current EXP-1383 Keychain key-set. No SSH or new evidence collection
occurred. This historical artifact does not authenticate current deployment,
verifier runtime or isolation; user review/acceptance is still needed.

EXP-1415/1416 local Ollama preflight: the 0.40.3 client had no running server.
EXP-1415's first startup exposed `OLLAMA_NO_CLOUD=false`, so no inventory call
was made and the server was immediately stopped. EXP-1416 restarted only on
`127.0.0.1:11434` with `OLLAMA_NO_CLOUD=1`; startup markers confirmed cloud
disabled and loopback bind. One local `ollama list` returned one installed
model; raw name/ID was suppressed. The temporary server was stopped and the
port is closed. No model inference, download, Worker, network request, Keychain
or remote operation occurred. This proves local model availability only, not
Worker readiness or repository-change execution. R2/MVP remain OPEN.

EXP-1417 compared the installed Ollama inventory against the code-pinned local
Worker model `qwen2.5-coder:7b` without invoking inference. With
`OLLAMA_NO_CLOUD=1`, the temporary server bound only to loopback, and the
bounded result was `PINNED_MODEL_PRESENT|true`. Raw model names/IDs were not
emitted; the process was stopped and the port is closed. This establishes
local model availability only, not Worker readiness or a successful target
run. R2/MVP remain OPEN.

EXP-1418 checked whether this macOS Security.framework can create an Ed25519
`SecKey` suitable for signing without exposing private bytes. Although the
framework exports Ed25519 type/algorithm symbols, a sanitized transient
`SecKeyCreateRandomKey` probe failed with `NSOSStatusErrorDomain/-4`; no key was
created. The EXP-1410 generic-password Keychain item was not accessed; its
public key-set file was read only and not modified. No real message was signed.
Its signer reads key bytes
back into process memory, so it does not meet the user's literal no-export
constraint and must not be used for EXP-1383. EXP-1383 remains DRAFT pending a
supported non-exporting Ed25519 Keychain signing interface and the existing
public-key pin/evidence review; R2/MVP remain OPEN.

EXP-1419 fixed the EXP-1383 signer CLI dispatch guard: the exact five-argument
`--sign` form is now reachable, while malformed/reordered forms are rejected by
a pure validator before stdin or Keychain access. Synthetic argument-shape tests,
Swift self-test, and `--help` passed; the full offline suite passed 1,867 tests
(25 skipped). No Keychain access, provisioning or signature occurred. This does
not resolve EXP-1418: the current CryptoKit-backed generic-password approach
loads key bytes into process memory and remains unusable under a strict
no-export interpretation. EXP-1383, R2 and MVP remain open.

EXP-1420 tested another local-only route with synthetic data. `SecKeyCreateWithData`
could sign/verify a synthetic Ed25519 message, but Security reported the imported
key as extractable. `SecItemImport` with no Keychain target rejected both raw
Ed25519 and unwrapped PKCS#8 representations as `errSecUnknownFormat` (-25257).
No Keychain item was created or queried. Thus native non-exportable Ed25519
signing remains unsupported by the tested APIs on this Mac; no production key
or EXP-1383 message was involved. R2/MVP remain OPEN.

EXP-1422 checked Apple's current [CryptoKit Keychain sample](https://developer.apple.com/documentation/cryptokit/storing-cryptokit-keys-in-the-keychain)
and [SecureEnclave API](https://developer.apple.com/documentation/cryptokit/secureenclave)
documentation against the EXP-1418–1420 local probes. The sample explicitly
says `Curve25519.Signing.PrivateKey` (Ed25519) has no direct `SecKey` corollary
and shows storing its raw representation as a generic-password item; that route
necessarily makes the key representation available to the signer process.
Apple's documented `SecureEnclave` signing interface is P-256, not Ed25519.
Together with the local `SecKeyCreateRandomKey`/`SecItemImport` failures, no
documented Apple-framework route was found for a non-exportable Ed25519 signer
on this Mac. This is not proof that no third-party/hardware signer exists, and
does not justify changing the protocol algorithm or using the legacy generic-
password key. EXP-1383 remains DRAFT until the user either permits strictly
bounded in-process key use or designates a different supported Ed25519 signing
source. No Keychain was accessed and no signature or remote operation occurred;
R2/MVP remain OPEN.

EXP-1424 registered a fresh one-shot credential-free local Worker profile,
EXP-1425, without changing existing profiles. Synthetic profile coverage passed
(51 focused CLI tests); full offline suite passed 1,868 tests (25 skipped), and
`git diff --check` passed. EXP-1425 used the exact pinned public snapshot and
one local Ollama call; target tests failed with bounded
`target-test-malformed-status-level-bool` before verifier or stage. The run
recorded observer cursor 76 (`completeness=partial`), `external_write=false`,
no approval and no publication. Both retained SQLite DBs pass `quick_check=ok`
and mode 0600. The owned Ollama process stopped and port 11434 is closed. This
new attempt does not authorize a retry; the prior successful EXP-1269 chain
remains the latest successful Worker→target→same-host verifier→stage run.
Independent verifier trust, authenticated approval, controlled PR and R2/MVP
remain OPEN.

EXP-1426 fetched only the pinned public `backend/routes.py` from commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`; its SHA-256 matched the local
EXP-1393 snapshot manifest. An in-memory AST summary found no explicit strict
integer type check in the `/save-session` handler or its reachable helpers
before the first database-like call. That confirms the baseline gap targeted
by the Worker instruction but cannot identify EXP-1425's unretained candidate
or explain its exact failure. No source was persisted and no retry occurred.
R2/MVP remain OPEN.

EXP-1427 made one separate anonymous GET of the same pinned route; its digest
matched. The `/save-session` handler accepts `data: dict` and has no `StrictInt`,
strict constrained integer type, or Request-body parser. Thus FastAPI does not
coerce `status_level` as a typed integer parameter before the handler receives
the dictionary; JSON booleans remain booleans. This rejects the proposed
parameter-coercion explanation, but the unretained EXP-1425 candidate and exact
failure cause remain unknown. No source was emitted/persisted, and no code, DB,
model, Docker, Keychain, or remote action occurred. EXP-1425 remains spent;
R2/MVP remain OPEN.

EXP-1428 added a distinct one-shot local Worker profile and made its prompt
explicit that Python `bool` subclasses `int` and must be rejected with
`type(value) is not int`. Focused CLI tests passed (51), the full offline suite
passed (1,868 tests, 25 skipped), and `git diff --check` passed. Local target
and verifier-manifest image IDs matched `linux/amd64`; the config image ID was
not present as a separate local alias and is not the runner's pinned image ID.
An owned Ollama server started cloud-disabled and loopback-only; the installed
model digest matched. A separate manual Python default-context GitHub quota
probe failed TLS verification with no HTTP status; it did not exercise the
runner transport. The run stopped before the runner readiness GET, snapshot
intake, model call or DB creation. The owned server was stopped and port 11434
is closed; EXP-1428 is spent and not retried.
Its static authorization profile was removed from the runner, with tests
asserting that the spent gate is unavailable.
EXP-1269 remains the latest successful Worker→target→same-host verifier→stage
run. Independent verifier trust, approval, publication and R2/MVP remain OPEN.

EXP-1429 inspected TLS roots locally without network access. Python 3.13 has no
default CA file/directory in its OpenSSL paths, while the installed `certifi`
package provides an existing regular non-symlink CA bundle at
`/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/certifi/cacert.pem`.
macOS curl reports Apple's SecureTransport backend. No CA contents/store or
environment were changed. A standard explicit CA bundle is available for a
future strictly verified request, but GitHub reachability through it has not
been established. R2/MVP remain OPEN.

EXP-1430 used that exact existing `certifi` bundle with a proxy-disabled
anonymous Python HTTPS request and normal certificate validation. The single
GitHub rate-limit GET returned HTTP 200, core remaining 35/60. TLS transport is
now proven, but quota is below the required threshold of 36; no runner
readiness/snapshot GET, Worker/model, DB or service was started. No retry.
R2/MVP remain OPEN.

EXP-1431 made one fresh quota-only GET with the validated `certifi` bundle and
no proxy/credentials. HTTP 200 returned core remaining 35/60, still below the
Worker card's threshold 36. No snapshot/runner request, model, DB or service
action followed. A new Worker attempt remains gated on an adequate quota
window and a separate READY card; R2/MVP remain OPEN.

EXP-1432 confirmed from source and tests that the runner's GitHub transport
constructs a verified default SSL context, loads `certifi.where()`, and checks
hostname validation, `CERT_REQUIRED` and a nonempty CA store for both
`/rate_limit` and snapshot GETs. Its focused suite passed (12). The manual
default-context failure in EXP-1428 therefore was not evidence of runner TLS
failure; EXP-1430's successful direct certifi request is consistent with the
runner's existing trust setup. No runner network request was made. Quota 35 is
still below the execution threshold; R2/MVP remain OPEN.

EXP-1433 used the fixed runner transport once for a fresh quota observation:
HTTP 200, core remaining 35, reset Unix `1792279750` (`2026-10-17 23:29:10 UTC`).
No snapshot or Worker action occurred. This gives the next eligible quota
window; the built-in readiness gate still requires remaining >=36. R2/MVP
remain OPEN.

EXP-1434 registers the next local Worker profile with the clarified bool
instruction. Its focused CLI tests passed (51) and the full offline suite passed
(1,868 tests, 25 skipped). Local target/verifier-manifest pins match
`linux/amd64`, the two DB destinations are absent/non-symlink, and port 11434 is
closed. Its reset time has passed, but the two-hour authorization expired before
runtime; no quota request, snapshot, Ollama startup, model call or DB creation
occurred under that card. EXP-1434 is now DRAFT pending a fresh card/authorization
and in-window quota check. EXP-1437 removed its expired static profile, snapshot
origin and backend mappings; the 51 focused CLI tests and the 1,868-test offline
suite (25 skipped) pass with assertions that the stale profile is unavailable.
No Worker/model or external request was made. R2/MVP remain OPEN.

EXP-1423 disabled the EXP-1410 legacy Keychain signer path. The Swift CLI now
returns the fixed marker `EXP1383_NONEXPORTING_ED25519_SIGNING_UNAVAILABLE`
for both `--sign` and `--provision` before stdin parsing or any Keychain call;
the Keychain import and raw-key retrieval code was removed. The existing
Keychain item and public key-set were not queried, changed or deleted. Synthetic
`--self-test` and `--help` pass; both disabled commands returned the fixed
marker with exit 2. The full offline suite passed (1,867 tests, 25 skipped),
and `git diff --check` passed. This enforces the user's no-export instruction
for the existing CLI but does not provide a usable non-exportable Ed25519
signer; EXP-1383 remains DRAFT and R2/MVP remain OPEN.

EXP-1435 records the user's explicit authorization for bounded, EXP-1383-only
Keychain use without exporting or displaying the private key. A distinct v2
Ed25519 generic-password item was created; the legacy item was not queried or
changed. Only the public key-set was emitted and saved at
`control-plane-authority-keys-exp1383-v2.json`, digest
`sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`.
CryptoKit's generic-password path transiently handles raw representation in
local process memory, so this is not a hardware-backed/non-exportable-key
claim. The CLI now gates its EXP-1383-only signing path on exact caller-supplied
key-set and host-evidence digests before Keychain read; synthetic self-test and
CLI help passed. No real trust message was signed. The new key-set digest still
needs the user's explicit pin, and current EXP-1436 fingerprint-only evidence
still needs user review/acceptance.
EXP-1383, independent verifier trust, approval, publication and R2/MVP remain
OPEN.

EXP-1436 collected the Mac and testdev identity fingerprints with exactly one
local hash command and one strict-host-key SSH invocation. Both raw identifiers
were withheld; the observed fingerprints differ, and testdev reported the
expected hostname/OS. The public evidence artifact
`verifier-host-separation-exp1436.json` references the v2 key-set digest above
and has SHA-256
`sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`.
It is in REVIEW only; its observation precision is date-only. This supports
fingerprint separation only, not current deployment identity, verifier runtime
or host isolation. No Keychain signing, verifier request, Worker, approval or
publication occurred. EXP-1383 remains DRAFT pending user review and explicit
digest pin; R2/MVP remain OPEN.

The EXP-1434 Worker one-shot did not run before its two-hour authorization
expired at 2026-10-18 00:25 UTC. Its runtime authorization is stale and requires
a fresh card/authorization plus an in-window quota check. The current offline
suite was rerun on 2026-10-19: 1,868 tests passed, 25 skipped. This is regression
evidence only, not a Worker or end-to-end result.

EXP-1437 retired the expired EXP-1434 static CLI profile; tests assert the old
card ID is absent from all three authorization maps. EXP-1438 added a new
one-shot profile, then performed exactly one anonymous verified-TLS GitHub
`/rate_limit` GET (HTTP 200, remaining 59). The exact target and verifier images
were present on `linux/amd64`. Its apparent model-pin failure was a formatting
bug: the predicate compared Ollama's bare 64-hex model digest with a
`sha256:`-prefixed literal. EXP-1439 repeated that flawed comparison, so its
`MODEL_NAME_PRESENT_PIN_MISMATCH` marker did not establish that the installed
model differed from the code pin. EXP-1440 made one separately scoped loopback
`/api/tags` request, emitted only the digest for `qwen2.5-coder:7b`, and
returned bare hex
`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`, matching
the code pin once its unsupported prefix is removed. The cloud-disabled Ollama
server was stopped before inference, snapshot or database creation; its
loopback port is closed and both evidence DB paths remain absent. EXP-1438's
static profile was removed after its spent preflight and cannot be retried.
The focused suite passed (51) and the full offline suite passed (1,868 tests,
25 skipped). Docker Desktop was started locally and remains running. No model
inference, snapshot, verifier, approval, provider or publication action
occurred; EXP-1441 is DRAFT pending a fresh exact one-shot authorization.
R2/MVP remain OPEN.

EXP-1439 classified the installed local Ollama model with one loopback-only
`/api/tags` request whose output was reduced to a fixed marker. The requested
model digest comparison was malformed because Ollama returns bare hex while the
expected value included `sha256:`. EXP-1440 then returned only the exact bare
digest for `qwen2.5-coder:7b`, matching the existing pin after removing that
prefix. EXP-1442 now enforces this exact pin at runtime: after the GitHub
readiness permit but before the snapshot/Worker runtime, the local-Ollama path
checks fixed Ollama version, model name and digest through the bounded local
metadata preflight. Success emits bounded metadata; failure stops with a fixed
marker before runtime. Focused CLI/preflight tests passed (60); full offline
suite passed (1,870 tests, 25 skipped). All new preflight tests used synthetic
loopback responses; no live model, Worker, snapshot or provider action occurred.
The live one-shot Worker remains pending EXP-1441's fresh authorization; R2/MVP
remain OPEN.

EXP-1444 moves the observer-enabled local Ollama metadata-preflight journal gate
into `local_model_observer_gate.py`, outside the verifier runtime source closure.
The shared `observer_runtime.py` is unchanged, so the current verifier code and
host-bundle pins remain valid. The gate writes one deterministic, one-shot
intent/checkpoint before metadata dispatch and a fixed redacted terminal event;
resume/repeat and pre-dispatch journal failure fail closed. Five synthetic gate
tests plus observer/CLI tests passed (107 total), and 12 verifier pin/bundle
regression tests passed. The full offline suite passed (1,875 tests, 25 skipped).
No Docker, network, Worker, model, verifier request or external effect occurred.
This validates local journal wiring only; EXP-1441 still requires fresh exact
authorization, and R2/MVP remain OPEN.

Control Plane update, 2026-10-19: public pinned-source inspection established
why the strict-bool Worker task failed: the target `/save-session` handler
coerces all five numeric fields with `int(data.get(...))` before validation,
which turns JSON `true` into integer `1`. EXP-1447 corrected the future Worker
instruction to remove those conversions, validate raw decoded values with
`type(value) is int` and signed-64 bounds, and complete validation before any
database/cursor operation. Synthetic prompt-contract tests pass. EXP-1441 was
superseded before authorization or runtime; EXP-1448 is the replacement DRAFT
for one local Ollama attempt with a new exact gate. The full offline suite was
rerun on 2026-10-19 and passed: 1,873 tests, 25 skipped. This is regression
evidence only; no Docker, GitHub request, Ollama, Worker/model, verifier,
database creation, approval or publication action occurred in that run. The
EXP-1448 profile was not yet installed at that checkpoint; EXP-1515 later
registered the bounded tuple, while runtime remains unauthorized.

For EXP-1383, the user selected bounded signer-process memory access for the
Keychain-backed Ed25519 item. This accepts transient private-key representation
in the local signer process but is not a hardware-backed/non-exportable-key
claim, nor does it authorize signing or verifier access. On 2026-10-19 the
user pinned the public v2 key-set digest
`sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12`.
The user also accepted EXP-1436 only as fingerprint-separation evidence
(`sha256:607a8dd219cfdc82f27e7a47fef84b63a1439fa14b05b47e068960c4c940b332`),
with date-only observation precision. It does not prove current deployment
identity, verifier runtime or host isolation. Those claims remain unsupported;
do not sign a host-decision or call the verifier as if they were established.
The synthetic Swift signer self-test was rerun on 2026-10-19 and returned
`EXP1383_SYNTHETIC_SIGNER_SELF_TEST_OK`; it generated an ephemeral in-memory key
and signed only synthetic enrollment/host-decision messages. It did not access
Keychain or sign a real trust record.
EXP-1383 remains DRAFT pending suitable current verifier deployment/runtime/
isolation evidence and a separate exact authorization for subsequent signing or
verifier access. Independent verifier trust, digest-bound approval, controlled
PR publication, and R2/MVP remain OPEN.

EXP-1452 adds a TTY-presence gate to normal pinned Worker CLI execution before
trust-artifact loading, Docker, credential access, readiness, model preflight,
database creation or input callback. A piped exact confirmation phrase now
returns a fixed cancellation marker and makes no run attempt. The explicit
noninteractive credential-source check remains unchanged. Synthetic tests
verify the refusal boundary; the integration harness uses a fake TTY only to
model interactive composition. Focused Worker CLI tests passed (52), and the
full offline suite passed (1,877 tests, 25 skipped); `git diff --check` passed.
This proves terminal presence, not operator identity. No real Docker, network,
Worker/model, credential, Keychain, verifier, SSH/testdev, approval or provider
operation occurred. The user's EXP-1383 choice allows transient private-key
representation in signer-process memory. The public key-set digest is now
pinned, and EXP-1436 is accepted only for its limited fingerprint-separation
scope; neither decision proves verifier runtime, deployment identity or
isolation. EXP-1383 remains DRAFT pending evidence for those claims and separate
authorization before any signing/verifier operation. EXP-1448 is still DRAFT;
R2/MVP remain OPEN.

Control Plane reran the required offline suite on the current worktree after
updating the EXP-1383 status and EXP-1453 draft: 1,877 tests passed, 25 skipped
(`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`). This is
regression evidence only; no network, SSH/testdev, Docker, Worker/model,
Keychain, verifier, approval or provider operation occurred.

EXP-1454 (2026-10-19) performed one anonymous public read-only
`git ls-remote ... HEAD` against `SoldatovAlexander/brainbooster_full_v11`.
It returned `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, matching the currently
pinned snapshot commit. This is a point-in-time advertised-HEAD comparison only;
it does not prove authorship/signature, content availability, or source trust.
No credentials or local checkout were used, and no runtime or external write was
performed. Full offline suite is run once at batch end under the current Control
Plane cadence decision; this source-head observation itself has no test result.
Batch-end full offline suite passed on the current worktree: 1,877 tests,
25 skipped in 81.595 seconds (`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
discover -s tests -q`); scoped `git diff --check` passed. This remains regression
evidence only and does not change any R2/MVP acceptance status.

Observer lifecycle audit (2026-10-19): the event schema and report understand
`agent_finished`, but the runtime has no writer for that event. The current
`JournaledProposalWorker` emits one `agent_started`; `resume_existing` requires
exactly one such event and rejects any `agent_finished`. This leaves the
normative “separate terminal event” rule without a compatible lifecycle
contract for a staged run that pauses and later resumes through approval or
publication. Criterion 13/14 remain partial. Control Plane decision EXP-1455
selects per-agent invocation pairing plus a distinct run-terminal event; a
paused workflow can resume with a new invocation, while legacy unclosed
lifecycle facts remain visible as gaps. The implementation and verifier-pin
refresh are not yet done; criterion 13/14 stay PARTIAL.
After recording EXP-1455's target contract, the batch-end full offline suite
passed on the current worktree: 1,877 tests, 25 skipped in 79.010 seconds
(`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`). The
decision changes documentation only; it is not implementation evidence.

EXP-1458 identifies a report-side false-closure: the current projection groups
`agent_started`/`agent_finished` by agent identity rather than invocation ID, so
one finish can hide another invocation's missing terminal event. The report
module is outside `VERIFIER_CONTEXT_MODULES`; a narrowly scoped report fix does
not change verifier runtime/image pins. Runtime still does not write
`agent_finished`, so this report correction cannot by itself close observer
criteria 13/14.

EXP-1459 queried the public GitHub commit-verification API once, anonymously,
for pinned commit `2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`. The bounded result
was `verified=True`, `reason=valid`, signature present, and the returned SHA
matched the pin. This is GitHub's cryptographic verification status for that
commit; it does not prove that the signing key belongs to the intended repository
owner or independently establish source trust. No credentials or raw response
were retained. R2/MVP remain OPEN.

EXP-1461 made a second, bounded public read of the same commit's GitHub actor
association: `author.login=SoldatovAlexander`, `committer.login=web-flow`,
`verified=True`, `reason=valid`, and the exact SHA matched. This associates the
commit with a GitHub account but does not prove the account holder personally
controlled the signing key or that the source is independently trusted.

EXP-1465 consumed one exact user-authorized replay attempt. Local digest, output
path, and forwarding-port preflights passed; one strict-host-key SSH session
started the pinned one-shot testdev verifier and returned a public `ready`
bootstrap. The command-output channel truncated that single-line JSON before
the complete bootstrap/CA could be captured and locally validated. The task's
stop rule was followed: no Keychain signer invocation, trust signatures,
verifier HTTPS request, Docker invocation, or replay DB/artifacts were produced;
there was no retry or manual cleanup. The queue card is BLOCKED. This result is
not verifier-readiness, trust, or replay evidence; the next attempt needs a new
exact card and fresh authorization, with bounded local capture that does not
expose the bootstrap to a truncating output channel. A subsequent read-only
source validation found both `EXP-1269-stage.sqlite3-wal` and `-shm`; the
project's `SQLiteStagedArtifactStore(read_only=True)` refuses this state before
opening SQLite. The attempted validation therefore read no stage data and made
no source changes. EXP-1467 was superseded before execution. EXP-1468 now
requires the existing WAL-aware snapshot helper to create a separate mode-0600
standalone source copy and validate the exact staged digest before any SSH.
Its destination is outside Git; the original main DB and sidecars must remain
unchanged. The helper's six synthetic tests pass, but no snapshot of EXP-1269
has yet been created. R2/MVP remain OPEN.

EXP-1470 implements the local Observer lifecycle core from EXP-1455: new runs
write a unique `invocation_id` on `agent_started`; explicit one-shot invocation
and run finish APIs append causally linked terminal events and fail closed on
pending/unknown work; resume validates sequence, intent/terminal and
checkpoint/causal relationships, lifecycle pairing, publication restrictions,
and reconstructed one-shot claims before appending a new invocation in the same
run. A legacy start without lifecycle fields remains unchanged and visible as
report gaps. Focused Observer runtime/report tests pass (70 tests). This core is
not yet integrated into the seven production entry points and is not evidence
of complete instrumentation, durable/attested journaling, approval, or
publication; criteria 13/14 remain PARTIAL, R2/MVP OPEN. EXP-1471 built local
verifier image `sha256:8e5d565a9ebc1479c6d11bcde1337f1333fdde7e4e4574343ff64a5fff365842`
with code digest
`sha256:ebb67e739fa1ab09d191fbf6fcb65370d0c5407cbe360ab758d3f2e45027c08e`;
one exact inspect confirmed `linux/amd64`, both synthetic container tests and
the pin-boundary test passed. Its one batch-end full suite reported 1,885 tests,
25 skipped, and 10 failures (7 lifecycle-resume integration and 3 verifier-host
bundle pin/stream checks). Batch AID is not accepted until these are corrected
and the corrective batch-end suite passes. No external operation occurred.

EXP-1472 is accepted. Bounded lifecycle finish is owned
by each operation boundary: replay finishes after its full read/verify/persist
path, R5 after `run_r5_attempt` has a classified result, and the local executor
only finishes its local-snapshot path after sandbox closure. This avoids
prematurely closing a remote-snapshot invocation before outer replay or R5
processing has completed. Worker CLI, DeepSeek Worker, stage approval, and
signed mock-publication entry paths also record only explicit known outcomes;
pending or unknown work stays open. Focused EXP-1472 tests pass (176 tests, 8
skipped), as does `git diff --check`. The one agreed batch-end full suite then
reported 1,886 tests, 25 skipped, and 8 failures in 82.123 seconds; five were
stale lifecycle-event expectations and three were bundle-pin mismatches after
the final verifier pin update. Batch AIE is not accepted, criteria 13/14 remain PARTIAL, and
R2/MVP remain OPEN. No live Worker/model, network, verifier, Docker, SSH,
publication, or provider action occurred.

EXP-1473 restored the deterministic verifier-host transfer pin after EXP-1472
changed source files inside the bundle. The in-memory rebuild matched
`sha256:9b46222a890fa875a8d857b4bc2e15b2115583cb05c977a61ad1566795948bce`,
33 members, 564,936 source bytes, and 604,160 archive bytes. The two focused
bundle/stream test modules passed (26 tests); no archive was written and no SSH
or remote transfer occurred. The final verifier pin in EXP-1474 subsequently
changed a bundled module, so the stream pin again needs synchronization in
Batch AIF. R2/MVP remain OPEN.

EXP-1474 rebuilt the verifier image after lifecycle integration using only the
pinned target dependency image, `linux/amd64`, `--pull=false`, and
`--network=none`. The helper returned Docker `/usr/local/bin/docker`, image
`sha256:bf77a9dba452d6a538cc688f41de1654b11ee1f7dc4d2075dfaf24c2f0aa754a`, and
code digest
`sha256:fdec77ec2ed3d1e0ec7d94272b6fa42869c62b1ff97d581d64c18a04fbb2521c`.
One exact-ID inspect confirmed `linux/amd64`, and two synthetic verifier
container tests plus two verifier pin-boundary tests passed. The local image is
not a deployment or independent-trust proof. Batch AIE's one full offline suite
failed as recorded above; EXP-1476/1477 address those results before another
batch-end suite. Criteria 13/14 remain PARTIAL and R2/MVP remain OPEN.

Batch AIF completed the corrective work. EXP-1479 made the successful local
executor's `stage_sink is None` path emit terminal status `ok`; the updated
focused lifecycle set passed 201 tests (10 skipped). EXP-1480 rebuilt and
inspected the current local verifier image
`sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`
for `linux/amd64`, bound to code digest
`sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`; both
synthetic container tests passed. EXP-1481 synchronized the current source
bundle to `sha256:3d7c9c30b2afc53c53b9a1427e95e113d684111209979ee5e7fbce2fe437dad4`
(33 members, 564,982 source bytes, 604,160 archive bytes); both focused bundle
modules passed (26 tests). The single Batch AIF full offline suite passed:
1,886 tests, 25 skipped in 86.038 seconds; `git diff --check` passed. These are
local regression and synthetic-verifier results only: they do not establish
host independence, trusted deployment, authenticated approval, or real PR
publication. Criteria 13/14 remain PARTIAL and R2/MVP remain OPEN.

Batch AIG (EXP-1482/1483) handled only the source snapshot needed for any future
independent-verifier replay. EXP-1482's relative-path call stopped before
snapshotting; EXP-1483 then created the exact WAL-aware standalone snapshot at
`/Volumes/DATA/Agent00X-local-evidence/exp1468-source-stage.sqlite3`, mode 0600,
16,384 bytes, file SHA-256
`10c5bc54684ac07712889992aeaff1a08ead50aba07d475ff4affadb46fa7c43`. Its
staged-artifact digest matched EXP-1269, SQLite `integrity_check=ok`, no
destination WAL/SHM were present, and source main/WAL/SHM hashes were unchanged.
The single Batch AIG full offline suite passed: 1,886 tests, 25 skipped in
80.493 seconds; `git diff --check` passed. These results validate a stable local
input only. EXP-1468 still names the superseded pre-AIF verifier image, code and
bundle pins, so its `RUN EXP-1468 ONCE` response was not used. No SSH, Keychain
signature, verifier request, replay, Docker invocation, approval, provider write
or publication occurred. Criteria 13/14 remain PARTIAL and R2/MVP OPEN.

Batch AIH synchronized the local transfer helpers after EXP-1468 was found to
name the pre-AIF verifier pins. The image streamer now pins
`sha256:59468457bb9a2ec5e6857e3a413df1e480481d832280027ecfd1f227517bdaa2`
(code `sha256:a1ca1bf92f8dff1197814be3b6702c4a028763a6e9735165e304b0d59d0fad9e`,
linux/amd64, 48,856,809 bytes, stream 48,870,912 bytes) and exact ordered
DiffIDs; the bundle streamer pins
`sha256:3d7c9c30b2afc53c53b9a1427e95e113d684111209979ee5e7fbce2fe437dad4`
(33 members, 564,982 source bytes, 604,160 archive bytes) and a new immutable
`exp-1484` target. Exact local inspect/stream size matched. Focused transfer
tests passed (23); the pin update exposed a retired hard-coded size in the
EXP-1349 negative fixture, which was made relative to the current pin and then
passed its focused tests (3). The final Batch AIH full offline suite passed:
1,886 tests, 25 skipped in 78.622 seconds; `git diff --check` passed. No image
or bundle was transferred, and no SSH, signature, verifier request or replay
occurred. Scope deviation: the one local `docker image save` used to count the
stream size was outside EXP-1484's stated scope; its bytes were piped only to
`wc -c`, with no archive file retained. These are local preparation pins, not
remote deployment identity.
Criteria 13/14 remain PARTIAL and R2/MVP OPEN.

Batch AII added `scripts/capture_pinned_verifier_bootstrap.py`, an import-inert
local supervisor for a future separately authorized verifier call. It invokes
only a strict-host-key, public-key-only SSH forward to the pinned current
`exp-1491` launcher, reads one newline-terminated bootstrap under the parser's
byte bound, validates exact bytes/profile/port, persists only that public line
to an exclusive mode-0600 caller-selected file, emits only digest/port with
`trust=unestablished`, and returns a held session handle with bounded wait and
stop/reap. Seven fake-pipe tests passed, including invalid/multiple/oversized
output and path safety. The batch-end full suite passed: 1,893 tests, 25 skipped
in 76.735 seconds. No SSH or live verifier call ran. The helper makes
orchestration reliable but does not establish host identity, deployment,
isolation or trust; R2/MVP remain OPEN.

Batch AIII synchronized the transfer runners' internal one-shot prompts with
their current DRAFT cards: bundle transfer requires `RUN EXP-1488 ONCE`, image
import requires `RUN EXP-1489 ONCE`. Both focused suites passed (23 tests), and
the batch-end full suite passed (1,893 tests, 25 skipped in 81.041 seconds).
This only aligned fail-closed gate text; no transfer or image import occurred.
EXP-1490 then found the classic-store config pin stale, so EXP-1488/1489 were
superseded before any remote operation. R2/MVP remain OPEN.

Batch AVI corrected the OCI manifest/config split before any transfer. EXP-1490
audited the current image archive in memory and found the authenticated
config-blob digest
`sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`,
while the old classic-store pin was stale; pinned layer DiffIDs still matched.
EXP-1491 updated the fixed classic-store and portable-chain pins, changed the
remote import verifier to inspect the config ID separately from the manifest
ID, and stopped treating remote storage `.Size` as content identity. The host
bundle now rebuilds deterministically at
`sha256:d0d51e4a37ba0dc86cd649acf79e7bab3c790dc680bd0ea81df5291782b0f35f`
(33 members, 564,982 source bytes, 604,160 archive bytes), targeting new
directory `exp-1491`. The profile digest remains
`sha256:afffe37328631803e9c1afa2631085b5f2bd7ab02feffdbe344f9df35deb7556`.
Focused tests passed (42); the one Batch AVI suite passed (1,895 tests, 25
skipped in 78.796 seconds). No SSH, remote transfer, verifier request or
deployment occurred. The old EXP-1488/1489 transfer drafts were superseded;
new exact transfer cards and fresh user gates are required. R2/MVP remain OPEN.

EXP-1526's one locally authorized save/parser process terminated, but its
sanitized result marker was not retained in the tool record. The attempt is
therefore inconclusive; no archive was retained and no retry or further Docker
operation was performed. EXP-1527 hardened the offline audit runner to consume
stdout incrementally under a 128 MiB cap and 60-second deadline, discard
stderr, and kill/reap the child on timeout or overflow. Thirteen focused tests
passed; Batch AKC's single full offline suite passed (1,910 tests, 26 skipped,
78.456 seconds). No Docker/live save ran in EXP-1527. Portable identity,
independent-host trust and isolation remain unverified; R2/MVP remain OPEN.
 Повторная проверка опирается на Ollama v0.40.3 [model resolver](https://github.com/ollama/ollama/blob/v0.40.3/server/model_resolver.go), [manifest digest resolution](https://github.com/ollama/ollama/blob/v0.40.3/manifest/paths.go) и [route registration/common chat handler](https://github.com/ollama/ollama/blob/v0.40.3/server/routes.go).

Batch AKAD (2026-10-19) завершил EXP-1553: разрешённая filesystem-only проверка
показала, что `/var/run/docker.sock` существует как Unix socket и доступен
текущему процессу на чтение/запись по `os.access`. К сокету не подключались,
Docker не вызывался. Это исключает только отсутствие/недоступность этого
локального socket path как очевидное объяснение сбоя EXP-1552; причину
`SYNTHETIC_VERIFIER_FAILED` это не устанавливает и не устраняет. EXP-1554
добавила к синтетическому runner фиксированные маркеры для
`VerifierProcessError`, прочего исключения и отклонённого результата без
вывода exception/response details. EXP-1555 добавила реальный обязательный
opt-in `RUN_DOCKER_SANDBOX_TESTS=1`, проверяемый до создания verifier.
EXP-1556 была superseded до исполнения: preflight нашёл, что runner выбирал
OCI config digest `sha256:8fd288eaae140b2ba5acbf70aa3e18db0d54c724c0a20e5a65080d214966eaeb`,
тогда как EXP-1551 установила загруженный Docker config ID
`sha256:f9352ed122050abfa42526544c101a713f4724271e0aa044fb92e56972a0ae38`;
EXP-1547 ранее подтвердила отсутствие OCI ID в Docker image store. EXP-1557
исправила runner pin на exact Docker ID и закрепила его synthetic assertion.
Batch AKAE (48 tests, 1,945/26 skipped), AKAF (49 tests, 1,946/26 skipped) и
AKAH (49 tests, 1,946/26 skipped) прошли focused и batch-end offline suites;
последний suite занял 76.747 секунды. `git diff --check` прошёл. После
исправления pin runtime invocation ещё не было; для него подготовлена DRAFT
EXP-1558 с точным fresh gate `RUN EXP-1558 ONCE`. Credentials и внешние
операции не использовались. Критерии 13/14 остаются PARTIAL, R2/MVP — OPEN.

EXP-1559 (2026-10-19 17:36 UTC) made one anonymous, credential-helper-disabled
`git ls-remote` request for public `HEAD` of
`SoldatovAlexander/brainbooster_full_v11`. It returned
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`, matching the pinned snapshot.
No clone, fetch, source blobs or refs were accessed/changed. This confirms only
HEAD equality at that observation time; it does not prove authorship/signature,
independently trusted source identity or that every pinned object remains
available. The earlier bounded content snapshot remains separate evidence.
R2/MVP remain OPEN.

Observer matrix correction: EXP-1310 remains a historical run that stopped at
readiness before Observer startup, but later EXP-989 instruments the optional
pinned Worker CLI's `GitHubReadiness.fetch` and `RemoteExecutionPermit.issue`
as pre-dispatch checkpoint/intent plus bounded terminal events on one run.
Its synthetic tests cover dispatch, refusal and unknown-without-retry. EXP-1444
separately instruments local Ollama metadata preflight. These hooks do not
record readiness values or model identity, and do not establish a complete,
mandatory, trusted or durable collector. Criteria 13/14 remain PARTIAL.

EXP-1561 added fixed, allow-listed failure-stage markers to the local synthetic
verifier runner for child launch, timeout, output limit, exit/rejection,
response parsing and nonce mismatch. Unknown process errors stay generic; no
exception text, exit status, streams or payload are printed. Fifty focused
tests and the Batch AKAL full offline suite (1,947 tests, 26 skipped in 79.802
seconds) passed; `git diff --check` passed. This only improves diagnostics for
a future single local verifier attempt; runtime status is now recorded under
EXP-1562 below. Criteria 13/14 plus R2/MVP remain PARTIAL/OPEN.

EXP-1562 ran the corrected EXP-1552 runner once against a locally converted
Docker candidate config image ID
`sha256:f9352ed122050abfa42526544c101a713f4724271e0aa044fb92e56972a0ae38`
and verifier code digest
`sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e`.
This candidate is distinct from the currently configured classic-store pin
`sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`;
EXP-1562 did not test that configured image. The fixed marker was
`SYNTHETIC_VERIFIER_CONFIRMED`, verdict `pass`, blockers 0, network `none`;
exit code 0. The request used only the synthetic calculator fixture. This
establishes a successful local same-host isolated verifier invocation for a
converted candidate, not execution of the configured pin, independent verifier
trust, current remote deployment, portable image provenance, or the full pinned snapshot → Worker → verifier →
digest-bound approval → controlled PR chain. No credentials or external writes
were used; there was no retry or additional Docker command. Criteria 13/14
remain PARTIAL, R2/MVP remain OPEN.

EXP-1563 issued one read-only Docker image inspect for the configured
classic-store ID `sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`,
requesting only ID/OS/architecture. It returned exit code 1 with no stdout and
suppressed stderr. This result is inconclusive: it cannot distinguish an absent
image from a daemon/transport failure. No second Docker command, retry, import,
or diagnostic was run. The configured pin's local availability therefore
remains unknown. No credentials or external writes were used; criteria 13/14
remain PARTIAL and R2/MVP remain OPEN.

EXP-1564 made one read-only `docker version` request through
`unix:///var/run/docker.sock`. It returned the fixed marker
`DOCKER_DAEMON_READY` with exit code 0; version text and stderr were not
retained. This confirms a responding local Docker daemon, but does not confirm
the configured classic-store image ID is present. No image or container was
inspected or changed; no credentials or external state were used. The
configured image ID remains unverified locally; criteria 13/14 remain PARTIAL
and R2/MVP remain OPEN.

EXP-1565 issued one read-only Docker inspect for configured classic-store image
ID `sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c`
after the local daemon responded. The exact tuple check did not match; the
fixed marker was `CONFIGURED_IMAGE_UNAVAILABLE_OR_MISMATCH` (wrapper exit code
0), with raw output and stderr suppressed. This does not confirm that the
configured image ID is present. No retry, diagnostic, import, build, tag or
other image/container operation occurred. The local daemon is available, but
the configured pin remains unavailable or mismatched in this Docker store.
No credentials or external state were used; criteria 13/14 remain PARTIAL and
R2/MVP remain OPEN.

EXP-1566 confirmed that previously offline-built candidate config image
`sha256:b2bf83dac718dea7afc71436a2554927e016b0137893013aa96cbb098fc7456b` is
present locally with platform `linux/amd64`. This candidate uses code digest
`sha256:e6fb28b9296648bc866560b81c87a0934b8f10cb36867a8c0191849761c29f1e`,
matching the current source-closure assertion, but it is not the configured
classic-store pin `4bc58e…` and does not establish independent verifier trust.
The next bounded action is two network-disabled synthetic container tests;
no Worker/model, credential, external request or publication operation is
authorized or implied. R2/MVP remain OPEN.

EXP-1567 attempted a local synthetic runtime check on that candidate, but the
unittest `-k` substring filter selected three tests rather than the intended
two. One startup-before-validation case failed because Docker emitted a
platform warning on stderr instead of the expected fixed request-rejection
marker. The invocation is not accepted as verifier runtime evidence; no retry
was made. The candidate image/code pair is still only a local artifact, not an
independently trusted verifier. The configured image pin, cross-host trust,
authenticated approval, and controlled PR remain unverified; R2/MVP remain
OPEN.

EXP-1568 added fixed `--platform=linux/amd64` to the verifier Docker argv before
the immutable image ID, preserving pull-never, no-network, read-only root,
UID 65532, dropped capabilities and resource limits. The focused verifier
container suite passed (26 tests, 3 opt-in skipped). Three explicitly named
opt-in synthetic container tests against the locally present EXP-1521 candidate
and matching source-closure digest passed, including the startup rejection
marker case that previously encountered Docker platform-warning stderr. This
improves deterministic local platform selection; it does not establish a
configured production pin, independent host, trust, or live Worker→approval→PR
chain. The batch-end full offline suite ran 1,947 tests and failed 3
verifier-host bundle tests: two stream tests stopped at stale-pin preflight
(exit 10), and the extracted-launcher test calculated bundle digest
`6e2e8d06bdef7117fd4e61a9cd1969287c5eeee5bb98371965276d484f6b9fbb` while the
transfer helper still pins
`da8e4b2925b9cf32582dc81ed3347d6c43e87dcc59f2a2f88e11630cca50d13b`. The
builder's expanded transitive launcher closure includes the updated verifier
adapter, explaining the changed source-bundle digest. Reconcile this pin before
accepting the batch. No external action occurred; R2/MVP remain OPEN.

EXP-1569 reconciled that stale bundle pin. Two in-memory builds produced
identical bytes and tuple: SHA-256
`6e2e8d06bdef7117fd4e61a9cd1969287c5eeee5bb98371965276d484f6b9fbb`, 33
members, 566543 source bytes, 604160 archive bytes. Updated only the derived
metadata in `stream_pinned_verifier_host_bundle.py`; transfer behavior and
remote target remain unchanged. Both focused bundle modules passed (26 tests),
and the batch-end suite passed (1,947 tests, 26 skipped, 84.641 seconds).
`git diff --check` passed. No SSH/transfer, Docker, credentials, or external
operation occurred. This restores local consistency only; independent host
trust, authenticated approval and controlled PR remain open. R2/MVP remain
OPEN.

EXP-1574 closes one narrow Observer lifecycle gap in the local signed-mock
approval and stage-approval CLIs: after a known refusal/failure has been
recorded as `agent_finished(failed)`, the wrapper now attempts
`run_finished(failed)`. If invocation finalization cannot be recorded because
work is still pending/unknown, the run is intentionally left open. Focused
tests passed (27 total); the batch-end full offline suite passed (1,956 tests,
26 skipped). The real GitHub publication path is unchanged, and this does
not establish complete or trusted Observer storage. Criteria 13/14 remain
PARTIAL; R2/MVP remain OPEN.

**R2 checkpoint through EXP-1583 (2026-10-19):** EXP-1580's single
Buildx `--load` → bounded `docker image save` attempt returned
`CLEANUP_FAILED`; no archive was accepted, verifier was not invoked, and the
production pin did not change. EXP-1581's exact filtered query established
only that `agent00x-verifier:exp-1580` is absent. Whether the temporary
dependency-copy container was removed remains unknown; no container query or
cleanup retry was made. EXP-1583 improves future fixed cleanup markers to name
only the owned resource class and, for a copy container, its generated exact
64-hex ID. It makes no Docker call and cannot recover EXP-1580's unrecorded ID.
The last successful Worker→target→same-host verifier→stage remains EXP-1269.
Independent verifier trust, authenticated approval, provider receipt and
controlled real PR evidence are still absent. Criteria remain OPEN/PARTIAL;
R2/MVP remain OPEN.

**Worker preparation delta (EXP-1584/1585, 2026-10-19):** after several local
Worker attempts stopped at the boolean `level=true` case, EXP-1584 strengthened
the fixed task instruction with a literal strict-integer helper skeleton and
registered a fresh credential-free profile. The unconsumed EXP-1448 gate was
retired before runtime. EXP-1585 is a DRAFT for one local Ollama attempt against
the pinned public snapshot; it requires a fresh exact gate and has not run. This
is prompt-contract preparation, not evidence that a Worker patch passes.
EXP-1269 remains the latest successful Worker→target→same-host verifier→stage
run. No criteria advance; R2/MVP remain OPEN.

**Local verifier-export delta (EXP-1586—1588, 2026-10-19):** EXP-1586 failed
at wrapper import before any Docker command. EXP-1587 corrected the import and
made one offline attempt under a new tag; its fixed result was
`CLEANUP_FAILED|resources=verifier_tag`. One exact read-only follow-up returned
`EXP1587_TAG_ABSENT`; the tag is absent, but an untagged image and whether the
archive passed validation remain unknown. No retry, image metadata inspect,
cleanup, or query of the unresolved EXP-1580 container occurred. No portable
candidate is accepted and no verifier was invoked. The current configured pins
did not change; R2/MVP remain OPEN.

**EXP-1589 / Batch AKBJ (2026-10-19):** corrected the local archive helper's
tag-cleanup classification. After its preflight confirms the task-unique tag is
absent and Buildx is entered, finalization now makes at most one exact filtered
presence query. An absent tag preserves the primary build/archive result; an
exact match permits one removal of that tag; an unclassified query fails
closed without a removal attempt. Synthetic tests cover absent/present tags
after build failure, ambiguous presence output and the successful archive path.
This is code/test evidence only: no Docker operation, candidate archive,
verifier invocation, or production pin change occurred. Batch-end offline suite
passed (1,990 tests, 26 skipped, 79.039 seconds); `git diff --check` passed.
R2/MVP remain OPEN.

**Local verifier-export delta (EXP-1590/1591, 2026-10-19):** registered a
fresh fixed entrypoint/tag and tested the no-opt-in guard. One bounded offline
export attempt passed local preflight and dependency copy/removal, then returned
only `BUILD_FAILED` (exit 14). The task tag was absent at the exact cleanup
check; no tag-removal attempt or retry occurred. No archive was accepted,
production pin changed, or verifier invoked. The Docker build failure is not
classified further; raw diagnostics remain undisclosed. The batch-end offline
suite passed (1,992 tests, 26 skipped, 78.939 seconds), and `git diff --check`
passed. R2/MVP remain OPEN.

**EXP-1592/1593:** added fixed allowlisted Buildx failure categories with bounded
exit/byte-count evidence and no raw stderr disclosure. One fresh offline attempt
returned `BUILD_FAILED|reason=unknown|exit=125|stderr_bytes=109`; no raw
diagnostic, retry, archive acceptance, verifier invocation or pin change
followed. Batch-end full offline suite passed (1,995 tests, 26 skipped,
79.958 seconds); `git diff --check` passed. R2/MVP remain OPEN.

**EXP-1585/1594/1595:** the user authorized one EXP-1585 run. Focused Worker
CLI/profile tests passed (53); evidence DB paths were absent/non-symlinks and
Ollama port 11434 was closed. Exact target/verifier ID-platform preflight
returned only `PINNED_IMAGES_FAILED`; the card stopped before GitHub quota,
Ollama startup, snapshot, DB creation or inference. No retry. EXP-1594 then
added a synthetic-tested exact-image inspector with sanitized per-image states
and an opt-in guard. Following a separate exact gate, EXP-1595 ran that helper
once and returned only `EXP1594_IMAGES|TARGET_MATCH|VERIFIER_MATCH`: both exact
local image IDs and linux/amd64 platforms match. This does not retry EXP-1585
and does not establish GitHub quota, Ollama readiness/inference, a new snapshot,
verifier runtime or stage. EXP-1585 remains BLOCKED; no Worker/model evidence or
R2 criterion advances. Batch-end full offline suite passed (2,000 tests, 26
skipped, 79.665 seconds); the five synthetic EXP-1594 tests passed and
`git diff --check` passed. R2/MVP remain OPEN.

**Batch AKBM preparation (EXP-1596/1597):** EXP-1595 confirmed both exact image
IDs/platforms only against `/var/run/docker.sock`, while the Worker CLI's
preflight uses `shutil.which("docker")` and the ambient Docker context without
an explicit host/config override. This difference is a plausible, unconfirmed
explanation for EXP-1585's `PINNED_IMAGES_FAILED`. EXP-1596 adds a helper that
mirrors the Worker invocation shape; six synthetic tests passed and no Docker
command ran. EXP-1597 remains DRAFT for one fresh-gated pair of read-only exact
image-ID checks through that same CLI context. The one authorized EXP-1597
attempt failed while importing the helper (`ModuleNotFoundError: No module
named 'scripts'`) before Docker path resolution; zero inspect commands ran and
the pin visibility result is unknown. EXP-1598 fixed direct-script import
resolution and added a no-opt-in subprocess guard; seven focused tests passed.
Batch AKBM's full suite passed (2,006 tests, 26 skipped, 77.819 seconds), and
`git diff --check` passed. EXP-1599 was superseded before runtime. EXP-1600 now
shares a single explicit local endpoint (`unix:///var/run/docker.sock`) across
Worker preflight, restricted Worker commands, target sandbox and verifier
commands. Five focused modules passed (114 run, 5 skipped), with no Docker
operation. EXP-1601 is DRAFT for a fresh-gated credential-free Worker-to-stage
attempt using the explicit endpoint. This change is not live runtime evidence;
R2/MVP remain OPEN.

**Batch AKBO end-check (2026-10-19):** the once-only offline suite ran 2,007
tests with 26 skipped and failed 6 tests plus 1 error. Failures identify an
unlisted `docker_endpoint.py` in the verifier source closure, a stale
`VERIFIER_RUNTIME_CODE_DIGEST`, a packaged verifier import failure, two stale
verifier-host bundle expectations, and one synthetic Docker argv fixture that
still expects the subcommand at argv index 1 after global endpoint pinning.
`git diff --check` passes. No Docker, Worker/model, GitHub, Ollama, credential,
SSH, or external operation occurred. The user returned `RUN EXP-1601 ONCE`, but
the gate was not consumed: `run_pinned_deepseek_worker.py` has no `EXP-1601`
authorization profile, so argparse rejects the exact invocation before any
preflight or side effect. Do not retry it under that gate. Batch AKBO is not
accepted; EXP-1602/1603 were split into code-only reconciliation and a separately
gated image build. R2/MVP remain OPEN.

**EXP-1602 code-only repair (2026-10-19):** the Worker verifier preflight now
uses the classic-store config ID for Docker `.Id` comparison while the portable
manifest identity remains separate. Added `docker_endpoint.py` to the exact
verifier source closure and Dockerfile, corrected the synthetic argv fixture,
and refreshed deterministic source/bundle digests. The recomputed code digest is
`sha256:705c3803ca36374ee0ab0bef80fb4d77b3211dd60e8168a7729a3fed46c7a2c7`; the
host bundle is `sha256:519090b97923be43f6e1a9f868fe1711069cd14b2ac4fc05f52de6fe2dc432d5`
(34 members, 566959 source bytes, 604160 archive bytes). The five focused test
modules passed (126 tests, 10 skipped); `git diff --check` passed. This is
source/package consistency only: no verifier image was rebuilt or inspected,
and the loaded image has not been shown to match the new code digest. The old
EXP-1601 card is superseded and its gate was not consumed or reused. EXP-1603
was subsequently completed as code-only helper preparation. EXP-1604 later
received its own gate and one offline build attempt, which failed before a
validated archive; its gate is consumed and the card is BLOCKED. The full suite
then exposed one stale profile-digest assertion, corrected test-only by EXP-1605;
see the current checkpoint above. No verifier image pins were updated.
Independent verifier trust, approval, controlled PR, R2 and MVP remain OPEN.

**EXP-1603 helper preparation (2026-10-19):** added a fixed opt-in
`agent00x-verifier:exp-1603` entrypoint around the bounded candidate exporter.
Synthetic checks bind `--pull=false`, `--network=none`, the fixed local Docker
socket, dynamic observed DiffIDs, a required portable OCI manifest, exact
config/source closure, and retention of the unique task tag. Legacy Docker
archives without a portable manifest fail closed. The focused exporter suite
passed (25 tests). This was code/tests only: no Docker command, image build,
pin update, Worker/model, network, credentials or provider operation occurred.
EXP-1604 was attempted once under a fresh exact gate and returned a bounded
build-failure marker; see the current checkpoint and outcome below. No retry
occurred and no image pins changed. R2/MVP remain OPEN.

**EXP-1604 / Batch AKBQ final outcome (2026-10-19):** the exact one-shot local
Buildx helper returned `BUILD_FAILED|reason=unknown|exit=125|stderr_bytes=109`.
Raw diagnostics were not retained. The candidate archive was not accepted and
the manifest/config/code pins were not updated. The helper's retained task tag
may or may not exist after this failed build; no inspect or cleanup was
authorized or performed. The batch-end offline suite ran once (2,011 tests,
26 skipped) and found one failure: the expected profile digest
`sha256:95187a75559f945fdaf40b194f5d8815da21baa6c8f165efc16cded68b57c`
did not match the current deterministically computed digest
`sha256:1ee01a5df3f1310de885ffbbb8cc17c825974fb0cc001ba2a3fda9c4e6f9ff78`.
EXP-1604 is BLOCKED; the gate is consumed and must not be reused.

**EXP-1605 / Batch AKBR (2026-10-19):** changed only the stale expected digest
in `tests/test_verifier_classic_store.py`; the verifier profile, runtime pins,
enrollment, trust records, signer allowlists and bootstrap were untouched. The
focused module passed (6 tests), and the batch-end full offline suite passed
(2,011 tests, 26 skipped); `git diff --check` passed. The computed digest is
local profile identity only, not enrollment or host-trust evidence. R2/MVP
remain OPEN.

**EXP-1606 / Batch AKBS (2026-10-19):** one filtered read-only query for the
exact `agent00x-verifier:exp-1603` tag returned exit code 0 and empty stdout;
the tag was absent at query time. The query did not inspect metadata, list
other images/containers, or test for untagged images. No image mutation or
follow-up Docker action occurred. `git diff --check` passed. EXP-1606 is DONE;
its gate is consumed. R2/MVP remain OPEN.

**EXP-1607–1608 / Batch AKBT (2026-10-19):** EXP-1607 added a new fixed
entrypoint/tag `agent00x-verifier:exp-1607`; 28 focused synthetic tests passed,
and `git diff --check` passed. EXP-1608 ran once under the exact self-approved
card and returned `BUILD_FAILED|reason=unknown|exit=125|stderr_bytes=109`.
Raw stderr was neither retained nor shown. No portable archive was accepted
and no production image/config/code pin changed. The helper may have left a
tagged or untagged image; no follow-up image query, metadata inspection, cleanup,
retry, or diagnostics were performed. The batch-end full offline suite passed
(2,014 tests, 26 skipped). This is local regression evidence only; R2/MVP
remain OPEN.

**EXP-1609 / Batch AKBU (2026-10-19):** one bounded read-only `docker buildx
inspect default` against the local socket and a fresh isolated Docker config
returned only `BUILDX_INSPECT_FAILED|exit=1`. Raw stderr was suppressed; no
retry or diagnostic followed. This cannot establish whether any ambient
named/default builder exists. `git diff --check` passed. R2/MVP remain OPEN.

**EXP-1610–1611 / Batches AKBV–AKBW (2026-10-19):** the unnamed local
`docker buildx inspect` returned only `BUILDX_INSPECT_FAILED|exit=1`; the
formatted local `docker buildx ls` returned only `BUILDX_LS_FAILED`. Both used
a fresh isolated Docker config, suppressed raw diagnostics, and ran once.
Synthetic suites passed (6 and 5 tests, respectively), with diff-checks. These
failures do not establish ambient builder state or explain EXP-1608. No retry,
mutation, network or credentials were involved. R2/MVP remain OPEN.

**EXP-1612 / Batch AKBX (2026-10-19):** one local `docker buildx version`
command with isolated Docker config and minimal environment returned only
`BUILDX_VERSION_FAILED`. No stderr was retained; no daemon query, build,
network, credential or mutation occurred. Five focused synthetic tests passed
and `git diff --check` passed. This result cannot distinguish an undiscovered
plugin binary from another CLI failure. R2/MVP remain OPEN.

**EXP-1613–1614 / Batches AKBY–AKBZ (2026-10-19):** EXP-1613 checked only
metadata for five fixed plugin paths and found one executable; its direct
version command returned zero but did not match the conservative parser, so
raw output was not retained. EXP-1614 added a fail-closed, synthetic-tested
link of a unique user-local plugin into the temporary Docker config, without
reading/copying credential config. The exporter focused suite passed (32
tests); no Docker operation occurred. EXP-1615 subsequently confirmed the
isolated Docker CLI can discover Buildx with the unique user-local plugin link.
R2/MVP remain OPEN.

**EXP-1613 / Batch AKBY (2026-10-19):** only executable-file metadata for five
fixed standard Buildx paths was checked. Exactly one candidate was executable;
the direct `version` process returned zero, but stdout did not match the
conservative parser and was not retained. Only
`BUILDX_PLUGIN_VERSION_UNCLASSIFIED` was emitted. No config/auth file, daemon,
network, or build action was accessed. Five synthetic tests and diff-check
passed. The binary exists in one fixed candidate location, but its version
was not established. R2/MVP remain OPEN.

**EXP-1615 / Batch AKBZ (2026-10-19):** one isolated-config, version-only
Docker CLI call returned `BUILDX_VERSION|version=v0.27.0-desktop.1` after the
temporary config received the unique user-local plugin symlink. This confirms
plugin discovery under the isolated setup, but does not prove that the prior
build failure was caused by this issue, and provides no daemon builder/image
identity or verifier trust. Five synthetic tests passed; batch-end full suite
and final diff-check passed; the full suite reported 2,044 tests, 26 skipped.

**EXP-1616–1617 / Batch AKCA (2026-10-19):** EXP-1616's focused suite passed
(35 tests). EXP-1617 reached the portable archive validator but returned
`ARCHIVE_INVALID`; no pin update or post-failure Docker query/cleanup occurred.
The candidate tag may remain. Batch-end full offline suite passed (2,047 tests,
26 skipped); `git diff --check` passed. This does not establish artifact
identity or verifier trust. R2/MVP remain OPEN.

**EXP-1618–1619 / Batch AKCB (2026-10-19):** EXP-1618 added only allowlisted
archive-validation stage evidence and a new EXP-1619 task tag; 40 focused tests
passed, with no Docker operation. EXP-1619 ran once and returned
`ARCHIVE_INVALID|stage=archive-validation`; the generic stage still does not
identify which archive check failed. No archive was accepted and no production
pin changed. The task tag may remain and was not queried or cleaned. Batch-end
full offline suite passed (2,052 tests, 26 skipped); `git diff --check` passed.
