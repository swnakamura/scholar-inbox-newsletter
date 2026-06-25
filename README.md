# scholar-inbox-newsletter

Turn the day's [Scholar Inbox](https://www.scholar-inbox.com) digest into a
self-contained HTML newsletter:

- One paper per article block, ranked by Scholar Inbox's relevance score.
- A teaser figure (Scholar Inbox already extracts these; no PDF scraping).
- Structured 5-section summary: **What / Why / How / Results / Thoughts** —
  in English *and* Japanese.
- Direct links to paper, code, project page, arXiv.

The pipeline is built as a [Claude Code](https://claude.com/claude-code) skill
(`SKILL.md`) so you can run it interactively, but the scripts are plain Python
and work standalone too.

## How it works

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  scholarinboxcli │───▶│  fetch_digest.py │───▶│   digest.json    │
│   (your auth)    │    │  (normalize)     │    │  (raw + figures  │
└──────────────────┘    └──────────────────┘    │   + 4-axis SI    │
                                                │   summaries)     │
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
Step 2 (the structured summaries) is where the model adds value:
restructuring Scholar Inbox's four pre-generated summary axes
(contributions / method / evaluation / problem) into the
What / Why / How / Results / Thoughts schema, plus translation.

## Install

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/<you>/scholar-inbox-newsletter.git
cd scholar-inbox-newsletter
uv sync
```

## Authenticate (one time)

Get a magic-link URL from a Scholar Inbox email (or from the web UI), then:

```bash
uv run scholarinboxcli auth login --url "https://www.scholar-inbox.com/login?sha_key=...&date=MM-DD-YYYY"
uv run scholarinboxcli auth status     # expect "is_logged_in": true
```

> ⚠️ **Do not commit your magic-link URL or the `sha_key` value anywhere in
> the repo.** The `scholarinboxcli` config containing the cookie lives at
> `~/.config/scholarinboxcli/config.json`, *outside* this repo, and stays
> there. `raw.json`, `digest.json`, and `newsletter.html` are produced
> locally and are git-ignored by default because they contain your user
> name / read history — keep it that way.

## Daily run

```bash
# 1. fetch and normalize
uv run python scripts/fetch_digest.py --date 05-26-2026 --top 15 \
    --raw-out raw.json --out digest.json

# 2. (open digest.json, add per-paper summary_struct / summary_struct_ja)
#    See SKILL.md for the schema and writing guidance.

# 3. render
uv run python scripts/render_html.py digest.json --out newsletter.html
open newsletter.html      # macOS
```

If you don't want to write the structured summaries by hand, point Claude
Code at `SKILL.md` — the skill instructs the model how to produce them from
the four `summaries.*` axes already in `digest.json`.

## What's in each file

```
SKILL.md             Claude Code skill: pipeline + writing guidance
scripts/
  fetch_digest.py    scholarinboxcli digest --json → normalized digest.json
  render_html.py     digest.json → newsletter.html (Jinja2 template inline)
pyproject.toml       uv project, deps: scholarinboxcli, jinja2
.gitignore           excludes raw.json / digest.json / newsletter.html / .env
```

## Customization

- **Number of papers**: `--top N` on `fetch_digest.py`.
- **Picked figure** (per paper): set `picked_figure_idx` on a paper in
  `digest.json` before rendering. Default is the lowest-numbered
  `figureType="Figure"` (Tables skipped).
- **Per-paper summary**: edit `summary_struct` / `summary_struct_ja` in
  `digest.json`. Sections can have any number of bullets; empty sections are
  collapsed in the output.
- **Styling**: the HTML/CSS template is inline at the top of
  `scripts/render_html.py`. Edit `TEMPLATE`.

## Privacy

Files that *might* contain your name, paper-read history, or the Scholar
Inbox session cookie:

| File | Contains | Safe to commit? |
|---|---|---|
| `~/.config/scholarinboxcli/config.json` | `sha_key`, cookies | **NO** — outside repo, stays there |
| `raw.json` | user name, `read_paper_ids` | NO (gitignored) |
| `digest.json` | user name, paper rankings for you | NO (gitignored) |
| `newsletter.html` | your name in the header | NO (gitignored) |
| `scripts/*.py`, `SKILL.md`, `pyproject.toml` | only code / docs | yes |

If you need to share an example output publicly, manually scrub the
`"user"` field from `digest.json` first and confirm there's nothing
personal in `read_paper_ids` etc.

## License

MIT.

## Credits

- [Scholar Inbox](https://www.scholar-inbox.com) (Andreas Geiger lab,
  Tübingen) for the paper recommendation service and the very rich API.
- [`scholarinboxcli`](https://github.com/mrshu/scholarinboxcli) for the
  third-party Python CLI used to authenticate and fetch the daily digest.
