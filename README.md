# video-to-article

A [Claude Code](https://claude.com/claude-code) skill that turns a video into an
illustrated article you can actually read.

It pulls the subtitles, scans **every frame** to find the diagrams, charts and
slides, cuts screenshots at the moment each graphic is fully drawn, cuts short mp4
excerpts where motion carries the meaning, and assembles a Markdown write-up plus a
styled HTML page where the clips play inline.

Works on a YouTube URL or a local video file.

## What you end up with

```
my-article/
  README.md      the article
  index.html     same article, clips playing inline, light/dark aware
  images/        screenshots of every diagram and chart
  clips/         short excerpts of the animated bits
  .vidnotes/     hidden: source video, subtitles, transcript, working sheets
```

`.vidnotes/` is where the weight is (the video) and nothing in the article links
into it, so it can be deleted once you are done.

## Install

Drop this folder into your Claude Code skills directory, keeping its name:

```
~/.claude/skills/video-to-article/
  SKILL.md
  scripts/vidnotes.py
```

On Windows that is `%USERPROFILE%\.claude\skills\video-to-article\`.

Claude Code picks it up on the next session. There is no registration step.

## Requirements

- **Python 3** — any version
- **ffmpeg** (with `ffprobe`) on PATH

```bash
winget install Python.Python.3 Gyan.FFmpeg      # Windows
brew install python ffmpeg                      # macOS
sudo apt install python3 ffmpeg                 # Debian/Ubuntu
```

`yt-dlp` and `markdown` install themselves on first use.

## Use

Just ask:

> make a text version of https://youtube.com/watch?v=... with the diagrams

Claude reads the transcript, looks through the contact sheets to find the graphics,
picks the frames, writes the article, and renders the page. The skill tells it how.

### Driving the script yourself

```
vidnotes.py fetch "<url|file>" --out <proj>     # subtitles + video + transcript
vidnotes.py sheets --out <proj>                 # tile the whole video, print a
                                                #   tile -> timestamp map
vidnotes.py probe  --out <proj> 93 1:36 2:56    # compare specific moments
vidnotes.py frames --out <proj> --spec f.txt    # TIME|name          -> images/
vidnotes.py clips  --out <proj> --spec c.txt    # START|DUR|name     -> clips/
vidnotes.py html   --out <proj>                 # README.md          -> index.html
```

Every command takes the same `--out` project directory. Timestamps accept `93`,
`1:33` or `0:01:33`.

## Why scan every frame

Picking timestamps from the subtitles alone does not work. Graphics routinely
finish animating 1–4 seconds after the line that introduces them, and some appear
with no narration at all. So the skill tiles the whole video into contact sheets,
has the model actually look at them, then confirms the exact moment with `probe`
before cutting — and checks its own work on a contact sheet afterwards.

In the HTML, any paragraph containing a link to `clips/*.mp4` becomes an inline
player, and the rest of that paragraph becomes the caption:

```markdown
🎬 **Clip:** [how the diagram assembles](clips/A-layers.mp4) (1:22–1:37)
```

## A note on what you make with it

The article is written in the model's own words, restructured into sections — not a
verbatim transcript. That is both the better read and the right call on someone
else's video. The raw transcript stays in `.vidnotes/` if you want it.

If you publish the result anywhere, credit the source video and link it.

## License

MIT — see [LICENSE](LICENSE).
