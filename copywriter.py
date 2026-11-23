"""Writes the on-screen hook + the post caption for each short.

Uses Claude when ANTHROPIC_API_KEY is set, otherwise falls back to templates.
"""
import json
import logging
import random

import config

log = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "caption", "hashtags"],
    "additionalProperties": False,
}

SYSTEM = """You write copy for vertical gaming shorts (YouTube Shorts, TikTok, Reels, Telegram) made from GTA 6 gameplay clips.

For each clip you return:
- hook: the big text burned onto the top of the video for the whole clip. 3 to 8 words, punchy, curiosity or humour, written like a real gamer posting, not like an ad. Plain text only: no emoji, no hashtags, no quotes (the video font can't draw emoji).
- caption: the post text, 1 to 2 short lines. One emoji at most. End with a light question or call to comment when it fits naturally.
- hashtags: 4 to 7 hashtags including #GTA6, each starting with #.

Base everything on what the clip's transcript and the creator's note actually show. Don't invent story spoilers, release news, or features that aren't in the clip. If the transcript is empty or is noise, write around the creator's note or a general gameplay moment."""

FALLBACK_HOOKS = [
    "Vice City has no chill",
    "Wait for the ending",
    "GTA 6 physics are unreal",
    "Leonida stays wild",
    "I did not plan this",
    "This game is too good",
    "Only in GTA 6",
    "Watch till the end",
]
FALLBACK_CAPTIONS = [
    "Leonida never disappoints 🌴 What would you have done?",
    "Just another day in Vice City. Rate this 1-10",
    "GTA 6 moments hit different 🔥",
    "Did not see that coming. Drop your best GTA 6 clip below",
]


def _fallback(note: str) -> dict:
    return {
        "hook": note[:60] if note else random.choice(FALLBACK_HOOKS),
        "caption": random.choice(FALLBACK_CAPTIONS),
        "hashtags": config.HASHTAGS.split(),
    }


def write_copy(transcript: str, note: str = "", recent_hooks: list[str] | None = None) -> dict:
    if not config.ANTHROPIC_API_KEY:
        return _fallback(note)

    import anthropic

    prompt = (
        f"Creator's note: {note or '(none)'}\n"
        f"Transcript of the clip's audio (may be game dialogue, radio or noise):\n{transcript or '(no speech detected)'}\n"
        f"Hooks used on recent posts, don't repeat them: {', '.join(recent_hooks or []) or '(none)'}"
    )
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if the model declines, the API retries on a fallback model
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            log.warning("Claude declined to write copy; using template")
            return _fallback(note)
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        data["hook"] = data["hook"].strip().strip('"')
        data["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in data["hashtags"]]
        return data
    except anthropic.RateLimitError:
        log.warning("Claude rate-limited; using template")
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; using template", e.status_code)
    except anthropic.APIConnectionError:
        log.warning("Can't reach Claude API; using template")
    except (StopIteration, json.JSONDecodeError, KeyError):
        log.warning("Unexpected Claude response; using template")
    return _fallback(note)
