"""Tests for jobs/currently.py — the ``/eddy currently`` slash handlers
and the per-type modal helper. The renderer + DB primitives are covered
in ``test_currently.py``; this file exercises the user-facing job layer."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.jobs import _base  # noqa: E402
from apps.workshop_bot.jobs import currently as currently_job
from apps.workshop_bot.tests._fixtures import DBTestCase  # noqa: E402
from apps.workshop_bot.tools import db  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _NoopRefireMixin:
    """Historically stubbed update-draft refires on mutating Currently
    ops. Currently mutations no longer refire (changes land in the next
    scheduled / manual update-draft instead), so this mixin is a no-op —
    kept as a base class so subclasses keep their existing MRO."""

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


def _set_active_window(n: int = 458, pub_date: str = "2026-05-23") -> None:
    db.set_issue_window(
        issue_number=n, pub_date=pub_date, end_date="2026-05-22",
        start_date="2026-05-15", day_count=7, set_by="test",
    )


class NoActiveWindowTests(_NoopRefireMixin, DBTestCase):
    def test_set_value_refuses_without_active_window(self):
        r = _run(currently_job.set_value(_base.JobContext(), type_label="Reading", value="x"))
        self.assertFalse(r.ok)
        self.assertIn("no active issue", r.message.lower())

    def test_list_state_refuses_without_active_window(self):
        r = _run(currently_job.list_state(_base.JobContext()))
        self.assertFalse(r.ok)
        self.assertIn("no active issue", r.message.lower())


class SetAndClearTests(_NoopRefireMixin, DBTestCase):
    def setUp(self):
        super().setUp()
        _set_active_window()

    def test_set_appends_with_next_position(self):
        r1 = _run(currently_job.set_value(_base.JobContext(), type_label="Listening", value="L"))
        r2 = _run(currently_job.set_value(_base.JobContext(), type_label="Reading", value="R"))
        self.assertTrue(r1.ok and r2.ok)
        self.assertEqual(r1.data["position"], 1)
        self.assertEqual(r2.data["position"], 2)

    def test_set_update_preserves_position(self):
        _run(currently_job.set_value(_base.JobContext(), type_label="Listening", value="first"))
        _run(currently_job.set_value(_base.JobContext(), type_label="Reading", value="R"))
        r = _run(currently_job.set_value(_base.JobContext(), type_label="Listening", value="updated"))
        self.assertEqual(r.data["position"], 1)

    def test_set_canonicalises_case(self):
        r = _run(currently_job.set_value(_base.JobContext(), type_label="listening", value="x"))
        self.assertTrue(r.ok)
        self.assertEqual(r.data["label"], "Listening")

    def test_set_unknown_type_errors_with_hint(self):
        r = _run(currently_job.set_value(_base.JobContext(), type_label="Surfing", value="waves"))
        self.assertFalse(r.ok)
        self.assertIn("add-type", r.message.lower())

    # Clear-with-entry semantics (delete + renumber) are canonical in
    # test_currently.py::test_clear_drops_and_renumbers; the job is a thin
    # wrapper whose routing is covered by the no-op path below.

    def test_clear_missing_entry_returns_friendly_no_op(self):
        r = _run(currently_job.clear_value(_base.JobContext(), type_label="Reading"))
        self.assertTrue(r.ok)
        self.assertIn("nothing to clear", r.message.lower())


class ReorderTests(_NoopRefireMixin, DBTestCase):
    def setUp(self):
        super().setUp()
        _set_active_window()
        for lbl in ("Listening", "Watching", "Reading"):
            _run(currently_job.set_value(_base.JobContext(), type_label=lbl, value=lbl[0]))

    def test_reorder_with_comma_separated_permutation(self):
        r = _run(currently_job.reorder(_base.JobContext(), labels="Watching, Reading, Listening"))
        self.assertTrue(r.ok)
        self.assertEqual(r.data["order"], ["Watching", "Reading", "Listening"])

    def test_reorder_missing_label_refused(self):
        r = _run(currently_job.reorder(_base.JobContext(), labels="Watching, Reading"))
        self.assertFalse(r.ok)
        # DB still untouched — entries keep their insertion order.
        rows = db.currently_get_entries(458)
        self.assertEqual([x["type_label"] for x in rows], ["Listening", "Watching", "Reading"])

    def test_reorder_empty_string_refused(self):
        r = _run(currently_job.reorder(_base.JobContext(), labels="  ,  ,  "))
        self.assertFalse(r.ok)


class TypePoolTests(_NoopRefireMixin, DBTestCase):
    def test_add_type_then_use(self):
        r = _run(currently_job.add_type(_base.JobContext(), label="Surfing"))
        self.assertTrue(r.ok)
        self.assertEqual(r.data["label"], "Surfing")
        # New type appears in the pool.
        self.assertIn("Surfing", [t["label"] for t in db.currently_list_types()])

    # Duplicate-add refusal is canonical in test_currently.py::
    # test_add_type_duplicate_refused; the job's CurrentlyError→error
    # mapping is covered by test_set_unknown_type_errors_with_hint.

    def test_retire_type_marks_inactive(self):
        r = _run(currently_job.retire_type(_base.JobContext(), label="Drinking"))
        self.assertTrue(r.ok)
        actives = {t["label"] for t in db.currently_list_types() if t["is_active"]}
        self.assertNotIn("Drinking", actives)


class ListStateTests(_NoopRefireMixin, DBTestCase):
    def setUp(self):
        super().setUp()
        _set_active_window()

    def test_list_state_shows_filled_and_stale(self):
        _run(currently_job.set_value(_base.JobContext(), type_label="Listening", value="L"))
        r = _run(currently_job.list_state(_base.JobContext()))
        self.assertTrue(r.ok)
        self.assertIn("WT458", r.message)
        self.assertIn("Listening", r.message)
        self.assertIn("Stale picks", r.message)


class ModalTests(_NoopRefireMixin, DBTestCase):
    def test_build_modal_no_active_window(self):
        modal, err = currently_job.build_modal(_base.JobContext(), type_label="Reading")
        self.assertIsNone(modal)
        self.assertIsNotNone(err)

    def test_build_modal_unknown_type(self):
        _set_active_window()
        modal, err = currently_job.build_modal(_base.JobContext(), type_label="Surfing")
        self.assertIsNone(modal)
        self.assertIn("add-type", (err or "").lower())

    def test_build_modal_prefills_existing_value(self):
        _set_active_window()
        _run(currently_job.set_value(_base.JobContext(), type_label="Reading", value="The Lathe of Heaven"))
        modal, err = currently_job.build_modal(_base.JobContext(), type_label="Reading")
        self.assertIsNone(err)
        self.assertIsNotNone(modal)
        self.assertEqual(modal.input.default, "The Lathe of Heaven")


if __name__ == "__main__":
    unittest.main()
