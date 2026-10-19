#!/usr/bin/env python3
"""vidnotes - turn a video into an illustrated article.

Subcommands (run `vidnotes.py <cmd> -h` for details):

  fetch   download subtitles + video (or adopt a local file), write a timed transcript
  sheets  tile the whole video into contact sheets and print the tile -> timestamp map
  probe   tile a specific list of timestamps into one sheet, to pick the exact moment
  frames  cut full-resolution screenshots from a "TIME|name" spec
  clips   cut short mp4 excerpts from a "START|DURATION|name" spec
  html    render a Markdown article into a styled page with inline <video> players

Everything lives under one project directory:

  <proj>/.vidnotes/ sources and intermediates (hidden; safe to delete)
  <proj>/images/    screenshots
  <proj>/clips/     video excerpts
  <proj>/README.md  the article you write
  <proj>/index.html the rendered page
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- utils

IS_WIN = os.name == "nt"


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def install_hint(name):
    if IS_WIN:
        return f"winget install Gyan.FFmpeg   # provides {name}"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg   # or your distro's equivalent"


def tool(name, env_var):
    """Locate an external binary, honouring an env override."""
    override = os.environ.get(env_var)
    if override:
        resolved = shutil.which(override)
        if not resolved:
            die(f"{env_var}={override!r} does not point to a runnable {name}")
        return resolved
    found = shutil.which(name)
    if not found:
        die(f"{name} not found on PATH\n"
            f"  install it:  {install_hint(name)}\n"
            f"  or point {env_var} at the executable")
    return found


def ffmpeg():
    return tool("ffmpeg", "FFMPEG")


def ffprobe():
    return tool("ffprobe", "FFPROBE")


def run(cmd, quiet=False, **kw):
    if not quiet:
        print("+", " ".join(str(c) for c in cmd[:3]), "...", flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def ensure_module(mod, pip_name=None):
    """Import a module, pip-installing it into the user site on first use."""
    try:
        return __import__(mod)
    except ImportError:
        pass
    pip_name = pip_name or mod
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--quiet", pip_name]
    print(f"installing {pip_name} ...", flush=True)
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        die(f"could not install {pip_name} ({exc})\n"
            f'  install it yourself:  "{sys.executable}" -m pip install --user {pip_name}\n'
            f"  (needs network access; behind a proxy set HTTPS_PROXY first)")
    import importlib
    importlib.invalidate_caches()
    try:
        return importlib.import_module(mod)
    except ImportError:
        die(f"{pip_name} installed but {mod} still will not import - "
            f"check that {sys.executable} sees your user site-packages")


TIME_RE = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parse_time(s):
    """Accept 93, 93.5, 1:33, 1:33.5 or 0:01:33 and return float seconds."""
    s = str(s).strip()
    m = TIME_RE.match(s)
    if not m:
        die(f"cannot parse timestamp {s!r} (use SS, MM:SS or HH:MM:SS)")
    a, b, c = m.groups()
    parts = [p for p in (a, b) if p is not None]
    total = float(c)
    if len(parts) == 1:
        total += int(parts[0]) * 60
    elif len(parts) == 2:
        total += int(parts[0]) * 3600 + int(parts[1]) * 60
    return total


def fmt_tc(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


WORKDIR = ".vidnotes"


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.work = self.root / WORKDIR
        # adopt a project laid out by an older version of this script
        if not self.work.exists() and (self.root / "work").exists():
            self.work = self.root / "work"
        self.images = self.root / "images"
        self.clips = self.root / "clips"

    def mkdirs(self):
        for d in (self.root, self.work, self.images, self.clips):
            d.mkdir(parents=True, exist_ok=True)
        self.hide_work()

    def hide_work(self):
        """Dot-prefix hides it everywhere but Explorer, which needs the attribute."""
        if IS_WIN and self.work.name.startswith("."):
            subprocess.run(["attrib", "+h", str(self.work)],
                           check=False, capture_output=True)

    @property
    def video(self):
        v = self.work / "video.mp4"
        if not v.exists():
            die(f"{v} not found - run `fetch` first")
        return v

    def duration(self):
        out = subprocess.run(
            [ffprobe(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of", "csv=p=0", str(self.video)],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        return float(out)


def read_spec(path):
    """Read a pipe-separated spec from a file or stdin ('-')."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append([p.strip() for p in line.split("|")])
    if not rows:
        die("spec is empty")
    return rows


