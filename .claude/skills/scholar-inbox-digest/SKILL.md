---
name: scholar-inbox-digest
description: Turn the day's Scholar Inbox digest into a self-contained HTML newsletter. Each paper gets up to two figures (teaser + architecture), a colored match-score badge, and a five-section structured summary (What / Why / How / Results / Thoughts) in both English and Japanese. Use this when the user asks for "today's digest", "今日のまとめ", or anything similar.
---

# Scholar Inbox digest → newsletter

Three-step pipeline. Steps 1 and 3 are deterministic Python; step 2 is the
model's job. The fetch step auto-handles authentication.

## Daily flow (after one-time setup below)

1. `uv run python scripts/fetch_digest.py --top 15 --out digest.json` — pulls
   today's digest. Calls `ensure_auth()` first; if the cookie expired, it
   re-logs in using the saved magic link with no user prompt.
2. Read `digest.json`. For each paper, write `summary_struct` and
   `summary_struct_ja` per the schema below.
3. `uv run python scripts/render_html.py digest.json --out newsletter.html
   && open newsletter.html`.

When the user says "今日のまとめを作って" / "today's digest" / similar, just
do all three steps without asking; treat that as the GO signal.

## One-time setup

1. Run once with `uv sync` to install deps (`scholarinboxcli`, `jinja2`).
2. Save the user's Scholar Inbox magic-link URL to:
   ```
   ~/.config/scholar-inbox-newsletter/magic_link
   ```
   A single line, no quotes, like
   `https://www.scholar-inbox.com/login?sha_key=...&date=...`. This file
   lives **outside** the repo and is never committed.
3. The first `fetch_digest.py` run uses that magic link to authenticate.
   Subsequent runs reuse the saved cookie until it expires. When it
   eventually expires, `fetch_digest.py` re-runs `auth login` using the same
   saved magic link automatically.

If the magic-link file is missing, `fetch_digest.py` prints a clear
recovery message and exits non-zero — *do not* paper over it with an
interactive scholarinboxcli prompt or by parsing the email.

## Step 2 — writing the structured summary (the model's job)

For each paper in `digest.json` add two fields:

```jsonc
{
  "summary_struct": {
    "what":     ["..."],          // 1-2 bullets
    "why":      ["..."],          // 1-2 bullets, NAME the past methods
    "how":      ["...", "..."],   // 2-5 bullets, the meaty section
    "results":  ["..."],          // 1-3 bullets, prefer concrete numbers
    "thoughts": ["..."]           // 1-3 bullets, your own commentary
  },
  "summary_struct_ja": { /* same shape, Japanese */ }
}
```

`**bold**` and `*italic*` are converted. Empty list / missing key skips the
section in the rendered HTML.

### What goes in each section

- **What** — the concrete task. Input → output → constraints. Not "we
  propose a novel..."; just the task. 1, sometimes 2 bullets. Source:
  `summaries.problem` and first line of `summaries.contributions`.

- **Why** — why does this matter, *and* why couldn't past methods solve it?
  This is the most important rule:
  > When you say "past methods fail because X", name 1–2 representative
  > prior methods by their short handle (e.g. `G-HOP`, `LatentHOI`,
  > `CONTHO`, `HIMO-Gen`, `DUSt3R`, `4DGS`, `HUGS`, `ScrewSplat`,
  > `Unified-VLA`, `Vid2Avatar`, `GSNet`, …). The reader needs to know
  > *which* prior work is being criticized — vague "single-view methods"
  > / "diffusion-based approaches" leaves the criticism unfalsifiable.
  >
  > Phrasing pattern: "Methods like *G-HOP* and *LatentHOI* …
  > because …".

  Source for the names: look at `summaries.evaluation` (the explicit
  comparison baselines) and the abstract. Do **not** invent names — if the
  source doesn't mention any specific prior work, write "past methods" and
  leave the names out. 1-2 bullets.

- **How** — the key technical ideas. 2-5 bullets, default 3-4. Each bullet
  should name a *mechanism* (a module, loss, training recipe, data
  construction), not a vague claim. Source: `summaries.method` + the
  methodological lines of `summaries.contributions`.

- **Results** — concrete evidence. Source: `summaries.evaluation`. Preserve
  specific numbers and dataset names (CD human, BEHAVE, FID, fps,
  +x pp) verbatim. Do not paraphrase numbers into adjectives like
  "substantial improvement". If a number isn't in the source, don't add
  one. 1-3 bullets.

