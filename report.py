"""
Serialization + aggregation for divergence runs.

The differ produces a per-file report (in-memory dataclasses). This module
turns a batch of those into (a) compact, storable per-file records and (b) the
aggregate divergence-rate statistics that are the core paper result (D3):

  - pairwise divergence rate: for each extractor pair, the fraction of files
    where they were both able to run yet disagreed (similarity < threshold)
  - blind-spot rate: for each extractor, the fraction of applicable files where
    it returned nothing (error or empty) while another extractor recovered text
    — this is the pipeline-aware attacker's target
  - breakdowns by format and by corpus group (baseline vs each mutation vector)

Stored records keep a hash + preview of extracted text, not the full text, so
results/ stays small and never carries corpus content (phishing/malware) verbatim.
"""
from __future__ import annotations
import hashlib
import math
from collections import defaultdict
from itertools import combinations

from differ import similarity


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion k/n.

    Preferred over the normal (Wald) interval for the rates this study reports:
    it stays inside [0,1], behaves well for the small per-format/per-group cells,
    and does not collapse to a zero-width interval at k=0 or k=n. Returns
    (low, high); (0.0, 0.0) for n=0.
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def serialize_report(rep: dict, group: str = "") -> dict:
    """Compact, storable form of one file's differ report."""
    results = []
    for r in rep["results"]:
        results.append({
            "extractor": r.extractor,
            "ok": r.ok,
            "error": r.error,
            "text_len": len(r.text),
            "text_sha1": _sha1(r.text) if r.text else "",
            "preview": r.text[:160],
            "meta": r.meta,
        })
    return {
        "file": rep["file"],
        "group": group,
        "format": rep["format"],
        "results": results,
        "errored": rep["errored"],
        "divergences": [
            {"left": d.left, "right": d.right, "score": round(d.score, 4),
             "kind": d.kind}
            for d in rep["divergences"]
        ],
    }


