from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.publication_seed import (
    PublicationSeed,
    PublicationSeedError,
    bind_publication_seed_to_target,
    derive_publication_intent,
)
from app_contracts.repository_binding import RepositoryTargetBinding
from app_contracts.github_app import GitHubAppBrokerConfig
from app_contracts.authority import check_intent_approved
from app_contracts.digests import sha256_digest
from app_contracts.controlled_publication import (
    ControlledPublicationError,
    _bind_stage_repository_identity,
)


class RepositoryTargetBindingTests(unittest.TestCase):
    def setUp(self):
        self.seed = PublicationSeed(
            process_id="process-binding-001",
            repository_id="SoldatovAlexander/brainbooster_full_v11",
            base_commit="a" * 40,
            staged_change_digest="sha256:" + "b" * 64,
            verified_contents_digest="sha256:" + "c" * 64,
            verifier_id="test-verifier",
            verdict="pass",
            snapshot_tree_digest="sha256:" + "d" * 64,
            snapshot_origin="github_rest_api_claim",
            snapshot_claim_digest="sha256:" + "e" * 64,
        )
        self.binding = RepositoryTargetBinding(
            source_repository_id="SoldatovAlexander/brainbooster_full_v11",
            provider_repository_id="github-installation/456/repository/1001",
        )

    def test_valid_binding_preserves_both_identities_in_seed_and_intent(self):
        bound = bind_publication_seed_to_target(self.seed, self.binding)
        intent = derive_publication_intent(bound, "agent/process-binding-001", "master")

        self.assertEqual(bound.repository_id, self.binding.provider_repository_id)
        self.assertEqual(bound.source_repository_id, self.binding.source_repository_id)
        self.assertEqual(self.seed.repository_id, self.binding.source_repository_id)
        self.assertEqual(intent.repository_id, self.binding.provider_repository_id)
        self.assertEqual(intent.source_repository_id, self.binding.source_repository_id)
        with self.assertRaises(FrozenInstanceError):
            bound.source_repository_id = "attacker/repository"

    def test_source_slug_mismatch_fails_closed(self):
        mismatch = RepositoryTargetBinding(
            source_repository_id="other/repository",
            provider_repository_id="github-installation/456/repository/1001",
        )
        with self.assertRaisesRegex(PublicationSeedError, "does not match source"):
            bind_publication_seed_to_target(self.seed, mismatch)

    def test_configured_github_app_slug_mismatch_fails_before_side_effects(self):
        config = GitHubAppBrokerConfig(
            app_id=123,
            installation_id=456,
            repository_id=1001,
            repository="another/repository",
            private_key_path=Path("/unused-key-reference"),
            api_url="https://api.github.com",
        )
        with self.assertRaisesRegex(PublicationSeedError, "does not match source"):
            bind_publication_seed_to_target(
                self.seed, config.repository_target_binding
            )

    def test_malformed_or_zero_provider_ids_are_rejected(self):
        for value in (
            "github-installation/0/repository/1",
            "github-installation/1/repository/0",
            "github-installation/01/repository/1",
            "github-installation/1/repository/1/extra",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "target identity is invalid"
            ):
                RepositoryTargetBinding(
                    source_repository_id="owner/repository",
                    provider_repository_id=value,
                )

    def test_binding_cannot_be_applied_twice_or_to_an_unrelated_seed(self):
        bound = bind_publication_seed_to_target(self.seed, self.binding)
        with self.assertRaisesRegex(PublicationSeedError, "does not match source"):
            bind_publication_seed_to_target(bound, self.binding)

        failed = replace(self.seed, verdict="fail")
        with self.assertRaisesRegex(PublicationSeedError, "target binding is invalid"):
            bind_publication_seed_to_target(failed, self.binding)

    def test_approved_intent_digest_binds_both_source_and_provider_identity(self):
        bound = bind_publication_seed_to_target(self.seed, self.binding)
        intent = derive_publication_intent(bound, "agent/process-binding-001", "master")
        approval = {"approved_intent_digest": sha256_digest(asdict(intent))}

        check_intent_approved(asdict(intent), approval)
        for mutated in (
            asdict(replace(intent, source_repository_id="other/repository")),
            asdict(
                replace(
                    intent,
                    repository_id="github-installation/456/repository/1002",
                )
            ),
        ):
            with self.subTest(repository=mutated.get("source_repository_id")):
                with self.assertRaisesRegex(
                    ValueError, "approved intent digest mismatch"
                ):
                    check_intent_approved(mutated, approval)

    def test_stage_source_mismatch_is_denied_before_any_collaborator(self):
        bound = bind_publication_seed_to_target(self.seed, self.binding)
        intent = derive_publication_intent(bound, "agent/process-binding-001", "master")
        with self.assertRaisesRegex(
            ControlledPublicationError,
            "^controlled publication: source repository binding mismatch$",
        ):
            _bind_stage_repository_identity(
                bound, intent, {"repository_id": "other/repository"}
            )

    def test_verified_stage_is_mapped_to_provider_identity_without_mutation(self):
        bound = bind_publication_seed_to_target(self.seed, self.binding)
        intent = derive_publication_intent(bound, "agent/process-binding-001", "master")
        staged_change = {
            "repository_id": self.binding.source_repository_id,
            "base_commit": self.seed.base_commit,
            "patch_digest": "sha256:" + "f" * 64,
        }

        provider_change = _bind_stage_repository_identity(
            bound, intent, staged_change
        )

        self.assertEqual(
            provider_change["repository_id"], self.binding.provider_repository_id
        )
        self.assertEqual(
            staged_change["repository_id"], self.binding.source_repository_id
        )


if __name__ == "__main__":
    unittest.main()
