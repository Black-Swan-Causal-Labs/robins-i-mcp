"""Review-level traffic-light figure across many assessed results.

The single-result report answers "why is this result graded this way"; this
answers "what does the evidence base look like". Rows are results, columns are
the six domains plus overall.

Kept deliberately, because robvis cannot: **six levels, not five.** "Low, except
for concerns about uncontrolled confounding" is drawn as its own level, because
it is the whole of what V2 says about domain 1 — that residual confounding
cannot be excluded in a non-randomized study, so that domain never reaches plain
low. robvis reduces cells to a first initial over a five-fill palette and
collapses it to Low; this does not.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .algorithms import Judgement
from .report import (
    ATTRIBUTION,
    DOMAIN_LABELS,
    FRAMEWORK_CITATION,
    JUDGEMENT_LABELS,
    NON_ENDORSEMENT,
    SOURCE_STATUS,
    Assessment,
    algorithm_fingerprint,
)
from .render_html import _CLASS, _CSS as _BASE_CSS, _SHORT
from .review import review_rows, review_summary

_EXTRA_CSS = """
  .grid { border:2px solid var(--line); background:var(--surface); margin-top:18px; overflow-x:auto; }
  table.tl { border-collapse:collapse; width:100%; min-width:760px; }
  table.tl th { font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--accent);
                font-weight:700; padding:9px 7px; border-bottom:1.5px solid var(--line);
                vertical-align:bottom; text-align:center; }
  table.tl th.study { text-align:left; width:34%; }
  table.tl td { padding:5px 6px; border-bottom:1px solid var(--line-soft); vertical-align:middle; }
  table.tl td.study { text-align:left; font-size:.92rem; line-height:1.3; }
  table.tl td.study .rid { display:block; font-size:11px; color:var(--ink-faint); }
  table.tl tr:last-child td { border-bottom:none; }
  table.tl td.ov { border-left:3px solid var(--line); background:var(--paper); }
  .chip { display:block; text-align:center; padding:7px 4px; border:1.25px solid var(--line);
          font-size:11.5px; font-weight:700; line-height:1.1; color:#fff; }
  .chip.j-low { background:var(--low); }
  .chip.j-lowc { background:var(--low); box-shadow:inset 0 0 0 2.5px var(--surface); }
  .chip.j-mod { background:var(--mod); }
  .chip.j-ser { background:var(--ser); }
  .chip.j-crit { background:var(--crit); }
  .chip.na { background:transparent; color:var(--ink-faint); border-style:dashed; font-weight:400; }
  .vbadge { display:inline-block; font-size:10px; letter-spacing:.08em; font-weight:700;
            border:1px solid var(--line-soft); padding:1px 5px; color:var(--ink-soft); margin-left:6px; }
  .legend { display:flex; flex-wrap:wrap; gap:8px 16px; margin-top:14px; align-items:center; }
  .legend .k { display:flex; align-items:center; gap:7px; font-size:12.5px; color:var(--ink-soft); }
  .legend .sw { width:26px; height:15px; border:1.25px solid var(--line); }
  .legend .sw.j-low { background:var(--low); }
  .legend .sw.j-lowc { background:var(--low); box-shadow:inset 0 0 0 2.5px var(--surface); }
  .legend .sw.j-mod { background:var(--mod); }
  .legend .sw.j-ser { background:var(--ser); }
  .legend .sw.j-crit { background:var(--crit); }
  .tally { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:0;
           border:2px solid var(--line); background:var(--surface); margin-top:18px; }
  .tally .t { padding:11px 13px; border-left:1.5px solid var(--line); }
  .tally .t:first-child { border-left:none; }
  .tally .t .n { font-size:1.5rem; font-weight:700; line-height:1.1; }
  .tally .t .cap { font-size:11px; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-faint); font-weight:700; }
  .caveat { border:1.5px solid var(--oxblood); background:rgba(155,58,46,.06); padding:12px 15px; margin-top:18px; }
  .caveat h3 { margin:0 0 7px; font-size:12px; letter-spacing:.1em; text-transform:uppercase; color:var(--oxblood); }
  .caveat ul { margin:0; padding-left:19px; }
  .caveat li { font-size:13.5px; line-height:1.5; margin:3px 0; color:var(--ink-soft); }
