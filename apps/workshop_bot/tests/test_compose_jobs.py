"""Tests for the compose-* jobs: compose-haiku, compose-meta, compose-cta,
and reorder. Extracted from ``test_content_jobs.py`` in Item 1.
Shared fixtures from ``tests/_fixtures.py``."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import (  # noqa: E402
    _base, compose_cta, compose_haiku, compose_meta, compose_thesis, reorder,
)
from apps.workshop_bot.tools import db # noqa: E402
from apps.workshop_bot.tools.discord import interaction
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
    FakeBotChannel as _FakeBotChannel,
    filled_final as _filled_final,
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

    def test_forces_sonnet_model(self):
        # Picker output is short and well within Sonnet — overriding the
        # persona's Opus default saves ~$0.18/issue.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            asyncio.run(compose_haiku.run(ctx))
        self.assertEqual(fc.bot.core.await_args.kwargs["model"], "sonnet")


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

    def test_forces_sonnet_model_for_both_passes(self):
        # Both the subject-picker round and the one-shot description round
        # must override to Sonnet (Eddy's default is Opus). Saves ~$0.40/issue
        # since this job makes two LLM calls.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _base.starter_template())
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(side_effect=[
            ("1. WT458 — Pick\n2. WT458 — B", {}),
            ("Description line.", {}),
        ])
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            asyncio.run(compose_meta.run(ctx))
        models = [c.kwargs["model"] for c in fc.bot.core.await_args_list]
        self.assertEqual(models, ["sonnet", "sonnet"], f"expected both Sonnet; got {models}")

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

    def test_editorial_review_model_is_opus(self):
        """One stored editorial pass, on Opus by default (the weekday-scaled
        `#editorial` card and its model split were retired). Env override wins."""
        from apps.workshop_bot.jobs import update_draft
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WORKSHOP_EDDY_DRAFT_REVIEW_MODEL", None)
            self.assertEqual(update_draft._draft_review_model(), "opus")
        with patch.dict(os.environ, {"WORKSHOP_EDDY_DRAFT_REVIEW_MODEL": "sonnet"}):
            self.assertEqual(update_draft._draft_review_model(), "sonnet")



class ComposeCtaTests(_DBTestCase):
    """Patty's compose-cta now writes a fixed slot set: cta-1.md,
    cta-2.md, thanks-1.md. No final.md scan — render_email decides
    placement via hardcoded CTA_SLOT_POSITIONS. Per-slot picker UX
    unchanged."""

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_SUPPORTERS", None)
        super().tearDown()

    def _window(self):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=458, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def test_writes_all_three_atoms(self):
        """Patty composes copy for cta-1, cta-2, thanks-1 every run —
        no marker discovery, no opt-in via final.md."""
        self._window()
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
        # All three atom files written with the right frontmatter kind.
        cta1 = self.ws.files[(458, "cta-1.md")]
        cta2 = self.ws.files[(458, "cta-2.md")]
        thanks1 = self.ws.files[(458, "thanks-1.md")]
        self.assertIn("kind: supporter", cta1)
        self.assertIn("cta-1 copy", cta1)
        self.assertIn("kind: supporter", cta2)
        self.assertIn("cta-2 copy", cta2)
        self.assertIn("kind: thanks", thanks1)
        self.assertIn("thanks-1 copy", thanks1)
        self.assertIn("cta-1 copy", self.ws.files[(458, "cta-1.md")])
        self.assertIn("cta-2 copy", self.ws.files[(458, "cta-2.md")])
        self.assertIn("thanks-1 copy", self.ws.files[(458, "thanks-1.md")])

    def test_already_filled_slot_skipped(self):
        """A slot whose copy file already has body content is skipped — the
        job is idempotent for already-filled slots; Jamie deletes the file
        to re-roll."""
        self._window()
        # Pre-fill cta-1.md.
        self.ws.write_issue_file(458, "cta-1.md", "---\nkind: supporter\n---\n\nalready filled.")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["new copy"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        # 1 skipped (cta-1.md already filled); 2 written (cta-2, thanks-1).
        self.assertEqual(result.data["slots_skipped"], 1)
        self.assertEqual(result.data["slots_written"], 2)
        # cta-1.md unchanged.
        self.assertIn("already filled.", self.ws.files[(458, "cta-1.md")])

    def test_await_choice_timeout_leaves_slot_unwritten(self):
        self._window()
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["a", "b"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        # All three slots time out → none written.
        self.assertEqual(result.data["slots_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)
        self.assertNotIn((458, "cta-2.md"), self.ws.files)
        self.assertNotIn((458, "thanks-1.md"), self.ws.files)

    def test_unparseable_reply_eventually_gives_up(self):
        """refresh_loop retries up to MAX_REFRESH_ROUNDS on unparseable JSON.
        After exhaustion, no file is written."""
        self._window()
        fc = _FakeBotChannel(persona="patty", reply="sorry, can't draft right now")
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok)
        self.assertEqual(result.data["slots_written"], 0)
        self.assertNotIn((458, "cta-1.md"), self.ws.files)

    def test_channel_send_failure_does_not_lose_written_slot(self):
        """If Discord glitches on the summary post, the file is already on
        S3 — the job must still complete and report the written slots."""
        self._window()
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["x"]}')
        fc.channel.send = AsyncMock(side_effect=RuntimeError("discord down"))
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.data["slots_written"], 3)
        self.assertIn("x", self.ws.files[(458, "cta-1.md")])

    def test_concurrent_run_is_blocked_by_job_lock(self):
        self._window()
        fc = _FakeBotChannel(persona="patty", reply='{"framings": []}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        # Pre-acquire one of the per-slot locks the job opens.
        with _base.job_lock([f"{458}/cta-1.md"], compose_cta.NAME):
            result = asyncio.run(compose_cta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("already running", result.message)
        fc.bot.core.assert_not_awaited()

    def test_thesis_block_injected_when_present(self):
        """If thesis.md exists, both CTA and thanks prompts get the thesis
        injected as a `## Thesis` block at the top of the user message."""
        self._window()
        self.ws.write_issue_file(458, "thesis.md", "Capital and code.")
        fc = _FakeBotChannel(persona="patty", reply='{"framings": ["x"]}')
        os.environ["DISCORD_CHANNEL_SUPPORTERS"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=0)):
            asyncio.run(compose_cta.run(ctx))
        sent = fc.bot.core.call_args.kwargs["latest"]
        self.assertIn("## Thesis", sent)
        self.assertIn("Capital and code.", sent)



class ReorderTests(_DBTestCase):
    """Row-backed reorder pass. Eddy returns a JSON object
    (``notable_order`` / ``brief_order``) with synthetic ids
    (``n1``/``b2``/``j3``); the job validates strictly then mutates
    ``issue_items`` rows (reorder Notable + Brief; Journal is never
    reordered). Thesis and Echoes are no longer fired here —
    `compose-thesis` and `compose-echoes` both run at mark-built
    (Build → Publish), so reorder's accept path is purely the reorder
    + post-render."""

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

    # ---- baseline accept/reject flow ----
    #
    # /eddy issue reorder no longer writes final.md; it mutates
    # issue_items.position in the DB. Tests verify row positions
    # rather than file bytes.

    def test_accept_mutates_row_order(self):
        from apps.workshop_bot.tools import issue_items
        # Reorder: notable [n2, n1], leave brief + journal identity.
        ctx, fc = self._setup(self._basic_reply(notable_order=("n2", "n1")))
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Row positions reflect the reorder (B before A in Notable).
        notable_rows = issue_items.list_items(458, section="notable")
        urls = [r["url"] for r in notable_rows]
        self.assertEqual(urls, ["http://b", "http://a"])
        # thesis.md is NOT written here — that moved to compose-thesis
        # at mark-built (Build → Publish transition).
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        # final.md is no longer written either.
        self.assertNotIn((458, "final.md"), self.ws.files)

    def test_reject_leaves_rows_unchanged(self):
        from apps.workshop_bot.tools import issue_items
        ctx, fc = self._setup(self._basic_reply(notable_order=("n2", "n1")))
        with patch.object(interaction, "await_approval", AsyncMock(return_value=False)):
            result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Row positions unchanged (A before B, the original order).
        notable_rows = issue_items.list_items(458, section="notable")
        urls = [r["url"] for r in notable_rows]
        self.assertEqual(urls, ["http://a", "http://b"])
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        self.assertNotIn((458, "final.md"), self.ws.files)

    def test_timeout_leaves_rows_unchanged(self):
        from apps.workshop_bot.tools import issue_items
        ctx, fc = self._setup(self._basic_reply())
        with patch.object(interaction, "await_approval", AsyncMock(return_value=None)):
            result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        # Timeout falls to the ❌ branch — rows unchanged.
        notable_rows = issue_items.list_items(458, section="notable")
        urls = [r["url"] for r in notable_rows]
        self.assertEqual(urls, ["http://a", "http://b"])
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        self.assertNotIn((458, "final.md"), self.ws.files)

    # ---- JSON validation ----

    def test_unparseable_reply_exhausts_retries(self):
        ctx, fc = self._setup("sorry can't draft right now")
        # No valid JSON ever. Loop exhausts MAX_REFRESH_ROUNDS; rows
        # are left unchanged and the result message says so.
        result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("rows unchanged", result.message)
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        self.assertNotIn((458, "final.md"), self.ws.files)

    def test_keeps_eddy_default_model_for_proposal(self):
        # reorder passes model=None so the persona default applies —
        # today that's Sonnet (EddyBot.preferred_model). reorder is a
        # constrained ordering decision, not editorial-grade judgment
        # (the substantive pass is update-draft:html-review on Opus), so
        # it deliberately does NOT override the model. This guards
        # against a future refactor hardcoding a model on the proposal
        # pass.
        ctx, fc = self._setup(self._basic_reply())
        # compose-echoes no longer fires inside reorder (moved to
        # mark-built), so there's no second LLM call to isolate from.
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            asyncio.run(reorder.run(ctx))
        # core() was called exactly once (one-shot accept); model arg is None.
        self.assertEqual(fc.bot.core.await_count, 1)
        self.assertIsNone(fc.bot.core.await_args.kwargs["model"])

    def test_missing_id_auto_fix_appends_omitted_ids(self):
        # The original WT348 regression on Opus was a dropped j-id in
        # journal_order; Journal is no longer reordered, so the auto-fix
        # path now only applies to Notable and Brief. Same shape: Eddy
        # drops an id, the auto-fix appends it in original order and
        # accepts the rest of the proposal — preserving the reorder
        # rather than passing through.
        bad = self._basic_reply(notable_order=("n1",))  # n2 dropped
        ctx, fc = self._setup(bad)
        # compose-echoes no longer fires inside reorder (moved to
        # mark-built); the LLM call counted here is just the proposal.
        with patch.object(interaction, "await_approval", AsyncMock(return_value=True)):
            result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        # The user-visible auto-fix note hit #editorial.
        sent_messages = [c.args[0] for c in fc.channel.send.await_args_list]
        self.assertTrue(
            any("omitted `n2`" in m and "appended in original order" in m
                for m in sent_messages),
            f"expected auto-fix note in sends; got: {sent_messages!r}",
        )
        # And only ONE LLM call happened for the proposal — no retry round,
        # no passthrough fall-through (compose-echoes is mocked, doesn't count).
        self.assertEqual(fc.bot.core.await_count, 1)

    # ---- compose-cta autofire + inline markers retired ----
    #
    # CTA placement is no longer an Eddy decision — render_email
    # splices supporter CTAs at hardcoded positions, and Patty composes
    # the three known atom files (cta-1.md, cta-2.md, thanks-1.md)
    # independently. The membership_blocks proposal field still parses
    # for backward compat but the apply step ignores it.

    # ---- Featured-from-category (replaces Eddy's promotions) ----
    #
    # The whole family of "Eddy promotes Journal entries" tests retired with
    # the move to upstream-driven Featured posts. Eddy doesn't propose
    # promotions; the prompt schema doesn't mention them; the validator
    # ignores any leftover ``promotions`` field; the apply step doesn't
    # promote anything. Featured posts now come from the micro.blog
    # ``Featured`` category and are exercised by the issue_items_sync tests
    # below. (Single-journal-promotion, two-promotion, notable-cannot-be-
    # promoted, brief-cannot-be-promoted, too-many-promotions,
    # membership-block-after-promoted-id, promoted-id-also-in-order — all
    # gone; the scenarios they tested aren't reachable any more.)


class ComposeThesisTests(_DBTestCase):
    """``compose-thesis`` fires at mark-built (Build → Publish). It reads
    the assembled ``draft.md``, asks Eddy for a 1–3 sentence editorial
    framing, and writes ``thesis.md``. One-shot, no picker. Best-effort:
    a missing window / empty draft / empty reply leaves the result
    unsuccessful and writes nothing — mark-built isn't gated on it."""

    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
                            start_date=w["start_date"], day_count=w["day_count"], set_by="test")

    def _ctx(self, reply="A crisp editorial thesis."):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        return _base.JobContext(deps=fc.deps()), fc

    def test_writes_thesis_md(self):
        self._window()
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        # Surrounding whitespace exercises the strip before write.
        ctx, fc = self._ctx(reply="  A crisp editorial thesis.  ")
        result = asyncio.run(compose_thesis.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.ws.files[(458, "thesis.md")], "A crisp editorial thesis.\n")
        self.assertEqual(result.data["thesis"], "A crisp editorial thesis.")
        self.assertEqual(result.data["issue_number"], 458)
        self.assertEqual(fc.bot.core.await_count, 1)

    def test_no_active_window_returns_unsuccessful(self):
        # No window set — the job bails before touching Eddy.
        ctx, fc = self._ctx()
        result = asyncio.run(compose_thesis.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no active issue window", result.message)
        self.assertEqual(fc.bot.core.await_count, 0)

    def test_no_draft_body_returns_unsuccessful(self):
        # Window exists but no draft.md — nothing to frame, no LLM call,
        # no write.
        self._window()
        ctx, fc = self._ctx()
        result = asyncio.run(compose_thesis.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("no draft body", result.message)
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        self.assertEqual(fc.bot.core.await_count, 0)

    def test_empty_eddy_response_no_write(self):
        # Eddy returns whitespace — the job treats it as empty, reports
        # unsuccessful, and writes no thesis.md (the call still happened).
        self._window()
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        ctx, fc = self._ctx(reply="   ")
        result = asyncio.run(compose_thesis.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("empty thesis", result.message)
        self.assertNotIn((458, "thesis.md"), self.ws.files)
        self.assertEqual(fc.bot.core.await_count, 1)

    def test_skips_when_eddy_unavailable(self):
        # Eddy not logged in (no .user) — skip cleanly without an LLM call.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        ctx, fc = self._ctx()
        fc.bot.user = None
        result = asyncio.run(compose_thesis.run(ctx))
        self.assertFalse(result.ok)
        self.assertIn("Eddy unavailable", result.message)
        self.assertEqual(fc.bot.core.await_count, 0)

    def test_uses_persona_default_model(self):
        # Thesis is composition work — the job passes model=None so the
        # persona default (Sonnet) applies. It deliberately does NOT
        # override the model; this guards against a future refactor
        # hardcoding a tier on the thesis pass.
        self._window()
        self.ws.write_issue_file(458, "draft.md", _filled_final())
        ctx, fc = self._ctx(reply="A thesis.")
        asyncio.run(compose_thesis.run(ctx))
        self.assertIsNone(fc.bot.core.await_args.kwargs["model"])