def _pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def aggregate(records: list[dict], threshold: float = 0.95) -> dict:
    """Compute divergence-rate statistics over serialized per-file records.

    Recomputes pair similarity from stored hashes only for equality; for the
    <threshold test we reuse the divergences already recorded by the differ
    (which had the full text). We therefore derive pair stats from each record's
    `results` (comparable?) plus its `divergences` (diverged?).
    """
    pair_comparable: dict[str, int] = defaultdict(int)
    pair_divergent: dict[str, int] = defaultdict(int)
    pair_by_group: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])  # (group,pair)->[comp,div]
    pair_by_format: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])  # (fmt,pair)->[comp,div]

    ext_applicable: dict[str, int] = defaultdict(int)
    ext_ok: dict[str, int] = defaultdict(int)
    ext_error: dict[str, int] = defaultdict(int)
    ext_empty: dict[str, int] = defaultdict(int)
    ext_blind: dict[str, int] = defaultdict(int)

    fmt_files: dict[str, int] = defaultdict(int)
    fmt_divergent_files: dict[str, int] = defaultdict(int)
    group_files: dict[str, int] = defaultdict(int)
    group_divergent_files: dict[str, int] = defaultdict(int)

    total_comparisons = 0
    total_divergent = 0

    for rec in records:
        group = rec.get("group", "")
        fmt = rec["format"]
        fmt_files[fmt] += 1
        group_files[group] += 1

        results = rec["results"]
        by_name = {r["extractor"]: r for r in results}
        # any extractor recovered non-empty text? (for blind-spot reference)
        someone_has_text = any(r["ok"] and r["text_len"] > 0 for r in results)

        for r in results:
            name = r["extractor"]
            ext_applicable[name] += 1
            if not r["ok"]:
                ext_error[name] += 1
            else:
                ext_ok[name] += 1
                if r["text_len"] == 0:
                    ext_empty[name] += 1
            blind = (not r["ok"]) or (r["ok"] and r["text_len"] == 0)
            if blind and someone_has_text:
                ext_blind[name] += 1

        # divergence set for this file (pair -> True)
        diverged_pairs = {_pair_key(d["left"], d["right"]) for d in rec["divergences"]}
        file_has_divergence = len(diverged_pairs) > 0
        if file_has_divergence:
            fmt_divergent_files[fmt] += 1
            group_divergent_files[group] += 1

        # comparable pairs: both ran ok on this file
        ok_names = [r["extractor"] for r in results if r["ok"]]
        for a, b in combinations(sorted(ok_names), 2):
            pk = _pair_key(a, b)
            pair_comparable[pk] += 1
            total_comparisons += 1
            diverged = pk in diverged_pairs
            if diverged:
                pair_divergent[pk] += 1
                total_divergent += 1
            gp = pair_by_group[(group, pk)]
            gp[0] += 1
            gp[1] += int(diverged)
            fp = pair_by_format[(fmt, pk)]
            fp[0] += 1
            fp[1] += int(diverged)

    def _rate(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    pairs = []
    for pk in sorted(pair_comparable):
        comp, div = pair_comparable[pk], pair_divergent[pk]
        lo, hi = _wilson(div, comp)
        pairs.append({"pair": pk, "comparable": comp, "divergent": div,
                      "divergence_rate": _rate(div, comp),
                      "ci_low": lo, "ci_high": hi})

    extractors = []
    for name in sorted(ext_applicable):
        appl = ext_applicable[name]
        lo, hi = _wilson(ext_blind[name], appl)
        extractors.append({
            "extractor": name,
            "applicable": appl,
            "ok": ext_ok[name],
            "error": ext_error[name],
            "empty": ext_empty[name],
            "blind": ext_blind[name],
            "blind_rate": _rate(ext_blind[name], appl),
            "blind_ci_low": lo, "blind_ci_high": hi,
        })

    def _fmt_row(f: str) -> dict:
        lo, hi = _wilson(fmt_divergent_files[f], fmt_files[f])
        return {"format": f, "files": fmt_files[f],
                "files_with_divergence": fmt_divergent_files[f],
                "rate": _rate(fmt_divergent_files[f], fmt_files[f]),
                "ci_low": lo, "ci_high": hi}

    by_format = [_fmt_row(f) for f in sorted(fmt_files)]

    def _group_row(g: str) -> dict:
        lo, hi = _wilson(group_divergent_files[g], group_files[g])
        return {"group": g or "(none)", "files": group_files[g],
                "files_with_divergence": group_divergent_files[g],
                "rate": _rate(group_divergent_files[g], group_files[g]),
                "ci_low": lo, "ci_high": hi}

    by_group = [_group_row(g) for g in sorted(group_files)]

    # per-format x per-pair divergence: which extractor pairs diverge on which
    # formats, with a CI per cell (the stratified view the scaled study needs so
    # a headline isn't an average over heterogeneous format mixes).
    by_format_pair = []
    for (fmt, pk) in sorted(pair_by_format):
        comp, div = pair_by_format[(fmt, pk)]
        lo, hi = _wilson(div, comp)
        by_format_pair.append({"format": fmt, "pair": pk,
                               "comparable": comp, "divergent": div,
                               "divergence_rate": _rate(div, comp),
                               "ci_low": lo, "ci_high": hi})

    o_lo, o_hi = _wilson(total_divergent, total_comparisons)
    return {
        "threshold": threshold,
        "n_files": len(records),
        "total_pair_comparisons": total_comparisons,
        "total_divergent_comparisons": total_divergent,
        "overall_divergence_rate": _rate(total_divergent, total_comparisons),
        "overall_ci_low": o_lo,
        "overall_ci_high": o_hi,
        "pairs": pairs,
        "extractors": extractors,
        "by_format": by_format,
        "by_format_pair": by_format_pair,
        "by_group": by_group,
    }


def pairs_csv(summary: dict) -> str:
    """Pairwise divergence table as CSV text (with 95% Wilson CI)."""
    lines = ["pair,comparable,divergent,divergence_rate,ci_low,ci_high"]
    for p in summary["pairs"]:
        lines.append(f"{p['pair']},{p['comparable']},{p['divergent']},"
                     f"{p['divergence_rate']},{p['ci_low']},{p['ci_high']}")
    return "\n".join(lines) + "\n"
