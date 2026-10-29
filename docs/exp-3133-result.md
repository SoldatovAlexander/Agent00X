# EXP-3133 result — local Worker phase evidence

Date: 2026-10-29. One credential-free local Worker invocation completed after
the single anonymous GitHub quota preflight. No API credential, SSH/testdev,
provider write, approval, PR, deployment or publication was used.

The staged-change digest is
`sha256:8742c54db9b4d2dadc1eaa68575e7a6a6de30be7b0f0ceb45cf7dcbac377ec3f`.
The read-only report validated as `repository-change-execution-evidence/v6`
with stage verdict `pass`, exact stage/Observer digest correlation, and exact
process/run binding (`process-exp-3133-local-001` /
`run-d6dd76bf7b3549c28f4d6f9afeab6842`). The verified contents digest is
`sha256:c7568018f1cf126ab80993437c6c667847b859af9af0ca7e7a4093b52e1674ae`.

Observer coverage remains partial: 48 events, 23 checkpoints, and gaps
`checkpoint_partial`, `checkpoint_state_metadata_only`, and
`collector_coverage_unverified`. The runtime sidecar is mode 0600 and reports
67,869 ms measured with `time.monotonic_ns()` for only
`run_remote_snapshot_with_runtime`; outcome `returned`, trust
`local_unattested`. It is not total workflow duration. Monetary cost is
unavailable. No independent verifier-host trust, authenticated human approval,
provider receipt, complete Observer collector coverage, or production
durability is established. This run does not complete an MVP criterion.

Local evidence databases and the mode-0600 sidecar remain outside the
repository at `/Volumes/AlexDATA/Agent00X-local-evidence/`; they are not part
of this report or a proposed commit.