def tile_images(paths, out_pattern, cols, rows, width, label=None):
    """Tile arbitrary image files into sheets.

    ffmpeg in many Windows builds has no glob support, so the files are copied
    into a temp directory under sequential names and read as an image2 sequence.
    """
    with tempfile.TemporaryDirectory() as td:
        for i, p in enumerate(paths, start=1):
            shutil.copyfile(p, Path(td) / f"{i:04d}{Path(p).suffix}")
        suffix = Path(paths[0]).suffix
        run([ffmpeg(), "-v", "error", "-f", "image2",
             "-i", str(Path(td) / f"%04d{suffix}"),
             "-vf", f"scale={width}:-1,tile={cols}x{rows}:margin=4:padding=4",
             str(out_pattern), "-y"], quiet=True)
    if label:
        print(label)


# --------------------------------------------------------------------------- fetch

def srt_to_transcript(srt_path, out_path):
    """Flatten an SRT into '[M:SS] text' lines, dropping the rolling duplicates
    that YouTube auto-captions produce."""
    text = Path(srt_path).read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n+", text.strip())
    lines, last = [], None
    for block in blocks:
        rows = block.strip().split("\n")
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start = rows[1].split("-->")[0].strip().replace(",", ".")
        body = " ".join(rows[2:]).strip()
        body = re.sub(r"<[^>]+>", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        if not body or body == last:
            continue
        last = body
        h, m, s = start.split(":")
        secs = int(h) * 3600 + int(m) * 60 + float(s)
        lines.append(f"[{fmt_tc(secs)}] {body}")
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def cmd_fetch(args):
    proj = Project(args.out)
    proj.mkdirs()
    source = args.source
    is_url = bool(re.match(r"^https?://", source))
    ytdlp = [sys.executable, "-m", "yt_dlp"]

    if is_url:
        ensure_module("yt_dlp", "yt-dlp")
        meta = subprocess.run(
            ytdlp + ["--skip-download", "--no-warnings", "--print",
                     "%(title)s\t%(uploader)s\t%(duration)s\t%(upload_date)s\t%(webpage_url)s",
                     source],
            check=True, capture_output=True, text=True,
        ).stdout.strip().splitlines()[-1]
        title, uploader, dur, date, url = (meta.split("\t") + [""] * 5)[:5]
        (proj.work / "meta.txt").write_text(
            f"title: {title}\nuploader: {uploader}\nduration_s: {dur}\n"
            f"upload_date: {date}\nurl: {url}\n", encoding="utf-8")
        print(f"\ntitle    : {title}\nuploader : {uploader}\n"
              f"duration : {fmt_tc(float(dur or 0))}\nuploaded : {date}\n")

        lang = args.lang
        run(ytdlp + ["--skip-download", "--write-subs", "--write-auto-subs",
                     "--sub-langs", f"{lang}-orig,{lang}", "--sub-format", "srt/vtt",
                     "--convert-subs", "srt", "--no-warnings",
                     "-o", str(proj.work / "video.%(ext)s"), source],
            stdout=subprocess.DEVNULL)

        picked = None
        for cand in (f"video.{lang}-orig.srt", f"video.{lang}.srt"):
            if (proj.work / cand).exists():
                picked = proj.work / cand
                break
        if picked:
            shutil.copyfile(picked, proj.work / "subs.srt")
            n = srt_to_transcript(proj.work / "subs.srt", proj.work / "transcript.txt")
            print(f"transcript: {n} lines -> {proj.work / 'transcript.txt'}")
        else:
            print("warning: no subtitles found for language", lang, file=sys.stderr)

        if not args.no_video:
            h = args.height
            fmt = (f"bv*[height<={h}][vcodec^=avc1]+ba/"
                   f"bv*[height<={h}]+ba/b[height<={h}]")
            run(ytdlp + ["-f", fmt, "--merge-output-format", "mp4", "--no-warnings",
                         "-o", str(proj.work / "video.%(ext)s"), source],
                stdout=subprocess.DEVNULL)
    else:
        src = Path(source)
        if not src.exists():
            die(f"{src} not found")
        shutil.copyfile(src, proj.work / "video.mp4")
        print(f"adopted local file -> {proj.work / 'video.mp4'}")
        for cand in (src.with_suffix(".srt"), src.with_suffix(".vtt")):
            if cand.exists():
                shutil.copyfile(cand, proj.work / "subs.srt")
                srt_to_transcript(proj.work / "subs.srt", proj.work / "transcript.txt")
                break

    if (proj.work / "video.mp4").exists():
        d = proj.duration()
        print(f"\nvideo: {proj.work / 'video.mp4'}  ({fmt_tc(d)}, {d:.1f}s)")
    print("\nnext: vidnotes.py sheets --out", proj.root)


# -------------------------------------------------------------------------- sheets

def cmd_sheets(args):
    proj = Project(args.out)
    sheets = proj.work / "sheets"
    if sheets.exists():
        shutil.rmtree(sheets)
    sheets.mkdir(parents=True)

    step, cols, rows = args.interval, args.cols, args.rows
    run([ffmpeg(), "-v", "error", "-i", str(proj.video),
         "-vf", f"fps=1/{step},scale={args.width}:-1,"
                f"tile={cols}x{rows}:margin=4:padding=4",
         "-an", str(sheets / "sheet_%02d.png"), "-y"], quiet=True)

    made = sorted(sheets.glob("sheet_*.png"))
    per = cols * rows
    total = proj.duration()
    print(f"\n{len(made)} sheet(s) in {sheets}")
    print(f"one frame every {step}s, {cols}x{rows} = {per} frames per sheet, "
          f"read left-to-right then top-to-bottom\n")
    for s, path in enumerate(made):
        base = s * per * step
        print(f"{path.name}: starts at {fmt_tc(base)}")
        for r in range(rows):
            cells = []
            for c in range(cols):
                t = base + (r * cols + c) * step
                cells.append(f"{fmt_tc(t):>7}" if t <= total else "      -")
            print("   " + " ".join(cells))
        print()
    print("Read each sheet, note the timestamps that show a diagram, chart or\n"
          "slide, then confirm the exact moment with `probe` before cutting frames.")


# --------------------------------------------------------------------------- probe

def cmd_probe(args):
    proj = Project(args.out)
    times = [parse_time(t) for t in args.times]
    pdir = proj.work / "probe"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)

    paths = []
    for i, t in enumerate(times, start=1):
        p = pdir / f"{i:03d}_{t:g}s.png"
        run([ffmpeg(), "-v", "error", "-ss", f"{t}", "-i", str(proj.video),
             "-frames:v", "1", "-vf", f"scale={args.width}:-1", str(p), "-y"],
            quiet=True)
        paths.append(p)

    cols = args.cols or min(4, len(paths))
    rows = (len(paths) + cols - 1) // cols
    out = proj.work / "probe_sheet.png"
    tile_images(paths, out, cols, rows, args.width)
    print(f"\n{out}")
    print(f"{cols} per row, left-to-right then top-to-bottom:\n")
    for r in range(rows):
        row = times[r * cols:(r + 1) * cols]
        print("   " + " ".join(f"{fmt_tc(t):>7}" for t in row))
    print("\nAnimations usually finish 1-4s after the line that introduces them,\n"
          "so prefer the latest timestamp where the graphic is still complete.")


