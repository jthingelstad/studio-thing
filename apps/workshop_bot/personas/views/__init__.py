"""Persistent Discord UI views for workshop_bot.

These are `discord.ui.View`s with `timeout=None` and static `custom_id`s,
registered once on a persona bot at startup (`bot.add_view(...)`) so button
clicks route to the right handler even after a restart.
"""
