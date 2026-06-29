"""Scout (producer) wiring tests.

Scope is intentionally narrow: the persona class is registered with the
right identity, it's first in ``TEAM_ORDER`` so it opens ``@Team``
rounds, its channel maps to ``DISCORD_CHANNEL_PRODUCTION``, the read-
only ``/scout status`` and ``/scout slate`` jobs return well-shaped
``JobResult`` payloads, and the slate-snapshot helper accepts the
multi-surface ``kind`` filter (forward-compatible with Phase 2's
``productions`` schema even though only newsletter has real data
today).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, scout_slate, scout_status  # noqa: E402
from apps.workshop_bot.personas import team  # noqa: E402
from apps.workshop_bot.personas.scout import ScoutBot  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ── persona class identity ───────────────────────────────────────────


class ScoutIdentityTests(unittest.TestCase):
    def test_class_attributes(self):
        self.assertEqual(ScoutBot.persona, "scout")
        self.assertEqual(ScoutBot.name, "Scout")
        self.assertEqual(ScoutBot.home_channel_env, "DISCORD_CHANNEL_PRODUCTION")
        self.assertEqual(ScoutBot.preferred_model, "sonnet")
        self.assertIn("issue", ScoutBot.slash_commands_summary)

    def test_scout_first_in_team_order(self):
        # Scout opens the @Team round with the slate framing so the others
        # respond in context of state.
        self.assertEqual(team.TEAM_ORDER[0], "scout")

    def test_all_four_legacy_personas_still_in_team_order(self):
        for persona in ("eddy", "marky", "patty", "linky"):
            self.assertIn(persona, team.TEAM_ORDER)


# ── /scout status job ────────────────────────────────────────────────


class _DBCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = os.environ.get("WORKSHOP_DB_PATH")
        os.environ["WORKSHOP_DB_PATH"] = str(Path(self._tmp.name) / "t.db")
        db.run_migrations()

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("WORKSHOP_DB_PATH", None)
        else:
            os.environ["WORKSHOP_DB_PATH"] = self._orig
        self._tmp.cleanup()


class ScoutStatusTests(_DBCase):
    def test_status_with_no_window(self):
        res = _run(scout_status.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("slate", res.message.lower())
        self.assertIn("empty", res.message.lower())
        # data dict is structured
        self.assertIn("issue_window", res.data)
        self.assertIsNone(res.data["issue_window"])

    def test_status_with_an_active_window(self):
        db.set_issue_window(
            issue_number=351,
            pub_date="2026-06-27",
            end_date="2026-06-26",
            start_date="2026-06-19",
            day_count=7,
            set_by="test",
        )
        res = _run(scout_status.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("WT351", res.message)
        self.assertIn("[build]", res.message)
        self.assertEqual(int(res.data["issue_window"]["issue_number"]), 351)


# ── /scout slate snapshot ────────────────────────────────────────────


class ScoutSlateSnapshotTests(_DBCase):
    def test_snapshot_unfiltered_includes_all_surfaces(self):
        lines, data = scout_slate.snapshot()
        text = "\n".join(lines)
        self.assertIn("Newsletter", text)
        self.assertIn("Blog", text)
        self.assertIn("Podcast", text)
        self.assertIn("Membership", text)
        for kind in ("newsletter", "blog", "podcast", "membership"):
            self.assertIn(kind, data)

    def test_snapshot_filtered_to_newsletter(self):
        lines, data = scout_slate.snapshot(kind="newsletter")
        text = "\n".join(lines)
        self.assertIn("Newsletter", text)
        self.assertNotIn("Blog", text)
        self.assertNotIn("Podcast", text)
        self.assertEqual(set(data), {"newsletter"})

    def test_snapshot_rejects_unknown_kind(self):
        lines, data = scout_slate.snapshot(kind="campaign")  # type: ignore[arg-type]
        self.assertEqual(data.get("error"), "unknown_kind")
        self.assertIn("Unknown", "\n".join(lines))

    def test_newsletter_block_reflects_active_windows(self):
        # Newsletters are concurrent — the block lists every in-flight issue.
        for n, pub in ((351, "2026-06-27"), (352, "2026-07-04")):
            db.set_issue_window(
                issue_number=n, pub_date=pub, end_date="2026-06-26",
                start_date="2026-06-19", day_count=7, set_by="test",
            )
        lines, data = scout_slate.snapshot(kind="newsletter")
        text = "\n".join(lines)
        self.assertIn("WT351", text)
        self.assertIn("WT352", text)
        numbers = {e["issue_number"] for e in data["newsletter"]["in_flight"]}
        self.assertEqual(numbers, {351, 352})

    def test_blog_and_podcast_blocks_read_from_registry(self):
        # The blog/podcast blocks now project active productions rows.
        db.create_production(production_type="article", title="On focus")
        _, data = scout_slate.snapshot()
        self.assertEqual(data["blog"]["in_flight"][0]["id"], "ART1")
        # No podcast rows yet → empty in_flight list (tracked, just nothing live).
        self.assertEqual(data["podcast"]["in_flight"], [])

    def test_run_returns_well_shaped_jobresult(self):
        res = _run(scout_slate.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("production slate", res.message.lower())
        for kind in ("newsletter", "blog", "podcast", "membership"):
            self.assertIn(kind, res.data)


if __name__ == "__main__":
    unittest.main()
