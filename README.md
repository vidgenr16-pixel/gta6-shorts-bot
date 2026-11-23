# GTA 6 Shorts Bot (Telegram)

Send the bot your GTA 6 gameplay clips. It finds the best moments, edits them into
vertical 9:16 shorts with a hook and word-by-word captions, queues them, and posts
one every day at the time you choose, to your Telegram channel or to you.

## What it does to each clip

1. **Picks the action**: scans the audio for loud, sudden moments like gunfire,
   crashes and shouting, and cuts the most intense 30 s window. A long recording
   gives up to 3 shorts.
2. **Transcribes** the speech locally with Whisper to get each word's timing.
3. **Writes copy**: a big on-screen hook, a post caption and hashtags. Claude writes
   these if you add an Anthropic API key. Otherwise it uses templates, or your own
   text if you put a caption on the video you send.
4. **Renders** a 1080×1920 short with a blurred background fill, zoomed gameplay,
   the hook at the top, captions that highlight the current word, loudness
   normalisation and optional background music.

Every finished short comes back to you as a preview with **🚀 Post now** and
**🗑 Discard** buttons. Anything you don't discard is posted in order, one per day.

## Setup (Windows)

The code can live anywhere, including Google Drive. The Python environment and the
working videos live in `C:\gta6bot`, which keeps Drive from syncing big temporary files
and keeps the path short (Whisper's DLL won't load from very deep folders).

1. Install Python 3.11+ and ffmpeg (`winget install Gyan.FFmpeg`).
2. Copy `.env.example` to `.env`. In Telegram, open **@BotFather**, send `/newbot`,
   and paste the token after `TELEGRAM_BOT_TOKEN=` in `.env`.
3. Double-click `start-bot.bat`. The first run installs everything into `C:\gta6bot`.
4. Message your bot in Telegram. It replies with your Telegram ID. Put that after
   `OWNER_ID=` in `.env`, close the bot window and double-click `start-bot.bat` again.
5. Optional: to post to a channel, add the bot to the channel as an admin and set
   `POST_CHAT_ID=@yourchannel`.
6. Optional: set `ANTHROPIC_API_KEY` for AI-written hooks and captions, drop
   royalty-free `.mp3` files into `C:\gta6bot\data\music`, and set `CHANNEL_HANDLE`
   for a watermark.

Finished shorts are in `C:\gta6bot\data\ready` (queued) and `C:\gta6bot\data\posted`.

Keep the bot running (leave the window open, or use Task Scheduler "at log on") so the
daily post goes out.

## Using it

| Do this | Result |
|---|---|
| Send a video, with a caption like "cop chase ends in the ocean" | Edits it; the caption steers the hook |
| Recording over 20 MB | Put it in the `drop` folder next to the code (in Google Drive, so your phone works too). The bot picks it up within a minute (Telegram won't let bots download files over 20 MB) |
| `/queue` | Lists the queued shorts and their ids |
| `/status` | Shows queue size and the next post time |
| `/postnow` | Posts the next short immediately |
| `/settime 19:30` | Changes the daily post time |
| `/hook <id> <text>` | Re-renders a queued short with a new hook |
| `/skip <id>` | Deletes a queued short |

Test the editor without Telegram: `C:\gta6bot\.venv\Scripts\python editor.py myclip.mp4 "optional note"`.
The result goes to `C:\gta6bot\data\ready\<id>\short.mp4`.

## Notes

- Use your own gameplay recordings. Re-uploading other people's clips or Rockstar's
  trailers will get you copyright strikes on YouTube and TikTok.
- Every finished short is also saved as `C:\gta6bot\data\ready\<id>\short.mp4`, with its caption
  in `meta.json`, so you can upload the same file to YouTube Shorts, TikTok and Reels.
- Captions come from speech (character dialogue, your mic). Clips with no talking
  get only the hook text.
