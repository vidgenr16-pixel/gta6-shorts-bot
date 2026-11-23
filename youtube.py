"""Downloads a YouTube video (yours, or one you have permission to reuse) so the editor can cut shorts from it."""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import config

log = logging.getLogger(__name__)

URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?\S*?v=|shorts/|live/|embed/)|youtu\.be/)[\w-]{11}\S*",
    re.IGNORECASE,
)


@dataclass
class Video:
    path: Path
    title: str
    duration: float


class TooLong(Exception):
    pass


def find_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    if not m:
        return None
    url = m.group(0)
    return url if url.lower().startswith("http") else "https://" + url


def _options() -> dict:
    import yt_dlp

    args = [
        "--no-playlist",
        "--js-runtimes", "node",  # YouTube needs a JavaScript runtime; Node.js or Deno
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "--merge-output-format", "mp4",
        "-o", str(config.SOURCES / "yt-%(id)s.%(ext)s"),
        "--quiet", "--no-warnings", "--no-progress",
    ]
    return yt_dlp.parse_options(args).ydl_opts


def download(url: str) -> Video:
    import yt_dlp

    with yt_dlp.YoutubeDL(_options()) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("is_live"):
            raise TooLong("That stream is still live. Send it again after it ends.")
        duration = float(info.get("duration") or 0)
        if duration > config.MAX_YT_MINUTES * 60:
            raise TooLong(
                f"That video is {duration / 60:.0f} min long; the limit is {config.MAX_YT_MINUTES} min "
                "(set MAX_YT_MINUTES in .env to change it)."
            )
        info = ydl.extract_info(url, download=True)
        path = Path(info["requested_downloads"][0]["filepath"])
    log.info("downloaded %s (%.0fs) -> %s", info.get("title"), duration, path.name)
    return Video(path=path, title=info.get("title") or "", duration=duration)
