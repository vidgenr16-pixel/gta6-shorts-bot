"""Telegram bot: send it GTA 6 gameplay clips, it edits them into captioned shorts
and posts one every day at POST_TIME.

Commands (owner only):
  /start            help
  /status           queue size + next post time
  /queue            list queued shorts
  /postnow          post the next short right now
  /settime HH:MM    change the daily post time
  /hook <id> <text> re-render a queued short with a new hook
  /skip <id>        delete a queued short
"""
import asyncio
import datetime as dt
import json
import logging
import shutil
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

import config
import editor

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

TZ = ZoneInfo(config.TIMEZONE)
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
edit_lock = asyncio.Lock()  # one render at a time


# ---------- helpers ----------

def load_settings() -> dict:
    if config.SETTINGS_FILE.exists():
        return json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    return {"post_time": config.POST_TIME}


def save_settings(s: dict):
    config.SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def queue() -> list[dict]:
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in config.READY.glob("*/meta.json")]
    return sorted(metas, key=lambda m: m["created"])


def post_text(m: dict) -> str:
    return f"{m['caption']}\n\n{' '.join(m['hashtags'])}"[:1024]


def owner_only(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != config.OWNER_ID:
            if update.effective_message:
                await update.effective_message.reply_text(
                    f"This bot is private. (Your Telegram ID is {user.id if user else '?'}; "
                    "put it in OWNER_ID in .env if this is your bot.)"
                )
            return
        return await fn(update, context)
    return wrapper


def buttons(sid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Post now", callback_data=f"post:{sid}"),
        InlineKeyboardButton("🗑 Discard", callback_data=f"skip:{sid}"),
    ]])


async def send_preview(context: ContextTypes.DEFAULT_TYPE, m: dict):
    with open(config.READY / m["id"] / "short.mp4", "rb") as f:
        await context.bot.send_video(
            config.OWNER_ID, f, supports_streaming=True, write_timeout=300, read_timeout=300,
            caption=f"✅ Ready ({m['id']})\nHook: {m['hook']}\n\n{post_text(m)}"[:1024],
            reply_markup=buttons(m["id"]),
        )


async def edit_and_report(context: ContextTypes.DEFAULT_TYPE, src: Path, note: str):
    async with edit_lock:
        try:
            made = await asyncio.to_thread(editor.make_shorts, src, note)
        except Exception as e:  # noqa: BLE001 - report any render failure to the owner
            log.exception("editing failed")
            await context.bot.send_message(config.OWNER_ID, f"❌ Couldn't edit {src.name}: {e}")
            return
    for m in made:
        await send_preview(context, m)
    await context.bot.send_message(config.OWNER_ID, f"📦 {len(queue())} short(s) in the queue.")


async def post_short(context: ContextTypes.DEFAULT_TYPE, m: dict):
    folder = config.READY / m["id"]
    with open(folder / "short.mp4", "rb") as f:
        await context.bot.send_video(
            config.POST_CHAT_ID, f, caption=post_text(m), supports_streaming=True,
            write_timeout=300, read_timeout=300,
        )
    shutil.move(str(folder), str(config.POSTED / m["id"]))
    log.info("posted %s", m["id"])


# ---------- scheduled jobs ----------

async def daily_post(context: ContextTypes.DEFAULT_TYPE):
    q = queue()
    if not q:
        await context.bot.send_message(config.OWNER_ID, "⚠️ Daily post skipped: the queue is empty. Send me some clips!")
        return
    await post_short(context, q[0])
    left = len(q) - 1
    msg = f"📤 Posted today's short: {q[0]['hook']}\n{left} left in the queue."
    if left < 3:
        msg += " Running low, send more clips."
    await context.bot.send_message(config.OWNER_ID, msg)


async def scan_drop_folder(context: ContextTypes.DEFAULT_TYPE):
    """Big recordings (> 20 MB) can't go through Telegram; drop them in the drop folder instead."""
    for p in sorted(config.DROP.iterdir()):
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        size = p.stat().st_size
        await asyncio.sleep(2)
        if p.stat().st_size != size:  # still being copied
            continue
        dest = config.SOURCES / f"{int(time.time())}-{p.name}"
        shutil.move(str(p), str(dest))
        await context.bot.send_message(config.OWNER_ID, f"🎬 Found {p.name} in the drop folder, editing…")
        await edit_and_report(context, dest, "")


def schedule_daily(app: Application, hhmm: str):
    for job in app.job_queue.get_jobs_by_name("daily"):
        job.schedule_removal()
    h, m = map(int, hhmm.split(":"))
    app.job_queue.run_daily(daily_post, dt.time(h, m, tzinfo=TZ), name="daily")


# ---------- commands ----------

