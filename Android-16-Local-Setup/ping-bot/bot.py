import json
import sys
import random
import os
import atexit
import discord
from discord.ext import tasks
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Single-instance lock ──────────────────────────────────────────────
# Prevents multiple bot instances from running simultaneously.
LOCK_FILE = Path(__file__).parent / "bot.lock"


def acquire_lock():
    """Write our PID to a lockfile. Exit if another instance is running."""
    if LOCK_FILE.exists():
        old_pid = LOCK_FILE.read_text().strip()
        # Check if that PID is actually still alive
        try:
            os.kill(int(old_pid), 0)  # signal 0 = just check existence
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ABORT: Another bot instance is already running (PID {old_pid}). Exiting.")
            sys.exit(0)
        except (OSError, ValueError):
            # Old process is dead, stale lockfile — we can take over
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Stale lockfile found (PID {old_pid}), taking over.")
    LOCK_FILE.write_text(str(os.getpid()))
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Lock acquired (PID {os.getpid()})")


def release_lock():
    """Remove lockfile on exit."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


acquire_lock()
atexit.register(release_lock)

# ── Config ────────────────────────────────────────────────────────────
config_path = Path(__file__).parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

TOKEN = config["token"]
CHANNEL_ID = int(config["channel_id"])

# Message variants: each slot is now a list of alternatives
# 4-step rotation: Todd solo -> Android-17 solo -> Android-16 solo -> All three
MESSAGE_SLOTS = [
    config["messages"]["todd_solo"],
    config["messages"]["android17_solo"],
    config["messages"]["android16_solo"],
    config["messages"]["both"],
]
ROTATION_SIZE = len(MESSAGE_SLOTS)  # 4

# Report card settings
REPORT_CARD_EVERY = config.get("report_card_every_n_cycles", 6)
REPORT_CARD_MESSAGE = config.get("report_card_message", "")

# Stall detection: if no successful ping in 25 min (~1.7x the 15-min interval),
# something is wrong and we should exit so the watchdog restarts us.
STALL_TIMEOUT_SECONDS = 25 * 60  # 25 min
SESSION_RESET_EVERY = 8  # every 8 pings x 15 min = 2 hours
last_successful_ping = None

# All three agent IDs for shared messages
ALL_AGENTS = "<@1469755091899908096> and <@1469775716076753010> and <@1470898132668776509>"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

cycle_step = 0        # tracks position within the 4-step rotation
total_pings = 0       # tracks total pings sent (for report card timing)


def pick_message(slot):
    """Pick a random variant from a message slot (list) or return string as-is."""
    if isinstance(slot, list):
        return random.choice(slot)
    return slot


async def send_long_message(channel, message):
    """Send a message, splitting into chunks if over Discord's 2000 char limit.
    Splits on sentence boundaries ('. ') to keep messages readable."""
    if len(message) <= 2000:
        await channel.send(message)
        return

    chunks = []
    remaining = message
    while remaining:
        if len(remaining) <= 2000:
            chunks.append(remaining)
            break
        # Find the last sentence boundary before 2000 chars
        split_at = remaining[:2000].rfind('.  ')
        if split_at == -1:
            split_at = remaining[:2000].rfind('. ')
        if split_at == -1:
            split_at = remaining[:2000].rfind(' ')
        if split_at == -1:
            split_at = 1999
        chunks.append(remaining[:split_at + 1])
        remaining = remaining[split_at + 1:].lstrip()

    for chunk in chunks:
        await channel.send(chunk)
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}]   (message split into {len(chunks)} parts)")


@tasks.loop(minutes=15)
async def ping_cycle():
    global cycle_step, total_pings, last_successful_ping
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR: Channel {CHANNEL_ID} not found")
        return

    # Cleanup: delete messages older than 2 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    try:
        deleted = await channel.purge(before=cutoff, limit=None)
        if deleted:
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CLEANUP: Deleted {len(deleted)} messages older than 2 hours")
    except discord.Forbidden:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CLEANUP ERROR: Missing manage_messages permission")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] CLEANUP ERROR: {e}")

    # Session reset: every 8 pings (2 hours), tell all agents to /new
    if total_pings > 0 and total_pings % SESSION_RESET_EVERY == 0:
        reset_msg = f"{ALL_AGENTS} -- SESSION RESET: Run /new right now to start a fresh session.  Your session context accumulates over time and will eventually overflow and crash you.  Run /new immediately, then continue with your current task.  This is mandatory maintenance, not optional."
        try:
            await send_long_message(channel, reset_msg)
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] SESSION RESET: Sent /new instruction (ping #{total_pings + 1})")
        except Exception as e:
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] SESSION RESET ERROR: {e}")
        # Brief pause to let them process the reset before the follow-up ping
        import asyncio
        await asyncio.sleep(10)

    # Check if it's report card time (every N complete cycles)
    # A complete cycle = 4 pings, so report card fires after every N*4 pings
    is_report_card = (
        REPORT_CARD_MESSAGE
        and total_pings > 0
        and total_pings % (REPORT_CARD_EVERY * ROTATION_SIZE) == 0
    )

    if is_report_card:
        message = REPORT_CARD_MESSAGE
        label = "REPORT CARD"
    else:
        slot = MESSAGE_SLOTS[cycle_step % ROTATION_SIZE]
        message = pick_message(slot)
        step_labels = ["Todd solo", "Android-17 solo", "Android-16 solo", "All three"]
        label = step_labels[cycle_step % ROTATION_SIZE]

    try:
        await send_long_message(channel, message)
        last_successful_ping = datetime.now()
        step_display = f"Step {cycle_step % ROTATION_SIZE + 1}/{ROTATION_SIZE} ({label})"
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {step_display} | Ping #{total_pings + 1}: sent message ({len(message)} chars)")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR sending message: {e}")

    # Only advance the rotation for non-report-card pings
    if not is_report_card:
        cycle_step += 1
    total_pings += 1


@ping_cycle.before_loop
async def before_ping():
    await client.wait_until_ready()


@tasks.loop(minutes=5)
async def heartbeat():
    """Check every 5 min that the bot hasn't stalled."""
    global last_successful_ping
    if last_successful_ping is None:
        return  # Haven't sent first message yet, skip
    elapsed = (datetime.now() - last_successful_ping).total_seconds()
    if elapsed > STALL_TIMEOUT_SECONDS:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] STALL DETECTED: {elapsed:.0f}s since last ping. Exiting for restart...")
        await client.close()
        sys.exit(1)
    else:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Heartbeat OK ({elapsed:.0f}s since last ping)")


