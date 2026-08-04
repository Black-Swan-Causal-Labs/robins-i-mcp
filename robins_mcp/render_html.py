"""HTML writer for a completed ROBINS-I assessment.

Self-contained single-file HTML — all CSS inline, no external assets — in the
Black Swan Causal Labs house style, matching the TARGET server's renderer so the
two instruments' outputs sit together.

Pure serializer: no scoring, no spec mutation. Two things it is required to
show, per the licensing position recorded in TRANSCRIPTION-NOTES.md:

* the attribution + non-endorsement block, and
* the algorithm judgement alongside the final judgement wherever a human
  overrode the algorithm.
"""

from __future__ import annotations

import html

from . import spec as _spec
from .algorithms import Judgement
from .report import (
    ATTRIBUTION,
    FRAMEWORK_CITATION,
    JUDGEMENT_LABELS,
    NON_ENDORSEMENT,
    Assessment,
)

#: labels for the summary strip. Words rather than glyphs, so the strip is
#: readable without a legend or knowledge of any colour convention.
_SHORT = {
    Judgement.LOW: "Low",
    Judgement.LOW_EXCEPT_CONFOUNDING: "Low*",
    Judgement.MODERATE: "Moderate",
    Judgement.SERIOUS: "Serious",
    Judgement.CRITICAL: "Critical",
}

_CLASS = {
    Judgement.LOW: "j-low",
    Judgement.LOW_EXCEPT_CONFOUNDING: "j-lowc",
    Judgement.MODERATE: "j-mod",
    Judgement.SERIOUS: "j-ser",
    Judgement.CRITICAL: "j-crit",
}

_MODE_LABEL = {
    "manuscript_positive": ("Manuscript", "m-pos"),
    "manuscript_absent": ("Absence", "m-abs"),
    "reviewer_prior": ("Reviewer prior", "m-prior"),
}

