---
name: scholar-inbox-digest
description: Turn the day's Scholar Inbox digest into a self-contained HTML newsletter. Each paper gets a teaser figure and a five-section structured summary (What / Why / How / Results / Thoughts) in both English and Japanese. Uses scholarinboxcli for fetch; figures and source bullets are taken from the Scholar Inbox response. The model writes the structured summaries.
---

# Scholar Inbox digest → newsletter

Three-step pipeline:

1. **fetch** (Python, deterministic) — pulls today's digest via `scholarinboxcli`,
   normalizes fields, captures the four Scholar-Inbox-provided summary axes
   (`contributions / method / evaluation / problem`).
2. **summarize** (the model) — for each paper, produces a structured 5-section
   summary in English *and* Japanese, drawing on the four source axes and the
   abstract.
3. **render** (Python, deterministic) — emits HTML with the teaser figure,
   both summaries, and paper / code / arXiv links.

## Prereqs (one-time per machine)

```bash
uv run scholarinboxcli auth login --url "https://www.scholar-inbox.com/login?sha_key=...&date=MM-DD-YYYY"
uv run scholarinboxcli auth status   # expect "is_logged_in": true
```

All commands below run from this skill's directory.

## Step 1 — fetch

```bash
uv run python scripts/fetch_digest.py --date MM-DD-YYYY --top 15 \
    --raw-out raw.json --out digest.json
```

- `--date` optional; defaults to today on the server.
- `--top` keeps the N top-ranked papers (default 15).
- `--raw-out` keeps the untouched API response — open it the first time per day
  to confirm field names haven't drifted.

Per-paper fields you'll work with in step 2:
- `abstract`
- `summaries.contributions` — key contributions, markdown bullets
- `summaries.method` — how the method works, markdown bullets
- `summaries.evaluation` — concrete results / numbers, markdown bullets
- `summaries.problem` — problem statement and limitations of past work
- `figures`, `method_shortname`, `display_venue`-derived `venue`, etc.

## Step 2 — write structured summaries

For each paper add two fields to its dict in `digest.json`:

```jsonc
{
  "summary_struct": {
    "what":     ["..."],          // 1-2 bullets
    "why":      ["..."],          // 1-2 bullets
    "how":      ["...", "..."],   // typically 2-5 bullets (the meaty section)
    "results":  ["..."],          // 1-3 bullets, prefer concrete numbers
    "thoughts": ["..."]           // 1-3 bullets, your own commentary
  },
  "summary_struct_ja": { /* same shape, Japanese */ }
}
```

Each list is a list of plain strings. `**bold**` and `*italic*` markdown is
converted by the renderer. Empty list (or missing key) for a section means
"skip this section" — the renderer collapses it cleanly.

### What goes in each section

