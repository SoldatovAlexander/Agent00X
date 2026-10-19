from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import tarfile
import tempfile
import unittest
from unittest import mock

from scripts import audit_portable_verifier_image_exp1350 as audit
from scripts import export_verify_portable_image_exp1529 as exp1529
from scripts import export_verify_oci_subset_exp1540 as exp1540
from scripts import inspect_local_verifier_pin_exp1542 as exp1542
from scripts import load_oci_verifier_candidate_exp1546 as exp1546
from scripts import inspect_loaded_oci_candidate_exp1547 as exp1547
from scripts import inspect_loaded_oci_candidate_tag_exp1548 as exp1548
from scripts import load_converted_oci_verifier_exp1549 as exp1549
from scripts import inspect_converted_oci_candidate_exp1551 as exp1551
from scripts import run_synthetic_loaded_verifier_exp1552 as exp1552
from scripts import probe_local_docker_socket_exp1553 as exp1553
from src.app_contracts.verifier_process import VerifierProcessError


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def make_archive(*, wrong_platform: bool = False, wrong_layer: bool = False,
                 corrupt_blob: bool = False, ref_name: str | None = None,
                 changed_config: bool = False):
    original_layers = (b"first layer content", b"second layer content")
    diff_ids = tuple(digest(layer) for layer in original_layers)
    layer_contents = (original_layers[0], b"different layer" if wrong_layer else original_layers[1])
    compressed = tuple(gzip.compress(layer) for layer in layer_contents)
    config_value = {"os": "windows" if wrong_platform else "linux",
                    "architecture": "amd64",
                    "rootfs": {"type": "layers", "diff_ids": list(diff_ids)}}
    if changed_config:
        config_value["created"] = "2026-10-19T00:00:00Z"
    config = json.dumps(config_value,
                        separators=(",", ":")).encode()
    config_digest = digest(config)
    layer_descriptors = [
        {"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
         "digest": digest(blob), "size": len(blob)} for blob in compressed
    ]
    manifest = json.dumps({"schemaVersion": 2,
                           "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                                      "digest": config_digest, "size": len(config)},
                           "layers": layer_descriptors}, separators=(",", ":")).encode()
    manifest_digest = digest(manifest)
    index = json.dumps({"schemaVersion": 2,
                        "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                                       "digest": manifest_digest, "size": len(manifest),
                                       "annotations": {"org.opencontainers.image.ref.name": ref_name or "agent00x-verifier:exp-1521-e6fb28b"}}]},
                       separators=(",", ":")).encode()
    files = {
        "index.json": index,
        "blobs/sha256/" + manifest_digest[7:]: manifest,
        "blobs/sha256/" + config_digest[7:]: config if not corrupt_blob else config + b"x",
    }
    files.update({"blobs/sha256/" + descriptor["digest"][7:]: blob
                  for descriptor, blob in zip(layer_descriptors, compressed)})
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue(), manifest_digest, config_digest, diff_ids


def make_legacy_archive(*, wrong_platform=False, wrong_layer=False,
                         layer_names=None, manifest_count=1, extra_records=0,
                         ambiguous=False, tagless=False):
    original_layers = (b"first legacy layer", b"second legacy layer")
    layer_contents = (original_layers[0], b"altered legacy layer" if wrong_layer else original_layers[1])
    diff_ids = tuple(digest(layer) for layer in original_layers)
    config = json.dumps({"os": "windows" if wrong_platform else "linux",
                         "architecture": "amd64",
                         "rootfs": {"type": "layers", "diff_ids": list(diff_ids)}},
                        separators=(",", ":")).encode()
    config_digest = digest(config)
    names = layer_names or ("layer0/layer.tar", "layer1/layer.tar")
    record = {"Config": config_digest[7:] + ".json",
              "RepoTags": None if tagless else ["agent00x-verifier:exp-1521-e6fb28b"],
              "Layers": list(names)}
    manifests = [record] * manifest_count
    files = {"manifest.json": json.dumps(manifests, separators=(",", ":")).encode(),
             record["Config"]: config,
             "layer0/layer.tar": layer_contents[0],
             "layer1/layer.tar": layer_contents[1]}
    if ambiguous:
        files["index.json"] = b'{"schemaVersion":2,"manifests":[]}'
    files.update({f"extra-{index}.bin": b"x" for index in range(extra_records)})
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue(), config_digest, diff_ids


def with_archive_entries(archive, *, directories=(), links=(), nonempty_directories=()):
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
        regular_files = [
            (member.name, source.extractfile(member).read())
            for member in source.getmembers()
            if member.isfile()
        ]
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        for name, data in regular_files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            target.addfile(info, io.BytesIO(data))
        for name in directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            target.addfile(info)
        for name in nonempty_directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.size = 1
            target.addfile(info, io.BytesIO(b"x"))
        for name, link_type in links:
            info = tarfile.TarInfo(name)
            info.type = link_type
            info.linkname = "target"
            target.addfile(info)
    return output.getvalue()


def replace_archive_file(archive, member_name, replacement):
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
        files = {
            member.name: source.extractfile(member).read()
            for member in source.getmembers()
            if member.isfile()
        }
    files[member_name] = replacement
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            target.addfile(info, io.BytesIO(data))
    return output.getvalue()


def make_combined_archive(*, wrong_config=False, wrong_tag=False, wrong_layer=False,
                          ref_name=None):
    oci_archive, manifest_digest, config_digest, diff_ids = make_archive(ref_name=ref_name)
    with tarfile.open(fileobj=io.BytesIO(oci_archive), mode="r:*") as source:
        files = {
            member.name: source.extractfile(member).read()
            for member in source.getmembers()
            if member.isfile()
        }
    index = json.loads(files["index.json"])
    manifest_path = "blobs/sha256/" + index["manifests"][0]["digest"][7:]
    manifest = json.loads(files[manifest_path])
    config_digest = manifest["config"]["digest"]
    config_path = "blobs/sha256/" + config_digest[7:]
    legacy_config = files[config_path]
    if wrong_config:
        changed = json.loads(legacy_config)
        changed["architecture"] = "arm64"
        legacy_config = json.dumps(changed, separators=(",", ":")).encode()
    legacy_config_name = hashlib.sha256(legacy_config).hexdigest() + ".json"
    files[legacy_config_name] = legacy_config

    layer_names = []
    for index_number, descriptor in enumerate(manifest["layers"]):
        blob_path = "blobs/sha256/" + descriptor["digest"][7:]
        layer_bytes = gzip.decompress(files[blob_path])
        if wrong_layer and index_number == 0:
            layer_bytes += b"altered"
        layer_name = f"legacy{index_number}/layer.tar"
        files[layer_name] = layer_bytes
        layer_names.append(layer_name)
    files["manifest.json"] = json.dumps(
        [{
            "Config": legacy_config_name,
            "RepoTags": [
                "agent00x-verifier:wrong" if wrong_tag
                else "agent00x-verifier:exp-1521-e6fb28b"
            ],
            "Layers": layer_names,
        }],
        separators=(",", ":"),
    ).encode()

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as target:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            target.addfile(info, io.BytesIO(data))
    return output.getvalue(), manifest_digest, config_digest, diff_ids