@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 GTA 6 Shorts Bot\n\n"
        "Send me gameplay clips (video or file, up to 20 MB). Add a caption to the video "
        "to tell me what happens, e.g. \"cop chase ends in the ocean\".\n"
        "For bigger recordings, put them in the 'drop' folder next to my code (Google Drive works).\n\n"
        "I find the best moments, cut 9:16 shorts with a hook and word-by-word captions, "
        f"and post one every day at {load_settings()['post_time']} ({config.TIMEZONE}).\n\n"
        "/status  /queue  /postnow  /settime HH:MM  /hook <id> <text>  /skip <id>"
    )


@owner_only
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs_by_name("daily")
    nxt = jobs[0].next_t.astimezone(TZ).strftime("%a %d %b %H:%M") if jobs and jobs[0].next_t else "not scheduled"
    await update.message.reply_text(
        f"Queue: {len(queue())} short(s)\nNext post: {nxt} ({config.TIMEZONE})\n"
        f"Posting to: {config.POST_CHAT_ID}\nPosted so far: {len(list(config.POSTED.iterdir()))}"
    )


@owner_only
async def list_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = queue()
    if not q:
        await update.message.reply_text("Queue is empty.")
        return
    lines = [f"{i + 1}. {m['id']} — {m['hook']}" for i, m in enumerate(q)]
    await update.message.reply_text("Next up first:\n" + "\n".join(lines))


@owner_only
async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = queue()
    if not q:
        await update.message.reply_text("Queue is empty.")
        return
    await post_short(context, q[0])
    await update.message.reply_text(f"📤 Posted: {q[0]['hook']}")


@owner_only
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hhmm = context.args[0]
        h, m = map(int, hhmm.split(":"))
        assert 0 <= h < 24 and 0 <= m < 60
    except (IndexError, ValueError, AssertionError):
        await update.message.reply_text("Usage: /settime 18:30")
        return
    hhmm = f"{h:02d}:{m:02d}"
    s = load_settings()
    s["post_time"] = hhmm
    save_settings(s)
    schedule_daily(context.application, hhmm)
    await update.message.reply_text(f"⏰ Daily post time set to {hhmm} ({config.TIMEZONE}).")


@owner_only
async def set_hook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2 or not (config.READY / context.args[0]).exists():
        await update.message.reply_text("Usage: /hook <id> <new hook text>  (ids are in /queue)")
        return
    sid, text = context.args[0], " ".join(context.args[1:])
    await update.message.reply_text("✏️ Re-rendering…")
    async with edit_lock:
        m = await asyncio.to_thread(editor.rerender, sid, text)
    await send_preview(context, m)


@owner_only
async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = context.args[0] if context.args else ""
    if not sid or not (config.READY / sid).exists():
        await update.message.reply_text("Usage: /skip <id>  (ids are in /queue)")
        return
    shutil.rmtree(config.READY / sid)
    await update.message.reply_text(f"🗑 Removed {sid}.")


@owner_only
async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    media = msg.video or msg.document
    if media.file_size and media.file_size > 20 * 1024 * 1024:
        await msg.reply_text(
            "That file is over 20 MB, which Telegram won't let bots download. "
            "Put it in the 'drop' folder next to my code (you can upload it to Google Drive from your phone) and I'll pick it up within a minute."
        )
        return
    name = getattr(media, "file_name", None) or "clip.mp4"
    dest = config.SOURCES / f"{int(time.time())}-{Path(name).stem}{Path(name).suffix or '.mp4'}"
    tg_file = await media.get_file(read_timeout=120)
    await tg_file.download_to_drive(dest, read_timeout=300)
    await msg.reply_text("🎬 Got it, editing… (first clip takes longer while the caption model downloads)")
    context.application.create_task(edit_and_report(context, dest, msg.caption or ""))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != config.OWNER_ID:
        await q.answer("Not allowed")
        return
    action, sid = q.data.split(":", 1)
    folder = config.READY / sid
    if not folder.exists():
        await q.answer("Already posted or removed")
        return
    if action == "post":
        m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        await q.answer("Posting…")
        await post_short(context, m)
        await q.edit_message_reply_markup(None)
        await context.bot.send_message(config.OWNER_ID, f"📤 Posted: {m['hook']}")
    elif action == "skip":
        shutil.rmtree(folder)
        await q.answer("Discarded")
        await q.edit_message_reply_markup(None)


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env first (see README.md).")
    if not config.OWNER_ID:
        log.warning("OWNER_ID not set: message the bot to get your ID, put it in .env, then restart.")
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("queue", list_queue))
    app.add_handler(CommandHandler("postnow", post_now))
    app.add_handler(CommandHandler("settime", set_time))
    app.add_handler(CommandHandler("hook", set_hook))
    app.add_handler(CommandHandler("skip", skip))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, on_video))
    app.add_handler(CallbackQueryHandler(on_button))
    if config.OWNER_ID:
        schedule_daily(app, load_settings()["post_time"])
        app.job_queue.run_repeating(scan_drop_folder, interval=60, first=10, name="drop")
    log.info("bot running; daily post at %s %s", load_settings()["post_time"], config.TIMEZONE)
    app.run_polling()


if __name__ == "__main__":
    main()
