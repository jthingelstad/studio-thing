"""Unit tests for ``tools.archive_lookup`` against a seeded temp DB.

Each test seeds a handful of ``issues`` + ``issue_links`` rows directly,
then asserts the helper returns the expected shape. Mirrors the
``DBTestCase`` pattern used elsewhere in the test suite.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tests._fixtures import DBTestCase  # noqa: E402
from apps.workshop_bot.tools import archive_lookup  # noqa: E402
from apps.workshop_bot.tools.db.connection import connect  # noqa: E402


def _seed_issue(
    conn,
    *,
    number,
    subject="",
    publish_date="2024-01-01",
    word_count=0,
    audio_url="",
    domains=None,
    links=None,
) -> None:
    """Insert one fully-formed ``issues`` row + optional ``issue_links``."""
    links = links or []
    notable = [lnk for lnk in links if lnk["section"] == "notable"]
    briefly = [lnk for lnk in links if lnk["section"] == "briefly"]
    domains = domains if domains is not None else sorted({lnk["domain"] for lnk in links})
    era = archive_lookup.derive_era(number)
    conn.execute(
        "INSERT INTO issues "
        "(number, subject, slug, description, publish_date, image, "
        " absolute_url, buttondown_id, word_count, notable_count, briefly_count, "
        " domain_count, link_count, audio_url, audio_duration_s, audio_byte_size, "
        " audio_voice, era) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            number,
            subject,
            f"wt-{number}",
            "desc",
            publish_date,
            "",
            f"https://example.test/wt-{number}",
            f"em_{number}",
            word_count,
            len(notable),
            len(briefly),
            len(domains),
            len(notable) + len(briefly),
            audio_url,
            1234 if audio_url else None,
            9999 if audio_url else None,
            "openai-tts-1-hd:echo" if audio_url else "",
            era,
        ),
    )
    for link in links:
        conn.execute(
            "INSERT INTO issue_links "
            "(issue_number, section, position, url, text, domain, heading_context) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                number,
                link["section"],
                link.get("position", 0),
                link["url"],
                link.get("text", ""),
                link["domain"],
                link.get("heading_context", ""),
            ),
        )


class GetIssueTests(DBTestCase):
    def test_get_issue_returns_full_row(self) -> None:
        with connect() as conn:
            _seed_issue(
                conn,
                number=200,
                subject="WT 200 / Test",
                publish_date="2022-04-30",
                word_count=1500,
                audio_url="https://files/wt-200.mp3",
            )
        row = archive_lookup.get_issue(200)
        self.assertIsNotNone(row)
        self.assertEqual(row["number"], 200)
        self.assertEqual(row["subject"], "WT 200 / Test")
        self.assertEqual(row["publish_date"], "2022-04-30")
        self.assertEqual(row["word_count"], 1500)
        self.assertEqual(row["audio_url"], "https://files/wt-200.mp3")
        self.assertEqual(row["audio_duration_s"], 1234)
        self.assertEqual(row["era"], "buttondown")

    def test_get_issue_missing_returns_none(self) -> None:
        self.assertIsNone(archive_lookup.get_issue(99999))


class DomainAndLinkTests(DBTestCase):
    def setUp(self) -> None:
        super().setUp()
        with connect() as conn:
            _seed_issue(
                conn,
                number=100,
                publish_date="2019-06-01",
                links=[
                    {
                        "section": "notable",
                        "position": 0,
                        "url": "https://daringfireball.net/x",
                        "domain": "daringfireball.net",
                        "text": "DF post",
                    },
                    {
                        "section": "briefly",
                        "position": 0,
                        "url": "https://example.com/a",
                        "domain": "example.com",
                        "text": "Ex",
                    },
                ],
            )
            _seed_issue(
                conn,
                number=200,
                publish_date="2022-04-30",
                links=[
                    {
                        "section": "notable",
                        "position": 0,
                        "url": "https://daringfireball.net/y",
                        "domain": "daringfireball.net",
                        "text": "DF post 2",
                    },
                ],
            )
            _seed_issue(
                conn,
                number=300,
                publish_date="2025-01-04",
                links=[
                    {
                        "section": "briefly",
                        "position": 0,
                        "url": "https://daringfireball.net/x",
                        "domain": "daringfireball.net",
                        "text": "DF re-share",
                    },
                ],
            )

    def test_find_by_domain_orders_newest_first(self) -> None:
        rows = archive_lookup.find_issues_by_domain("daringfireball.net")
        self.assertEqual([r["number"] for r in rows], [300, 200, 100])
        self.assertEqual(rows[0]["hit_count"], 1)

    def test_find_by_domain_unknown_returns_empty(self) -> None:
        self.assertEqual(archive_lookup.find_issues_by_domain("nope.example"), [])

    def test_link_history_exact_url(self) -> None:
        rows = archive_lookup.link_history("https://daringfireball.net/x")
        self.assertEqual([r["number"] for r in rows], [300, 100])
        # Section preserved
        sections = {r["number"]: r["section"] for r in rows}
        self.assertEqual(sections[100], "notable")
        self.assertEqual(sections[300], "briefly")

    def test_link_history_unknown_returns_empty(self) -> None:
        self.assertEqual(archive_lookup.link_history("https://nope.example/x"), [])

    def test_domain_history_aggregates(self) -> None:
        agg = archive_lookup.domain_history("daringfireball.net")
        self.assertEqual(agg["link_count"], 3)
        self.assertEqual(agg["issue_count"], 3)
        self.assertEqual(agg["first_issue"], 100)
        self.assertEqual(agg["last_issue"], 300)
        self.assertEqual(agg["first_date"], "2019-06-01")
        self.assertEqual(agg["last_date"], "2025-01-04")
        self.assertEqual(len(agg["recent"]), 3)
        self.assertEqual(agg["recent"][0]["number"], 300)

    def test_domain_history_unknown_returns_empty_dict(self) -> None:
        self.assertEqual(archive_lookup.domain_history("nope.example"), {})

    def test_list_issue_links_for_one_issue(self) -> None:
        rows = archive_lookup.list_issue_links(100)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["section"] for r in rows}, {"notable", "briefly"})

    def test_list_issue_links_section_filter(self) -> None:
        rows = archive_lookup.list_issue_links(100, section="notable")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://daringfireball.net/x")


class DateRangeTests(DBTestCase):
    def setUp(self) -> None:
        super().setUp()
        with connect() as conn:
            _seed_issue(conn, number=50, publish_date="2018-07-21")  # mailchimp
            _seed_issue(conn, number=180, publish_date="2020-12-19")  # buttondown
            _seed_issue(conn, number=290, publish_date="2024-03-15")
            _seed_issue(conn, number=300, publish_date="2024-06-01")

    def test_find_in_year(self) -> None:
        rows = archive_lookup.find_issues_in_year(2024)
        self.assertEqual([r["number"] for r in rows], [300, 290])

    def test_find_in_year_empty(self) -> None:
        self.assertEqual(archive_lookup.find_issues_in_year(2010), [])

    def test_find_in_range_inclusive(self) -> None:
        rows = archive_lookup.find_issues_in_range("2018-01-01", "2020-12-31")
        self.assertEqual({r["number"] for r in rows}, {50, 180})


class RecentAndStatsTests(DBTestCase):
    def setUp(self) -> None:
        super().setUp()
        with connect() as conn:
            for n in (10, 20, 30, 40, 50):
                _seed_issue(
                    conn,
                    number=n,
                    publish_date=f"2020-{n:02d}-01",
                    word_count=1000 + n,
                    audio_url=("https://x" if n >= 30 else ""),
                    links=[
                        {
                            "section": "notable",
                            "position": 0,
                            "url": f"http://e.test/{n}",
                            "domain": f"site-{n}.test",
                        }
                    ],
                )

    def test_recent_issues_orders_newest_first(self) -> None:
        rows = archive_lookup.recent_issues(3)
        self.assertEqual([r["number"] for r in rows], [50, 40, 30])

    def test_aggregate_stats(self) -> None:
        stats = archive_lookup.aggregate_stats()
        self.assertEqual(stats["total_issues"], 5)
        self.assertEqual(stats["total_links"], 5)
        self.assertEqual(stats["total_notable"], 5)
        self.assertEqual(stats["total_briefly"], 0)
        self.assertEqual(stats["total_words"], 5 * 1000 + (10 + 20 + 30 + 40 + 50))
        self.assertEqual(stats["unique_domains"], 5)
        self.assertEqual(stats["issues_with_audio"], 3)
        self.assertEqual(stats["audio_coverage_pct"], 60.0)
        self.assertEqual(stats["first_date"], "2020-10-01")
        self.assertEqual(stats["last_date"], "2020-50-01")


class EraTests(unittest.TestCase):
    def test_era_boundaries(self) -> None:
        self.assertEqual(archive_lookup.derive_era(1), "tinyletter")
        self.assertEqual(archive_lookup.derive_era(41), "tinyletter")
        self.assertEqual(archive_lookup.derive_era(42), "mailchimp")
        self.assertEqual(archive_lookup.derive_era(130), "mailchimp")
        self.assertEqual(archive_lookup.derive_era(131), "buttondown")
        self.assertEqual(archive_lookup.derive_era(349), "buttondown")


if __name__ == "__main__":
    unittest.main()