- **What** — what concrete problem does the paper solve? (Not "we improve X"
  but "X is the task; the input is Y, the desired output is Z, under
  constraints W".) Source: `summaries.problem` + first line of
  `summaries.contributions`. Usually 1, sometimes 2 bullets.
- **Why** — why does this matter, *and* why couldn't past methods solve it?
  Source: `summaries.problem` (it already enumerates gaps in past work). Keep
  the past-methods angle explicit — that's what makes "Why" different from
  "What". 1-2 bullets.
- **How** — the key technical ideas. This is the section that usually carries
  the paper's actual content; default to 2-5 bullets. Source: mainly
  `summaries.method` plus any methodological points hiding in
  `summaries.contributions`. Each bullet should name a *mechanism* (a module,
  loss, training recipe, data construction), not a vague claim.
- **Results** — concrete evidence. Source: `summaries.evaluation`. Keep the
  *specific numbers and dataset names* that are already there (CD human,
  BEHAVE, FID, fps, +x pp). Do not paraphrase numbers into adjectives like
  "substantial improvement" — if a number isn't in the source, do not add
  one. 1-3 bullets.
- **Thoughts** — your own commentary: where else could the key idea
  transfer? what's still unsolved, what was glossed over, what would you
  challenge? This is the only section that goes *beyond* the source — keep it
  honest:
  - If you're confident, say it.
  - If you're speculating, hedge ("likely transferable to...", "unclear how
    this behaves when...").
  - If the abstract gives you nothing to react to, write one short bullet
    rather than padding.
  - 1-3 bullets, often 1-2. Do not write "Thoughts" filler just to fill a
    slot.

### Sourcing rules

- The four `summaries.*` axes are already grounded in the paper. Reuse their
  phrasing for What/Why/How/Results — your job is mostly *restructuring* into
  the 5-section schema, not generating new claims.
- Never invent: numbers, dataset names, baselines, dates, author affiliations.
  If `summaries.evaluation` doesn't mention an ablation, do not write one.
- Keep handles like method shortnames (`**CrossHOI**`), terms of art
  (`SMPL-X`, `SE(3)`, `bundle adjustment`), and dataset names in English even
  in the Japanese version — translating them hurts more than it helps.
- Drop hype language ("novel", "state-of-the-art", "we propose"). Lead with
  the thing, not the framing.

### Japanese version

Translate the same content; *do not* produce different bullets in JA vs EN
unless the EN bullet is too verbose to fit one Japanese sentence (then split).
Keep technical terms English. Style: 体言止め / 簡潔な動詞止め, no marketing
adjectives. Same number of bullets per section as the EN version.

### Suggested workflow

1. Open `digest.json`. For each paper read `abstract` and all four
   `summaries.*` axes — the structure of what you write comes from there.
2. Maintain a single `/tmp/structs.json` keyed by `paper_id`:
   ```json
   {
     "4707840": {
       "en": {"what":[...], "why":[...], "how":[...], "results":[...], "thoughts":[...]},
       "ja": {"what":[...], "why":[...], "how":[...], "results":[...], "thoughts":[...]}
     },
     ...
   }
   ```
3. Inject in one shot:
   ```bash
   uv run python -c '
   import json
   d = json.load(open("digest.json"))
   tr = json.load(open("/tmp/structs.json"))
   for p in d["papers"]:
       t = tr.get(str(p["paper_id"]))
       if t:
           p["summary_struct"] = t["en"]
           p["summary_struct_ja"] = t["ja"]
   json.dump(d, open("digest.json","w"), indent=2, ensure_ascii=False)
   '
   ```
4. Render (step 3) and visually scan a couple of articles.

## Step 3 — render HTML

```bash
uv run python scripts/render_html.py digest.json --out newsletter.html
open newsletter.html   # macOS
```

Figure pick (heuristic, no override needed for most papers): lowest-numbered
`type=="Figure"` entry, skipping Tables. Override per-paper by setting
`picked_figure_idx` on the paper before rendering.

## When things go wrong

- **`scholarinboxcli` auth error.** Magic-link cookie expired — refresh from
  the Scholar Inbox email and re-run `auth login`.
- **All `figures` arrays are empty.** Open `raw.json`, check whether
  `teaser_figures` was renamed upstream; update `_figures()` in
  `fetch_digest.py`. Don't silently fall back.
- **A paper has near-empty `summaries.*` axes.** Some Scholar Inbox papers
  haven't been processed yet. Fall back to writing What/Why/How/Results from
  the abstract alone; flag your Thoughts bullet as "abstract-only" so the
  reader knows.
- **The model wrote Results bullets with fabricated numbers.** That's a hard
  failure — strip them, re-derive from `summaries.evaluation`. Do not ship
  invented numbers.

## What the model should NOT do

- Do not write Thoughts that just rephrase What/Why. Skip it instead.
- Do not insert promotional adjectives, "we", or "novel" into any section.
- Do not invent numbers or dataset names. Sourcing rule above is hard.
- Do not change the 5-section order, even when a section is empty (renderer
  enforces it via SECTION_ORDER).
