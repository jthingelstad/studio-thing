"""Tests for the compose-* jobs: compose-haiku, compose-meta, and reorder.
Extracted from ``test_content_jobs.py`` in Item 1.
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
    _base,
    compose_haiku,
    compose_meta,
    reorder,
)
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tests._fixtures import (
    FakeBotChannel as _FakeBotChannel,
)
from apps.workshop_bot.tools import content_store, db  # noqa: E402
from apps.workshop_bot.tools.discord import interaction


def _seed_issue_body(n: int = 458) -> None:
    """Seed one notable row so ``draft_body`` (rendered live from the DB —
    the DB is the draft) returns a non-empty body."""
    from apps.workshop_bot.tools import issue_items

    issue_items.upsert_item(
        issue_number=n,
        section="notable",
        source="pinboard",
        source_id="seed1",
        url="https://ex/a",
        title="Seed item",
        body_md="Seed blurb about capital and code.",
    )


class ComposeHaikuTests(_DBTestCase):
    def _window(self, n=458):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=n,
            pub_date=w["pub_date"],
            end_date=w["end_date"],
            start_date=w["start_date"],
            day_count=w["day_count"],
            set_by="test",
        )

    def tearDown(self):
        os.environ.pop("DISCORD_CHANNEL_EDITORIAL", None)
        super().tearDown()

    def _ctx(self, reply='{"options": ["one\\ntwo\\nthree", "a\\nb\\nc"]}'):
        fc = _FakeBotChannel(persona="eddy", reply=reply)
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        return _base.JobContext(deps=fc.deps()), fc

    def test_writes_haiku_on_pick(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=1)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(content_store.read_issue(458, "haiku.md").strip(), "a\nb\nc")

    def test_refresh_then_pick(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=["refresh", 0])):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(content_store.read_issue(458, "haiku.md").strip(), "one\ntwo\nthree")
        self.assertEqual(fc.bot.core.await_count, 2)  # initial + refresh

    def test_no_pick_no_write(self):
        self._window()
        _seed_issue_body(458)
        ctx, fc = self._ctx()
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_haiku.run(ctx))
        self.assertFalse(result.ok)
        self.assertIsNone(content_store.read_issue(458, "haiku.md"))

    def test_forces_sonnet_model(self):
        # Picker output is short and well within Sonnet — overriding the
        # persona's Opus default saves ~$0.18/issue.
        self._window()
        _seed_issue_body(458)
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
        db.set_issue_window(
            issue_number=n,
            pub_date=w["pub_date"],
            end_date=w["end_date"],
            start_date=w["start_date"],
            day_count=w["day_count"],
            set_by="test",
        )

    def test_writes_metadata_json(self):
        self._window()
        _seed_issue_body(458)
        subj_reply = (
            "Here are the options:\n\n"
            "1. WT458 — The Death of Scrum\n2. WT458 — Value Over Token Consumption\n"
            "3. WT458 — How Companies Learn With AI\n4. WT458 — Agentic Coding Is a Trap\n"
            "5. WT458 — Scrum, FilamentHound, DO_NOT_TRACK"
        )
        # The description prompt now returns a single comma-separated line
        # (no numbered list, no picker) — the job takes it verbatim.
        desc_reply = (
            "Claude personal guidance, Redis array type, watchOS maps, "
            "AI company learning, agentic coding, Death of Scrum."
        )
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(
            side_effect=[(subj_reply, {"iterations": 1}), (desc_reply, {"iterations": 1})]
        )
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j

        meta = _j.loads(content_store.read_issue(458, "metadata.json"))
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
        _seed_issue_body(458)
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(
            side_effect=[
                ("1. WT458 — Pick\n2. WT458 — B", {}),
                ("Description line.", {}),
            ]
        )
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

        _seed_issue_body(458)
        content_store.write_issue(
            458,
            "metadata.json",
            _j.dumps(
                {
                    "number": 458,
                    "subject": "old subject",
                    "description": "old description",
                    "image": "https://files.thingelstad.com/weekly-thing/458/cover.jpg",
                    "slug": "458",
                    "publish_date": "2026-05-16T12:00:00Z",
                    "buttondown_id": "em_existing_id_123",
                }
            ),
        )
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(
            side_effect=[
                ("1. WT458 — Fresh Pick\n2. WT458 — B", {}),
                ("Brand new description.", {}),
            ]
        )
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        meta = _j.loads(content_store.read_issue(458, "metadata.json"))
        self.assertEqual(meta["subject"], "WT458 — Fresh Pick")
        self.assertEqual(meta["description"], "Brand new description.")
        self.assertEqual(meta["buttondown_id"], "em_existing_id_123")

    def test_empty_description_reply_writes_empty_description(self):
        self._window()
        _seed_issue_body(458)
        # Model returns an empty description (whitespace only) — metadata.json
        # still written with the picked subject and an empty description.
        fc = _FakeBotChannel(persona="eddy")
        fc.bot.core = AsyncMock(
            side_effect=[
                ("1. WT458 — Picked Subject\n2. WT458 — B", {}),
                ("   \n  \n", {}),
            ]
        )
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(side_effect=[0])):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertTrue(result.ok, result.message)
        import json as _j

        meta = _j.loads(content_store.read_issue(458, "metadata.json"))
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
        _seed_issue_body(458)
        fc = _FakeBotChannel(persona="eddy", reply="1. WT458 — A\n2. WT458 — B")
        os.environ["DISCORD_CHANNEL_EDITORIAL"] = "123"
        ctx = _base.JobContext(deps=fc.deps())
        with patch.object(interaction, "await_choice", AsyncMock(return_value=None)):
            result = asyncio.run(compose_meta.run(ctx))
        self.assertFalse(result.ok)
        self.assertIsNone(content_store.read_issue(458, "metadata.json"))

    def test_parse_numbered_list_tolerates_wrappers(self):
        text = (
            "Sure — here you go:\n\n"
            "1.  **WT458 — One**  \n"
            "2. `WT458 — Two`\n"
            "3. WT458 — Three\n\n"
            "Hope that helps."
        )
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
        """One stored editorial pass, on Opus by default (now the on-demand
        ``eddy-review`` job). Env override wins."""
        from apps.workshop_bot.jobs import eddy_review

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WORKSHOP_EDDY_DRAFT_REVIEW_MODEL", None)
            self.assertEqual(eddy_review._review_model(), "opus")
        with patch.dict(os.environ, {"WORKSHOP_EDDY_DRAFT_REVIEW_MODEL": "sonnet"}):
            self.assertEqual(eddy_review._review_model(), "sonnet")


class ReorderTests(_DBTestCase):
    """Row-backed reorder pass. Eddy returns a JSON object
    (``notable_order`` / ``brief_order``) with synthetic ids
    (``n1``/``b2``/``j3``); the job validates strictly then mutates
    ``issue_items`` rows (reorder Notable + Brief; Journal is never
    reordered). The envelope and Echoes are no longer fired here —
    `compose-envelope` and `compose-echoes` both run at mark-built
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
            issue_number=458,
            section="notable",
            source="pinboard",
            source_id="hash-A",
            url="http://a",
            title="A",
            body_md="body A",
        )
        issue_items.upsert_item(
            issue_number=458,
            section="notable",
            source="pinboard",
            source_id="hash-B",
            url="http://b",
            title="B",
            body_md="body B",
        )
        issue_items.upsert_item(
            issue_number=458,
            section="brief",
            source="pinboard",
            source_id="hash-X",
            url="http://x",
            title="X",
            body_md="First.",
        )
        issue_items.upsert_item(
            issue_number=458,
            section="brief",
            source="pinboard",
            source_id="hash-Y",
            url="http://y",
            title="Y",
            body_md="Second.",
        )
        issue_items.upsert_item(
            issue_number=458,
            section="journal",
            source="microblog",
            source_id="https://j1",
            url="https://j1",
            title="",
            body_md="j-body1",
            metadata={"label": "Sunday @ 1:00 PM", "published": "2026-05-10T18:00:00Z"},
        )
        issue_items.upsert_item(
            issue_number=458,
            section="journal",
            source="microblog",
            source_id="https://j2",
            url="https://j2",
            title="",
            body_md="j-body2",
            metadata={"label": "Monday @ 2:00 PM", "published": "2026-05-11T19:00:00Z"},
        )
        issue_items.upsert_item(
            issue_number=458,
            section="journal",
            source="microblog",
            source_id="https://j3",
            url="https://j3",
            title="",
            body_md="j-body3",
            metadata={"label": "Tuesday @ 3:00 PM", "published": "2026-05-12T20:00:00Z"},
        )

    def _setup(self, reply: str, *, seed: bool = True):
        from apps.workshop_bot.tools.content import issue as issue_mod

        w = issue_mod.compute_window("2026-05-16", 7)
        db.set_issue_window(
            issue_number=458,
            pub_date=w["pub_date"],
            end_date=w["end_date"],
            start_date=w["start_date"],
            day_count=w["day_count"],
            set_by="test",
        )
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
        # thesis.md is retired — reorder never wrote it and nothing does now.
        self.assertIsNone(content_store.read_issue(458, "thesis.md"))
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
        self.assertIsNone(content_store.read_issue(458, "thesis.md"))
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
        self.assertIsNone(content_store.read_issue(458, "thesis.md"))
        self.assertNotIn((458, "final.md"), self.ws.files)

    # ---- JSON validation ----

    def test_unparseable_reply_exhausts_retries(self):
        ctx, fc = self._setup("sorry can't draft right now")
        # No valid JSON ever. Loop exhausts MAX_REFRESH_ROUNDS; rows
        # are left unchanged and the result message says so.
        result = asyncio.run(reorder.run(ctx))
        self.assertTrue(result.ok, result.message)
        self.assertIn("rows unchanged", result.message)
        self.assertIsNone(content_store.read_issue(458, "thesis.md"))
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
            any("omitted `n2`" in m and "appended in original order" in m for m in sent_messages),
            f"expected auto-fix note in sends; got: {sent_messages!r}",
        )
        # And only ONE LLM call happened for the proposal — no retry round,
        # no passthrough fall-through (compose-echoes is mocked, doesn't count).
        self.assertEqual(fc.bot.core.await_count, 1)

    # ---- CTA autofire + inline markers retired ----
    #
    # CTA placement is no longer an Eddy decision — render_email
    # can still splice existing supporter CTA atoms at hardcoded positions,
    # but Studio no longer runs an assistant CTA composer. The
    # membership_blocks proposal field still parses for backward compat but
    # the apply step ignores it.

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
