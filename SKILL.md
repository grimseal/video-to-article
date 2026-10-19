---
name: video-to-article
description: "Turn a video into an illustrated text article — pull the subtitles, scan every frame to find the diagrams, charts and slides, cut screenshots and short mp4 excerpts of the animated parts, and assemble a Markdown write-up plus a styled HTML page where the clips play inline. Use whenever someone wants to read a video instead of watching it — \"text version of this video\", \"transcribe this YouTube link with screenshots\", \"pull the slides or diagrams out of this talk\", \"конспект видео\", \"текстовая версия ролика\", \"достань схемы из видео\". Works on a YouTube URL or a local video file."
---

# Video → illustrated article

Produce something better than a transcript: a readable article, in the video's own
order, with the speaker's diagrams and charts dropped in where they are discussed,
and short video excerpts where a still frame would lose the point.

All the mechanical work is in `scripts/vidnotes.py`. Your job is the judgement:
which frames are worth showing, and writing the prose.

## Requirements

Check both before the first command — the script cannot report a missing Python,
because a missing Python is what stops it running at all:

```bash
python --version && ffmpeg -version
```

Any version of Python 3 will do. If either is missing, tell the user what to
install rather than guessing at a workaround:

```bash
winget install Python.Python.3 Gyan.FFmpeg      # Windows
brew install python ffmpeg                      # macOS
```

`yt-dlp` and `markdown` need no attention — the script pip-installs them into the
user site on first use. `ffmpeg`/`ffprobe` are found on PATH, or via the `FFMPEG` /
`FFPROBE` environment variables.

Invoke as `python <skill>/scripts/vidnotes.py <cmd> --out <proj> ...`. Every command
takes the same `--out` project directory and lays out:

```
<proj>/.vidnotes/ video.mp4, subs.srt, transcript.txt, meta.txt, sheets/, probe/, check_*.png
<proj>/images/    screenshots
<proj>/clips/     excerpts
<proj>/README.md  the article you write
<proj>/index.html the rendered page
```

`.vidnotes/` holds the sources and every intermediate. It is dot-prefixed and
carries the Windows hidden attribute, so the project folder shows only the four
things the user actually wants. Nothing in the article links into it, so it can be
deleted wholesale — and it is nearly all of the disk footprint, because the video
lives there.

Put the project somewhere the user can open it — inside the working directory,
not in a temp folder.

## Workflow

### 1. Fetch

```
vidnotes.py fetch "<url-or-local-file>" --out <proj> [--lang en] [--height 1080]
```

Prints title, uploader, duration, date; writes `.vidnotes/subs.srt`, a deduplicated
`.vidnotes/transcript.txt` with `[M:SS]` timecodes, and `.vidnotes/video.mp4`.

### 2. Read the transcript

Read `.vidnotes/transcript.txt` end to end before anything else. It gives you the
argument, the section boundaries and the numbers. Auto-captions have no
punctuation and mangle names — treat spellings as unreliable and check anything
you quote against a screenshot.

### 3. Scan every frame for graphics

```
vidnotes.py sheets --out <proj> [--interval 4]
```

Tiles the whole video into contact sheets and **prints a tile → timestamp grid for
each sheet**. Read the sheets with the Read tool. Use the printed grid to turn a
tile position into a timestamp — do not count tiles by eye.

Note every timestamp showing a diagram, chart, slide, code panel or UI mock, and
skip the talking-head shots. 4 s is right for a dense explainer; raise it for a
long talk, lower it for fast cuts.

**Do not pick timestamps from the subtitles alone.** Graphics routinely finish
animating 1–4 s after the line that introduces them, and some appear with no
narration at all.

### 4. Confirm the exact moment

```
vidnotes.py probe --out <proj> 93 1:36 2:56
```

Tiles those specific timestamps into one sheet so you can see which is the right
one. Pick the **latest** moment where the graphic is still complete — a frame
grabbed mid-build shows a half-drawn chart.

### 5. Cut the screenshots

Write a spec file (or pipe it in), one `TIME|name` per line, numbered so they sort
in reading order:

```
37|01-changes-per-day
1:36|02-two-repos
```

```
vidnotes.py frames --out <proj> --spec frames.txt
```

Writes full-resolution PNGs to `images/` and a `.vidnotes/check_*.png` contact sheet.
**Look at the check sheet.** On a first pass expect a handful to have landed early;
re-run those timestamps through `probe` and cut them again.

### 6. Cut clips for the animated parts

```
vidnotes.py clips --out <proj> --spec clips.txt     # START|DURATION|name
```

Only where motion carries meaning — a diagram assembling itself, a counter running
away, a sequence of states. 15–25 s each, five or so for a 10-minute video. A
static diagram does not need a clip; prefer the screenshot.

### 7. Write the article

Write `<proj>/README.md` yourself, in the user's language, following the video's
order. Reference each picture where it is discussed:

```markdown
![Short caption](images/01-changes-per-day.png)

🎬 **Отрывок:** [what it shows](clips/A-layers-building.mp4) (1:22–1:37)
```

Any paragraph containing a link to `clips/*.mp4` becomes an inline player; the
rest of that paragraph becomes the caption.

Write it **in your own words**, restructured into sections with headings — a
condensed version, not a line-by-line transcript. That is both the better read and
the right call on someone else's copyrighted video. The verbatim transcript stays
in `.vidnotes/` if the user wants it. Keep: section timecodes, every concrete number,
and the author's own caveats. Open with the source (title, channel, duration, date,
URL) and close with a short conclusion.

### 8. Render

```
vidnotes.py html --out <proj> [--lang ru]
```

Builds `index.html` — light/dark aware, images clickable to full size, clips
playing inline — and reports any referenced asset that is missing. Fix anything it
flags.

Tell the user the folder, link `README.md` and `index.html`, and give them a
command to open the page:

```bash
start "" "<proj>\index.html"
```

## Gotchas

- **The built-in browser cannot open `file://`**, so you cannot preview the page
  there. Verify by checking the `html` command's asset report instead.
- **Do not publish this as an artifact.** It is built from screenshots of someone
  else's video; keep it local unless the user asks otherwise.
- **ffmpeg's `-pattern_type glob` is unavailable in many Windows builds.** The
  script works around it by copying files to sequential names; reuse
  `tile_images()` rather than writing a new glob call.
- **`python -I` hides user site-packages**, so `yt-dlp` and `markdown` disappear.
  Run the script as plain `python`.
- `fetch --no-video` grabs subtitles only — useful to check the transcript before
  committing to a large download.
