"""Scout (producer) — Part 1 wiring tests.

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
        self.assertTrue(ScoutBot.slash_commands_summary)

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

    def test_newsletter_block_reflects_active_window(self):
        db.set_issue_window(
            issue_number=351,
            pub_date="2026-06-27",
            end_date="2026-06-26",
            start_date="2026-06-19",
            day_count=7,
            set_by="test",
        )
        lines, data = scout_slate.snapshot(kind="newsletter")
        self.assertIn("WT351", "\n".join(lines))
        self.assertEqual(
            data["newsletter"]["in_flight"]["issue_number"], 351,
        )

    def test_blog_and_podcast_blocks_marked_deferred(self):
        # Phase 2 will replace these stubs; the deferred flag is the contract
        # for callers so they don't misread the absent rows as "nothing in
        # flight" vs "we don't track this yet".
        _, data = scout_slate.snapshot()
        self.assertTrue(data["blog"].get("deferred"))
        self.assertTrue(data["podcast"].get("deferred"))

    def test_run_returns_well_shaped_jobresult(self):
        res = _run(scout_slate.run(_base.JobContext()))
        self.assertTrue(res.ok)
        self.assertIn("production slate", res.message.lower())
        for kind in ("newsletter", "blog", "podcast", "membership"):
            self.assertIn(kind, res.data)


if __name__ == "__main__":
    unittest.main()
