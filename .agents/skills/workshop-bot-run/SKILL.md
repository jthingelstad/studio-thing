---
name: workshop-bot-run
description: Run workshop_bot in the foreground locally with live monitoring of startup, errors, and connection events. Use when Jamie wants to bring up the four persona bots (Eddy, Linky, Marky, Patty + optional Thingy) directly — not as a launchd daemon — so we can iterate on changes and watch logs in real time.
user-invocable: true
allowed-tools:
  - Bash
  - Monitor
---

# /workshop-bot-run — Run workshop_bot locally in the foreground

Bring the workshop bot up directly via the repo venv, with a Monitor armed on the output so startup, errors, and connection blips surface as notifications in chat.

## Preflight

Before launching:

1. **Refuse to start a second instance.** If `launchctl list | grep -q com.weeklything.workshop-bot` returns true, the launchd daemon is still running on this machine. Tell Jamie and offer to stop it first via `apps/workshop_bot/scripts/admin.sh stop` — do not start a second copy in parallel (they'd both try to claim the same Discord tokens and clobber each other's gateway sessions).

2. **Refuse to start if another foreground run is already alive.** `pgrep -f "apps.workshop_bot.bot"` should return nothing. If it returns a PID, tell Jamie which task ID it's under (or that an unmanaged instance is running) and stop before launching a new one.

3. **Verify the venv exists.** `venv/bin/python -V` should print a Python 3.x version. If not, abort and surface the venv-creation command from `apps/workshop_bot/scripts/admin.sh`.

## Launch

Run from the repo root, in the background so the Monitor can attach:

```
venv/bin/python -m apps.workshop_bot.bot 2>&1
```

via Bash with `run_in_background: true`. Note the task ID — Jamie may ask to stop it later.

Then immediately attach a persistent Monitor to the task's output file so we get notifications for the things worth surfacing:

```
tail -f <output-file> 2>/dev/null | grep -E --line-buffered "online as|ready|startup|ERROR|CRITICAL|Traceback|Exception|LoginFailure|connection|Shutting|gateway|reconnect|disconnect|FAIL"
```

`persistent: true` so the watch lasts the session. The grep alternation covers both happy-path startup ("online as", "ready") and every failure signature you'd want to act on (tracebacks, gateway disconnects, login failures) — silence on a crash would look identical to "still running."

## After launch

Tell Jamie:
- The background task ID for the bot process (so he can ask to stop it).
- That events will arrive in chat as the personas come online or anything misbehaves.
- That `Ctrl+C` won't reach the background process — when he wants to stop it, ask and use `TaskStop` on the bot's task ID.

## Stopping

When Jamie says to stop:
1. `TaskStop` the bot's background task ID. The Python process receives SIGTERM, discord.py disconnects cleanly.
2. `TaskStop` the Monitor task as well.
3. Confirm with `pgrep -f "apps.workshop_bot.bot"` returning no PIDs.

Do not `kill -9` unless a graceful stop hangs for more than ~10 seconds — clean shutdown lets discord.py close gateway connections so Discord doesn't think the bots crashed.
