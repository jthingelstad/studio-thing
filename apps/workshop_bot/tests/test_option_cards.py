"""option_cards_html + refresh_loop's cards_* threading."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _llm_job  # noqa: E402
from apps.workshop_bot.tools import db, render  # noqa: E402
from apps.workshop_bot.tools.discord import interaction  # noqa: E402


class OptionCardsHtmlTests(unittest.TestCase):
    def test_basic_page(self):
        page = render.option_cards_html(
            "WT349 — subject options",
            [
                "WT349 — Mythos and the maintenance frontier",
                "WT349 — When agents start carrying the cost",
            ],
            subtitle="2 candidates",
        )
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>WT349 — subject options</title>", page)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page)
        # Subtitle present.
        self.assertIn(">2 candidates<", page)
        # Card 1 + card 2 present.
        self.assertIn("option 1", page)
        self.assertIn("option 2", page)
        self.assertIn("WT349 — Mythos and the maintenance frontier", page)
        self.assertIn("WT349 — When agents start carrying the cost", page)
        # Copy buttons.
        self.assertEqual(page.count('class="card-copy"'), 2)
        # Copy script.
        self.assertIn("navigator.clipboard", page)

    def test_escapes_option_text(self):
        page = render.option_cards_html(
            "Picker",
            ["<script>alert(1)</script>"],
        )
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_mono_body_kind_switches_class(self):
        page = render.option_cards_html(
            "Haiku picker",
            ["one\ntwo\nthree", "four\nfive\nsix"],
            body_kind="mono",
        )
        self.assertIn("card-body-mono", page)

    def test_hint_renders(self):
        page = render.option_cards_html(
            "Picker",
            ["a"],
            hint="Pick the one that fits the arc.",
        )
        self.assertIn(">Pick the one that fits the arc.<", page)


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


class RefreshLoopHtmlIntegrationTests(_DBCase):
    def _bot_and_channel(self, reply: str):
        bot = MagicMock()
        bot.user = object()
        bot.core = AsyncMock(return_value=(reply, {"iterations": 1}))
        channel = MagicMock()
        channel.send = AsyncMock()
        return bot, channel

    def test_cards_url_appended_to_prompt_label(self):
        # Parser returns 2 options; await_choice picks index 0; the cards
        # upload returns a fake URL we can assert was woven into the
        # prompt label.
        bot, channel = self._bot_and_channel(reply="1. Alpha\n2. Beta\n")

        def parser(text):
            return [line.split(".", 1)[1].strip() for line in text.splitlines() if line.strip()]

        with (
            patch.object(
                render,
                "render_and_upload_option_cards",
                return_value="https://files.thingelstad.com/weekly-thing/349/subject-options.html",
            ) as mock_upload,
            patch.object(
                interaction,
                "await_choice",
                AsyncMock(return_value=0),
            ) as mock_choice,
        ):
            picked = asyncio.run(
                _llm_job.refresh_loop(
                    bot,
                    channel,
                    base_msg="prompt body",
                    parser=parser,
                    prompt_label="📰 5 subject options for WT349 — react to pick:",
                    trigger="compose-meta:subject",
                    cards_issue=349,
                    cards_filename="subject-options",
                    cards_title="WT349 — subject options",
                )
            )
        self.assertEqual(picked, "Alpha")
        # The upload happened with the parsed options.
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        self.assertEqual(args[0], 349)
        self.assertEqual(args[1], "subject-options")
        self.assertEqual(args[2], "WT349 — subject options")
        self.assertEqual(args[3], ["Alpha", "Beta"])
        # The prompt label carried the URL through to await_choice.
        choice_kwargs = mock_choice.call_args.kwargs
        self.assertIn(
            "https://files.thingelstad.com/weekly-thing/349/subject-options.html",
            choice_kwargs["prompt"],
        )

    def test_cards_not_uploaded_when_kwargs_missing(self):
        bot, channel = self._bot_and_channel(reply="1. Alpha\n2. Beta\n")

        def parser(text):
            return ["Alpha", "Beta"]

        with (
            patch.object(
                render,
                "render_and_upload_option_cards",
                return_value="https://x/y.html",
            ) as mock_upload,
            patch.object(
                interaction,
                "await_choice",
                AsyncMock(return_value=0),
            ) as mock_choice,
        ):
            picked = asyncio.run(
                _llm_job.refresh_loop(
                    bot,
                    channel,
                    base_msg="prompt body",
                    parser=parser,
                    prompt_label="React to pick:",
                    trigger="test",
                )
            )
        self.assertEqual(picked, "Alpha")
        mock_upload.assert_not_called()
        choice_kwargs = mock_choice.call_args.kwargs
        self.assertEqual(choice_kwargs["prompt"], "React to pick:")

    def test_failed_upload_does_not_break_pick(self):
        bot, channel = self._bot_and_channel(reply="1. Alpha\n")

        def parser(text):
            return ["Alpha"]

        with (
            patch.object(
                render,
                "render_and_upload_option_cards",
                return_value=None,
            ),
            patch.object(
                interaction,
                "await_choice",
                AsyncMock(return_value=0),
            ) as mock_choice,
        ):
            picked = asyncio.run(
                _llm_job.refresh_loop(
                    bot,
                    channel,
                    base_msg="prompt",
                    parser=parser,
                    prompt_label="React:",
                    trigger="test",
                    cards_issue=349,
                    cards_filename="x",
                    cards_title="X",
                )
            )
        self.assertEqual(picked, "Alpha")
        # Upload failed → no URL appended; pick still works.
        choice_kwargs = mock_choice.call_args.kwargs
        self.assertEqual(choice_kwargs["prompt"], "React:")


if __name__ == "__main__":
    unittest.main()
