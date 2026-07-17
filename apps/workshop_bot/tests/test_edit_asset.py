"""``/eddy edit <asset>`` — modal-based asset editor."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base, edit_asset  # noqa: E402
from apps.workshop_bot.tests._fixtures import (  # noqa: E402
    DBTestCase as _DBTestCase,
)
from apps.workshop_bot.tools import content_store, db  # noqa: E402


class _Case(_DBTestCase):
    def _window(self, n=349):
        from apps.workshop_bot.tools.content import issue as issue_mod
        w = issue_mod.compute_window("2026-05-23", 7)
        db.set_issue_window(
            issue_number=n, pub_date=w["pub_date"], end_date=w["end_date"],
            start_date=w["start_date"], day_count=w["day_count"], set_by="test",
        )

    def _ctx(self):
        deps = MagicMock()
        deps.team = MagicMock()
        return _base.JobContext(deps=deps)


class BuildModalTests(_Case):

    def test_rejects_unknown_asset(self):
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="totally-unknown")
        self.assertIsNone(modal)
        self.assertIn("unknown asset", err)

    def test_no_active_window_returns_error(self):
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="intro")
        self.assertIsNone(modal)
        self.assertIn("no active issue window", err)

    def test_modal_prefilled_with_current_content(self):
        self._window()
        content_store.write_issue(349, "intro.md", "Welcome to year nine.")
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="intro")
        self.assertIsNone(err)
        self.assertIsNotNone(modal)
        self.assertEqual(modal.input.default, "Welcome to year nine.")
        self.assertEqual(modal.filename, "intro.md")
        self.assertEqual(modal.issue_number, 349)

    def test_modal_for_missing_file_pre_fills_empty(self):
        # Edit doubles as create — opening a modal for a file that
        # doesn't exist on S3 yet should succeed (blank default), so
        # Jamie can author the asset on the spot.
        #
        # Discord rejects modals where a TextInput has `default=""`
        # alongside `required=False`, so we pass `default=None` for
        # the empty case. Placeholder still gives a hint.
        self._window()
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="outro")
        self.assertIsNone(err)
        self.assertIsNone(modal.input.default)
        # Placeholder is set so the empty field has a hint of what to write.
        self.assertTrue(modal.input.placeholder)
        # Existing content path: default is set, not None.
        content_store.write_issue(349, "outro.md", "the existing outro")
        modal2, _ = edit_asset.build_modal(self._ctx(), asset_key="outro")
        self.assertEqual(modal2.input.default, "the existing outro")

    def test_cta_modal_builds(self):
        self._window()
        content_store.write_issue(349, "cta-1.md", "---\nkind: supporter\n---\n\nx")
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="cta-1")
        self.assertIsNone(err)
        self.assertIsNotNone(modal)

    def test_oversized_body_refuses(self):
        self._window()
        content_store.write_issue(349, "intro.md", "a" * (edit_asset._MODAL_MAX + 1))
        modal, err = edit_asset.build_modal(self._ctx(), asset_key="intro")
        self.assertIsNone(modal)
        self.assertIn("4,000", err)
        self.assertIn("S3 console", err)


class ModalSubmitTests(_Case):

    def _interaction(self):
        interaction = MagicMock()
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        return interaction

    def test_submit_writes_file_and_acks(self):
        self._window()
        content_store.write_issue(349, "intro.md", "old content")
        modal, _ = edit_asset.build_modal(self._ctx(), asset_key="intro")
        modal.input.value = "new content (edited)"
        interaction = self._interaction()
        asyncio.run(modal.on_submit(interaction))
        # New content written — the DB is the draft; the save IS the update.
        self.assertEqual(content_store.read_issue(349, "intro.md"), "new content (edited)")
        # Ack message went to Jamie (ephemeral).
        interaction.response.send_message.assert_awaited()
        kwargs = interaction.response.send_message.call_args.kwargs
        self.assertTrue(kwargs.get("ephemeral"))
        msg = interaction.response.send_message.call_args.args[0]
        self.assertIn("intro.md", msg)
        self.assertIn("Done.", msg)

    def test_submit_on_cta_writes_and_acks(self):
        self._window()
        modal, _ = edit_asset.build_modal(self._ctx(), asset_key="cta-1")
        modal.input.value = "---\nkind: supporter\n---\n\nNew CTA copy."
        interaction = self._interaction()
        asyncio.run(modal.on_submit(interaction))
        self.assertEqual(
            content_store.read_issue(349, "cta-1.md"),
            "---\nkind: supporter\n---\n\nNew CTA copy.",
        )
        msg = interaction.response.send_message.call_args.args[0]
        self.assertIn("Done.", msg)

    def test_submit_empty_value_writes_empty_file(self):
        # Allowed — Jamie may want to clear an asset and re-author it.
        self._window()
        content_store.write_issue(349, "outro.md", "old outro")
        modal, _ = edit_asset.build_modal(self._ctx(), asset_key="outro")
        modal.input.value = ""
        interaction = self._interaction()
        asyncio.run(modal.on_submit(interaction))
        self.assertEqual(content_store.read_issue(349, "outro.md"), "")

    def test_submit_creates_file_that_didnt_exist(self):
        # The /eddy edit-as-create path: no existing intro.md on S3,
        # submit writes the file fresh.
        self._window()
        # Confirm baseline: intro.md is not in the workspace.
        self.assertIsNone(content_store.read_issue(349, "intro.md"))
        modal, _ = edit_asset.build_modal(self._ctx(), asset_key="intro")
        modal.input.value = "Brand new intro paragraph for WT349."
        interaction = self._interaction()
        asyncio.run(modal.on_submit(interaction))
        self.assertEqual(
            content_store.read_issue(349, "intro.md"),
            "Brand new intro paragraph for WT349.",
        )

    def test_submit_propagates_write_failure_to_ack(self):
        self._window()
        modal, _ = edit_asset.build_modal(self._ctx(), asset_key="haiku")
        modal.input.value = "line one\nline two\nline three"
        interaction = self._interaction()
        with patch.object(
            content_store, "write_issue", side_effect=RuntimeError("DB boom"),
        ):
            asyncio.run(modal.on_submit(interaction))
        msg = interaction.response.send_message.call_args.args[0]
        self.assertIn("Couldn't write", msg)
        self.assertIn("DB boom", msg)


class SlashCommandWiringTests(unittest.TestCase):

    def test_eddy_edit_and_currently_commands_retired(self):
        """`/eddy edit` and `/eddy currently` were retired — content editing
        moved to the web production page. The edit_asset / currently jobs
        themselves stay (driven by the web + agent tools + cron)."""
        from apps.workshop_bot.personas import commands as commands_module

        class _StubBot:
            user = MagicMock()
            def get_partial_messageable(self, _id):
                return None
        tree = commands_module.register_eddy_commands(_StubBot())
        eddy_group = next(
            g for g in tree.groups if getattr(g, "name", None) == "eddy"
        )
        leaf_names = {
            getattr(c, "_cmd_name", getattr(c, "name", None))
            for c in eddy_group.commands
        }
        self.assertNotIn("edit", leaf_names)
        self.assertNotIn("currently", leaf_names)
        # The compose/editorial commands that have no web equivalent stay.
        self.assertIn("issue", leaf_names)


if __name__ == "__main__":
    unittest.main()
