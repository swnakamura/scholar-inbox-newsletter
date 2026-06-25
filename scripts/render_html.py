"""Render digest.json to a self-contained HTML newsletter.

The HTML/CSS layout lives in `templates/newsletter.html.j2`. Edit it there if
you want to change styling; this script only prepares per-paper data.

Per-paper fields it consumes (filled in by step 2 of the pipeline):
  - summary_struct,    summary_struct_ja: {what, why, how, results, thoughts}
    where each section is list[str].
  - picked_figure_idxs: list[int] (optional) to override figure selection.

Defaults:
  - Figure pick: teaser = lowest-numbered type=="Figure"; arch = next
    type=="Figure" whose caption matches architecture/pipeline keywords.
  - Score badge color: high ≥ 0.85, mid ≥ 0.70, else low.

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

from jinja2 import Environment, FileSystemLoader, select_autoescape

BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITAL_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
ARCH_RE = re.compile(
    r"\b(architecture|pipeline|framework|overview|network)\b",
    re.I,
)

SECTION_ORDER = ("what", "why", "how", "results", "thoughts")
SECTION_LABELS = {
    "what":     "What",
    "why":      "Why",
    "how":      "How",
    "results":  "Results",
    "thoughts": "Thoughts",
}

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
TEMPLATE_NAME = "newsletter.html.j2"


def _md_inline(text: str) -> str:
    t = html.escape(text)
    t = BOLD_RE.sub(r"<strong>\1</strong>", t)
    t = ITAL_RE.sub(r"<em>\1</em>", t)
    return t


def _struct_sections(paper: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
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
            out.append({"label": SECTION_LABELS[sk], "bullets": bullets})
    return out or None


def _abstract_fallback(paper: dict[str, Any]) -> str | None:
    abstract = (paper.get("abstract") or "").strip().replace("\n", " ")
    if not abstract:
        return None
    short = abstract[:280] + ("..." if len(abstract) > 280 else "")
    return html.escape(short)


def _pick_figures(paper: dict[str, Any]) -> list[dict[str, Any]]:
    figs = paper.get("figures") or []
    if not figs:
        if paper.get("first_page_image"):
            return [{
                "url": paper["first_page_image"],
                "caption": "First page preview.",
                "type": "Page",
                "n": None,
            }]
        return []

    override = paper.get("picked_figure_idxs")
    if isinstance(override, list) and override:
        return [figs[i] for i in override if isinstance(i, int) and 0 <= i < len(figs)]

    figures_only = sorted(
        [f for f in figs if (f.get("type") or "Figure") == "Figure"],
        key=lambda f: f.get("n") if f.get("n") is not None else 999,
    )
    if not figures_only:
        return [figs[0]]

    teaser = figures_only[0]
    picks = [teaser]
    teaser_is_arch = bool(ARCH_RE.search(teaser.get("caption") or ""))
    if not teaser_is_arch:
        for f in figures_only[1:]:
            if ARCH_RE.search(f.get("caption") or ""):
                picks.append(f)
                break
    return picks


def _score_view(score: float | None) -> tuple[str, str]:
    if score is None:
        return ("", "")
    if score >= 0.85:
        return ("score-high", f"{score:.2f}")
    if score >= 0.70:
        return ("score-mid",  f"{score:.2f}")
    return ("score-low", f"{score:.2f}")


def _prepare(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in papers:
        struct_en = _struct_sections(p, "summary_struct")
        struct_ja = _struct_sections(p, "summary_struct_ja")
        score_class, score_text = _score_view(p.get("score"))
        out.append({
            **p,
            "struct_en": struct_en,
            "struct_ja": struct_ja,
            "abstract_short": None if struct_en else _abstract_fallback(p),
            "figures": _pick_figures(p),
            "score_class": score_class,
            "score_text": score_text,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("digest", help="Path to digest.json")
    ap.add_argument("--out", default="newsletter.html")
    ap.add_argument("--template-dir", default=str(TEMPLATE_DIR),
                    help="Directory containing newsletter.html.j2")
    args = ap.parse_args()

    data = json.loads(Path(args.digest).read_text())
    papers = _prepare(data.get("papers", []))

    env = Environment(
        loader=FileSystemLoader(args.template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    tmpl = env.get_template(TEMPLATE_NAME)
    out_html = tmpl.render(date=data.get("date"), user=data.get("user"), papers=papers)
    Path(args.out).write_text(out_html)
    print(f"wrote {args.out} ({len(papers)} papers)")


if __name__ == "__main__":
    main()
