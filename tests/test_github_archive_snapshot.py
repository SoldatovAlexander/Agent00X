from __future__ import annotations

import hashlib
import io
import ssl
from pathlib import Path
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.github_archive_snapshot import (
    GitHubArchiveSnapshotError,
    GitHubArchiveSnapshotRequest,
    GitHubCodeloadArchiveTransport,
    parse_github_archive_snapshot,
    read_github_archive_snapshot_contents,
)
from app_contracts.github_snapshot import (
    GitHubBlobClaim,
    GitHubSnapshotContents,
    GitHubSnapshotError,
    GitHubSnapshotRequest,
    _snapshot_content_digest,
)
from app_contracts.pinned_snapshot import MAX_SNAPSHOT_FILE_BYTES
from tests.test_github_snapshot import complete_tree_listing, git_tree_oid


OWNER = "octo-org"
REPOSITORY = "hello-world"
COMMIT = "a" * 40
ARCHIVE_ROOT = "hello-world-aaaaaaaa"


def _tree_oid(files: tuple[tuple[str, str, bytes], ...]) -> str:
    blob_entries = [
        {
            "path": path,
            "mode": mode,
            "type": "blob",
            "sha": hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content
            ).hexdigest(),
        }
        for path, mode, content in files
    ]
    return complete_tree_listing(blob_entries)[1]


def _request(files: tuple[tuple[str, str, bytes], ...]) -> GitHubArchiveSnapshotRequest:
    return GitHubArchiveSnapshotRequest(
        owner=OWNER,
        repository=REPOSITORY,
        commit_oid=COMMIT,
        tree_oid=_tree_oid(files),
        content_digest=_snapshot_content_digest(list(files)),
        file_count=len(files),
    )


def _archive(
    files: tuple[tuple[str, str, bytes], ...],
    *,
    extra_members: tuple[tarfile.TarInfo, ...] = (),
    tar_mode_overrides: dict[str, int] | None = None,
) -> bytes:
    output = io.BytesIO()
    directories = {
        "/".join(path.split("/")[:index])
        for path, _, _ in files
        for index in range(1, len(path.split("/")))
    }
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        root = tarfile.TarInfo(ARCHIVE_ROOT + "/")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        archive.addfile(root)
        for directory in sorted(directories):
            info = tarfile.TarInfo(ARCHIVE_ROOT + "/" + directory + "/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)
        for path, mode, content in files:
            info = tarfile.TarInfo(ARCHIVE_ROOT + "/" + path)
            info.type = tarfile.REGTYPE
            info.mode = (tar_mode_overrides or {}).get(path, int(mode[-3:], 8))
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for member in extra_members:
            archive.addfile(
                member,
                io.BytesIO(b"x" * member.size) if member.isfile() and member.size else None,
            )
    return output.getvalue()


def _files() -> tuple[tuple[str, str, bytes], ...]:
    return (
        ("README.md", "100644", b"archive fixture\n"),
        ("backend/routes.py", "100755", b"def route():\n    return 200\n"),
    )


class _Transport:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, owner: str, repository: str, commit_oid: str) -> bytes:
        self.calls.append((owner, repository, commit_oid))
        return self.body


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.read_limit: int | None = None
        self.closed = False

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        return self.body[:limit]

    def close(self) -> None:
        self.closed = True


class _Connection:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request_args: tuple | None = None
        self.closed = False

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.request_args = (method, path, headers)

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


