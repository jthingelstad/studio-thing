"""agent_loop.first_turn_tool_choice — forces a tool call on the opening turn
only, then reverts to auto so the model can still finish with a text report."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from apps.workshop_bot.tests import _stubs  # noqa: E402

_stubs.install()

from apps.workshop_bot.tools.llm import agent_loop  # noqa: E402


def _block(**kw):
    return types.SimpleNamespace(**kw)


def _usage():
    return types.SimpleNamespace(
        input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )


class _FakeMessages:
    """Records each create() call and scripts two turns: a tool_use turn then
    a final text turn."""

    def __init__(self):
        self.calls = []
        self._turn = 0

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self._turn += 1
        if self._turn == 1:
            return types.SimpleNamespace(
                content=[_block(type="tool_use", id="t1", name="draft__section_status", input={})],
                stop_reason="tool_use",
                usage=_usage(),
            )
        return types.SimpleNamespace(
            content=[_block(type="text", text="done — clustered one.")],
            stop_reason="end_turn",
            usage=_usage(),
        )


class FirstTurnToolChoiceTests(unittest.TestCase):
    def _run(self, **extra):
        fake = _FakeMessages()
        fake_client = types.SimpleNamespace(messages=fake)
        deps = types.SimpleNamespace()
        with (
            patch.object(agent_loop.anthropic_client, "client", return_value=fake_client),
            patch.object(agent_loop, "_build_system_blocks", return_value=[]),
            patch.object(
                agent_loop, "_build_tool_specs", return_value=[{"name": "draft__section_status"}]
            ),
            patch.object(agent_loop, "_execute_tool", return_value='{"ok": true}'),
        ):
            text, meta = agent_loop.run(
                persona="eddy",
                user_message="review",
                tools=["draft__section_status"],
                deps=deps,
                **extra,
            )
        return fake, text, meta

    def test_choice_applied_first_turn_only(self):
        fake, _text, _meta = self._run(first_turn_tool_choice={"type": "any"})
        self.assertEqual(fake.calls[0].get("tool_choice"), {"type": "any"})
        # Second turn reverts to auto (no tool_choice key).
        self.assertNotIn("tool_choice", fake.calls[1])

    def test_no_choice_by_default(self):
        fake, _text, _meta = self._run()
        self.assertNotIn("tool_choice", fake.calls[0])


if __name__ == "__main__":
    unittest.main()
