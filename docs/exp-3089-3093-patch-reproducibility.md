# EXP-3089–3093: staged route patch reproducibility

Date: 2026-10-29

The read-only EXP-3087 stage payload was checked against its repository,
commit, staged-change, and patch pins. One anonymous codeload GET fetched
`SoldatovAlexander/brainbooster_full_v11` at commit
`2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e`; safe extraction reproduced the
recorded source-tree digest. No target checkout was changed.

The stored patch was rejected by one `git apply --check` attempt on the exact
temporary source snapshot. A separate local check on the stored one-file
preimage also rejected it. Reconstructing the desired file from the recorded
base and verified contents succeeded through the system `patch` parser, with
the resulting bytes exactly matching the staged verified artifact. A Git
`--recount` check did not resolve Git's rejection. The cause remains
unclassified; no attempt was made to modify the real `brainbooster_full_v11`
checkout, create a PR, or publish there. All temporary directories were
removed. No trust, approval, or MVP criterion was advanced.

Batch-end Agent00X offline suite: 2,976 tests, 27 skipped (124.362 s),
successful. `git diff --check` passed. The separate Agent00X helper and local
Worker-wrapper code/tests from this work were committed and pushed as
`9aa8afa`; this report is intended as a narrow follow-up record. The wider
working tree remains dirty, so unrelated changes are excluded from this
commit.