@heartbeat.before_loop
async def before_heartbeat():
    await client.wait_until_ready()


WORKSPACE_REMINDER = f"{ALL_AGENTS} -- WORKSPACE MAINTENANCE REMINDER: Check your workspace file sizes right now.  MEMORY.md must stay under 10K chars and AGENTS.md must stay under 10K chars.  These files are injected into EVERY API call you make -- if they bloat, you choke on your own context before the conversation even starts.  Rule of thumb: if you don't need it on every single message, it doesn't belong in the workspace bootstrap files.  Archive old entries to memory/archive/ in your GitHub repo.  Store reference docs, detailed specs, infrastructure notes, and anything not immediately relevant in GitHub -- pull them on demand when you need them.  Keep the workspace lean, keep GitHub fat.  Run: wc -c ~/.openclaw/workspace/MEMORY.md ~/.openclaw/workspace/AGENTS.md -- and trim if needed."


@tasks.loop(minutes=90)
async def workspace_reminder():
    """Remind agents to keep workspace files lean every 90 minutes."""
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        return
    try:
        await send_long_message(channel, WORKSPACE_REMINDER)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] WORKSPACE REMINDER: Sent maintenance ping")
    except Exception as e:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] WORKSPACE REMINDER ERROR: {e}")


@workspace_reminder.before_loop
async def before_workspace_reminder():
    await client.wait_until_ready()
    # Offset so it doesn't fire immediately on startup
    import asyncio
    await asyncio.sleep(90 * 60)


@client.event
async def on_ready():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Bot connected as {client.user}")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Target channel: {CHANNEL_ID}")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Cycle: Todd -> Android-17 -> Android-16 -> All three (every 15 min)")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Message variants: {sum(len(s) if isinstance(s, list) else 1 for s in MESSAGE_SLOTS)} total across {ROTATION_SIZE} slots")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Report card: every {REPORT_CARD_EVERY} cycles ({REPORT_CARD_EVERY * ROTATION_SIZE} pings / {REPORT_CARD_EVERY * ROTATION_SIZE * 15} min)")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Stall timeout: {STALL_TIMEOUT_SECONDS}s | Heartbeat: every 5 min")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Cleanup: purging messages older than 2 hours, every ping cycle")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Session reset: /new instruction every {SESSION_RESET_EVERY} pings ({SESSION_RESET_EVERY * 15} min)")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Workspace reminder: every 90 min (first after 90 min)")
    if not ping_cycle.is_running():
        ping_cycle.start()
    if not heartbeat.is_running():
        heartbeat.start()
    if not workspace_reminder.is_running():
        workspace_reminder.start()


@client.event
async def on_disconnect():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Disconnected from Discord. Will attempt to reconnect...")


@client.event
async def on_resumed():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Reconnected to Discord successfully.")


client.run(TOKEN)