class ArchiveSnapshotParserTests(unittest.TestCase):
    def test_exact_archive_content_tree_and_blob_ids_are_bound_with_archive_origin(self):
        files = _files()
        request = _request(files)
        transport = _Transport(_archive(files))
        snapshot = read_github_archive_snapshot_contents(request, transport)
        self.assertEqual(transport.calls, [(OWNER, REPOSITORY, COMMIT)])
        self.assertEqual(snapshot.claim.evidence_origin, "github_codeload_archive")
        self.assertEqual(snapshot.claim.tree_oid, request.tree_oid)
        self.assertEqual(snapshot.claim.content_digest, request.content_digest)
        self.assertIsNone(snapshot.verified_commit_object)
        self.assertTrue(
            all(blob.evidence_origin == "github_codeload_archive" for blob in snapshot.files)
        )
        self.assertEqual([blob.path for blob in snapshot.files], ["README.md", "backend/routes.py"])

    def test_posix_permissions_map_to_git_executable_bit_and_special_bits_reject(self):
        files = _files()
        request = _request(files)
        snapshot = parse_github_archive_snapshot(
            request,
            _archive(
                files,
                tar_mode_overrides={"README.md": 0o664, "backend/routes.py": 0o775},
            ),
        )
        self.assertEqual(
            [(blob.path, blob.mode) for blob in snapshot.files],
            [("README.md", "100644"), ("backend/routes.py", "100755")],
        )

        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "file mode is invalid"):
            parse_github_archive_snapshot(
                request,
                _archive(files, tar_mode_overrides={"README.md": 0o4644}),
            )

    def test_archive_origin_cannot_be_mislabeled_or_mixed_with_rest_blob_claims(self):
        files = _files()
        request = _request(files)
        archive = parse_github_archive_snapshot(request, _archive(files))
        rest_blob = GitHubBlobClaim(
            path=archive.files[0].path,
            mode=archive.files[0].mode,
            sha=archive.files[0].sha,
            size=archive.files[0].size,
            content=archive.files[0].content,
            content_digest=archive.files[0].content_digest,
        )
        with self.assertRaises(GitHubSnapshotError):
            GitHubSnapshotContents(claim=archive.claim, files=(rest_blob,))
        with self.assertRaises(GitHubSnapshotError):
            GitHubSnapshotRequest(
                owner=OWNER,
                repository=REPOSITORY,
                commit_oid=COMMIT,
                evidence_origin="github_codeload_archive",
            )

    def test_wrong_content_digest_and_wrong_tree_oid_fail_closed(self):
        files = _files()
        request = _request(files)
        wrong_digest = GitHubArchiveSnapshotRequest(
            OWNER,
            REPOSITORY,
            COMMIT,
            request.tree_oid,
            "sha256:" + "0" * 64,
            len(files),
        )
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "content digest mismatch"):
            parse_github_archive_snapshot(wrong_digest, _archive(files))
        wrong_tree = GitHubArchiveSnapshotRequest(
            OWNER,
            REPOSITORY,
            COMMIT,
            "b" * 40,
            request.content_digest,
            len(files),
        )
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "tree OID mismatch"):
            parse_github_archive_snapshot(wrong_tree, _archive(files))

    def test_malformed_multiple_root_traversal_absolute_duplicate_and_empty_dirs_reject(self):
        files = _files()
        request = _request(files)
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "archive is invalid"):
            parse_github_archive_snapshot(request, b"not a tar archive")

        second_root = tarfile.TarInfo("other-root/evil.txt")
        second_root.type = tarfile.REGTYPE
        second_root.size = 1
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "file limit exceeded"):
            parse_github_archive_snapshot(request, _archive(files, extra_members=(second_root,)))

        for unsafe in ("../escape", "nested/../../escape"):
            bad_files = ((unsafe, "100644", b"x"),)
            bad_request = _request(bad_files)
            with self.subTest(path=unsafe):
                with self.assertRaisesRegex(GitHubArchiveSnapshotError, "member path is invalid"):
                    parse_github_archive_snapshot(bad_request, _archive(bad_files))

        absolute = tarfile.TarInfo("/absolute")
        absolute.type = tarfile.REGTYPE
        absolute.size = 1
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "member path is invalid"):
            parse_github_archive_snapshot(request, _archive(files, extra_members=(absolute,)))

        duplicate = tarfile.TarInfo(ARCHIVE_ROOT + "/README.md")
        duplicate.type = tarfile.REGTYPE
        duplicate.size = 1
        duplicate.mode = 0o644
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "duplicate member"):
            parse_github_archive_snapshot(request, _archive(files, extra_members=(duplicate,)))

        empty_dir_files = files
        empty_dir = tarfile.TarInfo(ARCHIVE_ROOT + "/empty/")
        empty_dir.type = tarfile.DIRTYPE
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "directory structure mismatch"):
            parse_github_archive_snapshot(
                _request(empty_dir_files), _archive(empty_dir_files, extra_members=(empty_dir,))
            )

    def test_symlink_hardlink_special_and_out_of_limit_files_reject(self):
        files = _files()
        request = _request(files)
        for member_type in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            info = tarfile.TarInfo(ARCHIVE_ROOT + "/backend/unsafe")
            info.type = member_type
            info.linkname = "README.md"
            with self.subTest(member_type=member_type):
                with self.assertRaisesRegex(GitHubArchiveSnapshotError, "member type is invalid"):
                    parse_github_archive_snapshot(request, _archive(files, extra_members=(info,)))

        too_large = (("large.bin", "100644", b"x" * (MAX_SNAPSHOT_FILE_BYTES + 1)),)
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "file limit exceeded"):
            parse_github_archive_snapshot(_request(too_large), _archive(too_large))

    def test_wrong_file_count_and_total_size_reject(self):
        files = _files()
        request = _request(files)
        wrong_count = GitHubArchiveSnapshotRequest(
            OWNER, REPOSITORY, COMMIT, request.tree_oid, request.content_digest, 1
        )
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "file limit exceeded"):
            parse_github_archive_snapshot(wrong_count, _archive(files))


