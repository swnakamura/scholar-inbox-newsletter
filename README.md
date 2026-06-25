# scholar-inbox-newsletter

Turn the day's [Scholar Inbox](https://www.scholar-inbox.com) digest into a
self-contained HTML newsletter:

- One paper per article block, ranked by Scholar Inbox's relevance score,
  shown as a colored badge (green / amber / grey by score).
- Up to **two figures per paper**: the teaser plus, if there is one, the
  architecture / pipeline figure (caption match — no PDF scraping).
- Structured 5-section summary — **What / Why / How / Results / Thoughts**
  — in English *and* Japanese. The Why section names representative prior
  methods being criticized.
- Direct links to paper, code, project page, arXiv.

The pipeline is built as a [Claude Code](https://claude.com/claude-code)
skill (`.claude/skills/scholar-inbox-digest/SKILL.md`), so the daily
workflow is: `cd` into this directory, start `claude`, say **"今日のまとめを
作って"** (or "today's digest"), done. The scripts are plain Python and
also work standalone.

## How it works

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  scholarinboxcli │───▶│  fetch_digest.py │───▶│   digest.json    │
│   + your saved   │    │  (auto-auth,     │    │  (raw + figures  │
│   magic-link     │    │   normalize)     │    │   + 4-axis SI    │
└──────────────────┘    └──────────────────┘    │   summaries)     │
                                                └────────┬─────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │  Claude (you)    │
                                                │  writes 5-sec    │
                                                │  summaries EN/JA │
                                                └────────┬─────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │  render_html.py  │
                                                │   → newsletter   │
                                                │     .html        │
                                                └──────────────────┘
```

Step 1 (fetch) and step 3 (render) are deterministic Python.
Step 2 is the model's job: restructure Scholar Inbox's four pre-generated
summary axes (contributions / method / evaluation / problem) into the
What / Why / How / Results / Thoughts schema, plus translation.

## Install

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<you>/scholar-inbox-newsletter.git
cd scholar-inbox-newsletter
uv sync
```

## One-time auth setup

Save your Scholar Inbox magic-link URL to a known file, then `fetch_digest.py`
auto-handles login (and re-login when cookies expire):

```bash
mkdir -p ~/.config/scholar-inbox-newsletter
# Open any Scholar Inbox digest email, copy the magic-link URL
# (https://www.scholar-inbox.com/login?sha_key=...&date=...),
# and paste it into this file as a single line, no quotes:
$EDITOR ~/.config/scholar-inbox-newsletter/magic_link
```

Alternative: export `SCHOLAR_INBOX_AUTH_URL=...` instead.

> ⚠️ **Never commit the magic-link URL or its `sha_key`.** The auth file
> lives outside this repo by design. `raw.json`, `digest.json`, and
> `newsletter.html` are produced locally with your user name embedded and
> are git-ignored — keep it that way.

## Daily run

```bash
# fetch (auto-authenticates on first use / cookie expiry)
uv run python scripts/fetch_digest.py --top 15 --out digest.json --raw-out raw.json

# now write summary_struct / summary_struct_ja per paper in digest.json
# (or just let Claude Code do it — see SKILL.md)

# render
uv run python scripts/render_html.py digest.json --out newsletter.html

# serve + open in browser; also proxies the like/dislike click to
# Scholar Inbox so 👍 / 👎 actually persist on your account
uv run python scripts/serve.py
```

> ⚠️ Don't `open newsletter.html` directly — the 👍/👎 buttons will fail
> silently because Scholar Inbox's session cookie is `SameSite=Lax`, so
> the browser refuses to attach it to cross-origin requests from
> `file://`. The local server at `http://127.0.0.1:8765/` proxies the
> rating call server-side using the scholarinboxcli session, which has
> no such restriction.

If you're using Claude Code in this directory, just say **"今日のまとめを
作って"**. The skill follows all three steps automatically.

## Customization

- **Number of papers**: `--top N` on `fetch_digest.py`.
- **Per-paper figures**: set `picked_figure_idxs: [int, ...]` on a paper in
  `digest.json` before rendering. Default is teaser + first matching
  architecture-keyword figure.
- **Per-paper summary**: edit `summary_struct` / `summary_struct_ja` in
  `digest.json`. Sections can have any number of bullets; empty sections are
  collapsed in the output.
- **Styling**: the HTML/CSS template is in
  [`templates/newsletter.html.j2`](templates/newsletter.html.j2). Edit
  there — `render_html.py` does not inline a template.

## What's in each file

```
.claude/skills/scholar-inbox-digest/
  SKILL.md           Claude Code skill: pipeline + writing guidance
templates/
  newsletter.html.j2 Jinja2 template (full HTML + CSS for the newsletter)
scripts/
  fetch_digest.py    scholarinboxcli digest --json → normalized digest.json
                     (calls ensure_auth() first to handle login)
  render_html.py     digest.json → newsletter.html (loads template above)
  serve.py           serves newsletter.html at localhost:8765 and proxies
                     the like/dislike click to api.scholar-inbox.com using
                     the scholarinboxcli session
pyproject.toml       uv project, deps: scholarinboxcli, jinja2
.gitignore           excludes raw.json / digest.json / newsletter.html / .env
```

## Privacy

Files that *might* contain your name, paper-read history, or the Scholar
Inbox session cookie:

| File | Contains | Safe to commit? |
|---|---|---|
| `~/.config/scholar-inbox-newsletter/magic_link` | `sha_key` in URL | **NO** — outside repo by design |
| `~/.config/scholar-inbox-newsletter/config.json` (created by scholarinboxcli) | session cookie | **NO** — outside repo |
| `raw.json` | user name, `read_paper_ids` | NO (gitignored) |
| `digest.json` | user name, paper rankings for you | NO (gitignored) |
| `newsletter.html` | your name in the header | NO (gitignored) |
| code, `SKILL.md`, `pyproject.toml`, `templates/*` | only code / docs | yes |

If you need to share an example output publicly, scrub the `"user"` field
from `digest.json` first and confirm nothing personal is in
`read_paper_ids` etc.

## License

MIT.

## Credits

- [Scholar Inbox](https://www.scholar-inbox.com) (Andreas Geiger lab,
  Tübingen) for the recommendation service and the very rich API.
- [`scholarinboxcli`](https://github.com/mrshu/scholarinboxcli) for the
  third-party CLI used to authenticate and fetch the daily digest.