# -------------------------------------------------------------------------- frames

def cmd_frames(args):
    proj = Project(args.out)
    proj.mkdirs()
    rows = read_spec(args.spec)
    made = []
    for row in rows:
        if len(row) < 2:
            die(f"frames spec needs 'TIME|name', got: {row}")
        t, name = parse_time(row[0]), row[1]
        dst = proj.images / f"{name}.png"
        run([ffmpeg(), "-v", "error", "-ss", f"{t}", "-i", str(proj.video),
             "-frames:v", "1", "-q:v", "2", str(dst), "-y"], quiet=True)
        made.append((t, dst))
        print(f"  {fmt_tc(t):>7}  {dst.name}")
    print(f"\n{len(made)} frame(s) -> {proj.images}")

    if not args.no_check and made:
        cols = 5
        rows_n = (len(made) + cols - 1) // cols
        tile_images([p for _, p in made], proj.work / "check_%02d.png",
                    cols, min(rows_n, 4), 440)
        print(f"check sheets: {proj.work / 'check_01.png'} (and following)\n"
              "Look at them and re-cut anything that landed mid-animation.")


# --------------------------------------------------------------------------- clips

def cmd_clips(args):
    proj = Project(args.out)
    proj.mkdirs()
    rows = read_spec(args.spec)
    for row in rows:
        if len(row) < 3:
            die(f"clips spec needs 'START|DURATION|name', got: {row}")
        start, dur, name = parse_time(row[0]), parse_time(row[1]), row[2]
        dst = proj.clips / f"{name}.mp4"
        run([ffmpeg(), "-v", "error", "-ss", f"{start}", "-t", f"{dur}",
             "-i", str(proj.video), "-vf", f"scale={args.width}:-2",
             "-c:v", "libx264", "-crf", str(args.crf), "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
             str(dst), "-y"], quiet=True)
        size = dst.stat().st_size / 1e6
        print(f"  {fmt_tc(start)}-{fmt_tc(start + dur)}  {dst.name}  ({size:.1f} MB)")
    print(f"\n{len(rows)} clip(s) -> {proj.clips}")


