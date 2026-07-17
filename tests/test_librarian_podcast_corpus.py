"""Tests for Another Thing podcast import + corpus building."""

import json
import tempfile
import unittest
from pathlib import Path

from librarian_core.corpus import build_podcast_corpus

from pipeline.podcast.import_another_thing import import_episodes


def _episode(source_dir: Path, *, body: str, transcript: str) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "001-how-do-you-start-a-podcast.md").write_text(
        "---\n"
        "title: How do you start a podcast?\n"
        "number: 1\n"
        "slug: how-do-you-start-a\n"
        "date: 2025-10-05T18:48:44-05:00\n"
        "audio: /uploads/2025/another-thing-1.mp3\n"
        "transcript: 001-how-do-you-start-a-podcast.txt\n"
        "summary: Stepping into podcasting and trying my hand at something new.\n"
        "guid: https://another.thingelstad.com/2025/10/05/how-do-you-start-a.html\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    (source_dir / "001-how-do-you-start-a-podcast.txt").write_text(transcript, encoding="utf-8")


class PodcastCorpusTests(unittest.TestCase):
    def test_import_normalizes_another_thing_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "another" / "content" / "episodes"
            output = Path(tmp) / "studio" / "data" / "podcast"
            _episode(source, body="Show notes body.", transcript="Transcript body about starting a podcast.")

            written = import_episodes(source_dir=source, output_dir=output)
            record = json.loads(written[0].read_text(encoding="utf-8"))

        self.assertEqual(len(written), 1)
        self.assertEqual(record["show"], "Another Thing")
        self.assertEqual(record["source_kind"], "podcast")
        self.assertEqual(record["number"], 1)
        self.assertEqual(record["title"], "How do you start a podcast?")
        self.assertEqual(record["publish_date"], "2025-10-05")
        self.assertEqual(record["url"], "https://another.thingelstad.com/2025/10/05/how-do-you-start-a.html")
        self.assertEqual(record["transcript_url"], record["url"] + "#transcript")
        self.assertEqual(record["audio_url"], "https://another.thingelstad.com/uploads/2025/another-thing-1.mp3")
        self.assertIn("starting a podcast", record["transcript_text"])

    def test_build_podcast_corpus_shape_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "another" / "content" / "episodes"
            output = Path(tmp) / "studio" / "data" / "podcast"
            _episode(
                source,
                body=(
                    "These are [show notes](https://example.com/show) with [the podcast site](/about/), "
                    "[a blog post](https://thingelstad.com/2026/05/25/note.html), and "
                    "[a newsletter issue](https://weekly.thingelstad.com/archive/350/), plus "
                    "[photos](https://photos.thingelstad.com/album/)."
                ),
                transcript="Podcast transcripts make Thingy aware.",
            )
            import_episodes(source_dir=source, output_dir=output)

            corpus = build_podcast_corpus(output)

        self.assertEqual(corpus["version"], 2)
        self.assertEqual(corpus["issues"], [])
        self.assertEqual(corpus["topics"], [])
        self.assertEqual(corpus["episode_count"], 1)
        self.assertGreaterEqual(corpus["chunk_count"], 2)
        self.assertEqual(corpus["link_count"], 5)
        self.assertEqual(len(corpus["episodes"]), 1)
        episode = corpus["episodes"][0]
        self.assertEqual(episode["publish_date"], "2025-10-05")
        self.assertEqual(episode["issue_year"], 2025)
        self.assertEqual(episode["domains"], ["example.com"])
        self.assertEqual(episode["links"][0]["link_kind"], "external")
        self.assertEqual(episode["links"][0]["link_category"], "external")
        self.assertFalse(episode["links"][0]["target_resolved"])
        self.assertEqual(episode["links"][1]["link_kind"], "internal")
        self.assertEqual(episode["links"][1]["link_category"], "internal_site")
        self.assertEqual(episode["links"][1]["url"], "https://another.thingelstad.com/about/")
        self.assertEqual(episode["links"][2]["link_kind"], "internal")
        self.assertEqual(episode["links"][2]["link_category"], "cross_source")
        self.assertEqual(episode["links"][2]["target_source_kind"], "blog")
        self.assertEqual(episode["links"][3]["link_kind"], "internal")
        self.assertEqual(episode["links"][3]["link_category"], "cross_source")
        self.assertEqual(episode["links"][3]["target_source_kind"], "weekly_thing")
        self.assertEqual(episode["links"][4]["link_kind"], "internal")
        self.assertEqual(episode["links"][4]["link_category"], "internal_site")
        self.assertEqual(episode["links"][4]["target_source_kind"], "site")
        self.assertIn("body_hash", episode)

        chunks = {chunk["section"]: chunk for chunk in corpus["chunks"]}
        transcript = chunks["Transcript"]
        self.assertRegex(transcript["id"], r"^podcast:another-thing:001:transcript:0:[0-9a-f]{16}$")
        self.assertEqual(transcript["source_kind"], "podcast")
        self.assertEqual(transcript["content_kind"], "podcast_transcript")
        self.assertEqual(transcript["podcast"], "another-thing")
        self.assertEqual(transcript["show"], "Another Thing")
        self.assertEqual(transcript["episode_number"], 1)
        self.assertEqual(transcript["subject"], "How do you start a podcast?")
        self.assertIsNone(transcript["issue_number"])
        self.assertEqual(transcript["publish_date"], "2025-10-05")
        self.assertEqual(transcript["issue_year"], 2025)
        self.assertEqual(transcript["domains"], ["example.com"])
        self.assertIn("Thingy aware", transcript["text"])
        self.assertEqual(chunks["Show notes"]["content_kind"], "podcast_notes")


if __name__ == "__main__":
    unittest.main()
