#!/usr/bin/env python3
"""Regenerate the GitHub Pages site in docs/ from the skill's own files.

Run it after changing SKILL.md or scripts/vidnotes.py:

    python tools/build_site.py

It writes docs/skill.html, docs/script.html and docs/pygments.css, and copies
the raw SKILL.md and vidnotes.py into docs/ so they are downloadable straight
from the site. docs/index.html and docs/style.css are hand-written and left
alone.
"""

import html
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
REPO = "https://github.com/grimseal/video-to-article"


def need(mod, pip_name=None):
    try:
        return __import__(mod)
    except ImportError:
        pip_name = pip_name or mod
        print(f"installing {pip_name} ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                        "--quiet", pip_name], check=True)
        import importlib
        importlib.invalidate_caches()
        return importlib.import_module(mod)


NAV = [
    ("index.html", "Overview"),
    ("skill.html", "SKILL.md"),
    ("script.html", "vidnotes.py"),
]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#127916;</text></svg>">
<link rel="stylesheet" href="style.css">
{extra_head}
</head>
<body>
<div class="wrap{wide}">
{nav}
<div class="pagehead">
  <h1>{heading}</h1>
  <p>{subtitle}</p>
  <div class="actions">{actions}</div>
</div>
{body}
<footer>
  <a href="{repo}">Source on GitHub</a>
  <span>MIT licensed</span>
</footer>
</div>
{script}
</body>
</html>
"""

COPY_JS = """<script>
document.querySelectorAll('[data-copy]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    fetch(btn.dataset.copy).then(function (r) { return r.text(); }).then(function (text) {
      var done = function () {
        var old = btn.textContent;
        btn.textContent = 'Copied'; btn.classList.add('done');
        setTimeout(function () { btn.textContent = old; btn.classList.remove('done'); }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  });
});
</script>"""


def nav_html(current):
    out = ['<nav>']
    for href, label in NAV:
        cur = ' aria-current="page"' if href == current else ''
        out.append(f'<a href="{href}"{cur}>{label}</a>')
    out.append('<span class="sep"></span>')
    out.append(f'<a class="ext" href="{REPO}">GitHub &#8599;</a>')
    out.append('</nav>')
    return "\n".join(out)


def build_skill_page():
    markdown = need("markdown")
    src = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    # strip the YAML frontmatter, and surface it as the subtitle instead
    body_md = src
    if src.startswith("---"):
        end = src.find("\n---\n", 3)
        if end != -1:
            body_md = src[end + 5:]

    body = markdown.markdown(
        body_md, extensions=["tables", "sane_lists", "fenced_code"])

    actions = (
        '<a class="btn" href="SKILL.md" download>Download</a>'
        '<button class="btn" data-copy="SKILL.md">Copy raw</button>'
        f'<a class="btn" href="{REPO}/blob/main/SKILL.md">View on GitHub</a>'
    )
    page = PAGE.format(
        title="SKILL.md &middot; video-to-article",
        extra_head="", wide="", nav=nav_html("skill.html"),
        heading="SKILL.md",
        subtitle="The instructions Claude Code reads. This is the whole skill - "
                 "the script below just does the mechanical parts.",
        actions=actions, body=f'<div class="md">{body}</div>',
        repo=REPO, script=COPY_JS)
    (DOCS / "skill.html").write_text(page, encoding="utf-8")
    shutil.copyfile(ROOT / "SKILL.md", DOCS / "SKILL.md")
    return len(body_md.splitlines())


def build_script_page():
    need("pygments")
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import HtmlFormatter

    code = (ROOT / "scripts" / "vidnotes.py").read_text(encoding="utf-8")
    formatter = HtmlFormatter(style="friendly", linenos="table",
                              cssclass="highlight", wrapcode=True)
    listing = highlight(code, PythonLexer(), formatter)

    # one stylesheet, three scopes: light default, system dark, forced dark
    light = HtmlFormatter(style="friendly").get_style_defs(".highlight")
    dark_sys = HtmlFormatter(style="native").get_style_defs(
        ':root:not([data-theme="light"]) .highlight')
    dark_set = HtmlFormatter(style="native").get_style_defs(
        ':root[data-theme="dark"] .highlight')
    css = (
        f"{light}\n"
        f"@media (prefers-color-scheme:dark){{\n{dark_sys}\n}}\n"
        f"{dark_set}\n"
        # let the container's own background show through either way
        ".highlight, .highlight pre{background:none !important}\n"
    )
    (DOCS / "pygments.css").write_text(css, encoding="utf-8")

    actions = (
        '<a class="btn" href="vidnotes.py" download>Download</a>'
        '<button class="btn" data-copy="vidnotes.py">Copy raw</button>'
        f'<a class="btn" href="{REPO}/blob/main/scripts/vidnotes.py">View on GitHub</a>'
    )
    page = PAGE.format(
        title="vidnotes.py &middot; video-to-article",
        extra_head='<link rel="stylesheet" href="pygments.css">',
        wide=" wide", nav=nav_html("script.html"),
        heading="scripts/vidnotes.py",
        subtitle=f"{len(code.splitlines())} lines. Fetching, frame scanning, "
                 "cutting and rendering - every mechanical step the skill drives.",
        actions=actions, body=f'<div class="src">{listing}</div>',
        repo=REPO, script=COPY_JS)
    (DOCS / "script.html").write_text(page, encoding="utf-8")
    shutil.copyfile(ROOT / "scripts" / "vidnotes.py", DOCS / "vidnotes.py")
    return len(code.splitlines())


def main():
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").touch()
    (DOCS / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    n_md = build_skill_page()
    n_py = build_script_page()
    print(f"docs/skill.html   <- SKILL.md ({n_md} lines)")
    print(f"docs/script.html  <- scripts/vidnotes.py ({n_py} lines)")
    print("docs/SKILL.md, docs/vidnotes.py  (raw copies)")
    print("docs/pygments.css")
    missing = [p for p in ("index.html", "style.css") if not (DOCS / p).exists()]
    if missing:
        print("warning: hand-written file(s) missing:", ", ".join(missing),
              file=sys.stderr)


if __name__ == "__main__":
    main()
