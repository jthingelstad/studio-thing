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


def _post(
    blog_dir: Path,
    *,
    mid: int,
    date: str,
    slug: str,
    title: str,
    body: str,
    kind: str = "post",
    categories: str = "[]",
) -> None:
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
            _post(
                blog,
                mid=111,
                date="2018-04-02",
                slug="on-systems-thinking",
                title="On Systems Thinking",
                body="Systems thinking is a discipline for seeing wholes.",
            )
            _post(
                blog,
                mid=222,
                date="2026-05-25",
                slug="quick-note",
                title="",
                kind="micropost",
                body="A quick thought about RSS feeds.",
            )
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
        self.assertEqual(
            post["url"], "https://www.thingelstad.com/2018/04/02/on-systems-thinking.html"
        )

        micro = by_prefix["blog:222:0"]
        self.assertEqual(micro["section"], "Micropost")
        # Untitled micropost gets a derived label from its text.
        self.assertTrue(micro["subject"])
        self.assertIn("RSS", micro["subject"])

    def test_blog_links_and_domains_are_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(
                blog,
                mid=222,
                date="2026-05-24",
                slug="note",
                title="My Note",
                body="This is the target post.",
            )
            _post(
                blog,
                mid=111,
                date="2026-05-25",
                slug="links",
                title="Links",
                body=(
                    "I liked [Example](https://example.com/story) and "
                    "[my own note](https://micro.thingelstad.com/2026/05/24/note.html).\n\n"
                    '<a href="https://sub.example.org/page">Sub Example</a>\n\n'
                    "![Photo](https://images.example.net/photo.jpg)"
                ),
            )
            archive = Path(tmp) / "archive"
            archive.mkdir()
            result = build_blog_corpus(blog_dir=blog, archive_dir=archive)

        self.assertEqual(result["link_count"], 3)
        self.assertEqual(
            [link["domain"] for link in result["links"]],
            [
                "example.com",
                "micro.thingelstad.com",
                "sub.example.org",
            ],
        )
        source_post = next(post for post in result["posts"] if post["microblog_id"] == 111)
        source_chunk = next(
            chunk for chunk in result["chunks"] if chunk["id"].startswith("blog:111:")
        )
        self.assertEqual(source_post["domains"], ["example.com", "sub.example.org"])
        self.assertEqual(source_chunk["domains"], ["example.com", "sub.example.org"])
        self.assertEqual(result["links"][0]["source_kind"], "blog")
        self.assertEqual(result["links"][0]["microblog_id"], 111)
        self.assertEqual(
            result["links"][0]["post_url"], "https://www.thingelstad.com/2026/05/25/links.html"
        )
        self.assertEqual(result["links"][0]["text"], "Example")
        self.assertEqual(result["links"][0]["link_kind"], "external")
        self.assertEqual(result["links"][0]["link_category"], "external")
        self.assertFalse(result["links"][0]["target_resolved"])
        internal = result["links"][1]
        self.assertEqual(internal["link_kind"], "internal")
        self.assertEqual(internal["link_category"], "resolved_post")
        self.assertTrue(internal["target_resolved"])
        self.assertEqual(internal["target_source_kind"], "blog")
        self.assertEqual(internal["target_blog_path"], "2026/05/24/note")
        self.assertEqual(internal["target_microblog_id"], 222)
        self.assertEqual(
            internal["target_post_url"], "https://www.thingelstad.com/2026/05/24/note.html"
        )
        self.assertNotIn("images.example.net", {link["domain"] for link in result["links"]})

    def test_blog_link_categories_flag_internal_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(
                blog,
                mid=111,
                date="2011-04-12",
                slug="awesome-new-community",
                title="Old link shapes",
                body=(
                    "[Collection](https://www.thingelstad.com/collections/texas-hellweek-2001/) "
                    "[Upload](https://www.thingelstad.com/uploads/2026/photo.jpg) "
                    "[Malformed](http://micro.thingelstad.com/2011/04/12/www.cornertablerestaurant.com/csk.php)"
                ),
            )
            archive = Path(tmp) / "archive"
            archive.mkdir()
            result = build_blog_corpus(blog_dir=blog, archive_dir=archive)

        by_text = {link["text"]: link for link in result["links"]}
        self.assertEqual(by_text["Collection"]["link_category"], "collection_page")
        self.assertEqual(by_text["Upload"]["link_category"], "upload_asset")
        self.assertEqual(by_text["Malformed"]["link_category"], "malformed_internal")
        self.assertFalse(by_text["Malformed"]["target_resolved"])

    def test_blog_cross_source_links_are_not_external_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(
                blog,
                mid=111,
                date="2026-05-25",
                slug="cross-source",
                title="Cross Source",
                body=(
                    "[Weekly Thing](https://weekly.thingelstad.com/archive/350/) "
                    "[Another Thing](https://another.thingelstad.com/2025/10/05/how-do-you-start-a.html) "
                    "[Blog home](https://thingelstad.com/) "
                    "[Micro home](https://micro.thingelstad.com/) "
                    "[Photos](https://photos.thingelstad.com/album/)"
                ),
            )
            archive = Path(tmp) / "archive"
            archive.mkdir()
            result = build_blog_corpus(blog_dir=blog, archive_dir=archive)

        by_text = {link["text"]: link for link in result["links"]}
        self.assertEqual(by_text["Weekly Thing"]["link_kind"], "internal")
        self.assertEqual(by_text["Weekly Thing"]["link_category"], "cross_source")
        self.assertEqual(by_text["Weekly Thing"]["target_source_kind"], "weekly_thing")
        self.assertEqual(by_text["Another Thing"]["link_kind"], "internal")
        self.assertEqual(by_text["Another Thing"]["link_category"], "cross_source")
        self.assertEqual(by_text["Another Thing"]["target_source_kind"], "podcast")
        self.assertEqual(by_text["Blog home"]["link_kind"], "internal")
        self.assertNotEqual(by_text["Blog home"]["link_category"], "cross_source")
        self.assertEqual(by_text["Micro home"]["link_kind"], "internal")
        self.assertEqual(by_text["Micro home"]["link_category"], "internal_unresolved")
        self.assertNotIn("target_source_kind", by_text["Micro home"])
        self.assertEqual(by_text["Photos"]["link_kind"], "internal")
        self.assertEqual(by_text["Photos"]["link_category"], "internal_site")
        self.assertEqual(by_text["Photos"]["target_source_kind"], "site")
        source_post = next(post for post in result["posts"] if post["microblog_id"] == 111)
        self.assertEqual(source_post["domains"], [])

    def test_also_in_issues_cross_reference(self):
        # An issue Journal links the blog post inline (not via curated
        # links[]) — the matching blog chunk should carry also_in_issues.
        with tempfile.TemporaryDirectory() as tmp:
            blog = Path(tmp) / "posts"
            _post(
                blog,
                mid=111,
                date="2026-05-23",
                slug="a-pattern-ive-adopted",
                title="A Pattern I've Adopted",
                body="Here is a workflow pattern I have been using lately.",
            )
            _post(
                blog,
                mid=999,
                date="2026-05-24",
                slug="unreferenced",
                title="Unreferenced",
                body="Nobody links to this one.",
            )
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
            _post(
                blog,
                mid=111,
                date="2026-05-25",
                slug="photo",
                title="",
                kind="micropost",
                body='Look up.\n\n<img src="https://www.thingelstad.com/uploads/x.jpg" '
                'width="600" alt="A hawk circling above a field.">',
            )
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
            _post(
                blog,
                mid=111,
                date="2026-05-25",
                slug="leak",
                title="Leak",
                body="We now have subscriber_count readers.",
            )
            archive = Path(tmp) / "archive"
            archive.mkdir()
            with self.assertRaisesRegex(RuntimeError, "Privacy denylist"):
                build_blog_corpus(blog_dir=blog, archive_dir=archive)


if __name__ == "__main__":
    unittest.main()
