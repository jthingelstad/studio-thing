"""Tests for the compose-* jobs: compose-haiku, compose-meta, compose-cta,
and create-final. Extracted from ``test_content_jobs.py`` in Item 1.
Shared fixtures from ``tests/_fixtures.py``."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import (  # noqa: E402
    _base, build_publish, compose_cta, compose_haiku, compose_meta, create_final,
)
from apps.workshop_bot.tools import db, s3 # noqa: E402
from apps.workshop_bot.tools.discord import interaction
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    FakeWorkspace,
    filled_final as _filled_final,
    patch_s3 as _patch_s3,
)


class ComposeHaikuTests(_DBTestCase):
    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _ctx(self, reply='{"options": ["one\\ntwo\\nthree", "a\\nb\\nc"]}'):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_writes_haiku_on_pick(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=1)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.ws.files[(458, "haiku.md")].strip(), "a\nb\nc")

    def test_refresh_then_pick(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=["refresh", 0])):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.ws.files[(458, "haiku.md")].strip(), "one\ntwo\nthree")
        self.assertEqual(fc.bot.core.await_count, 2)  # initial + refresh

    def test_no_pick_no_write(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertFalse(result.ok)
        self.assertNotIn((458, "haiku.md"), self.ws.files)



class ComposeMetaTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_writes_metadata_json(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        subj_reply = ("Here are the options:\n\n"
                      "1. WT458 — The Death of Scrum\n2. WT458 — Value Over Token Consumption\n"
                      "3. WT458 — How Companies Learn With AI\n4. WT458 — Agentic Coding Is a Trap\n"
                      "5. WT458 — Scrum, FilamentHound, DO_NOT_TRACK")
        # The description prompt now returns a single comma-separated line
        # (no numbered list, no picker) — the job takes it verbatim.
        desc_reply = ("Claude personal guidance, Redis array type, watchOS maps, "
                      "AI company learning, agentic coding, Death of Scrum.")
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[(subj_reply, {"iterations": 1}), (desc_reply, {"iterations": 1})])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["number"], 458)
        self.assertEqual(meta["subject"], "WT458 — The Death of Scrum")
        self.assertEqual(meta["description"], desc_reply)
        self.assertEqual(meta["slug"], "458")
        self.assertTrue(meta["image"].endswith("/458/cover.jpg"))
        self.assertTrue(meta["publish_date"].startswith("2026-05-16"))
        # The success post in #editorial surfaces both subject and description.
        sent = fc.channel.send.await_args_list[-1].args[0]
        self.assertIn("**Subject:** WT458 — The Death of Scrum", sent)
        self.assertIn("**Description:** Claude personal guidance,", sent)

    def test_preserves_buttondown_id_on_rerun(self):
        # Once send-to-buttondown has written buttondown_id, a later
        # compose-meta re-run must keep it so the next send PATCHes the
        # same draft rather than POSTing a duplicate.
        self._window()
        import json as _j
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        self.ws.write_issue_file(458, "metadata.json", _j.dumps({
            "number": 458,
            "subject": "old subject",
            "description": "old description",
            "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
            "slug": "458",
            "publish_date": "2026-05-16T12:00:00Z",
            "buttondown_id": "em_existing_id_123",
        }))
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[
            ("1. WT458 — Fresh Pick\n2. WT458 — B", {}),
            ("Brand new description.", {}),
        ])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["subject"], "WT458 — Fresh Pick")
        self.assertEqual(meta["description"], "Brand new description.")
        self.assertEqual(meta["buttondown_id"], "em_existing_id_123")

    def test_empty_description_reply_writes_empty_description(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        # Model returns an empty description (whitespace only) — metadata.json
        # still written with the picked subject and an empty description.
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[
            ("1. WT458 — Picked Subject\n2. WT458 — B", {}),
            ("   \n  \n", {}),
        ])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j
        meta = _j.loads(self.ws.files[(458, "metadata.json")])
        self.assertEqual(meta["subject"], "WT458 — Picked Subject")
        self.assertEqual(meta["description"], "")

    def test_first_nonempty_line(self):
        # The description prompt is "Output: a single line"; the helper
        # strips leading/trailing blank lines + per-line whitespace.
        self.assertEqual(
            compose_meta._first_nonempty_line("   \n\nA single concrete description.\n  "),
            "A single concrete description.",
        )
        self.assertEqual(
            compose_meta._first_nonempty_line(
                "Claude personal guidance, Redis arrays, FilamentHound, Death of Scrum."
            ),
            "Claude personal guidance, Redis arrays, FilamentHound, Death of Scrum.",
        )
        self.assertEqual(compose_meta._first_nonempty_line(""), "")
        self.assertEqual(compose_meta._first_nonempty_line("   \n\n"), "")

    def test_no_subject_pick_fails_cleanly(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="eddy", reply="1. WT458 — A\n2. WT458 — B")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertFalse(result.ok)
        self.assertNotIn((458, "metadata.json"), self.ws.files)

    def test_parse_numbered_list_tolerates_wrappers(self):
        text = ("Sure — here you go:\n\n"
                "1.  **WT458 — One**  \n"
                "2. `WT458 — Two`\n"
                "3. WT458 — Three\n\n"
                "Hope that helps.")
        parser = compose_meta._parse_numbered_list_factory(8)
        self.assertEqual(
            parser(text),
            ["WT458 — One", "WT458 — Two", "WT458 — Three"],
        )

    def test_parse_numbered_list_factory_respects_limit(self):
        text = "\n".join(f"{i}. item-{i}" for i in range(1, 11))
        self.assertEqual(len(compose_meta._parse_numbered_list_factory(3)(text)), 3)
        self.assertEqual(len(compose_meta._parse_numbered_list_factory(8)(text)), 8)

    def test_compose_max_refresh_rounds_is_shared(self):
        # All three compose-flow jobs share a single constant.
        from apps.workshop_bot.jobs import _llm_job
        self.assertEqual(_llm_job.MAX_REFRESH_ROUNDS, 3)

    def test_resolved_bot_is_a_named_tuple(self):
        """Tuple unpack stays as before, AND callers can use field access."""
        from apps.workshop_bot.jobs._llm_job import ResolvedBot
        r = ResolvedBot("BOT", "CHANNEL", None)
        # tuple-unpack — what existing callers do
        bot, channel, reason = r
        self.assertEqual((bot, channel, reason), ("BOT", "CHANNEL", None))
        # field access — what new callers can do
        self.assertEqual(r.bot, "BOT")
        self.assertEqual(r.channel, "CHANNEL")
        self.assertIsNone(r.error_reason)

    def test_review_model_by_weekday(self):
        """Model selection across the week: Sun–Wed Haiku, Thu–Sat Sonnet,
        env override wins for any weekday."""
        from apps.workshop_bot.jobs import update_draft
        # Weekday integers: Mon=0, Tue=1, …, Sun=6.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WORKSHOP_EDDY_REVIEW_MODEL", None)
            self.assertEqual(update_draft._review_model(6), "haiku")   # Sun
            self.assertEqual(update_draft._review_model(0), "haiku")   # Mon
            self.assertEqual(update_draft._review_model(1), "haiku")   # Tue
            self.assertEqual(update_draft._review_model(2), "haiku")   # Wed
            self.assertEqual(update_draft._review_model(3), "sonnet")  # Thu
            self.assertEqual(update_draft._review_model(4), "sonnet")  # Fri
            # Sat: also Sonnet now — Eddy keeps commenting up to publish.
            self.assertEqual(update_draft._review_model(5), "sonnet")
        # Env override wins for any weekday.
        with patch.dict(os.environ, {"WORKSHOP_EDDY_REVIEW_MODEL": "opus"}):
            self.assertEqual(update_draft._review_model(3), "opus")



class ComposeCtaTests(_DBTestCase):
    """Rewritten for the chunk-based editorial rework.

    Slots are now discovered by scanning ``final.md`` for inline
    ``<!-- cta:N -->`` / ``<!-- thanks:N -->`` markers placed by
    ``create-final``. Patty no longer decides count or placement — only
    copy for the slots Eddy declared. The per-slot LLM reply shape is
    ``{"framings": [...]}``, and the picked body is written into
    ``cta-N.md`` / ``thanks-N.md`` with ``kind:`` YAML frontmatter."""

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_SUPPORTERS", None)
        super().tearDown()

    def _window(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def _seed_final(self, notable_marker_after_a: str = "") -> None:
        """Write a final.md with the three required blocks. Optionally inject
        a marker into the Notable block content."""
        notable = "### [A](http://a)\n\nx" + (
            f"\n\n{notable_marker_after_a}" if notable_marker_after_a else ""
        )
        self.ws.write_issue_file(458, "final.md", _filled_final(notable=notable))

    def test_returns_ok_when_no_markers_in_final(self):
        self._window()
        self._seed_final()  # no markers
        fc = _FakeBotChannel(persona="patty", reply='{"framings": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_total"], 0)
        self.assertEqual(result.data["slots_written"], 0)
        # No LLM call when there are no slots.
        fc.bot.core.assert_not_awaited()
        # No cta files written.
        self.assertNotIn((458, "cta-1.md"), self.ws.files)
        self.assertNotIn((458, "thanks-1.md"), self.ws.files)

    def test_refuses_when_final_md_missing(self):
        self._window()
        # No final.md written.
        fc = _FakeBotChannel(persona="patty", reply='{"framings": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no `final.md`", result.message)
        self.assertIn("/eddy issue final", result.message)

    def test_one_cta_marker_writes_supporter_file(self):
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->")
        reply = '{"framings": ["Thingy here. Your support funds the EFF."]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_written"], 1)
        cta = self.ws.files[(458, "cta-1.md")]
        self.assertIn("kind: supporter", cta)
        self.assertIn("Thingy here.", cta)
        # The new format drops `placement:` frontmatter.
        self.assertNotIn("placement:", cta)

    def test_thanks_marker_writes_thanks_file_with_kind(self):
        self._window()
        self._seed_final(notable_marker_after_a="<!-- thanks:1 -->")
        reply = '{"framings": ["Thank you for keeping this free."]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_written"], 1)
        thanks = self.ws.files[(458, "thanks-1.md")]
        self.assertIn("kind: thanks", thanks)
        self.assertIn("Thank you for keeping this free.", thanks)
        # cta-1.md NOT written (thanks marker → thanks file only).
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_multiple_markers_fill_each_slot(self):
        """Two cta + one thanks. Each slot fired independently with its own
        framings; per-slot picker UX."""
        self._window()
        marker_block = "<!-- cta:1 -->\n\n<!-- cta:2 -->\n\n<!-- thanks:1 -->"
        self._seed_final(notable_marker_after_a=marker_block)
        # Three calls; each returns one framing.
        replies = iter([
            ('{"framings": ["cta-1 copy"]}', {"iterations": 1}),
            ('{"framings": ["cta-2 copy"]}', {"iterations": 1}),
            ('{"framings": ["thanks-1 copy"]}', {"iterations": 1}),
        ])
        fc = _FakeBotChannel(persona="patty")
        fc.bot.core = AsyncMock(side_effect=lambda **kw: next(replies))
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_written"], 3)
        self.assertEqual(result.data["slots_total"], 3)
        self.assertIn("cta-1 copy", self.ws.files[(458, "cta-1.md")])
        self.assertIn("cta-2 copy", self.ws.files[(458, "cta-2.md")])
        self.assertIn("thanks-1 copy", self.ws.files[(458, "thanks-1.md")])

    def test_already_filled_slot_skipped(self):
        """A slot whose copy file already has body content is skipped — the
        job is idempotent for already-filled slots; Jamie deletes the file
        to re-roll."""
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->\n\n<!-- cta:2 -->")
        # Pre-fill cta-1.md.
        self.ws.write_issue_file(458, "cta-1.md", "---\nkind: supporter\n---\n\nalready filled.")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["new copy"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_skipped"], 1)
        self.assertEqual(result.data["slots_written"], 1)
        # cta-1.md unchanged.
        self.assertIn("already filled.", self.ws.files[(458, "cta-1.md")])
        # cta-2.md got the new copy.
        self.assertIn("new copy", self.ws.files[(458, "cta-2.md")])

    def test_await_choice_timeout_leaves_slot_unwritten(self):
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["a", "b"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["slots_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_unparseable_reply_eventually_gives_up(self):
        """refresh_loop retries up to MAX_REFRESH_ROUNDS on unparseable JSON.
        After exhaustion, no file is written."""
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->")
        fc = _FakeBotChannel(persona="patty", reply="sorry, can't draft right now")
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)  # not a job failure; just no copy written
        self.assertEqual(result.data["slots_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_channel_send_failure_does_not_lose_written_slot(self):
        """If Discord glitches on the summary post, the file is already on
        S3 — the job must still complete and report slots_written=1."""
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["x"]}')
        fc.channel.send = AsyncMock(side_effect=RuntimeError("discord down"))
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_written"], 1)
        self.assertIn("x", self.ws.files[(458, "cta-1.md")])

    def test_concurrent_run_is_blocked_by_job_lock(self):
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->\n\n<!-- thanks:1 -->")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        # Pre-acquire one of the per-slot locks the job opens.
        with _base.job_lock([f"{458}/cta-1.md", f"{458}/thanks-1.md"], compose_cta.NAME):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        fc.bot.core.assert_not_awaited()

    def test_thesis_block_injected_when_present(self):
        """If thesis.md exists, both CTA and thanks prompts get the thesis
        injected as a `## Thesis` block at the top of the user message."""
        self._window()
        self._seed_final(notable_marker_after_a="<!-- cta:1 -->")
        self.ws.write_issue_file(458, "thesis.md", "Capital and code.")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["x"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            asyncio.run(compose_cta.run(ctx))
        sent = fc.bot.core.call_args.kwargs["latest"]
        self.assertIn("## Thesis", sent)
        self.assertIn("Capital and code.", sent)



class CreateFinalTests(_DBTestCase):
    """Rewritten for the row-backed editorial pass. Eddy still returns a
    JSON object (``thesis``, ``*_order``, ``promotions``,
    ``membership_blocks``) with synthetic ids (``n1``/``b2``/``j3``);
    the job validates strictly, then mutates ``issue_items`` rows
    (reorder + promote) and assembles ``final.md`` from rows + atoms.
    Promoted items splice inline at their declared position — there
    are no feature1/feature2 blocks anymore."""

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _seed_rows(self):
        """Insert 2 Notable + 2 Brief + 3 Journal rows; the synthetic
        ids the test replies use (``n1``/``n2``/``b1``/``b2``/``j1``/
        ``j2``/``j3``) map to insertion order."""
        from apps.workshop_bot.tools import issue_items
        issue_items.upsert_item(
            issue_number=458, section="notable", source="pinboard",
            source_id="hash-A", url="http://a", title="A", body_md="body A",
        )
        issue_items.upsert_item(
            issue_number=458, section="notable", source="pinboard",
            source_id="hash-B", url="http://b", title="B", body_md="body B",
        )
        issue_items.upsert_item(
            issue_number=458, section="brief", source="pinboard",
            source_id="hash-X", url="http://x", title="X", body_md="First.",
        )
        issue_items.upsert_item(
            issue_number=458, section="brief", source="pinboard",
            source_id="hash-Y", url="http://y", title="Y", body_md="Second.",
        )
        issue_items.upsert_item(
            issue_number=458, section="journal", source="microblog",
            source_id="https://j1", url="https://j1", title="", body_md="j-body1",
            metadata={"label": "Sunday @ 1:00 PM", "published": "2026-05-10T18:00:00Z"},
        )
        issue_items.upsert_item(
            issue_number=458, section="journal", source="microblog",
            source_id="https://j2", url="https://j2", title="", body_md="j-body2",
            metadata={"label": "Monday @ 2:00 PM", "published": "2026-05-11T19:00:00Z"},
        )
        issue_items.upsert_item(
            issue_number=458, section="journal", source="microblog",
            source_id="https://j3", url="https://j3", title="", body_md="j-body3",
            metadata={"label": "Tuesday @ 3:00 PM", "published": "2026-05-12T20:00:00Z"},
        )

    def _setup(self, reply: str, *, seed: bool = True):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        if seed:
            self._seed_rows()
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    @staticmethod
    def _basic_reply(
        *,
        thesis: str = "Test thesis for the issue.",
        notable_order=("n1", "n2"),
        brief_order=("b1", "b2"),
        journal_order=("j1", "j2", "j3"),
        promotions=(),
        membership_blocks=(),
    ) -> str:
        payload = {
            "thesis": thesis,
            "notable_order": list(notable_order),
            "brief_order": list(brief_order),
            "journal_order": list(journal_order),
            "promotions": list(promotions),
            "membership_blocks": list(membership_blocks),
        }
        return json.dumps(payload)

    # ---- baseline accept/reject/refuse flow ----

    def test_refuses_if_final_exists(self):
        ctx, fc = self._setup(self._basic_reply())
        self.ws.write_issue_file(458, "final.md", "already there")
        result = asyncio.run(create_final.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already has", result.message)

    def test_accept_writes_reorder_and_thesis(self):
        # Reorder: notable [n2, n1], leave brief + journal identity.
        ctx, fc = self._setup(self._basic_reply(notable_order=("n2", "n1")))
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # final.md exists and reflects the new order (B before A).
        final = self.ws.files[(458, "final.md")]
        b_pos = final.index("### [B](http://b)")
        a_pos = final.index("### [A](http://a)")
        self.assertLess(b_pos, a_pos)
        # thesis.md written.
        self.assertIn("Test thesis for the issue.", self.ws.files[(458, "thesis.md")])
        # Brief / Journal sections rendered.
        self.assertIn("**[X](http://x)**", final)
        self.assertIn("[Sunday @ 1:00 PM]", final)
        # Block markers preserved (the assembler still emits them).
        self.assertIn("<!-- block:notable -->", final)
        self.assertIn("<!-- /block:notable -->", final)
        # Pipeline hint preserved.
        self.assertIn("issue haiku", result.message)
        self.assertTrue(result.data["thesis_written"])

    def test_reject_uses_current_row_order(self):
        ctx, fc = self._setup(self._basic_reply(notable_order=("n2", "n1")))
        with patch.object(interaction, "await_approval", AsyncMock(return_value=False)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Current row order survives (A before B); no thesis.md.
        final = self.ws.files[(458, "final.md")]
        a_pos = final.index("### [A](http://a)")
        b_pos = final.index("### [B](http://b)")
        self.assertLess(a_pos, b_pos)
        self.assertNotIn((458, "thesis.md"), self.ws.files)

    def test_timeout_writes_current_row_order_and_returns(self):
        ctx, fc = self._setup(self._basic_reply())
        with patch.object(interaction, "await_approval", AsyncMock(return_value=None)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Timeout → falls into the ❌ branch; rows render in current order.
        final = self.ws.files[(458, "final.md")]
        self.assertIn("### [A](http://a)", final)
        self.assertNotIn((458, "thesis.md"), self.ws.files)

    # ---- JSON validation ----

    def test_unparseable_reply_eventually_falls_back_to_rows(self):
        ctx, fc = self._setup("sorry can't draft right now")
        # No valid JSON ever. Loop exhausts MAX_REFRESH_ROUNDS; the
        # fallback writes the current row order as final.md and returns ok.
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("rows as-is", result.message)
        self.assertIn("### [A](http://a)", self.ws.files[(458, "final.md")])
        self.assertNotIn((458, "thesis.md"), self.ws.files)

    def test_invalid_order_permutation_refuses(self):
        # n1 omitted from notable_order — validation error.
        bad = self._basic_reply(notable_order=("n2",))
        ctx, fc = self._setup(bad)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("rows as-is", result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(any("didn't validate" in m for m in sent_messages),
                        f"sent_messages = {sent_messages!r}")

    # ---- compose-cta autofire ----

    def test_membership_blocks_autofires_compose_cta(self):
        # When Jamie approves a proposal with cta/thanks markers,
        # create-final should schedule compose-cta as a background task
        # (no manual `/patty cta` required — addresses the WT348 skip-Patty
        # failure mode).
        reply = self._basic_reply(
            membership_blocks=[
                {"kind": "cta", "after": "n1", "rationale": "after first"},
            ],
        )
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)), \
             patch.object(create_final, "_schedule_compose_cta") as mock_sched:
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.data["cta_autofired"])
        self.assertEqual(result.data["cta_slots_declared"], 1)
        mock_sched.assert_called_once()
        kwargs = mock_sched.call_args.kwargs
        self.assertEqual(kwargs["issue_number"], 458)
        self.assertEqual(kwargs["slots_declared"], 1)
        # The success message references the autofire.
        self.assertIn("compose-cta", result.message)
        self.assertIn("auto-fires", result.message)

    def test_no_markers_no_autofire(self):
        reply = self._basic_reply()  # empty membership_blocks
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)), \
             patch.object(create_final, "_schedule_compose_cta") as mock_sched:
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertFalse(result.data["cta_autofired"])
        self.assertEqual(result.data["cta_slots_declared"], 0)
        mock_sched.assert_not_called()

    def test_rejected_proposal_does_not_autofire(self):
        reply = self._basic_reply(
            membership_blocks=[{"kind": "cta", "after": "n1", "rationale": "x"}],
        )
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=False)), \
             patch.object(create_final, "_schedule_compose_cta") as mock_sched:
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok)
        self.assertFalse(result.data["cta_autofired"])
        mock_sched.assert_not_called()

    # ---- membership block markers ----

    def test_membership_blocks_marker_inline(self):
        reply = self._basic_reply(
            membership_blocks=[
                {"kind": "cta", "after": "n1", "rationale": "after first item"},
                {"kind": "thanks", "before_haiku": True, "rationale": "end of issue"},
            ],
        )
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        final = self.ws.files[(458, "final.md")]
        # cta:1 marker appears in the Notable block, after item A.
        self.assertIn("<!-- cta:1 -->", final)
        a_pos = final.index("### [A](http://a)")
        cta_pos = final.index("<!-- cta:1 -->")
        b_pos = final.index("### [B](http://b)")
        self.assertLess(a_pos, cta_pos)
        self.assertLess(cta_pos, b_pos)
        # thanks:1 marker appears in the last non-empty section (Brief).
        self.assertIn("<!-- thanks:1 -->", final)

    def test_membership_block_after_promoted_id_refused(self):
        reply = self._basic_reply(
            journal_order=("j2", "j3"),
            promotions=[{
                "id": "j1",
                "heading": "Featured Journal",
                "position": "after_journal",
                "rationale": "the central piece",
            }],
            membership_blocks=[
                {"kind": "cta", "after": "j1", "rationale": "trying to anchor on promoted"},
            ],
        )
        ctx, fc = self._setup(reply)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(any("promoted" in m for m in sent_messages),
                        f"sent_messages = {sent_messages!r}")

    # ---- promotions ----

    def test_single_journal_promotion_splices_inline(self):
        # Promote j2 to its own featured section. Journal_order keeps the
        # other two entries; the featured section splices inline AFTER
        # the Journal block, BEFORE the Brief section — what Jamie sees
        # in final.md is exactly where it'll land in publish.md.
        reply = self._basic_reply(
            journal_order=("j1", "j3"),  # j2 promoted out
            promotions=[{
                "id": "j2",
                "heading": "Featured: A Big Journal Read",
                "position": "after_journal",
                "rationale": "this post is the editorial heart of the week",
            }],
        )
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        final = self.ws.files[(458, "final.md")]
        # The featured section renders as ``## Heading\n\n{body}``, inline.
        self.assertIn("## Featured: A Big Journal Read", final)
        # No feature1/feature2 blocks anywhere — the splice is inline.
        self.assertNotIn("<!-- block:feature1 -->", final)
        self.assertNotIn("<!-- block:feature2 -->", final)
        # j2 lives in the featured section; the Journal block has only j1 + j3.
        journal_block_start = final.index("<!-- block:journal -->")
        journal_block_end = final.index("<!-- /block:journal -->")
        journal_body = final[journal_block_start:journal_block_end]
        self.assertNotIn("[Monday @ 2:00 PM](https://j2)", journal_body)
        self.assertIn("[Sunday @ 1:00 PM](https://j1)", journal_body)
        self.assertIn("[Tuesday @ 3:00 PM](https://j3)", journal_body)
        # The featured section appears AFTER the Journal block close and
        # BEFORE the Brief heading.
        feature_pos = final.index("## Featured: A Big Journal Read")
        journal_close = final.index("<!-- /block:journal -->")
        brief_heading = final.index("## Briefly")
        self.assertLess(journal_close, feature_pos)
        self.assertLess(feature_pos, brief_heading)

    def test_two_journal_promotions_splice_at_distinct_positions(self):
        # Rare case: promote two Journal entries at different positions.
        # Both splice inline at their declared positions.
        reply = self._basic_reply(
            journal_order=("j2",),
            promotions=[
                {"id": "j1", "heading": "Featured One", "position": "after_journal",
                 "rationale": "lead piece"},
                {"id": "j3", "heading": "Featured Two", "position": "after_brief",
                 "rationale": "second feature later in the issue"},
            ],
        )
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        final = self.ws.files[(458, "final.md")]
        self.assertIn("## Featured One", final)
        self.assertIn("## Featured Two", final)
        # No feature blocks.
        self.assertNotIn("<!-- block:feature1 -->", final)
        # Featured One splices after Journal; Featured Two splices after Briefly.
        one_pos = final.index("## Featured One")
        two_pos = final.index("## Featured Two")
        journal_close = final.index("<!-- /block:journal -->")
        brief_close = final.index("<!-- /block:brief -->")
        self.assertLess(journal_close, one_pos)
        self.assertLess(brief_close, two_pos)

    def test_notable_id_cannot_be_promoted(self):
        # Notable links stay in their parent section — only Journal
        # entries earn featured treatment.
        reply = self._basic_reply(
            notable_order=("n2",),
            promotions=[{
                "id": "n1",
                "heading": "Featured Notable",
                "position": "after_notable",
                "rationale": "wishful thinking",
            }],
        )
        ctx, fc = self._setup(reply)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(
            any("Notable" in m and "n1" in m for m in sent_messages),
            f"sent_messages = {sent_messages!r}",
        )

    def test_brief_id_cannot_be_promoted(self):
        reply = self._basic_reply(
            brief_order=("b2",),
            promotions=[{
                "id": "b1",
                "heading": "Featured Brief",
                "position": "after_notable",
                "rationale": "...",
            }],
        )
        ctx, fc = self._setup(reply)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(any("Brief" in m for m in sent_messages),
                        f"sent_messages = {sent_messages!r}")

    def test_promoted_id_also_in_order_refused(self):
        # j1 in journal_order AND in promotions — must reject because the
        # order validation expects (parsed - promoted), which means j1
        # appears as an unknown id in the order.
        reply = self._basic_reply(
            journal_order=("j1", "j2", "j3"),
            promotions=[{
                "id": "j1",
                "heading": "Featured One",
                "position": "after_journal",
                "rationale": "...",
            }],
        )
        ctx, fc = self._setup(reply)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(
            any("journal" in m and "j1" in m for m in sent_messages),
            f"sent_messages = {sent_messages!r}",
        )

    def test_too_many_promotions_refused(self):
        # 3 Journal promotions exceeds _MAX_PROMOTIONS=2 — and 3 is also
        # everything in the Journal section, which would be an absurd shape.
        reply = self._basic_reply(
            journal_order=(),
            promotions=[
                {"id": "j1", "heading": "F1", "position": "after_journal", "rationale": "..."},
                {"id": "j2", "heading": "F2", "position": "after_journal", "rationale": "..."},
                {"id": "j3", "heading": "F3", "position": "after_journal", "rationale": "..."},
            ],
        )
        ctx, fc = self._setup(reply)
        result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(any("too many promotions" in m for m in sent_messages),
                        f"sent_messages = {sent_messages!r}")



