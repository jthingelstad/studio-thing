"""Pricing helper in :mod:`tools.llm.anthropic_client`.

Co-locates a regression-style test for the rate table and ``cost_usd``
helper, so the in-process callers (AgentRun analytics, exercise harness,
ad-hoc scripts) and the workshop-bot-llm-usage SKILL stay in sync —
when Anthropic changes prices, this catches an out-of-date table the
first time a developer runs the suite.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.llm import anthropic_client  # noqa: E402


class CostHelper(unittest.TestCase):
    def test_known_model_costs(self):
        # 1M input + 1M output on Sonnet ⇒ $3 + $15 = $18.00.
        cost = anthropic_client.cost_usd(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        self.assertEqual(cost, 18.00)

    def test_cache_tokens_priced_separately(self):
        # Cache reads are cheap (~10% of input), cache writes a touch
        # pricier than input — verify both lanes contribute.
        cost = anthropic_client.cost_usd(
            "claude-haiku-4-5-20251001",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=1_000_000,
            cache_create_tokens=1_000_000,
        )
        # haiku: input=$1, cache_read=$0.10, cache_create=$1.25 ⇒ $2.35
        self.assertAlmostEqual(cost, 2.35, places=4)

    def test_unknown_model_returns_none(self):
        # Distinguish "untracked" (caller can flag for follow-up) from
        # "zero" (genuinely free) — None is the explicit "no rate" signal.
        self.assertIsNone(anthropic_client.cost_usd("claude-future-1"))
        self.assertIsNone(anthropic_client.cost_usd(None))

    def test_all_registered_models_priced(self):
        # Every model exposed in MODELS must have a rate — otherwise an
        # agent_runs row will quietly show cost_usd=None.
        for model_id in anthropic_client.MODELS.values():
            self.assertIn(model_id, anthropic_client.RATES_USD_PER_MTOK,
                          f"missing rates for registered model {model_id!r}")


if __name__ == "__main__":
    unittest.main()