_CSS = """
  *, *::before, *::after { box-sizing: border-box; }
  :root {
    --paper:#F4F1E8; --surface:#FAF8F1; --ink:#111412; --ink-soft:#4B4E47; --ink-faint:#8A8C81;
    --line:#111412; --line-soft:rgba(17,20,18,.15); --accent:#15655A; --oxblood:#9B3A2E;
    --low:#2E6B34; --low-bg:rgba(46,107,52,.12);
    --mod:#9A6714; --mod-bg:rgba(154,103,20,.13);
    --ser:#9B3A2E; --ser-bg:rgba(155,58,46,.11);
    --crit:#111412; --crit-bg:rgba(17,20,18,.12);
    --font:"Times New Roman", Times, Georgia, serif; --maxw:1120px;
  }
  body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--font); font-size:16px; line-height:1.5; }
  .wrap { max-width:var(--maxw); margin:0 auto; padding:clamp(20px,4vw,52px) clamp(16px,4vw,40px) 72px; }
  .eyebrow { font-size:13px; letter-spacing:.2em; text-transform:uppercase; font-weight:700; margin:0 0 14px; }
  h1 { font-weight:700; font-size:clamp(1.7rem,3.4vw,2.5rem); line-height:1.12; margin:0 0 8px; letter-spacing:-.01em; }
  .subtitle { font-weight:700; font-style:italic; font-size:1.3rem; color:var(--accent); margin:0 0 16px; }
  .attrib { font-size:.95rem; color:var(--ink-soft); margin:0 0 18px; }
  .rule-bar { height:11px; background:var(--line); margin:22px 0 0; }
  .rule-bar.foot { margin:0 0 14px; }
  .meta { display:grid; grid-template-columns:max-content 1fr; gap:6px 18px; padding:14px 16px; background:var(--surface); border:1.5px solid var(--line); margin-top:22px; }
  .meta dt { font-size:12px; letter-spacing:.09em; text-transform:uppercase; color:var(--accent); font-weight:700; padding-top:2px; }
  .meta dd { margin:0; font-size:1rem; }
  .meta dd.cite { font-style:italic; color:var(--ink-soft); line-height:1.45; }
  h2 { font-size:13px; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-faint); font-weight:700; margin:34px 0 12px; }
  .verdict { display:flex; flex-wrap:wrap; align-items:center; gap:14px; padding:16px 18px; border:2px solid var(--line); background:var(--surface); }
  .verdict .lbl { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--ink-faint); font-weight:700; }
  .verdict .val { font-size:1.5rem; font-weight:700; }
  /* Summary strip: one cell per domain plus overall, spanning the full content
     width so its edges line up with the bordered blocks above and below. */
  .lights { display:grid; grid-template-columns:repeat(7,1fr); margin-top:18px; border:2px solid var(--line); background:var(--surface); }
  .cell { display:flex; flex-direction:column; gap:7px; padding:12px 11px 13px; border-left:1.5px solid var(--line); min-width:0; }
  .cell:first-child { border-left:none; }
  .cell.overall { border-left-width:3px; background:var(--paper); }
  .cell .dnum { font-size:10px; letter-spacing:.11em; text-transform:uppercase; font-weight:700; color:var(--ink-faint); }
  .cell .dname { font-size:11.5px; line-height:1.28; color:var(--ink-soft); }
  .band { display:flex; align-items:center; justify-content:center; text-align:center; padding:11px 5px; border:1.5px solid var(--line); font-weight:700; font-size:.9rem; line-height:1.12; color:#fff; }
  .band.j-low { background:var(--low); }
  .band.j-lowc { background:var(--low); box-shadow:inset 0 0 0 3px var(--surface); }
  .band.j-mod { background:var(--mod); }
  .band.j-ser { background:var(--ser); }
  .band.j-crit { background:var(--crit); }
  .ovr-mark { font-size:.72em; margin-left:2px; vertical-align:super; }
  @media (max-width:820px) { .lights { grid-template-columns:repeat(2,1fr); }
    .cell { border-left:none; border-top:1.5px solid var(--line); }
    .cell:nth-child(odd) { border-right:1.5px solid var(--line); }
    .cell:nth-child(-n+2) { border-top:none; }
    .cell.overall { border-left:none; } }
  .table-wrap { margin-top:14px; overflow-x:auto; border:2px solid var(--line); background:var(--surface); }
  table { border-collapse:collapse; width:100%; min-width:860px; table-layout:fixed; }
  td .pill { white-space:normal; }
  th { text-align:left; font-size:12px; letter-spacing:.1em; text-transform:uppercase; font-weight:700; padding:11px 14px; border-bottom:2px solid var(--line); background:var(--paper); }
  td { padding:12px 14px; border-bottom:1px solid var(--line-soft); vertical-align:top; font-size:1rem; }
  td.dom { font-weight:700; white-space:nowrap; }
  td.dom span { display:block; font-weight:400; font-size:12px; letter-spacing:.07em; text-transform:uppercase; color:var(--accent); }
  .pill { display:inline-block; font-size:13px; font-weight:700; padding:2px 10px; border:1.5px solid; white-space:nowrap; }
  .pill.j-low { color:var(--low); background:var(--low-bg); border-color:var(--low); }
  .pill.j-lowc { color:var(--low); background:var(--low-bg); border-color:var(--low); border-style:dashed; }
  .pill.j-mod { color:var(--mod); background:var(--mod-bg); border-color:var(--mod); }
  .pill.j-ser { color:var(--ser); background:var(--ser-bg); border-color:var(--ser); }
  .pill.j-crit { color:#fff; background:var(--crit); border-color:var(--crit); }
  .ovr { display:block; margin-top:5px; font-size:12px; font-style:italic; color:var(--oxblood); line-height:1.35; }
  .same { color:var(--ink-faint); font-size:.92rem; }
  details { border:1.5px solid var(--line-soft); background:var(--surface); margin-top:9px; }
  details[open] { border-color:var(--line); }
  summary { cursor:pointer; padding:9px 14px; font-weight:700; font-size:.95rem; list-style:none; display:flex; justify-content:space-between; gap:12px; align-items:center; }
  summary::-webkit-details-marker { display:none; }
  summary::after { content:"▸"; color:var(--accent); font-size:.9rem; }
  details[open] summary::after { content:"▾"; }
  summary .n { font-weight:400; color:var(--ink-faint); font-size:.86rem; }
  .trail { padding:2px 14px 14px; }
  .step { border-top:1px solid var(--line-soft); padding:11px 0; }
  .step:first-child { border-top:none; }
  .step .hd { display:flex; flex-wrap:wrap; gap:9px; align-items:baseline; }
  .qid { font-weight:700; font-variant-numeric:tabular-nums; }
  .qlab { color:var(--ink-soft); font-size:.95rem; }
  .ans { font-weight:700; font-size:.86rem; letter-spacing:.06em; padding:1px 7px; border:1.5px solid var(--line); background:var(--paper); }
  .mode { font-size:10.5px; letter-spacing:.09em; text-transform:uppercase; font-weight:700; padding:1px 7px; border:1px solid; }
  .mode.m-pos { color:var(--low); border-color:var(--low); }
  .mode.m-abs { color:var(--ink-faint); border-color:var(--ink-faint); }
  .mode.m-prior { color:var(--oxblood); border-color:var(--oxblood); background:rgba(155,58,46,.08); }
  .step p { margin:7px 0 0; font-size:.95rem; line-height:1.5; }
  blockquote { margin:7px 0 0 0; padding:5px 0 5px 13px; border-left:3px solid var(--accent); font-size:.93rem; color:var(--ink-soft); font-style:italic; }
  blockquote cite { display:block; margin-top:4px; font-style:normal; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--accent); font-weight:700; }
  blockquote cite.unbound { color:var(--oxblood); }
  .note { font-size:.9rem; color:var(--ink-faint); margin:8px 0 0; }
  .flag { border:2px solid var(--oxblood); background:rgba(155,58,46,.07); padding:15px 18px; margin-top:14px; }
  .flag h3 { margin:0 0 9px; font-size:13px; letter-spacing:.13em; text-transform:uppercase; color:var(--oxblood); }
  .flag ul { margin:0; padding-left:20px; } .flag li { margin:4px 0; font-size:.96rem; }
  .conf { columns:2; column-gap:28px; font-size:.96rem; margin:0; padding-left:20px; }
  .conf li { margin:3px 0; break-inside:avoid; }
  footer { margin-top:40px; font-size:.88rem; color:var(--ink-soft); line-height:1.55; }
  footer .stamp { font-weight:700; color:var(--ink-soft); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; word-break:break-all; }
  footer p { margin:0 0 10px; }
  @media (max-width:640px) { .meta { grid-template-columns:1fr; gap:2px 0; } .meta dt { padding-top:9px; } .conf { columns:1; } }
"""


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def _pill(judgement: Judgement) -> str:
    return f'<span class="pill {_CLASS[judgement]}">{_esc(JUDGEMENT_LABELS[judgement])}</span>'


