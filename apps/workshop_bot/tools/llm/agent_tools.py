"""Compatibility facade for workshop-bot LLM tools.

The public import path stays ``tools.llm.agent_tools``. The registry and
ContextVars live in ``tool_registry.py``; local helper implementations and
Anthropic specs live in ``local_tools.py``.
"""

from __future__ import annotations

from .local_tools import (
    FUNCS,
    SPECS,
    register_local_helpers,
    t_campaigns_get,
    t_campaigns_history,
    t_campaigns_list,
    t_campaigns_set_actual_signups,
    t_current_issue_window,
    t_draft_section_status,
    t_fetch_url,
    t_followup_cancel,
    t_followup_list,
    t_followup_schedule,
    t_forget_note,
    t_get_issue,
    t_get_section,
    t_get_support_state,
    t_list_issue_windows,
    t_list_recent_issues,
    t_quote_search,
    t_react_add,
    t_read_length,
    t_recall,
    t_remember,
    t_search_archive,
    t_workspace_list_all,
    t_workspace_list_files,
    t_workspace_read,
    t_workspace_write,
)
from .tool_registry import (
    Tool,
    ToolRegistry,
    active_persona,
    active_react_target,
)

__all__ = [
    "FUNCS",
    "SPECS",
    "Tool",
    "ToolRegistry",
    "active_persona",
    "active_react_target",
    "register_local_helpers",
    "t_campaigns_get",
    "t_campaigns_history",
    "t_campaigns_list",
    "t_campaigns_set_actual_signups",
    "t_current_issue_window",
    "t_draft_section_status",
    "t_fetch_url",
    "t_followup_cancel",
    "t_followup_list",
    "t_followup_schedule",
    "t_forget_note",
    "t_get_issue",
    "t_get_section",
    "t_get_support_state",
    "t_list_issue_windows",
    "t_list_recent_issues",
    "t_quote_search",
    "t_react_add",
    "t_read_length",
    "t_recall",
    "t_remember",
    "t_search_archive",
    "t_workspace_list_all",
    "t_workspace_list_files",
    "t_workspace_read",
    "t_workspace_write",
]
