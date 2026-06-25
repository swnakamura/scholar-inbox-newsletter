"""Fetch a daily Scholar Inbox digest via scholarinboxcli and normalize fields.

The Scholar Inbox response is already very rich: each paper has `teaser_figures`
(figure URLs + captions, with figureType="Figure"/"Table"), `summaries`
(4-question markdown bullets), and `display_venue`, `shortened_authors`, etc.
We do not need an arXiv enrichment step — figures are server-side artifacts.

Output JSON shape:
    {
      "date": str | null,                  # digest date echoed back from server
      "user": str | null,
      "count": int,
      "papers": [
        {
          "rank": int, "score": float | null,
          "title": str, "method_shortname": str | null,
          "authors": str, "abstract": str,
          "venue": str, "year": str,
          "paper_id": str, "arxiv_id": str | null,
          "url": str, "pdf_url": str | null,
          "github_url": str | null, "project_url": str | null,
          "summaries": {                  # 4-axis markdown bullets, untouched
            "contributions": str | null,
            "method":        str | null,
            "evaluation":    str | null,
            "problem":       str | null,
          },
          "figures": [                    # absolute https:// urls
            {"url": str, "caption": str, "type": "Figure"|"Table", "n": int},
            ...
          ],
          "first_page_image": str | null, # absolute url, fallback thumbnail
          "raw": dict                     # original row (for debugging)
        }, ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

SI_BASE = "https://www.scholar-inbox.com"


def _run_cli(date: str | None) -> Any:
    cmd = ["scholarinboxcli", "digest", "--json"]
    if date:
        cmd += ["--date", date]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"scholarinboxcli failed (exit {res.returncode})")
    return json.loads(res.stdout)


def _abs_url(maybe: str | None) -> str | None:
    if not maybe:
        return None
    if maybe.startswith("http://") or maybe.startswith("https://"):
        return maybe
    return urljoin(SI_BASE, maybe)


def _figures(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for f in raw.get("teaser_figures") or []:
        img = f.get("imageUrl")
        if not img:
            continue
        out.append(
            {
                "url": _abs_url(img),
                "caption": (f.get("caption") or "").strip(),
                "type": f.get("figureType") or "Figure",
                "n": f.get("figureNumber"),
            }
        )
    return out


def _summaries(raw: dict[str, Any]) -> dict[str, str | None]:
    s = raw.get("summaries") or {}
    return {
        "contributions": s.get("contributions_question"),
        "method":        s.get("method_explanation_question"),
        "evaluation":    s.get("evaluation_question"),
        "problem":       s.get("problem_definition_question"),
    }


def _venue(raw: dict[str, Any]) -> str:
    return str(raw.get("display_venue") or raw.get("conference") or raw.get("abbreviation") or "").strip()


def _year(raw: dict[str, Any]) -> str:
    y = raw.get("conference_year") or raw.get("year")
    if y is not None:
        try:
            return str(int(float(y)))
        except (ValueError, TypeError):
            return str(y)
    pd = raw.get("publication_date")
    if isinstance(pd, str) and len(pd) >= 4 and pd[:4].isdigit():
        return pd[:4]
    return ""


def _pdf_url(raw: dict[str, Any]) -> str | None:
    arx = raw.get("arxiv_id")
    if arx:
        return f"https://arxiv.org/pdf/{arx}"
    u = raw.get("url") or ""
    if u.endswith(".pdf"):
        return u
    return None


def _score(raw: dict[str, Any]) -> float | None:
    s = raw.get("ranking_score")
    try:
        return float(s) if s is not None else None
    except (ValueError, TypeError):
        return None


def normalize(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, p in enumerate(papers, start=1):
        title = str(p.get("title") or "").strip()
        kw = p.get("keywords_metadata") or {}
        out.append(
            {
                "rank": i,
                "score": _score(p),
                "title": title,
                "method_shortname": (kw.get("method_shortname") or None),
                "authors": (p.get("shortened_authors") or p.get("authors") or "").strip(),
                "abstract": (p.get("abstract") or "").strip(),
                "venue": _venue(p),
                "year": _year(p),
                "paper_id": str(p.get("paper_id") or ""),
                "arxiv_id": p.get("arxiv_id"),
                "url": p.get("url") or (f"https://arxiv.org/abs/{p['arxiv_id']}" if p.get("arxiv_id") else ""),
                "pdf_url": _pdf_url(p),
                "github_url": p.get("github_url"),
                "project_url": p.get("project_url"),
                "summaries": _summaries(p),
                "figures": _figures(p),
                "first_page_image": _abs_url((p.get("first_page_image") or {}).get("imageUrl")),
                "raw": p,
            }
        )
    return out


def _extract_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        for k in ("digest_df", "papers", "results", "items", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return [p for p in v if isinstance(p, dict)]
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="MM-DD-YYYY (default: today)")
    ap.add_argument("--top", type=int, default=15, help="Keep top-N highest-ranked")
    ap.add_argument("--out", default="digest.json")
    ap.add_argument("--raw-out", default=None)
    args = ap.parse_args()

    raw = _run_cli(args.date)
    if args.raw_out:
        Path(args.raw_out).write_text(json.dumps(raw, indent=2, ensure_ascii=False))

    papers = normalize(_extract_list(raw))[: args.top]
    out = {
        "date": (raw.get("current_digest_date") if isinstance(raw, dict) else None) or args.date,
        "user": (raw.get("username") if isinstance(raw, dict) else None),
        "count": len(papers),
        "papers": papers,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    sys.stderr.write(f"wrote {len(papers)} papers to {args.out}\n")


if __name__ == "__main__":
    main()