def render(assessment: Assessment, *, title: str | None = None) -> str:
    """Serialize a finalized assessment to a standalone HTML document."""
    a = assessment
    prov = a.provenance()
    doc_title = title or f"Risk of Bias Assessment — {a.result_id}"

    out: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{_esc(doc_title)}</title><style>{_CSS}</style></head><body><div class='wrap'>",
        "<p class='eyebrow'>Black Swan Causal Labs</p>",
        "<h1>Risk of Bias Assessment</h1>",
        "<p class='subtitle'>ROBINS-I V2 &middot; follow-up (cohort) studies</p>",
        f"<p class='attrib'>{_esc(ATTRIBUTION)}</p>",
        "<div class='rule-bar'></div>",
    ]

    # ---- what was assessed ------------------------------------------------
    variant = "B — per-protocol effect" if a.per_protocol else "A — intention-to-treat effect"
    out.append("<dl class='meta'>")
    for term, value, cls in [
        ("Study", a.citation, "cite"),
        ("Result assessed", a.result_assessed, ""),
        ("Outcome", a.outcome, ""),
        ("Location in report", a.result_location, ""),
        ("Estimand (C4)", variant, ""),
        ("Information sources", ", ".join(a.information_sources), ""),
    ]:
        if value:
            klass = f" class='{cls}'" if cls else ""
            out.append(f"<dt>{_esc(term)}</dt><dd{klass}>{_esc(value)}</dd>")
    out.append("</dl>")

    # ---- target trial specification (C1-C3) -------------------------------
    if a.target_trial:
        out.append("<h2>Target trial specified for this study (C1&ndash;C3)</h2>")
        out.append("<dl class='meta' style='margin-top:0'>")
        for term, value in a.target_trial.items():
            out.append(f"<dt>{_esc(term.replace('_', ' '))}</dt><dd>{_esc(value)}</dd>")
        out.append("</dl>")

    # ---- overall ----------------------------------------------------------
    out.append("<h2>Overall risk of bias</h2><div class='verdict'>")
    out.append("<span class='lbl'>Judgement</span>")
    out.append(f"<span class='val'>{_pill(a.overall)}</span>")
    if a.overall_overridden:
        out.append(
            "<span class='ovr'>Algorithm: "
            f"{_esc(JUDGEMENT_LABELS[a.overall_algorithm.judgement])} &mdash; "
            f"overridden. {_esc(a.overall_override_justification)}</span>"
        )
    for note in a.overall_algorithm.notes:
        out.append(f"<span class='same'>{_esc(note)}</span>")
    if a.direction_of_bias:
        out.append(f"<span class='same'>Predicted direction: {_esc(a.direction_of_bias)}</span>")
    out.append("</div>")

    # ---- traffic lights ---------------------------------------------------
    any_override = any(d.overridden for d in a.domains) or a.overall_overridden
    out.append("<div class='lights'>")
    for d in sorted(a.domains, key=lambda x: x.domain):
        mark = "<sup class='ovr-mark'>&dagger;</sup>" if d.overridden else ""
        out.append(
            f"<div class='cell'><span class='dnum'>Domain {d.domain}</span>"
            f"<span class='band {_CLASS[d.judgement]}'>{_esc(_SHORT[d.judgement])}{mark}</span>"
            f"<span class='dname'>{_esc(d.label)}</span></div>"
        )
    mark = "<sup class='ovr-mark'>&dagger;</sup>" if a.overall_overridden else ""
    out.append(
        f"<div class='cell overall'><span class='dnum'>Overall</span>"
        f"<span class='band {_CLASS[a.overall]}'>{_esc(_SHORT[a.overall])}{mark}</span>"
        "<span class='dname'>Worst domain, unless overridden</span></div>"
    )
    out.append("</div>")
    note = (
        "&ldquo;Low*&rdquo; is the best judgement attainable in domain 1: residual confounding "
        "cannot be excluded in a non-randomized study, so that domain never reaches plain low."
    )
    if any_override:
        note += (
            " &dagger; marks a judgement the assessor set against the algorithm; the strip shows "
            "the final value and the algorithm&rsquo;s own output is in the table below."
        )
    out.append(f"<p class='note'>{note}</p>")

    # ---- ratification queue ----------------------------------------------
    queue = a.ratification_queue
    if queue:
        out.append("<div class='flag'><h3>Requires human ratification before this is final</h3><ul>")
        out.extend(f"<li>{_esc(item)}</li>" for item in queue)
        out.append("</ul></div>")

    # ---- domain table -----------------------------------------------------
    out.append("<h2>Domain judgements</h2><div class='table-wrap'><table><thead><tr>")
    out.append(
        "<th style='width:23%'>Domain</th><th style='width:19%'>Algorithm</th>"
        "<th style='width:19%'>Final</th><th>Support for judgement</th></tr></thead><tbody>"
    )
    for d in sorted(a.domains, key=lambda x: x.domain):
        final_cell = (
            _pill(d.judgement) + f"<span class='ovr'>Override: {_esc(d.override_justification)}</span>"
            if d.overridden
            else "<span class='same'>as algorithm</span>"
        )
        support = _esc(d.support)
        if d.direction_of_bias:
            support += f"<span class='ovr' style='color:var(--ink-faint)'>Predicted direction: {_esc(d.direction_of_bias)}</span>"
        out.append(
            f"<tr><td class='dom'><span>Domain {d.domain}</span>{_esc(d.label)}</td>"
            f"<td>{_pill(d.algorithm.judgement)}</td><td>{final_cell}</td><td>{support}</td></tr>"
        )
    out.append("</tbody></table></div>")

    # ---- audit trail ------------------------------------------------------
    out.append("<h2>Audit trail</h2>")
    out.append(
        "<p class='note'>Only the signalling questions the algorithm actually reached are shown, "
        "in the order it reached them &mdash; which is not always numerical order, because some "
        "questions are only asked on particular branches. The remainder are not applicable on "
        "this path. Descriptions are this implementation's own wording; question identifiers are "
        "the interoperable part.</p>"
    )
    for d in sorted(a.domains, key=lambda x: x.domain):
        steps = a.trail(d.domain)
        skipped = len(d.algorithm.not_reached)
        out.append(
            f"<details><summary><span>Domain {d.domain} &mdash; {_esc(d.label)}</span>"
            f"<span class='n'>{len(steps)} reached &middot; {skipped} not applicable</span></summary>"
            "<div class='trail'>"
        )
        for step in steps:
            label = _spec.label_for(str(step["question"]), per_protocol=a.per_protocol)
            mode = step["evidence_mode"]
            mode_html = ""
            if mode:
                text, cls = _MODE_LABEL[str(mode)]
                mode_html = f"<span class='mode {cls}'>{_esc(text)}</span>"
            out.append(
                f"<div class='step'><div class='hd'><span class='qid'>{_esc(step['question'])}</span>"
                f"<span class='ans'>{_esc(step['response'])}</span>{mode_html}"
                f"<span class='qlab'>{_esc(label)}</span></div>"
            )
            if step["rationale"]:
                out.append(f"<p>{_esc(step['rationale'])}</p>")
            for quote in step["quotes"]:
                locator = quote.get("locator") or ""
                span = quote.get("span")
                cite = ""
                if locator:
                    offsets = f" [{span[0]}&ndash;{span[1]}]" if span else ""
                    cite = f"<cite>{_esc(locator)}{offsets}</cite>"
                else:
                    cite = "<cite class='unbound'>not resolved to the source</cite>"
                out.append(f"<blockquote>{_esc(quote['text'])}{cite}</blockquote>")
            if step["search_record"]:
                badge = "" if step.get("search_auditable") else " (free text — not auditable)"
                out.append(
                    f"<p class='note'>Absence check: {_esc(step['search_record'])}{badge}</p>"
                )
            if step["prior_ref"]:
                out.append(f"<p class='note'>Judged against: {_esc(step['prior_ref'])}</p>")
            out.append("</div>")
        for note in d.algorithm.notes:
            out.append(f"<p class='note'>{_esc(note)}</p>")
        out.append("</div></details>")

    # ---- prespecified confounders ----------------------------------------
    out.append("<h2>Prespecified confounding factors (P1)</h2>")
    if a.prespecified_confounders:
        out.append("<ul class='conf'>")
        out.extend(f"<li>{_esc(c)}</li>" for c in a.prespecified_confounders)
        out.append("</ul>")
    else:
        out.append(
            "<div class='flag'><h3>None supplied</h3><p style='margin:0'>Domain 1 asks whether "
            "<em>all important</em> confounding factors were controlled for. Which factors count "
            "as important is set at review level, not by the assessed paper, so this domain "
            "cannot be finalized without it.</p></div>"
        )

    # ---- footer -----------------------------------------------------------
    out.append("<div class='rule-bar foot' style='margin-top:40px'></div><footer>")
    out.append(f"<p class='stamp'>{_esc(a.provenance_line())}</p>")
    out.append(f"<p>{_esc(NON_ENDORSEMENT)}</p>")
    out.append(f"<p><em>{_esc(FRAMEWORK_CITATION)}</em></p>")
    out.append(
        "<p>Domain and overall judgements are computed by algorithm from the signalling-question "
        "answers; they are not asserted directly. Where a human overrode the algorithm, both "
        "values are shown above. Algorithm transcription is fingerprinted in the stamp above so "
        "that a later correction is detectable in reports produced under the earlier version.</p>"
    )
    out.append("</footer></div></body></html>")
    return "\n".join(out)


def write(assessment: Assessment, path: str, *, title: str | None = None) -> str:
    from pathlib import Path

    Path(path).write_text(render(assessment, title=title), encoding="utf-8")
    return path
