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

EXP-3094 then generated a Git-native diff from the exact stored base and
verified file in isolated temporary repositories. One `git apply --check`
and apply succeeded, and the resulting bytes matched the verified artifact.
Generated patch digest:
`sha256:98d2943a2c1aea98b0f654f766551a60cb9146135eb12230f20050bc9262a0a6`.
The temporary repositories were removed; this did not modify the actual
brainbooster checkout or its stage record. The final full offline suite passed
2,976 tests with 27 skipped (117.885 s), and `git diff --check` passed.
