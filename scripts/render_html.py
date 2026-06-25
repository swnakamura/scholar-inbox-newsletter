"""Render digest.json (the rich Scholar Inbox output) to a self-contained HTML.

Per-paper structure (filled in by the model between fetch and render):
  - summary_struct, summary_struct_ja: {what, why, how, results, thoughts}
    where each section is a list[str] of plain-string bullets (flexible count;
    empty list / missing key means "skip this section"). Markdown **bold** and
    *italic* inside bullets are converted.
  - picked_figure_idx (optional): override default figure pick.

Picked figure default: lowest-numbered item with type=="Figure" (Tables skipped),
falling back to first_page_image when there are no Figure entries.

Usage:
    uv run python scripts/render_html.py digest.json [--out newsletter.html]
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader, select_autoescape

BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITAL_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")

SECTION_ORDER = ("what", "why", "how", "results", "thoughts")
SECTION_LABELS = {
    "what":     "What",
    "why":      "Why",
    "how":      "How",
    "results":  "Results",
    "thoughts": "Thoughts",
}


def _md_inline(text: str) -> str:
    t = html.escape(text)
    t = BOLD_RE.sub(r"<strong>\1</strong>", t)
    t = ITAL_RE.sub(r"<em>\1</em>", t)
    return t


def _struct_sections(paper: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    """Return [{key, label, bullets:[html,...]}, ...] for non-empty sections,
    or None if no struct exists."""
    struct = paper.get(key)
    if not isinstance(struct, dict):
        return None
    out = []
    for sk in SECTION_ORDER:
        items = struct.get(sk)
        if not isinstance(items, list):
            continue
        bullets = [_md_inline(s) for s in items if isinstance(s, str) and s.strip()]
        if bullets:
            out.append({"key": sk, "label": SECTION_LABELS[sk], "bullets": bullets})
    return out or None


def _abstract_fallback(paper: dict[str, Any]) -> str | None:
    abstract = (paper.get("abstract") or "").strip().replace("\n", " ")
    if not abstract:
        return None
    short = abstract[:280] + ("..." if len(abstract) > 280 else "")
    return html.escape(short)


def _pick_figure(paper: dict[str, Any]) -> dict[str, Any] | None:
    figs = paper.get("figures") or []
    if not figs:
        if paper.get("first_page_image"):
            return {
                "url": paper["first_page_image"],
                "caption": "First page preview.",
                "type": "Page",
                "n": None,
            }
        return None
    idx = paper.get("picked_figure_idx")
    if isinstance(idx, int) and 0 <= idx < len(figs):
        return figs[idx]
    figures_only = [f for f in figs if (f.get("type") or "Figure") == "Figure"]
    if figures_only:
        figures_only.sort(key=lambda f: (f.get("n") if f.get("n") is not None else 999))
        return figures_only[0]
    return figs[0]


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scholar Inbox digest — {{ date or "today" }}</title>
<style>
  :root { --fg: #1a1a1a; --muted: #6a6a6a; --soft: #e6e6e6; --link: #0a55c4;
          --section: #7a4a00; --section-ja: #4a4a4a; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 820px; margin: 32px auto; padding: 0 18px; color: var(--fg);
         line-height: 1.55; -webkit-font-smoothing: antialiased; }
  header { margin-bottom: 28px; }
  header h1 { font-size: 24px; margin: 0 0 4px; letter-spacing: -0.01em; }
  header .meta { color: var(--muted); font-size: 13px; }
  article.paper { border-top: 1px solid var(--soft); padding: 24px 0 28px; }
  article.paper:first-of-type { border-top: none; padding-top: 8px; }
  .rank { display: inline-block; min-width: 26px; color: var(--muted); font-size: 13px;
          font-variant-numeric: tabular-nums; }
  .title { font-size: 17px; font-weight: 600; margin: 0 0 4px; }
  .title a { color: var(--fg); text-decoration: none; }
  .title a:hover { text-decoration: underline; }
  .shortname { color: #b34800; font-weight: 700; margin-right: 6px; }
  .score { color: var(--muted); font-size: 12px; margin-left: 6px;
           font-variant-numeric: tabular-nums; }
  .byline { color: var(--muted); font-size: 13px; margin: 0 0 12px 26px; }
  .body { margin-left: 26px; }

  .struct { font-size: 14px; margin: 6px 0 8px; }
  .struct .sec { margin: 6px 0; padding: 0; }
  .struct .sec-h { font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
                   text-transform: uppercase; color: var(--section);
                   margin: 0 0 2px; }
  .struct ul { margin: 2px 0 6px; padding-left: 20px; }
  .struct li { margin: 2px 0; }

  .struct-ja { font-size: 13.5px; margin: 4px 0 10px; color: #2a2a2a;
               border-left: 2px solid #d9d9d9; padding: 4px 0 4px 12px; }
  .struct-ja .sec { margin: 4px 0; }
  .struct-ja .sec-h { font-size: 11px; font-weight: 700; letter-spacing: 0.04em;
                      color: var(--section-ja); margin: 0 0 2px; }
  .struct-ja ul { margin: 2px 0 4px; padding-left: 18px; }
  .struct-ja li { margin: 2px 0; }

  .abstract-fallback { font-size: 13px; color: #555; margin: 6px 0 10px; }

  figure { margin: 12px 0 8px; }
  figure img { max-width: 100%; height: auto; border: 1px solid var(--soft);
               border-radius: 4px; display: block; }
  figcaption { color: var(--muted); font-size: 12px; margin-top: 6px; line-height: 1.4; }
  .links { font-size: 13px; margin-top: 8px; }
  .links a { color: var(--link); text-decoration: none; margin-right: 14px; }
  .links a:hover { text-decoration: underline; }
  .nofig { color: #a0a0a0; font-size: 12px; font-style: italic; }
</style>
</head>
<body>
<header>
  <h1>Scholar Inbox digest</h1>
  <div class="meta">
    {% if date %}{{ date }} · {% endif %}
    {% if user %}for {{ user }} · {% endif %}
    {{ papers|length }} papers
  </div>
</header>

{% for p in papers %}
<article class="paper">
  <h2 class="title">
    <span class="rank">{{ p.rank }}.</span>
    {% if p.method_shortname %}<span class="shortname">{{ p.method_shortname }}:</span>{% endif %}
    {% if p.url %}<a href="{{ p.url }}">{{ p.title }}</a>{% else %}{{ p.title }}{% endif %}
    {% if p.score is not none %}<span class="score">{{ "%.2f"|format(p.score) }}</span>{% endif %}
  </h2>
  <div class="byline">
    {{ p.authors }}{% if p.venue %} · {{ p.venue }}{% endif %}
  </div>

  <div class="body">
    {% if p.struct_en %}
    <div class="struct">
      {% for s in p.struct_en %}
      <div class="sec">
        <div class="sec-h">{{ s.label }}</div>
        <ul>{% for b in s.bullets %}<li>{{ b|safe }}</li>{% endfor %}</ul>
      </div>
      {% endfor %}
    </div>
    {% elif p.abstract_short %}
    <p class="abstract-fallback">{{ p.abstract_short }}</p>
    {% endif %}

    {% if p.struct_ja %}
    <div class="struct-ja">
      {% for s in p.struct_ja %}
      <div class="sec">
        <div class="sec-h">{{ s.label }}</div>
        <ul>{% for b in s.bullets %}<li>{{ b|safe }}</li>{% endfor %}</ul>
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {% if p.figure %}
    <figure>
      <img src="{{ p.figure.url }}" alt="{{ p.figure.caption[:80] }}">
      {% if p.figure.caption %}<figcaption>{{ p.figure.caption }}</figcaption>{% endif %}
    </figure>
    {% else %}
    <div class="nofig">(no figure available)</div>
    {% endif %}

    <div class="links">
      {% if p.url %}<a href="{{ p.url }}">paper</a>{% endif %}
      {% if p.pdf_url and p.pdf_url != p.url %}<a href="{{ p.pdf_url }}">pdf</a>{% endif %}
      {% if p.github_url %}<a href="{{ p.github_url }}">code</a>{% endif %}
      {% if p.project_url %}<a href="{{ p.project_url }}">project</a>{% endif %}
      {% if p.arxiv_id %}<a href="https://arxiv.org/abs/{{ p.arxiv_id }}">arXiv</a>{% endif %}
    </div>
  </div>
</article>
{% endfor %}
</body>
</html>
"""


def _prepare(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in papers:
        struct_en = _struct_sections(p, "summary_struct")
        struct_ja = _struct_sections(p, "summary_struct_ja")
        out.append({
            **p,
            "struct_en": struct_en,
            "struct_ja": struct_ja,
            "abstract_short": None if struct_en else _abstract_fallback(p),
            "figure": _pick_figure(p),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("digest", help="Path to digest.json")
    ap.add_argument("--out", default="newsletter.html")
    args = ap.parse_args()

    data = json.loads(Path(args.digest).read_text())
    papers = _prepare(data.get("papers", []))

    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))
    tmpl = env.from_string(TEMPLATE)
    out_html = tmpl.render(date=data.get("date"), user=data.get("user"), papers=papers)
    Path(args.out).write_text(out_html)
    print(f"wrote {args.out} ({len(papers)} papers)")


if __name__ == "__main__":
    main()