class ArchiveTransportTests(unittest.TestCase):
    def test_transport_uses_one_fixed_tls_get_and_bounds_response(self):
        response = _Response(200, b"archive-bytes")
        connection = _Connection(response)
        factory_calls: list[tuple[str, float, ssl.SSLContext]] = []

        def factory(host: str, *, timeout: float, context: ssl.SSLContext) -> _Connection:
            factory_calls.append((host, timeout, context))
            return connection

        transport = GitHubCodeloadArchiveTransport(
            timeout_seconds=12,
            connection_factory=factory,
        )
        self.assertEqual(transport(OWNER, REPOSITORY, COMMIT), b"archive-bytes")
        self.assertEqual(factory_calls[0][0:2], ("codeload.github.com", 12.0))
        self.assertTrue(factory_calls[0][2].check_hostname)
        self.assertEqual(factory_calls[0][2].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(
            connection.request_args[0:2],
            ("GET", f"/{OWNER}/{REPOSITORY}/legacy.tar.gz/{COMMIT}"),
        )
        self.assertNotIn("Authorization", connection.request_args[2])
        self.assertEqual(response.read_limit, 16 * 1024 * 1024 + 1)
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "already used"):
            transport(OWNER, REPOSITORY, COMMIT)
        self.assertEqual(len(factory_calls), 1)

    def test_redirect_status_is_not_followed_and_response_size_is_bounded(self):
        response = _Response(302, b"redirect")
        connection = _Connection(response)
        transport = GitHubCodeloadArchiveTransport(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        with self.assertRaises(GitHubArchiveSnapshotError) as caught:
            transport(OWNER, REPOSITORY, COMMIT)
        self.assertEqual(caught.exception.http_status, 302)
        self.assertIsNone(response.read_limit)

        oversized = _Response(200, b"x" * (16 * 1024 * 1024 + 1))
        oversized_connection = _Connection(oversized)
        oversized_transport = GitHubCodeloadArchiveTransport(
            connection_factory=lambda *_args, **_kwargs: oversized_connection
        )
        with self.assertRaisesRegex(GitHubArchiveSnapshotError, "response exceeds limit"):
            oversized_transport(OWNER, REPOSITORY, COMMIT)


if __name__ == "__main__":
    unittest.main()
