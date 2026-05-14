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
        from apps.workshop_bot.tools import issue as issue_mod
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
        from apps.workshop_bot.tools import issue as issue_mod
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
        """The Tue–Fri model selection: Tue/Wed Haiku, Thu/Fri Sonnet,
        env override wins for any weekday."""
        from apps.workshop_bot.jobs import update_draft
        # Weekday integers: Mon=0, Tue=1, …, Sun=6.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WORKSHOP_EDDY_REVIEW_MODEL", None)
            self.assertEqual(update_draft._review_model(1), "haiku")
            self.assertEqual(update_draft._review_model(2), "haiku")
            self.assertEqual(update_draft._review_model(3), "sonnet")
            self.assertEqual(update_draft._review_model(4), "sonnet")
            # Sat/Sun fall back (never actually called — gated above —
            # but the fallback should be safe).
            self.assertEqual(update_draft._review_model(5), "haiku")
        # Env override wins for any weekday.
        with patch.dict(os.environ, {"WORKSHOP_EDDY_REVIEW_MODEL": "opus"}):
            self.assertEqual(update_draft._review_model(3), "opus")



class ComposeCtaTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_SUPPORTERS", None)
        super().tearDown()

    def _window(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_zero_ctas(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="patty", reply='{"ctas": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["ctas_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_one_cta_written_with_frontmatter(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"ctas": [{"placement": "after_brief", "framings": ["Thingy here. Your support funds the EFF."]}]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["ctas_written"], 1)
        cta = self.ws.files[(458, "cta-1.md")]
        self.assertIn("placement: after_brief", cta)
        self.assertIn("Thingy here.", cta)

    def test_two_ctas_written_with_distinct_placements(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = (
            '{"ctas": ['
            ' {"placement": "after_notable", "framings": ["A1", "A2"]},'
            ' {"placement": "before_haiku", "framings": ["B1"]}'
            ']}'
        )
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        # Jamie picks the first option for each slot.
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["ctas_written"], 2)
        c1 = self.ws.files[(458, "cta-1.md")]
        c2 = self.ws.files[(458, "cta-2.md")]
        self.assertIn("placement: after_notable", c1)
        self.assertIn("A1", c1)
        self.assertIn("placement: before_haiku", c2)
        self.assertIn("B1", c2)

    def test_third_cta_dropped_silently(self):
        # The job caps at ctas[:2]; a third proposal must be ignored.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = (
            '{"ctas": ['
            ' {"placement": "after_notable", "framings": ["A"]},'
            ' {"placement": "after_journal", "framings": ["B"]},'
            ' {"placement": "before_haiku", "framings": ["C — should be dropped"]}'
            ']}'
        )
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["ctas_written"], 2)
        self.assertNotIn((458, "cta-3.md"), self.ws.files)

    def test_invalid_placement_falls_back_to_default(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"ctas": [{"placement": "above_everything", "framings": ["x"]}]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Falls back to compose._DEFAULT_PLACEMENT (`after_notable`).
        from apps.workshop_bot.jobs import _llm_job as _llm_job_mod
        self.assertIn(f"placement: {_llm_job_mod.DEFAULT_PLACEMENT}", self.ws.files[(458, "cta-1.md")])

    def test_empty_framings_slot_skipped(self):
        # A CTA dict whose framings list is empty / all-whitespace doesn't
        # get a slot — `written` reflects only real picks.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = (
            '{"ctas": ['
            ' {"placement": "after_notable", "framings": ["   ", ""]},'
            ' {"placement": "before_haiku", "framings": ["real one"]}'
            ']}'
        )
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        # Only the second slot wrote — but it goes to cta-2.md, not cta-1.md
        # (the loop index is the source-list index; an empty slot leaves
        # its filename unwritten).
        self.assertEqual(result.data["ctas_written"], 1)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)
        self.assertIn("real one", self.ws.files[(458, "cta-2.md")])

    def test_malformed_json_reply_returns_parse_error(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        # parse_json_payload pulls the first {…} block — a reply with no
        # JSON object should fail the `ctas` shape check.
        fc = _FakeBotChannel(persona="patty", reply="sorry, can't draft right now")
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("parseable", result.message)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_await_choice_timeout_leaves_slot_unwritten(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"ctas": [{"placement": "after_brief", "framings": ["a", "b"]}]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["ctas_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_body_truncated_to_issue_body_cap(self):
        # An oversized final.md must be capped at _llm_job.ISSUE_BODY_CAP
        # before being fed to Patty.
        from apps.workshop_bot.jobs import _llm_job as _llm_job_mod
        self._window()
        cap = _llm_job_mod.ISSUE_BODY_CAP
        oversized = "## Notable\n\n" + ("x" * (cap + 5_000))
        self.ws.write_issue_file(458, "final.md", oversized)
        fc = _FakeBotChannel(persona="patty", reply='{"ctas": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        sent = fc.bot.core.call_args.kwargs["latest"]
        # The fenced markdown block carries at most `cap` body chars.
        body = sent.split("```markdown\n", 1)[1].rsplit("\n```", 1)[0]
        self.assertEqual(len(body), cap)

    def test_channel_send_failure_does_not_lose_written_cta(self):
        # If Discord glitches on the success post, the CTA file is already
        # on S3 — the job must still complete successfully and report
        # ctas_written=1, not bubble the discord error out.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        reply = '{"ctas": [{"placement": "after_brief", "framings": ["x"]}]}'
        fc = _FakeBotChannel(persona="patty", reply=reply)
        fc.channel.send = AsyncMock(side_effect=RuntimeError("discord down"))
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["ctas_written"], 1)
        self.assertIn("x", self.ws.files[(458, "cta-1.md")])

    def test_concurrent_run_is_blocked_by_job_lock(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="patty", reply='{"ctas": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        # Pre-acquire the same multi-asset lock the job opens.
        with _base.job_lock([f"{458}/cta-1.md", f"{458}/cta-2.md"], compose_cta.NAME):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        fc.bot.core.assert_not_awaited()



class CreateFinalTests(_DBTestCase):
    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _setup(self, reply):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_refuses_if_final_exists(self):
        from apps.workshop_bot.tools import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        self.ws.write_issue_file(458, "final.md", "already there")
        ctx, fc = self._setup("ignored")
        self.ws.files[(458, "final.md")] = "already there"  # _setup overwrote draft only
        result = asyncio.run(create_final.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already has", result.message)

    def test_accept_uses_eddy_body(self):
        proposed = _filled_final(notable="### [Z reordered](http://z)\n\nlead")
        reply = f"Reordered Notable to lead with Z.\n\n```markdown\n{proposed}\n```"
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("Z reordered", self.ws.files[(458, "final.md")])
        # No auto-chain: the result points Jamie at the compose jobs.
        self.assertIn("issue haiku", result.message)
        # ...and Eddy never touched any other job.
        self.assertFalse(hasattr(create_final, "compose_haiku"))
        # final.html preview written, banner says FINAL.
        html = self.ws.files[(458, "final.html")]
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("FINAL (post-Eddy ordering) · WT458", html)
        self.assertIn("Z reordered", html)
        self.assertEqual(result.data["preview_url"], "https://files.thingelstad.com/weekly-thing/458/final.html")

    def test_reject_uses_draft_body(self):
        proposed = _filled_final(notable="### [Z reordered](http://z)\n\nlead")
        reply = f"here's a take\n\n```markdown\n{proposed}\n```"
        ctx, fc = self._setup(reply)
        with patch.object(interaction, "await_approval", AsyncMock(return_value=False)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Draft body used, not the proposed reorder.
        self.assertIn("### [A](http://a)", self.ws.files[(458, "final.md")])
        self.assertNotIn("Z reordered", self.ws.files[(458, "final.md")])

    def test_timeout_writes_draft_and_returns(self):
        ctx, fc = self._setup("here's a take\n\n```markdown\n" + _filled_final(notable="### [Z](http://z)") + "\n```")
        with patch.object(interaction, "await_approval", AsyncMock(return_value=None)):
            result = asyncio.run(create_final.run(ctx))
        self.assertTrue(result.ok, result.message)
        # On timeout the draft body is written as-is (don't block forever).
        self.assertIn("### [A](http://a)", self.ws.files[(458, "final.md")])



