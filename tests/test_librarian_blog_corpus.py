"""Tests for build_blog_corpus — the thingelstad.com blog corpus (separate
from the Weekly Thing issue corpus). Mirrors test_librarian_corpus.py's
site_page/faq chunk tests."""

import tempfile
import unittest
from pathlib import Path

from librarian_core.corpus import (
    build_blog_corpus,
    journal_blog_xref,
)


def _post(blog_dir: Path, *, mid: int, date: str, slug: str, title: str,
          body: str, kind: str = "post", categories: str = "[]") -> None:
    y, m, _ = date.split("-")
    path = blog_dir / y / m / f"{date}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"microblog_id: {mid}\n"
        f'url: "https://www.thingelstad.com/{y}/{m}/{date.split("-")[2]}/{slug}.html"\n'
        f'title: "{title}"\n'
        f'published: "{date}T12:00:00+00:00"\n'
        f"post_kind: {kind}\n"
        f"categories: {categories}\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


class BuildBlogCorpusTests(unittest.TestCase):
    def test_blog_chunks_shape_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(blog, mid=111, date="2018-04-02", slug="on-systems-thinking",
                  title="On Systems Thinking",
                  body="Systems thinking is a discipline for seeing wholes.")
            _post(blog, mid=222, date="2026-05-25", slug="quick-note",
                  title="", kind="micropost",
                  body="A quick thought about RSS feeds.")
            archive = Path(tmp) / "archive"
            archive.mkdir()
            corpus = build_blog_corpus(blog_dir=blog, archive_dir=archive)

        self.assertEqual(corpus["version"], 2)
        self.assertEqual(corpus["issues"], [])
        self.assertEqual(corpus["topics"], [])
        self.assertEqual(corpus["links"], [])
        self.assertEqual(corpus["post_count"], 2)
        self.assertGreaterEqual(corpus["chunk_count"], 2)

        # Chunk ids are content-deterministic: `blog:{mbid}:{index}:{hash}`.
        by_prefix = {c["id"].rsplit(":", 1)[0]: c for c in corpus["chunks"]}
        self.assertIn("blog:111:0", by_prefix)
        self.assertIn("blog:222:0", by_prefix)
        # The content-hash suffix makes the id change when the body changes.
        self.assertRegex(by_prefix["blog:111:0"]["id"], r"^blog:111:0:[0-9a-f]{16}$")

        post = by_prefix["blog:111:0"]
        self.assertEqual(post["source_kind"], "blog")
        self.assertEqual(post["content_kind"], "blog")
        self.assertEqual(post["section"], "Blog post")
        self.assertEqual(post["subject"], "On Systems Thinking")
        self.assertIsNone(post["issue_number"])
        self.assertEqual(post["publish_date"], "2018-04-02")
        self.assertEqual(post["issue_year"], 2018)
        self.assertEqual(post["url"], "https://www.thingelstad.com/2018/04/02/on-systems-thinking.html")

        micro = by_prefix["blog:222:0"]
        self.assertEqual(micro["section"], "Micropost")
        # Untitled micropost gets a derived label from its text.
        self.assertTrue(micro["subject"])
        self.assertIn("RSS", micro["subject"])

    def test_also_in_issues_cross_reference(self):
        # An issue Journal links the blog post inline (not via curated
        # links[]) — the matching blog chunk should carry also_in_issues.
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(blog, mid=111, date="2026-05-23", slug="a-pattern-ive-adopted",
                  title="A Pattern I've Adopted",
                  body="Here is a workflow pattern I have been using lately.")
            _post(blog, mid=999, date="2026-05-24", slug="unreferenced",
                  title="Unreferenced", body="Nobody links to this one.")
            archive = Path(tmp) / "archive"
            (archive / "350").mkdir(parents=True)
            (archive / "350" / "archive.md").write_text(
                "---\nnumber: 350\nsubject: WT350\npublish_date: 2026-05-25T12:00:00Z\n---\n"
                "## Journal\n\n"
                "[8:50 AM](https://www.thingelstad.com/2026/05/23/a-pattern-ive-adopted.html) — a note.\n",
                encoding="utf-8",
            )
            corpus = build_blog_corpus(blog_dir=blog, archive_dir=archive)

        by_prefix = {c["id"].rsplit(":", 1)[0]: c for c in corpus["chunks"]}
        self.assertEqual(by_prefix["blog:111:0"].get("also_in_issues"), [350])
        self.assertNotIn("also_in_issues", by_prefix["blog:999:0"])

    def test_journal_xref_normalizes_host_and_html_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive"
            (archive / "42").mkdir(parents=True)
            # legacy micro.thingelstad.com host + .html suffix should
            # normalize to the same key as a www.thingelstad.com permalink.
            (archive / "42" / "archive.md").write_text(
                "---\nnumber: 42\nsubject: WT42\npublish_date: 2019-01-01T12:00:00Z\n---\n"
                "See [this](https://micro.thingelstad.com/2011/03/16/tilt-shift-lens.html).\n",
                encoding="utf-8",
            )
            xref = journal_blog_xref(archive_dir=archive)
        self.assertEqual(xref.get("2011/03/16/tilt-shift-lens"), [42])

    def test_img_alt_inlined_and_tags_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(blog, mid=111, date="2026-05-25", slug="photo", title="",
                  kind="micropost",
                  body='Look up.\n\n<img src="https://www.thingelstad.com/uploads/x.jpg" '
                       'width="600" alt="A hawk circling above a field.">')
            archive = Path(tmp) / "archive"
            archive.mkdir()
            corpus = build_blog_corpus(blog_dir=blog, archive_dir=archive)
        text = corpus["chunks"][0]["text"]
        self.assertIn("Look up.", text)
        self.assertIn("A hawk circling above a field.", text)  # alt inlined
        self.assertNotIn("<img", text)  # raw tag stripped
        self.assertNotIn("uploads/x.jpg", text)  # src not in embed text

    def test_privacy_denylist_blocks_subscriber_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(blog, mid=111, date="2026-05-25", slug="leak", title="Leak",
                  body="We now have subscriber_count readers.")
            archive = Path(tmp) / "archive"
            archive.mkdir()
            with self.assertRaisesRegex(RuntimeError, "Privacy denylist"):
                build_blog_corpus(blog_dir=blog, archive_dir=archive)


if __name__ == "__main__":
    unittest.main()
