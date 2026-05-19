"""Tests for tools/github_repo.py — Git Data API commit client."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools import github_repo  # noqa: E402


def _resp(status: int, body=None):
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=body or {})
    r.text = "" if body is None else str(body)
    return r


class GitBlobShaTests(unittest.TestCase):
    def test_known_sha_for_empty_blob(self):
        # `git hash-object --stdin < /dev/null` → e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
        self.assertEqual(
            github_repo.git_blob_sha(b""),
            "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        )

    def test_known_sha_for_hello_world(self):
        # `printf "hello\n" | git hash-object --stdin` → ce013625030ba8dba906f756967f9e9ca394464a
        self.assertEqual(
            github_repo.git_blob_sha(b"hello\n"),
            "ce013625030ba8dba906f756967f9e9ca394464a",
        )


class PutTreeTests(unittest.TestCase):
    def setUp(self):
        self._token_was = os.environ.get("GITHUB_PAT_TOKEN")
        self._repo_was = os.environ.get("GITHUB_REPO_NWO")
        os.environ["GITHUB_PAT_TOKEN"] = "github_pat_test"
        os.environ["GITHUB_REPO_NWO"] = "test-owner/test-repo"

    def tearDown(self):
        for k, v in (
            ("GITHUB_PAT_TOKEN", self._token_was),
            ("GITHUB_REPO_NWO", self._repo_was),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_missing_token_raises(self):
        os.environ.pop("GITHUB_PAT_TOKEN", None)
        with self.assertRaises(github_repo.MissingTokenError):
            github_repo.put_tree([("foo.md", b"hi")], "msg")

    def test_first_write_full_sequence(self):
        """Initial commit path: ref → commit → tree → blobs → tree → commit → ref PATCH."""
        gets = {
            "/git/ref/heads/main": {"object": {"sha": "old-commit"}},
            "/git/commits/old-commit": {"tree": {"sha": "old-tree"}},
            "/git/trees/old-tree": {"tree": [], "truncated": False},
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            key = url.replace("https://api.github.com/repos/test-owner/test-repo", "")
            return _resp(200, gets[key])

        posts = []

        def fake_post(url, headers=None, json=None, timeout=None):
            posts.append((url, json))
            if "/git/blobs" in url:
                return _resp(201, {"sha": "blob-" + str(len(posts))})
            if "/git/trees" in url:
                return _resp(201, {"sha": "new-tree"})
            if "/git/commits" in url:
                return _resp(201, {"sha": "new-commit"})
            raise AssertionError(f"unexpected POST {url}")

        patches = []

        def fake_patch(url, headers=None, json=None, timeout=None):
            patches.append((url, json))
            return _resp(200, {"object": {"sha": "new-commit"}})

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = fake_post
            fake_requests.patch.side_effect = fake_patch
            sha = github_repo.put_tree(
                [("a.md", b"alpha"), ("b.md", b"beta")],
                "test commit",
            )

        self.assertEqual(sha, "new-commit")
        # Two blobs + one tree + one commit.
        self.assertEqual(len(posts), 4)
        # Exactly one ref update.
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0][1]["sha"], "new-commit")

    def test_noop_when_all_files_match_existing_tree(self):
        """If every file's git blob SHA matches the existing tree entry,
        no blobs/trees/commits/refs are created."""
        alpha_sha = github_repo.git_blob_sha(b"alpha")
        beta_sha = github_repo.git_blob_sha(b"beta")

        gets = {
            "/git/ref/heads/main": {"object": {"sha": "head-commit"}},
            "/git/commits/head-commit": {"tree": {"sha": "head-tree"}},
            "/git/trees/head-tree": {
                "tree": [
                    {"path": "a.md", "type": "blob", "sha": alpha_sha},
                    {"path": "b.md", "type": "blob", "sha": beta_sha},
                ],
                "truncated": False,
            },
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            key = url.replace("https://api.github.com/repos/test-owner/test-repo", "")
            return _resp(200, gets[key])

        post_calls = []
        patch_calls = []

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = lambda *a, **k: post_calls.append(a) or AssertionError("no POST expected")
            fake_requests.patch.side_effect = lambda *a, **k: patch_calls.append(a) or AssertionError("no PATCH expected")
            sha = github_repo.put_tree(
                [("a.md", b"alpha"), ("b.md", b"beta")],
                "should be a no-op",
            )

        self.assertEqual(sha, "head-commit")
        self.assertEqual(post_calls, [])
        self.assertEqual(patch_calls, [])

    def test_partial_change_only_uploads_changed_blob(self):
        """If one file matches and one differs, we upload one blob only."""
        alpha_sha = github_repo.git_blob_sha(b"alpha")

        gets = {
            "/git/ref/heads/main": {"object": {"sha": "head-commit"}},
            "/git/commits/head-commit": {"tree": {"sha": "head-tree"}},
            "/git/trees/head-tree": {
                "tree": [
                    {"path": "a.md", "type": "blob", "sha": alpha_sha},
                    {"path": "b.md", "type": "blob", "sha": "stale-beta-sha"},
                ],
                "truncated": False,
            },
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            key = url.replace("https://api.github.com/repos/test-owner/test-repo", "")
            return _resp(200, gets[key])

        posts = []

        def fake_post(url, headers=None, json=None, timeout=None):
            posts.append((url, json))
            if "/git/blobs" in url:
                return _resp(201, {"sha": "fresh-beta-blob"})
            if "/git/trees" in url:
                return _resp(201, {"sha": "new-tree"})
            if "/git/commits" in url:
                return _resp(201, {"sha": "new-commit"})
            raise AssertionError(url)

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = fake_post
            fake_requests.patch.side_effect = lambda *a, **k: _resp(
                200, {"object": {"sha": "new-commit"}}
            )
            github_repo.put_tree(
                [("a.md", b"alpha"), ("b.md", b"beta-changed")],
                "partial",
            )

        # Exactly one blob POST (for b.md only), plus the tree + commit.
        blob_posts = [p for p in posts if "/git/blobs" in p[0]]
        tree_posts = [p for p in posts if "/git/trees" in p[0]]
        self.assertEqual(len(blob_posts), 1)
        self.assertEqual(len(tree_posts), 1)
        # The tree's single entry is b.md, pointing at the freshly POSTed blob.
        tree_entries = tree_posts[0][1]["tree"]
        self.assertEqual(len(tree_entries), 1)
        self.assertEqual(tree_entries[0]["path"], "b.md")
        self.assertEqual(tree_entries[0]["sha"], "fresh-beta-blob")

    def test_422_retry_then_succeeds(self):
        """Ref update 422 once → refetch ref → retry → 200."""
        ref_seq = iter(
            [
                {"object": {"sha": "head-1"}},  # first attempt
                {"object": {"sha": "head-2"}},  # second attempt (after losing race)
            ]
        )
        commit_seq = iter(
            [
                {"tree": {"sha": "tree-1"}},
                {"tree": {"sha": "tree-2"}},
            ]
        )

        def fake_get(url, headers=None, params=None, timeout=None):
            if "/git/ref/heads/" in url:
                return _resp(200, next(ref_seq))
            if "/git/commits/" in url:
                return _resp(200, next(commit_seq))
            if "/git/trees/" in url:
                return _resp(200, {"tree": [], "truncated": False})
            raise AssertionError(url)

        def fake_post(url, headers=None, json=None, timeout=None):
            if "/git/blobs" in url:
                return _resp(201, {"sha": "blob-x"})
            if "/git/trees" in url:
                return _resp(201, {"sha": "new-tree"})
            if "/git/commits" in url:
                return _resp(201, {"sha": "new-commit"})
            raise AssertionError(url)

        patch_responses = iter(
            [
                _resp(422, "ref out of date"),
                _resp(200, {"object": {"sha": "new-commit"}}),
            ]
        )

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = fake_post
            fake_requests.patch.side_effect = lambda *a, **k: next(patch_responses)
            sha = github_repo.put_tree([("a.md", b"alpha")], "msg")

        self.assertEqual(sha, "new-commit")

    def test_422_twice_raises_conflict(self):
        """Two consecutive 422s give up — RefUpdateConflict."""
        def fake_get(url, headers=None, params=None, timeout=None):
            if "/git/ref/heads/" in url:
                return _resp(200, {"object": {"sha": "head"}})
            if "/git/commits/" in url:
                return _resp(200, {"tree": {"sha": "tree"}})
            if "/git/trees/" in url:
                return _resp(200, {"tree": [], "truncated": False})
            raise AssertionError(url)

        def fake_post(url, headers=None, json=None, timeout=None):
            if "/git/blobs" in url:
                return _resp(201, {"sha": "blob"})
            if "/git/trees" in url:
                return _resp(201, {"sha": "tree2"})
            if "/git/commits" in url:
                return _resp(201, {"sha": "commit2"})
            raise AssertionError(url)

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = fake_post
            fake_requests.patch.side_effect = lambda *a, **k: _resp(422, "no")
            with self.assertRaises(github_repo.RefUpdateConflict):
                github_repo.put_tree([("a.md", b"alpha")], "msg")

    def test_truncated_tree_forces_full_upload(self):
        """If GitHub truncates the tree response we can't prove no-op safely —
        treat as if no files match and re-upload everything."""
        alpha_sha = github_repo.git_blob_sha(b"alpha")

        gets = {
            "/git/ref/heads/main": {"object": {"sha": "head"}},
            "/git/commits/head": {"tree": {"sha": "tree"}},
            "/git/trees/tree": {
                "tree": [{"path": "a.md", "type": "blob", "sha": alpha_sha}],
                "truncated": True,
            },
        }

        def fake_get(url, headers=None, params=None, timeout=None):
            key = url.replace("https://api.github.com/repos/test-owner/test-repo", "")
            return _resp(200, gets[key])

        posts = []

        def fake_post(url, headers=None, json=None, timeout=None):
            posts.append((url, json))
            if "/git/blobs" in url:
                return _resp(201, {"sha": "blob"})
            if "/git/trees" in url:
                return _resp(201, {"sha": "tree2"})
            if "/git/commits" in url:
                return _resp(201, {"sha": "commit2"})
            raise AssertionError(url)

        with patch.object(github_repo, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            fake_requests.post.side_effect = fake_post
            fake_requests.patch.side_effect = lambda *a, **k: _resp(
                200, {"object": {"sha": "commit2"}}
            )
            sha = github_repo.put_tree([("a.md", b"alpha")], "msg")

        self.assertEqual(sha, "commit2")
        # Even though the content matches, the truncated tree forced an upload.
        self.assertTrue(any("/git/blobs" in p[0] for p in posts))


if __name__ == "__main__":
    unittest.main()
