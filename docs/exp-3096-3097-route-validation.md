# EXP-3096–3097: pinned snapshot and strict-route validation

Date: 2026-10-29

EXP-3096 used the project's native codeload archive parser with the pinned
source-claim artifact for `SoldatovAlexander/brainbooster_full_v11` at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`. The parser validated tree OID
`2007066217aadafd9887fb3e3069220333b4fddb`, 23 files, and content digest
`sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad`.
Exported snapshot bytes matched the recorded tree digest. The snapshot has no
discoverable test files, so no upstream test suite ran; the temporary copy was
removed. No repository source was changed.

EXP-3097 separately compiled only the two staged route functions into an
in-memory harness with a recording fake cursor/connection. Across all five
integer fields, `true`, `false`, string, float, and values below/above SQLite's
signed 64-bit range each raised 422 before cursor execution or commit. A valid
payload using signed 64-bit boundary values performed exactly one insert and
one commit. This is synthetic function-level evidence, not a FastAPI or real
SQLite integration test and not independent-verifier evidence.

Agent00X batch-end offline suite passed 2,976 tests with 27 skipped
(132.269 s); `git diff --check` passed. No approval, provider action, PR,
deployment, trust promotion, or MVP criterion advancement occurred.