- **Thoughts** — *your own* commentary, the only section that goes beyond
  the source: where else can the key idea transfer? what's unsolved or
  glossed over? what's the brittle assumption? Hedge when speculating
  ("likely transferable to...", "unclear how this behaves under..."). If
  you have nothing real to add, write one short bullet rather than
  filler. 1-3 bullets.

### Sourcing rules (hard)

- The four `summaries.*` axes from Scholar Inbox are already grounded in
  the paper. Reuse their phrasing — your job is mostly *restructuring*.
- Never invent numbers, dataset names, baselines, dates, or affiliations.
- Keep method shortnames (`**CrossHOI**`), terms of art (`SMPL-X`,
  `SE(3)`, `bundle adjustment`), and dataset names in English even in
  the Japanese version — translating them hurts more than it helps.
- Drop hype words ("novel", "state-of-the-art", "we propose"). Lead with
  the thing, not the framing.

### Japanese version

Translate the same content; same bullet count per section. Keep technical
terms English. 体言止め / 簡潔な動詞止め, no marketing adjectives.

### Suggested workflow (model)

1. Read `abstract` + all four `summaries.*` axes for each paper.
2. Build a single `/tmp/structs.json` keyed by `paper_id`:
   ```json
   {"4707840": {"en": {"what":[...],...}, "ja": {"what":[...],...}}, ...}
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

## Step 3 — render

```bash
uv run python scripts/render_html.py digest.json --out newsletter.html
open newsletter.html
```

Default selections (no override needed for most papers):
- **Figures**: up to two per paper — the teaser (lowest-numbered
  `type=="Figure"`) and the next Figure whose caption matches
  architecture / pipeline / framework / overview / network. If the teaser
  itself is an arch/overview figure, only one is shown.
- **Score badge color**: ≥0.85 = green (high), 0.70–0.85 = amber (mid),
  <0.70 = grey (low).
- **Title link**: goes to `https://www.scholar-inbox.com/paper/{paper_id}`
  (not arXiv / not the conference PDF) so the user can like / dislike on
  Scholar Inbox if needed. The conference PDF / arXiv links live in the
  link row at the bottom.
- **Like / dislike buttons**: every paper gets 👍 / 👎 buttons below the
  score badge. Clicking calls `POST https://api.scholar-inbox.com/api/make_rating/`
  with `{rating: 1|-1|0, id: <paper_id>}` and `credentials: "include"`.
  This works *only when the reader is signed in to scholar-inbox.com in the
  same browser* (the API server allows `null` origin so `file://` is OK,
  but the session cookie must be present). On failure a toast appears.
  Initial button state comes from `p.rating` (-1 / 0 / 1) captured at
  fetch time.

Per-paper overrides (set on the paper dict in `digest.json` before render):
- `picked_figure_idxs: [int, int]` — explicit indices into `figures`.

The HTML/CSS lives in `templates/newsletter.html.j2`. If the user wants a
style tweak, edit *that* file — do not inline another template in
`render_html.py`.

## When things go wrong

- **auth file missing** — `fetch_digest.py` prints recovery instructions.
  Tell the user to save their magic-link URL to
  `~/.config/scholar-inbox-newsletter/magic_link`, then re-run.
- **auth file present but login fails** — the magic-link URL is stale.
  Tell the user to refresh from a recent Scholar Inbox email and rewrite
  the file.
- **All `figures` arrays empty** — open `raw.json` and check whether
  `teaser_figures` was renamed upstream. Update `_figures()` in
  `fetch_digest.py`. Do not silently fall back.
- **Architecture figure is wrong** for a specific paper — override
  `picked_figure_idxs` on that paper, re-render.
- **Results bullets contain fabricated numbers** — strip them, re-derive
  from `summaries.evaluation`. Do not ship invented numbers.

## What the model should NOT do

- Don't say "past methods fail" without naming them. The rule above is hard.
- Don't write Thoughts that just rephrase What/Why. Skip the section.
- Don't insert promotional adjectives, "we", or "novel".
- Don't invent numbers, baselines, dataset names.
- Don't change the 5-section order even when a section is empty.
- Don't add an arXiv HTML scraping step — figures are already in the
  Scholar Inbox response.
- Don't inline a template in `render_html.py`. Edit
  `templates/newsletter.html.j2` instead.