"""

_LEVELS = (
    Judgement.LOW,
    Judgement.LOW_EXCEPT_CONFOUNDING,
    Judgement.MODERATE,
    Judgement.SERIOUS,
    Judgement.CRITICAL,
)


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def render(
    assessments: Sequence[Assessment],
    *,
    review_id: str = "",
    title: str | None = None,
    labels: Mapping[str, str] | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Serialize a set of assessments to a standalone review-level HTML figure."""
    if not assessments:
        raise ValueError("a review figure needs at least one finalized assessment")

    rows = review_rows(assessments, labels)
    summary = review_summary(assessments)
    when = generated_at or datetime.now(timezone.utc)
    doc_title = title or (
        f"Risk of Bias Across Results — {review_id}" if review_id
        else "Risk of Bias Across Results"
    )

    out: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{_esc(doc_title)}</title><style>{_BASE_CSS}{_EXTRA_CSS}</style>",
        "</head><body><div class='wrap'>",
        "<p class='eyebrow'>Black Swan Causal Labs</p>",
        "<h1>Risk of Bias Across Results</h1>",
        "<p class='subtitle'>ROBINS-I V2 &middot; follow-up (cohort) studies</p>",
        f"<p class='attrib'>{_esc(ATTRIBUTION)}</p>",
        "<div class='rule-bar'></div>",
    ]

    # ---- counts ----------------------------------------------------------- #
    out.append("<div class='tally'>")
    for n, cap in (
        (summary["n_results"], "Results assessed"),
        (summary["n_studies"], "Distinct documents"),
        (f"{summary['n_variant_a']} / {summary['n_variant_b']}", "Variant A / B"),
        (summary["n_unratified"], "Awaiting ratification"),
    ):
        out.append(
            f"<div class='t'><span class='cap'>{_esc(cap)}</span>"
            f"<div class='n'>{_esc(n)}</div></div>"
        )
    out.append("</div>")

    # ---- the grid --------------------------------------------------------- #
    out.append("<h2>Domain judgements by result</h2><div class='grid'><table class='tl'>")
    out.append("<thead><tr><th class='study'>Result assessed</th>")
    for d in range(1, 7):
        out.append(f"<th title='{_esc(DOMAIN_LABELS[d])}'>D{d}</th>")
    out.append("<th>Overall</th></tr></thead><tbody>")

    for row in rows:
        out.append("<tr>")
        out.append(
            f"<td class='study'>{_esc(row['label'])}"
            f"<span class='vbadge'>Variant {_esc(row['variant'])}</span>"
            f"<span class='rid'>{_esc(row['outcome'])}</span></td>"
        )
        for d in range(1, 7):
            cell = row["domains"].get(d)
            if cell is None:
                out.append("<td><span class='chip na'>n/a</span></td>")
                continue
            j = Judgement(cell["judgement"])
            mark = "<sup>&dagger;</sup>" if cell["overridden"] else ""
            out.append(
                f"<td><span class='chip {_CLASS[j]}' title='{_esc(cell['label'])}'>"
                f"{_esc(_SHORT[j])}{mark}</span></td>"
            )
        j = Judgement(row["overall"])
        mark = "<sup>&dagger;</sup>" if row["overall_overridden"] else ""
        out.append(
            f"<td class='ov'><span class='chip {_CLASS[j]}' "
            f"title='{_esc(row['overall_label'])}'>{_esc(_SHORT[j])}{mark}</span></td>"
        )
        out.append("</tr>")
    out.append("</tbody></table></div>")

    # ---- legend ----------------------------------------------------------- #
    out.append("<div class='legend'>")
    for j in _LEVELS:
        out.append(
            f"<span class='k'><span class='sw {_CLASS[j]}'></span>"
            f"{_esc(JUDGEMENT_LABELS[j])}</span>"
        )
    out.append("</div>")
    out.append(
        "<p class='note'>D1 bias due to confounding &middot; D2 classification of "
        "interventions &middot; D3 selection of participants &middot; D4 missing data "
        "&middot; D5 measurement of the outcome &middot; D6 selection of the reported "
        "result. &dagger; marks a judgement the assessor set against the algorithm.</p>"
    )

    # ---- what the figure must not be read as ------------------------------ #
    caveats = [
        "<b>Rows are results, not studies.</b> ROBINS-I assesses one numerical "
        f"result at a time. These {summary['n_results']} rows come from "
        f"{summary['n_studies']} document(s), so rows are not independent "
        "evidence and must not be counted as if they were.",
    ]
    if summary["n_variant_a"] and summary["n_variant_b"]:
        caveats.append(
            "<b>The D1 column does not mean one thing.</b> This set mixes domain 1 "
            "variants: under variant A the domain concerns baseline confounding "
            "only, under variant B baseline and time-varying confounding. Each row "
            "is badged with its variant."
        )
    if summary["n_unratified"]:
        caveats.append(
            f"<b>{summary['n_unratified']} of {summary['n_results']} results carry "
            "unratified items</b> — reviewer-prior answers, overrides, or an "
            "unratified P1. Those assessments are provisional until a human signs "
            "them off; see the per-result reports."
        )
    caveats.append(
        "<b>The instrument itself is a draft.</b> "
        f"Source: {_esc(SOURCE_STATUS)}."
    )
    out.append("<div class='caveat'><h3>How to read this figure</h3><ul>")
    out.extend(f"<li>{c}</li>" for c in caveats)
    out.append("</ul></div>")

    # ---- footer ----------------------------------------------------------- #
    out.append("<div class='rule-bar foot' style='margin-top:40px'></div><footer>")
    out.append(
        "<p class='stamp'>"
        f"Provenance — ROBINS-I V2 (follow-up/cohort), source {_esc(SOURCE_STATUS)} "
        f"&middot; impl Black Swan Causal Labs &middot; spec "
        f"{_esc(', '.join(summary['spec_versions']))} &middot; algorithms "
        f"{_esc(algorithm_fingerprint())} &middot; {summary['n_results']} result(s) "
        f"&middot; {when.strftime('%Y-%m-%d %H:%M UTC')}</p>"
    )
    out.append(f"<p>{_esc(NON_ENDORSEMENT)}</p>")
    out.append(f"<p><em>{_esc(FRAMEWORK_CITATION)}</em></p>")
    out.append(
        "<p>Each row is one ROBINS-I assessment of one numerical result, computed "
        "by algorithm from that result's signalling-question answers. This figure "
        "is a projection of those assessments; nothing is re-scored here. For why "
        "any single row reads as it does, see that result's own report.</p>"
    )
    out.append("</footer></div></body></html>")
    return "".join(out)


def write(assessments: Sequence[Assessment], path: str, **kwargs) -> str:
    html_text = render(assessments, **kwargs)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return path