# ---------------------------------------------------------------------------- html

PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#5f6368;--line:#e3e3e0;--accent:#c15f3c;--code:#f4f3f0;--card:#faf9f7}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#17181a;--fg:#e8e6e3;--muted:#9aa0a6;--line:#2e3034;--accent:#e08a63;--code:#222427;--card:#1d1f21}}}}
:root[data-theme="dark"]{{--bg:#17181a;--fg:#e8e6e3;--muted:#9aa0a6;--line:#2e3034;--accent:#e08a63;--code:#222427;--card:#1d1f21}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);margin:0;padding:48px 16px 96px;
 font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
 -webkit-font-smoothing:antialiased}}
main{{max-width:860px;margin:0 auto}}
h1{{font-size:2.05rem;line-height:1.2;letter-spacing:-.02em;margin:0 0 .6em}}
h2{{font-size:1.5rem;line-height:1.25;letter-spacing:-.01em;margin:2.4em 0 .7em}}
h3{{font-size:1.16rem;margin:1.9em 0 .5em}}
h4{{font-size:1rem;margin:1.6em 0 .4em}}
p{{margin:0 0 1em}}
a{{color:var(--accent)}}
hr{{border:0;border-top:1px solid var(--line);margin:2.6em 0}}
ul,ol{{padding-left:1.4em;margin:0 0 1.1em}}
li{{margin:.35em 0}}
code{{background:var(--code);padding:.12em .38em;border-radius:4px;font-size:.88em;
 font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
pre{{background:var(--code);padding:1em;border-radius:8px;overflow:auto}}
pre code{{background:none;padding:0}}
figure{{margin:1.8em 0}}
figure img,figure video{{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:10px;background:#000}}
figcaption{{color:var(--muted);font-size:.86rem;margin-top:.55em;text-align:center}}
figure.clip video{{border-color:var(--accent)}}
table{{border-collapse:collapse;width:100%;margin:1.4em 0;font-size:.94rem}}
th,td{{border:1px solid var(--line);padding:.6em .7em;text-align:left;vertical-align:top}}
th{{background:var(--card);font-weight:600}}
blockquote{{margin:1.2em 0;padding:.1em 1em;border-left:3px solid var(--line);color:var(--muted)}}
@media (max-width:640px){{body{{padding:28px 16px 64px}}h1{{font-size:1.65rem}}h2{{font-size:1.3rem}}}}
</style>
</head>
<body>
<main>
{content}
</main>
</body>
</html>
"""

CLIP_P = re.compile(
    r'<p>(?P<before>(?:(?!</p>).)*?)'
    r'<a href="(?P<src>[^"]+\.(?:mp4|webm|m4v))"[^>]*>(?P<label>(?:(?!</a>).)*)</a>'
    r'(?P<after>(?:(?!</p>).)*)</p>',
    re.S)

IMG_P = re.compile(
    r'<p>\s*<img alt="(?P<alt>[^"]*)" src="(?P<src>[^"]+)"\s*/?>\s*</p>')

TAG = re.compile(r"<[^>]+>")


def cmd_html(args):
    proj = Project(args.out)
    md_path = proj.root / args.md
    if not md_path.exists():
        die(f"{md_path} not found - write the article first")
    markdown = ensure_module("markdown")

    text = md_path.read_text(encoding="utf-8")
    html = markdown.markdown(text, extensions=["tables", "sane_lists", "fenced_code"])

    def clip_sub(m):
        src, label = m.group("src"), TAG.sub("", m.group("label"))
        before = TAG.sub("", m.group("before"))
        after = TAG.sub("", m.group("after"))
        cap = " ".join(f"{before} {label} {after}".split())
        return (f'<figure class="clip"><video controls preload="metadata" '
                f'src="{src}"></video><figcaption>{cap}</figcaption></figure>')

    def img_sub(m):
        src, alt = m.group("src"), m.group("alt")
        cap = f"<figcaption>{alt}</figcaption>" if alt else ""
        return (f'<figure><a href="{src}" target="_blank" rel="noopener">'
                f'<img src="{src}" alt="{alt}" loading="lazy"></a>{cap}</figure>')

    n_clips = len(CLIP_P.findall(html))
    html = CLIP_P.sub(clip_sub, html)
    n_imgs = len(IMG_P.findall(html))
    html = IMG_P.sub(img_sub, html)

    title = args.title
    if not title:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        title = TAG.sub("", m.group(1)).strip() if m else md_path.stem

    out = proj.root / args.output
    out.write_text(
        PAGE.format(lang=args.lang, title=title, content=html), encoding="utf-8")

    missing = []
    for src in re.findall(r'(?:src|href)="((?:images|clips)/[^"]+)"', out.read_text(encoding="utf-8")):
        if not (proj.root / src).exists():
            missing.append(src)
    print(f"{out}  ({out.stat().st_size} bytes)")
    print(f"  {n_imgs} figure(s), {n_clips} inline video(s)")
    if missing:
        print("  MISSING assets:", ", ".join(sorted(set(missing))), file=sys.stderr)
    else:
        print("  all referenced assets exist")


# ---------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        prog="vidnotes", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_out(p):
        p.add_argument("--out", required=True, metavar="DIR",
                       help="project directory")
        return p

    p = with_out(sub.add_parser("fetch", help="download video + subtitles"))
    p.add_argument("source", help="video URL, or a path to a local video file")
    p.add_argument("--lang", default="en", help="subtitle language (default: en)")
    p.add_argument("--height", type=int, default=1080, help="max video height")
    p.add_argument("--no-video", action="store_true",
                   help="subtitles only, skip the video download")
    p.set_defaults(func=cmd_fetch)

    p = with_out(sub.add_parser("sheets", help="contact sheets of the whole video"))
    p.add_argument("--interval", type=float, default=4, help="seconds between frames")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--rows", type=int, default=5)
    p.add_argument("--width", type=int, default=300, help="thumbnail width in px")
    p.set_defaults(func=cmd_sheets)

    p = with_out(sub.add_parser("probe", help="tile specific timestamps into one sheet"))
    p.add_argument("times", nargs="+", help="timestamps: 93 1:33 0:01:33 ...")
    p.add_argument("--width", type=int, default=600)
    p.add_argument("--cols", type=int, default=0, help="0 = auto")
    p.set_defaults(func=cmd_probe)

    p = with_out(sub.add_parser("frames", help="cut screenshots from a spec"))
    p.add_argument("--spec", required=True, help="file with 'TIME|name' lines, or -")
    p.add_argument("--no-check", action="store_true",
                   help="skip the verification contact sheet")
    p.set_defaults(func=cmd_frames)

    p = with_out(sub.add_parser("clips", help="cut mp4 excerpts from a spec"))
    p.add_argument("--spec", required=True,
                   help="file with 'START|DURATION|name' lines, or -")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--crf", type=int, default=24)
    p.set_defaults(func=cmd_clips)

    p = with_out(sub.add_parser("html", help="render the article to a styled page"))
    p.add_argument("--md", default="README.md", help="source Markdown (default README.md)")
    p.add_argument("--output", default="index.html")
    p.add_argument("--title", default="", help="override the <title>")
    p.add_argument("--lang", default="en", help="html lang attribute")
    p.set_defaults(func=cmd_html)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