class PortableVerifierImageTests(unittest.TestCase):
    def test_fixed_current_manifest_config_pin(self):
        self.assertEqual(
            audit.CONFIG_DIGEST,
            "sha256:4bc58e997bad6a48a59f8496f92aad05f294a9480ce269ef2b53862f86cab87c",
        )

    def check_archive(self, archive, manifest_digest, config_digest, diff_ids):
        output = io.StringIO()
        code = audit.audit_archive(archive, manifest_digest=manifest_digest,
                                   config_digest=config_digest, diff_ids=diff_ids,
                                   stream_size=len(archive), output=output)
        return code, output.getvalue()

    def test_complete_oci_chain_accepts_exact_config_and_uncompressed_layers(self):
        args = make_archive()
        self.assertEqual(self.check_archive(*args), (0, "PORTABLE_IMAGE_CHAIN_CONFIRMED\n"))

    def test_wrong_manifest_or_config_link_and_corrupt_blob_fail_closed(self):
        archive, manifest_digest, config_digest, diff_ids = make_archive()
        wrong = "sha256:" + "0" * 64
        self.assertEqual(self.check_archive(archive, wrong, config_digest, diff_ids)[0], 13)
        self.assertEqual(self.check_archive(archive, manifest_digest, wrong, diff_ids)[0], 13)
        self.assertEqual(self.check_archive(*make_archive(corrupt_blob=True)),
                         (13, "PORTABLE_IMAGE_CHAIN_INVALID\n"))

    def test_platform_and_uncompressed_layer_identity_are_required(self):
        for args in (make_archive(wrong_platform=True), make_archive(wrong_layer=True)):
            with self.subTest(args=args[1:3]):
                self.assertEqual(self.check_archive(*args),
                                 (13, "PORTABLE_IMAGE_CHAIN_INVALID\n"))

    def test_portable_archive_parser_binds_oci_facts_to_daemon_tuple(self):
        archive, manifest_digest, config_digest, diff_ids = make_archive()
        facts = audit.parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(facts.archive_format, "oci")
        self.assertEqual(facts.portable_manifest_digest, manifest_digest)
        self.assertEqual(facts.config_digest, config_digest)
        self.assertEqual(facts.diff_ids, diff_ids)
        self.assertEqual(facts.repo_tags, ("agent00x-verifier:exp-1521-e6fb28b",))

    def test_portable_archive_parser_keeps_legacy_format_distinct(self):
        archive, config_digest, diff_ids = make_legacy_archive()
        facts = audit.parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(facts.archive_format, "docker-legacy")
        self.assertIsNone(facts.portable_manifest_digest)
        self.assertEqual(facts.config_digest, config_digest)
        self.assertEqual(facts.diff_ids, diff_ids)

    def test_tagless_legacy_archive_is_accepted_only_when_explicitly_expected(self):
        tagless_archive, config_digest, diff_ids = make_legacy_archive(tagless=True)
        facts = audit.parse_portable_archive(
            tagless_archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag=None,
        )
        self.assertEqual(facts.archive_format, "docker-legacy")
        self.assertEqual(facts.repo_tags, ())

        tagged_archive, _, _ = make_legacy_archive()
        for archive, expected_tag in (
            (tagless_archive, "agent00x-verifier:exp-1521-e6fb28b"),
            (tagged_archive, None),
        ):
            with self.subTest(expected_tag=expected_tag), self.assertRaises(audit.InvalidChain):
                audit.parse_portable_archive(
                    archive,
                    expected_config_digest=config_digest,
                    expected_os="linux",
                    expected_architecture="amd64",
                    expected_diff_ids=diff_ids,
                    expected_repo_tag=expected_tag,
                )

    def test_tagless_hybrid_requires_null_legacy_tags_and_no_oci_ref_name(self):
        archive, _, config_digest, diff_ids = make_combined_archive()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
            files = {
                member.name: source.extractfile(member).read()
                for member in source.getmembers()
                if member.isfile()
            }
        legacy = json.loads(files["manifest.json"])
        legacy[0]["RepoTags"] = None
        files["manifest.json"] = json.dumps(legacy, separators=(",", ":")).encode()
        index = json.loads(files["index.json"])
        descriptor = index["manifests"][0]
        descriptor["annotations"] = {}
        files["index.json"] = json.dumps(index, separators=(",", ":")).encode()
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as target:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
        facts = audit.parse_portable_archive(
            output.getvalue(),
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag=None,
        )
        self.assertEqual(facts.archive_format, "oci+docker-legacy")
        self.assertEqual(facts.repo_tags, ())

        tagged_index_archive, _, _, _ = make_combined_archive()
        with self.assertRaises(audit.InvalidChain) as error:
            audit.parse_portable_archive(
                tagged_index_archive,
                expected_config_digest=config_digest,
                expected_os="linux",
                expected_architecture="amd64",
                expected_diff_ids=diff_ids,
                expected_repo_tag=None,
            )
        self.assertEqual(error.exception.stage, "oci-index-ref-name-mismatch")

    def test_portable_archive_parser_rejects_wrong_facts_layers_extra_and_ambiguous_layouts(self):
        archive, config_digest, diff_ids = make_legacy_archive()
        common = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        bad_inputs = (
            (archive, {**common, "expected_config_digest": digest(b"wrong config")}),
            (make_legacy_archive(wrong_platform=True)[0], common),
            (make_legacy_archive(wrong_layer=True)[0], common),
            (make_legacy_archive(manifest_count=2)[0], common),
            (make_legacy_archive(layer_names=("../layer.tar", "layer1/layer.tar"))[0], common),
            (make_legacy_archive(extra_records=127)[0], common),
            (make_legacy_archive(ambiguous=True)[0], common),
        )
        for candidate, kwargs in bad_inputs:
            with self.subTest(size=len(candidate)):
                with self.assertRaises(audit.InvalidChain):
                    audit.parse_portable_archive(candidate, **kwargs)

    def test_oci_parser_enforces_aggregate_expanded_layer_limit(self):
        archive, _, config_digest, diff_ids = make_archive()
        layer_bytes = len(b"first layer content") + len(b"second layer content")
        kwargs = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        self.assertEqual(
            audit.parse_portable_archive(
                archive, **kwargs, max_uncompressed_layer_bytes=layer_bytes
            ).diff_ids,
            diff_ids,
        )
        with self.assertRaises(audit.InvalidChain):
            audit.parse_portable_archive(
                archive, **kwargs, max_uncompressed_layer_bytes=layer_bytes - 1
            )

    def test_legacy_parser_enforces_aggregate_expanded_layer_limit(self):
        archive, config_digest, diff_ids = make_legacy_archive()
        layer_bytes = len(b"first legacy layer") + len(b"second legacy layer")
        kwargs = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        self.assertEqual(
            audit.parse_portable_archive(
                archive, **kwargs, max_uncompressed_layer_bytes=layer_bytes
            ).diff_ids,
            diff_ids,
        )
        with self.assertRaises(audit.InvalidChain):
            audit.parse_portable_archive(
                archive, **kwargs, max_uncompressed_layer_bytes=layer_bytes - 1
            )

    def test_portable_parser_rejects_invalid_size_budgets(self):
        archive, _, config_digest, diff_ids = make_archive()
        kwargs = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        for parameter in ("max_archive_bytes", "max_uncompressed_layer_bytes"):
            with self.subTest(parameter=parameter):
                with self.assertRaises(audit.InvalidChain):
                    audit.parse_portable_archive(archive, **kwargs, **{parameter: True})

    def test_parser_stage_codes_are_fixed_and_format_specific(self):
        oci_archive, _, oci_config, oci_diff_ids = make_archive(wrong_layer=True)
        oci_kwargs = {
            "expected_config_digest": oci_config,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": oci_diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        with self.assertRaises(audit.InvalidChain) as oci_error:
            audit.parse_portable_archive(oci_archive, **oci_kwargs)
        self.assertEqual(oci_error.exception.stage, "oci-layers")

        legacy_archive, legacy_config, legacy_diff_ids = make_legacy_archive(wrong_layer=True)
        legacy_kwargs = {
            **oci_kwargs,
            "expected_config_digest": legacy_config,
            "expected_diff_ids": legacy_diff_ids,
        }
        with self.assertRaises(audit.InvalidChain) as legacy_error:
            audit.parse_portable_archive(legacy_archive, **legacy_kwargs)
        self.assertEqual(legacy_error.exception.stage, "docker-layer-diff-id-mismatch")

    def test_safe_directory_entries_are_accepted_in_both_formats(self):
        oci_archive, _, oci_config, oci_diff_ids = make_archive()
        oci_archive = with_archive_entries(
            oci_archive, directories=("blobs/", "blobs/sha256/")
        )
        common = {
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        oci_facts = audit.parse_portable_archive(
            oci_archive,
            expected_config_digest=oci_config,
            expected_diff_ids=oci_diff_ids,
            **common,
        )
        self.assertEqual(oci_facts.archive_format, "oci")

        legacy_archive, legacy_config, legacy_diff_ids = make_legacy_archive()
        legacy_archive = with_archive_entries(
            legacy_archive, directories=("layer0/", "layer1/")
        )
        legacy_facts = audit.parse_portable_archive(
            legacy_archive,
            expected_config_digest=legacy_config,
            expected_diff_ids=legacy_diff_ids,
            **common,
        )
        self.assertEqual(legacy_facts.archive_format, "docker-legacy")

    def test_directory_traversal_duplicates_and_nonregular_records_are_rejected(self):
        archive, _, config_digest, diff_ids = make_archive()
        common = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        invalid_archives = (
            with_archive_entries(archive, directories=("../escape/",)),
            with_archive_entries(archive, directories=("index.json/",)),
            with_archive_entries(archive, nonempty_directories=("extra/",)),
            with_archive_entries(archive, links=(("link", tarfile.SYMTYPE),)),
            with_archive_entries(archive, links=(("hardlink", tarfile.LNKTYPE),)),
        )
        for invalid_archive in invalid_archives:
            with self.subTest(size=len(invalid_archive)):
                with self.assertRaises(audit.InvalidChain):
                    audit.parse_portable_archive(invalid_archive, **common)

    def test_combined_oci_and_legacy_metadata_is_accepted_only_when_consistent(self):
        archive, manifest_digest, config_digest, diff_ids = make_combined_archive()
        combined = archive
        facts = audit.parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(facts.archive_format, "oci+docker-legacy")
        self.assertEqual(facts.portable_manifest_digest, manifest_digest)
        self.assertEqual(facts.config_digest, config_digest)

        for options, expected_stage in (
            ({"wrong_config": True}, "docker-config"),
            ({"wrong_tag": True}, "docker-manifest"),
            ({"wrong_layer": True}, "docker-layer-diff-id-mismatch"),
        ):
            invalid, _, _, _ = make_combined_archive(**options)
            with self.subTest(expected_stage=expected_stage):
                with self.assertRaises(audit.InvalidChain) as error:
                    audit.parse_portable_archive(
                        invalid,
                        expected_config_digest=config_digest,
                        expected_os="linux",
                        expected_architecture="amd64",
                        expected_diff_ids=diff_ids,
                        expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
                    )
                self.assertEqual(error.exception.stage, expected_stage)
                if expected_stage == "docker-layer-diff-id-mismatch":
                    self.assertEqual(error.exception.layer_index, 0)

        missing_layer, _, _, _ = make_combined_archive()
        with tarfile.open(fileobj=io.BytesIO(missing_layer), mode="r:*") as source:
            files = {
                member.name: source.extractfile(member).read()
                for member in source.getmembers()
                if member.isfile() and member.name != "legacy0/layer.tar"
            }
        missing_output = io.BytesIO()
        with tarfile.open(fileobj=missing_output, mode="w") as target:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
        with self.assertRaises(audit.InvalidChain) as member_error:
            audit.parse_portable_archive(missing_output.getvalue(), **{
                "expected_config_digest": config_digest,
                "expected_os": "linux",
                "expected_architecture": "amd64",
                "expected_diff_ids": diff_ids,
                "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
            })
        self.assertEqual(member_error.exception.stage, "docker-layer-member")

        with self.assertRaises(audit.InvalidChain) as size_error:
            audit.parse_portable_archive(
                combined,
                expected_config_digest=config_digest,
                expected_os="linux",
                expected_architecture="amd64",
                expected_diff_ids=diff_ids,
                expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
                max_uncompressed_layer_bytes=len(b"first layer content") + len(b"second layer content"),
            )
        self.assertEqual(size_error.exception.stage, "docker-layer-size-limit")

    def test_oci_index_failures_have_distinct_fixed_substages(self):
        archive, _, config_digest, diff_ids = make_archive()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as source:
            index = json.loads(source.extractfile("index.json").read())
        cases = (
            ("oci-index-header", {**index, "schemaVersion": 1}),
            ("oci-index-manifest-list", {**index, "manifests": []}),
            ("oci-index-descriptor", {**index, "manifests": ["bad"]}),
            (
                "oci-index-ref-name-mismatch",
                {
                    **index,
                    "manifests": [
                        {
                            **index["manifests"][0],
                            "annotations": {"org.opencontainers.image.ref.name": "wrong"},
                        }
                    ],
                },
            ),
        )
        kwargs = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        for expected_stage, changed_index in cases:
            candidate = replace_archive_file(
                archive,
                "index.json",
                json.dumps(changed_index, separators=(",", ":")).encode(),
            )
            with self.subTest(stage=expected_stage):
                with self.assertRaises(audit.InvalidChain) as error:
                    audit.parse_portable_archive(candidate, **kwargs)
                self.assertEqual(error.exception.stage, expected_stage)

    def test_missing_oci_ref_name_requires_matching_legacy_tag(self):
        combined, _, config_digest, diff_ids = make_combined_archive()
        with tarfile.open(fileobj=io.BytesIO(combined), mode="r:*") as source:
            index = json.loads(source.extractfile("index.json").read())
        index["manifests"][0].pop("annotations")
        combined_missing_ref = replace_archive_file(
            combined, "index.json", json.dumps(index, separators=(",", ":")).encode()
        )
        common = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        facts = audit.parse_portable_archive(combined_missing_ref, **common)
        self.assertEqual(facts.archive_format, "oci+docker-legacy")

        oci_only, _, oci_config_digest, oci_diff_ids = make_archive()
        with tarfile.open(fileobj=io.BytesIO(oci_only), mode="r:*") as source:
            oci_index = json.loads(source.extractfile("index.json").read())
        oci_index["manifests"][0].pop("annotations")
        oci_missing_ref = replace_archive_file(
            oci_only, "index.json", json.dumps(oci_index, separators=(",", ":")).encode()
        )
        with self.assertRaises(audit.InvalidChain) as oci_error:
            audit.parse_portable_archive(
                oci_missing_ref,
                expected_config_digest=oci_config_digest,
                expected_os="linux",
                expected_architecture="amd64",
                expected_diff_ids=oci_diff_ids,
                expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
            )
        self.assertEqual(oci_error.exception.stage, "oci-index-ref-name-unbound")

        wrong_index = dict(index)
        wrong_descriptor = dict(index["manifests"][0])
        wrong_descriptor["annotations"] = {"org.opencontainers.image.ref.name": "wrong"}
        wrong_index["manifests"] = [wrong_descriptor]
        combined_wrong_ref = replace_archive_file(
            combined,
            "index.json",
            json.dumps(wrong_index, separators=(",", ":")).encode(),
        )
        with self.assertRaises(audit.InvalidChain) as wrong_error:
            audit.parse_portable_archive(combined_wrong_ref, **common)
        self.assertEqual(wrong_error.exception.stage, "oci-index-ref-name-mismatch")

        malformed_index = dict(index)
        malformed_descriptor = dict(index["manifests"][0])
        malformed_descriptor["annotations"] = "not-an-object"
        malformed_index["manifests"] = [malformed_descriptor]
        malformed_archive = replace_archive_file(
            combined,
            "index.json",
            json.dumps(malformed_index, separators=(",", ":")).encode(),
        )
        with self.assertRaises(audit.InvalidChain) as malformed_error:
            audit.parse_portable_archive(malformed_archive, **common)
        self.assertEqual(malformed_error.exception.stage, "oci-index-annotations-invalid")

    def test_oci_ref_name_accepts_exact_tag_component_and_registry_port_tag(self):
        expected_tag = "exp-1521-e6fb28b"
        archive, _, config_digest, diff_ids = make_archive(ref_name=expected_tag)
        facts = audit.parse_portable_archive(
            archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(facts.archive_format, "oci")

        registry_tag = "registry.example:5000/agent00x-verifier:exp-1521-e6fb28b"
        registry_archive, _, registry_config, registry_diff_ids = make_archive(
            ref_name=expected_tag
        )
        registry_facts = audit.parse_portable_archive(
            registry_archive,
            expected_config_digest=registry_config,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=registry_diff_ids,
            expected_repo_tag=registry_tag,
        )
        self.assertEqual(registry_facts.repo_tags, (registry_tag,))

        combined, _, combined_config, combined_diff_ids = make_combined_archive(
            ref_name=expected_tag
        )
        combined_facts = audit.parse_portable_archive(
            combined,
            expected_config_digest=combined_config,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=combined_diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(combined_facts.archive_format, "oci+docker-legacy")

    def test_pinned_daemon_facts_have_distinct_fixed_substages(self):
        archive, _, config_digest, diff_ids = make_archive()
        common = {
            "expected_config_digest": config_digest,
            "expected_os": "linux",
            "expected_architecture": "amd64",
            "expected_diff_ids": diff_ids,
            "expected_repo_tag": "agent00x-verifier:exp-1521-e6fb28b",
        }
        cases = (
            ({**common, "expected_config_digest": "sha256:" + "0" * 64},
             "daemon-config-digest-mismatch"),
            ({**common, "expected_os": "windows"}, "daemon-platform-mismatch"),
        )
        for kwargs, expected_stage in cases:
            with self.subTest(stage=expected_stage):
                with self.assertRaises(audit.InvalidChain) as error:
                    audit.parse_portable_archive(archive, **kwargs)
                self.assertEqual(error.exception.stage, expected_stage)

        legacy, _, legacy_diff_ids = make_legacy_archive()
        with tarfile.open(fileobj=io.BytesIO(legacy), mode="r:*") as source:
            files = {
                member.name: source.extractfile(member).read()
                for member in source.getmembers()
                if member.isfile()
            }
        legacy_manifest = json.loads(files["manifest.json"])
        old_config_name = legacy_manifest[0]["Config"]
        altered_config = json.loads(files[old_config_name])
        altered_config["rootfs"]["diff_ids"] = ["sha256:" + "0" * 64, *legacy_diff_ids[1:]]
        altered_config_raw = json.dumps(altered_config, separators=(",", ":")).encode()
        altered_config_name = digest(altered_config_raw)[7:] + ".json"
        files.pop(old_config_name)
        files[altered_config_name] = altered_config_raw
        legacy_manifest[0]["Config"] = altered_config_name
        files["manifest.json"] = json.dumps(legacy_manifest, separators=(",", ":")).encode()
        altered_output = io.BytesIO()
        with tarfile.open(fileobj=altered_output, mode="w") as target:
            for name, payload in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                target.addfile(info, io.BytesIO(payload))
        with self.assertRaises(audit.InvalidChain) as diff_error:
            audit.parse_portable_archive(
                altered_output.getvalue(),
                expected_config_digest=digest(altered_config_raw),
                expected_os="linux",
                expected_architecture="amd64",
                expected_diff_ids=legacy_diff_ids,
                expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
            )
        self.assertEqual(diff_error.exception.stage, "daemon-diff-id-mismatch")

    def test_config_pin_mismatch_exposes_only_verified_content_digest(self):
        archive, _, observed_config, diff_ids = make_archive(changed_config=True)
        expected_config = "sha256:" + "0" * 64
        with self.assertRaises(audit.InvalidChain) as error:
            audit.parse_portable_archive(
                archive,
                expected_config_digest=expected_config,
                expected_os="linux",
                expected_architecture="amd64",
                expected_diff_ids=diff_ids,
                expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
            )
        self.assertEqual(error.exception.stage, "daemon-config-digest-mismatch")
        self.assertEqual(error.exception.observed_digest, observed_config)

    def test_opt_in_blocks_docker_before_process(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "0"}), \
             mock.patch.object(audit, "_bounded_process_output") as runner:
            self.assertEqual(audit.audit_local_image(output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        runner.assert_not_called()

    def test_bounded_capture_accepts_exact_limit(self):
        result = audit._bounded_process_output(
            (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'1234')"),
            max_bytes=4,
            timeout=2,
        )
        self.assertEqual(result.stdout, b"1234")
        self.assertEqual(result.returncode, 0)

    def test_bounded_capture_rejects_limit_plus_one_without_returning_payload(self):
        with self.assertRaises(audit.OutputLimitExceeded):
            audit._bounded_process_output(
                (sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'12345')"),
                max_bytes=4,
                timeout=2,
            )

    def test_bounded_capture_kills_timed_out_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            audit._bounded_process_output(
                (sys.executable, "-c", "import time; time.sleep(5)"),
                max_bytes=4,
                timeout=0.05,
            )

    def test_save_failure_suppresses_process_output(self):
        output = io.StringIO()
        process = subprocess.CompletedProcess(("synthetic",), 1, b"payload", None)
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(audit, "_bounded_process_output", return_value=process) as runner:
            self.assertEqual(audit.audit_local_image(output), 11)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_SAVE_FAILED\n")
        runner.assert_called_once_with(
            ("/usr/local/bin/docker", "image", "save", audit.pinned.IMAGE_ID),
            max_bytes=128 * 1024 * 1024,
            timeout=60,
        )

    def test_save_size_limit_and_timeout_have_only_fixed_markers(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(audit, "_bounded_process_output", side_effect=audit.OutputLimitExceeded):
            self.assertEqual(audit.audit_local_image(output), 12)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_STREAM_SIZE_MISMATCH\n")

        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(audit, "_bounded_process_output", side_effect=subprocess.TimeoutExpired("synthetic", 1)):
            self.assertEqual(audit.audit_local_image(output), 11)
        self.assertEqual(output.getvalue(), "LOCAL_IMAGE_SAVE_FAILED\n")

    def test_exp1529_runner_uses_exact_pin_bounds_minimal_env_and_sanitized_success(self):
        archive, manifest_digest, config_digest, diff_ids = make_archive()
        tag = "agent00x-verifier:exp-1521-e6fb28b"
        output = io.StringIO()
        config_dirs = []

        def runner(command, *, max_bytes, timeout, env):
            self.assertEqual(command, ("/usr/local/bin/docker", "image", "save", tag))
            self.assertEqual(max_bytes, 128 * 1024 * 1024)
            self.assertEqual(timeout, 60)
            self.assertEqual(set(env), {"DOCKER_CONFIG", "PATH"})
            self.assertEqual(env["PATH"], "/usr/local/bin:/usr/bin:/bin")
            self.assertTrue(os.path.isdir(env["DOCKER_CONFIG"]))
            self.assertEqual(os.listdir(env["DOCKER_CONFIG"]), [])
            config_dirs.append(env["DOCKER_CONFIG"])
            return subprocess.CompletedProcess(command, 0, archive, b"sensitive stderr")

        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1529, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1529, "DIFF_IDS", diff_ids):
            code = exp1529.run_once(runner=runner, output=output)

        self.assertEqual(code, 0)
        self.assertEqual(
            output.getvalue(),
            "PORTABLE_IMAGE_IDENTITY_CONFIRMED|"
            f"format=oci|archive_bytes={len(archive)}|manifest={manifest_digest}|"
            f"config={config_digest}|platform=linux/amd64|"
            f"diff_ids={','.join(diff_ids)}|repo_tag={tag}\n",
        )
        self.assertNotIn("sensitive stderr", output.getvalue())
        self.assertEqual(len(config_dirs), 1)
        self.assertFalse(os.path.exists(config_dirs[0]))

    def test_exp1529_runner_accepts_legacy_without_inventing_manifest_digest(self):
        archive, config_digest, diff_ids = make_legacy_archive()
        tag = "agent00x-verifier:exp-1521-e6fb28b"
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, archive, b"")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1529, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1529, "DIFF_IDS", diff_ids):
            code = exp1529.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertIn("format=docker-legacy|", output.getvalue())
        self.assertIn("manifest=null|", output.getvalue())

    def test_exp1531_runner_emits_only_fixed_archive_failure_stage(self):
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, b"not a tar", b"raw")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            code = exp1529.run_once(runner=runner, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(output.getvalue(), "PORTABLE_IMAGE_CHAIN_INVALID|stage=archive-layout\n")
        self.assertNotIn("raw", output.getvalue())

    def test_exp1539_runner_reports_only_bounded_legacy_layer_index(self):
        archive, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, archive, b"raw")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1529, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1529, "DIFF_IDS", diff_ids):
            code = exp1529.run_once(runner=runner, output=output)
        self.assertEqual(code, 14)
        self.assertEqual(
            output.getvalue(),
            "PORTABLE_IMAGE_CHAIN_INVALID|stage=docker-layer-diff-id-mismatch|layer_index=0\n",
        )
        self.assertNotIn("raw", output.getvalue())

    def test_exp1540_extracts_and_validates_oci_subset_without_legacy_layers(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        subset = exp1540.make_oci_subset(combined)
        facts = audit.parse_portable_archive(
            subset,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag="agent00x-verifier:exp-1521-e6fb28b",
        )
        self.assertEqual(facts.archive_format, "oci")
        with tarfile.open(fileobj=io.BytesIO(subset), mode="r:*") as source:
            names = {member.name for member in source.getmembers()}
        self.assertIn("index.json", names)
        self.assertNotIn("manifest.json", names)
        self.assertFalse(any(name.endswith("/layer.tar") for name in names))

    def test_exp1540_runner_outputs_only_validated_oci_facts(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, combined, b"raw")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1540.pinned, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1540.pinned, "DIFF_IDS", diff_ids):
            code = exp1540.run_once(runner=runner, output=output)
        self.assertEqual(code, 0)
        self.assertIn("OCI_SUBSET_CONFIRMED|legacy=unverified|", output.getvalue())
        self.assertIn(f"config={config_digest}|platform=linux/amd64|", output.getvalue())
        self.assertNotIn("layer.tar", output.getvalue())
        self.assertNotIn("raw", output.getvalue())
        runner.assert_called_once()

    def test_exp1542_inspect_is_read_only_bounded_and_redacts_failures(self):
        output = io.StringIO()
        expected = (
            f"{exp1542.pinned.CONFIG_DIGEST}|linux|amd64|"
            f"{json.dumps(list(exp1542.pinned.DIFF_IDS))}"
        ).encode()

        def runner(command, *, max_bytes, timeout, env):
            self.assertEqual(command[1:3], ("image", "inspect"))
            self.assertEqual(command[-1], exp1542.pinned.IMAGE_TAG)
            self.assertEqual(max_bytes, exp1542.MAX_OUTPUT_BYTES)
            self.assertEqual(timeout, exp1542.TIMEOUT_SECONDS)
            self.assertEqual(set(env), {"DOCKER_CONFIG", "PATH"})
            self.assertTrue(os.path.isdir(env["DOCKER_CONFIG"]))
            return subprocess.CompletedProcess(command, 0, expected, b"private")

        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1542.run_once(runner=runner, output=output), 0)
        self.assertTrue(output.getvalue().startswith("LOCAL_IMAGE_PIN_CONFIRMED|"))
        self.assertNotIn("private", output.getvalue())

        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(
                exp1542.run_once(
                    runner=mock.Mock(side_effect=OSError("private diagnostic")),
                    output=output,
                ),
                11,
            )
        self.assertEqual(output.getvalue(), "INSPECT_FAILED\n")
        self.assertNotIn("private", output.getvalue())

    def test_exp1543_runner_reports_only_validated_config_digests(self):
        archive, _, observed_config, diff_ids = make_archive(changed_config=True)
        expected_config = "sha256:" + "0" * 64
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, archive, b"raw config")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1540.pinned, "CONFIG_DIGEST", expected_config), \
             mock.patch.object(exp1540.pinned, "DIFF_IDS", diff_ids):
            self.assertEqual(exp1540.run_once(runner=runner, output=output), 14)
        self.assertEqual(
            output.getvalue(),
            "OCI_SUBSET_INVALID|stage=daemon-config-digest-mismatch|"
            f"expected_config={expected_config}|observed_config={observed_config}\n",
        )
        self.assertNotIn("created", output.getvalue())
        self.assertNotIn("raw config", output.getvalue())

    def test_exp1546_prepares_oci_layout_with_isolated_candidate_tag(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        candidate = exp1546.prepare_tagged_oci_archive(
            combined, config_digest=config_digest, diff_ids=diff_ids
        )
        with tarfile.open(fileobj=io.BytesIO(candidate), mode="r:*") as archive:
            files = {
                member.name: archive.extractfile(member).read()
                for member in archive.getmembers()
                if member.isfile()
            }
        self.assertEqual(json.loads(files["oci-layout"]), {"imageLayoutVersion": "1.0.0"})
        index = json.loads(files["index.json"])
        self.assertEqual(
            index["manifests"][0]["annotations"]["org.opencontainers.image.ref.name"],
            "exp-1546-oci-candidate",
        )
        self.assertNotIn("manifest.json", files)

    def test_exp1546_runs_one_load_then_exact_inspect(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        save_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, combined, b"raw save")
        )
        load_runner = mock.Mock(return_value=subprocess.CompletedProcess(("docker",), 0, b"", b""))
        inspect_result = (
            f"{config_digest}|linux|amd64|{json.dumps(list(diff_ids))}|"
            f"65532:65532|{json.dumps(list(exp1546.ENTRYPOINT))}"
        ).encode()
        inspect_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, inspect_result, b"raw inspect")
        )
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1546, "OCI_CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1546, "DIFF_IDS", diff_ids):
            code = exp1546.run_once(
                save_runner=save_runner,
                load_runner=load_runner,
                inspect_runner=inspect_runner,
                output=output,
            )
        self.assertEqual(code, 0)
        self.assertIn("OCI_LOAD_CONFIRMED|", output.getvalue())
        self.assertIn(f"tag={exp1546.IMAGE_TAG}", output.getvalue())
        self.assertNotIn("raw", output.getvalue())
        save_runner.assert_called_once()
        load_runner.assert_called_once()
        inspect_runner.assert_called_once()

    def test_exp1547_inspects_exact_id_and_redacts_failures(self):
        output = io.StringIO()
        payload = (
            f"{exp1547.IMAGE_ID}|linux|amd64|"
            f"{json.dumps(list(exp1546.DIFF_IDS))}|65532:65532|"
            f"{json.dumps(list(exp1546.ENTRYPOINT))}"
        ).encode()

        def runner(command, *, max_bytes, timeout, env):
            self.assertEqual(command[-1], exp1547.IMAGE_ID)
            self.assertEqual(command[1:3], ("image", "inspect"))
            self.assertEqual(max_bytes, exp1547.MAX_OUTPUT_BYTES)
            self.assertEqual(timeout, exp1547.TIMEOUT_SECONDS)
            self.assertEqual(set(env), {"DOCKER_CONFIG", "PATH"})
            return subprocess.CompletedProcess(command, 0, payload, b"raw")

        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1547.run_once(runner=runner, output=output), 0)
        self.assertIn("IMAGE_ID_INSPECTED|", output.getvalue())
        self.assertNotIn("raw", output.getvalue())

        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(
                exp1547.run_once(
                    runner=mock.Mock(return_value=subprocess.CompletedProcess(("docker",), 1, b"", b"secret")),
                    output=output,
                ),
                11,
            )
        self.assertEqual(output.getvalue(), "IMAGE_ID_NOT_FOUND\n")

    def test_exp1548_inspects_only_candidate_tag_and_redacts_not_found(self):
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 1, b"", b"private")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1548.run_once(runner=runner, output=output), 11)
        self.assertEqual(output.getvalue(), "CANDIDATE_TAG_NOT_FOUND\n")
        command = runner.call_args.args[0]
        self.assertEqual(command[-1], exp1548.IMAGE_TAG)
        self.assertEqual(command[1:3], ("image", "inspect"))
        self.assertNotIn("private", output.getvalue())

    def test_exp1549_converts_verified_oci_layers_not_legacy_layer_files(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        docker_archive = exp1549.make_docker_archive(
            combined, config_digest=config_digest, diff_ids=diff_ids
        )
        facts = audit.parse_portable_archive(
            docker_archive,
            expected_config_digest=config_digest,
            expected_os="linux",
            expected_architecture="amd64",
            expected_diff_ids=diff_ids,
            expected_repo_tag=exp1549.IMAGE_TAG,
        )
        self.assertEqual(facts.archive_format, "docker-legacy")
        self.assertEqual(facts.config_digest, config_digest)
        with tarfile.open(fileobj=io.BytesIO(docker_archive), mode="r:*") as archive:
            names = {member.name for member in archive.getmembers()}
            manifest = json.loads(archive.extractfile("manifest.json").read())
        self.assertNotIn("index.json", names)
        self.assertEqual(manifest[0]["RepoTags"], [exp1549.IMAGE_TAG])

    def test_exp1549_load_runner_calls_load_and_inspect_once(self):
        combined, _, config_digest, diff_ids = make_combined_archive(wrong_layer=True)
        save_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, combined, b"")
        )
        load_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, b"", b"")
        )
        inspect_payload = (
            f"{config_digest}|linux|amd64|{json.dumps(list(diff_ids))}|"
            f"{exp1549.USER}|{json.dumps(list(exp1549.ENTRYPOINT))}"
        ).encode()
        inspect_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, inspect_payload, b"")
        )
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1549, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1549, "DIFF_IDS", diff_ids):
            result = exp1549.run_once(
                save_runner=save_runner,
                load_runner=load_runner,
                inspect_runner=inspect_runner,
                output=output,
            )
        self.assertEqual(result, 0)
        self.assertIn("DOCKER_LOAD_CONFIRMED|", output.getvalue())
        self.assertIn(f"tag={exp1549.IMAGE_TAG}", output.getvalue())
        save_runner.assert_called_once()
        load_runner.assert_called_once()
        inspect_runner.assert_called_once()

    def test_exp1550_enforces_expanded_layer_limit_and_emits_fixed_marker(self):
        combined, _, config_digest, diff_ids = make_combined_archive()
        with mock.patch.object(exp1549, "MAX_EXPANDED_LAYER_BYTES", 8):
            with self.assertRaises(audit.InvalidChain) as error:
                exp1549.make_docker_archive(
                    combined, config_digest=config_digest, diff_ids=diff_ids
                )
        self.assertEqual(error.exception.stage, "oci-layers")

        save_runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 0, combined, b"")
        )
        load_runner = mock.Mock()
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}), \
             mock.patch.object(exp1549, "MAX_EXPANDED_LAYER_BYTES", 8), \
             mock.patch.object(exp1549, "CONFIG_DIGEST", config_digest), \
             mock.patch.object(exp1549, "DIFF_IDS", diff_ids):
            result = exp1549.run_once(
                save_runner=save_runner,
                load_runner=load_runner,
                output=output,
            )
        self.assertEqual(result, 14)
        self.assertEqual(output.getvalue(), "DOCKER_ARCHIVE_INVALID|stage=oci-layers\n")
        load_runner.assert_not_called()

    def test_exp1551_inspects_exact_converted_tag_and_redacts_not_found(self):
        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 1, b"", b"private")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1551.run_once(runner=runner, output=output), 11)
        self.assertEqual(output.getvalue(), "CANDIDATE_TAG_NOT_FOUND\n")
        self.assertEqual(runner.call_args.args[0][-1], exp1551.IMAGE_TAG)
        self.assertEqual(runner.call_args.args[0][1:3], ("image", "inspect"))
        self.assertNotIn("private", output.getvalue())

    def test_exp1552_synthetic_request_uses_exact_image_and_safe_input(self):
        prepared = exp1552.build_synthetic_input()
        fake_result = __import__("src.app_contracts.executor", fromlist=["VerifierResult"]).VerifierResult(
            process_id=prepared.process_id,
            base_commit=prepared.base_commit,
            snapshot_tree_digest=prepared.snapshot_tree_digest,
            replay_result_digest=prepared.replay_result_digest,
            verifier_id="docker-image:local/code:local",
            patch_digest=prepared.patch_digest,
            evidence_digest=prepared.evidence_digest,
            verification_digest=prepared.verification_digest,
            verified_contents_digest=prepared.verified_contents_digest,
            verdict=__import__("src.app_contracts.executor", fromlist=["VerifierVerdict"]).VerifierVerdict.PASS,
            blocker_codes=(),
            evidence_origin="local_test",
        )
        fake = mock.Mock()
        fake.verify.return_value = fake_result
        factory = mock.Mock(return_value=fake)
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 0)
        self.assertEqual(output.getvalue(),
                         "SYNTHETIC_VERIFIER_CONFIRMED|"
                         f"config={exp1552.CONFIG_DIGEST}|code={exp1552.CODE_DIGEST}|"
                         "verdict=pass|blockers=0|network=none\n")
        config = factory.call_args.args[0]
        self.assertEqual(config.runtime_image_id, exp1552.CONFIG_DIGEST)
        self.assertEqual(
            config.runtime_image_id,
            "sha256:f9352ed122050abfa42526544c101a713f4724271e0aa044fb92e56972a0ae38",
        )
        self.assertEqual(fake.verify.call_args.args[0].repository_id, "synthetic-local-fixture")
        self.assertIn("EXP1552_CANARY", prepared.test_command[-1])

    def test_exp1552_suppresses_verifier_failure_details(self):
        output = io.StringIO()
        verifier = mock.Mock()
        verifier.verify.side_effect = RuntimeError("private output")
        factory = mock.Mock(return_value=verifier)
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 2)
        self.assertEqual(output.getvalue(), "SYNTHETIC_VERIFIER_EXCEPTION\n")
        self.assertNotIn("private output", output.getvalue())

    def test_exp1554_classifies_verifier_process_error_without_details(self):
        output = io.StringIO()
        verifier = mock.Mock()
        verifier.verify.side_effect = VerifierProcessError("private diagnostic")
        factory = mock.Mock(return_value=verifier)
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 1)
        self.assertEqual(output.getvalue(), "SYNTHETIC_VERIFIER_PROCESS_ERROR\n")
        self.assertNotIn("private diagnostic", output.getvalue())

    def test_exp1561_maps_only_fixed_verifier_process_failure_stages(self):
        cases = (
            ("verifier process: child launch failed", "SYNTHETIC_VERIFIER_PROCESS_LAUNCH_FAILED"),
            ("verifier process: child timed out", "SYNTHETIC_VERIFIER_PROCESS_TIMEOUT"),
            ("verifier process: child output exceeds limit", "SYNTHETIC_VERIFIER_PROCESS_OUTPUT_LIMIT"),
            ("verifier process: child response is empty", "SYNTHETIC_VERIFIER_RESPONSE_EMPTY"),
            ("verifier process: child response is malformed", "SYNTHETIC_VERIFIER_RESPONSE_MALFORMED"),
            ("verifier process: child exit failed (status=125)", "SYNTHETIC_VERIFIER_CHILD_EXIT_FAILED"),
            ("verifier process: child rejected (invalid-input)", "SYNTHETIC_VERIFIER_CHILD_REJECTED"),
            ("verifier container: invocation nonce mismatch", "SYNTHETIC_VERIFIER_NONCE_MISMATCH"),
            ("private diagnostic with secret-shaped data", "SYNTHETIC_VERIFIER_PROCESS_ERROR"),
        )
        for message, expected_marker in cases:
            with self.subTest(expected_marker=expected_marker):
                output = io.StringIO()
                verifier = mock.Mock()
                verifier.verify.side_effect = VerifierProcessError(message)
                factory = mock.Mock(return_value=verifier)
                with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
                    self.assertEqual(
                        exp1552.run_once(verifier_factory=factory, output=output), 1
                    )
                self.assertEqual(output.getvalue(), expected_marker + "\n")
                self.assertNotIn(message, output.getvalue())

    def test_exp1554_classifies_rejected_result_without_details(self):
        output = io.StringIO()
        verifier = mock.Mock()
        verifier.verify.return_value = {"private": "response"}
        factory = mock.Mock(return_value=verifier)
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 3)
        self.assertEqual(output.getvalue(), "SYNTHETIC_VERIFIER_RESULT_REJECTED\n")
        self.assertNotIn("private", output.getvalue())

    def test_exp1555_requires_exact_docker_opt_in_before_factory(self):
        factory = mock.Mock()
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "0"}):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        factory.assert_not_called()

        factory.reset_mock()
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(exp1552.run_once(verifier_factory=factory, output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        factory.assert_not_called()

    def test_exp1553_checks_only_socket_type_and_access(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            socket_path = os.path.join(directory, "docker.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                listener.bind(socket_path)
                self.assertEqual(exp1553.run_once(output=output, path=socket_path), 0)
                self.assertEqual(output.getvalue(), "DOCKER_SOCKET_READY\n")
            finally:
                listener.close()

            output = io.StringIO()
            with open(os.path.join(directory, "regular-file"), "w", encoding="utf-8") as file:
                file.write("synthetic")
            self.assertEqual(
                exp1553.run_once(output=output, path=os.path.join(directory, "regular-file")),
                2,
            )
            self.assertEqual(output.getvalue(), "DOCKER_SOCKET_NOT_SOCKET\n")

            output = io.StringIO()
            self.assertEqual(
                exp1553.run_once(output=output, path=os.path.join(directory, "missing")),
                1,
            )
            self.assertEqual(output.getvalue(), "DOCKER_SOCKET_MISSING\n")

    def test_exp1529_runner_opt_in_and_failure_outputs_are_fixed(self):
        runner = mock.Mock()
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "0"}):
            self.assertEqual(exp1529.run_once(runner=runner, output=output), 10)
        self.assertEqual(output.getvalue(), "OPT_IN_REQUIRED\n")
        runner.assert_not_called()

        failures = (
            (audit.OutputLimitExceeded, "IMAGE_SAVE_SIZE_LIMIT\n", 12),
            (subprocess.TimeoutExpired("docker", 60), "IMAGE_SAVE_TIMEOUT\n", 13),
            (OSError("private diagnostics"), "IMAGE_SAVE_FAILED\n", 11),
        )
        for error, expected_output, expected_code in failures:
            with self.subTest(expected_output=expected_output):
                output = io.StringIO()
                with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
                    actual = exp1529.run_once(
                        runner=mock.Mock(side_effect=error), output=output
                    )
                self.assertEqual((actual, output.getvalue()), (expected_code, expected_output))
                self.assertNotIn("private diagnostics", output.getvalue())

        output = io.StringIO()
        runner = mock.Mock(
            return_value=subprocess.CompletedProcess(("docker",), 1, b"payload", b"secret")
        )
        with mock.patch.dict(os.environ, {"RUN_DOCKER_SANDBOX_TESTS": "1"}):
            self.assertEqual(exp1529.run_once(runner=runner, output=output), 11)
        self.assertEqual(output.getvalue(), "IMAGE_SAVE_FAILED\n")

    def test_exp1530_direct_entrypoint_reaches_opt_in_guard_without_docker(self):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" / "export_verify_portable_image_exp1529.py"),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(result.stdout, "OPT_IN_REQUIRED\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
