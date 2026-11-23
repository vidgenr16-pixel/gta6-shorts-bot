"""All settings come from .env (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name) or default)


def _float(name: str, default: float) -> float:
    return float(os.getenv(name) or default)


# Telegram
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = _int("OWNER_ID", 0)  # only this Telegram user can control the bot
POST_CHAT_ID = os.getenv("POST_CHAT_ID", "") or str(OWNER_ID)  # channel (@name or -100...) or your own chat
POST_TIME = os.getenv("POST_TIME", "18:00")  # daily post time, HH:MM
TIMEZONE = os.getenv("TIMEZONE", "UTC")  # e.g. Asia/Kolkata, America/New_York

# Editing
CLIP_SECONDS = _int("CLIP_SECONDS", 30)  # length of each short
MAX_SHORTS_PER_VIDEO = _int("MAX_SHORTS_PER_VIDEO", 3)  # long recordings get cut into several shorts
FG_ZOOM = _float("FG_ZOOM", 1.25)  # how much to zoom landscape gameplay inside the 9:16 frame
MUSIC_VOLUME = _float("MUSIC_VOLUME", 0.12)  # background music level (drop mp3s in data/music)
CAPTION_FONT = os.getenv("CAPTION_FONT", "Arial Black")
CHANNEL_HANDLE = os.getenv("CHANNEL_HANDLE", "")  # small watermark, e.g. @vicecityclips
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # tiny/base/small/medium; bigger = better captions, slower
HASHTAGS = os.getenv("HASHTAGS", "#GTA6 #GTAVI #ViceCity #Leonida #gaming #shorts")

# Claude writes hooks/captions if a key is set; otherwise templates are used
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

# Folders
# Working videos live in DATA_DIR (keep it off Google Drive so Drive isn't syncing big temp files)
DATA = Path(os.getenv("DATA_DIR", "") or ROOT / "data")
SOURCES = DATA / "sources"  # raw clips you sent
# Big recordings go here (Telegram bots can't download files > 20 MB). It sits next to the code,
# so if the code is in Google Drive you can upload recordings to it from your phone too.
DROP = ROOT / "drop"
READY = DATA / "ready"  # finished shorts waiting to be posted
POSTED = DATA / "posted"
MUSIC = DATA / "music"
WORK = DATA / "work"
FONTS = ROOT / "fonts"  # optional: drop .ttf files here and set CAPTION_FONT to their name
SETTINGS_FILE = DATA / "settings.json"

for d in (SOURCES, DROP, READY, POSTED, MUSIC, WORK, FONTS):
    d.mkdir(parents=True, exist_ok=True)
