"""Review-level aggregation across many assessed results.

ROBINS-I assesses ONE result at a time — that is the unit, and it is stricter
than one study. But the tool is explicitly built for a *series* of assessments
inside a review: P1 is a planning-stage input agreed once and applied to every
study, and the source requires preliminaries to be agreed between assessors
before anyone works individually. This module is the review-level view of that
series: a row per assessed result, and an export for `robvis`.

Two things it refuses to blur.

**Rows are results, not studies.** A paper contributing three outcomes gets
three rows. That is more honest than the usual figure, which implies three
studies' worth of independent evidence; `n_studies` is reported separately from
`n_results` so the difference is visible.

**Domain 1 is not comparable across variants.** A row scored under C4 = no
(variant A) has a domain 1 about baseline confounding; under C4 = yes (variant
B) it is about baseline *and* time-varying confounding. Every row carries its
variant so the figure can say so rather than implying one column means one
thing.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping, Sequence

from .algorithms import Judgement
from .report import DOMAIN_LABELS, JUDGEMENT_LABELS, Assessment, algorithm_fingerprint

# --------------------------------------------------------------------------- #
# robvis interoperability
#
# robvis (McGuinness & Higgins) is how risk-of-bias assessments become
# Cochrane-style traffic-light and summary figures. Getting a file into it
# correctly is not a matter of writing our six columns out in order, for two
# reasons established by reading robvis's own source.
#
# 1. Its `tool="ROBINS-I"` template is ROBINS-I *V1*: seven domains, and V1
#    orders selection of participants BEFORE classification of interventions.
#    V2 has six domains and swaps that pair. A positional dump loses no data and
#    raises no error — it silently prints the classification judgement under the
#    heading "Bias due to selection of participants". So we place our judgements
#    into V1's SLOTS rather than emitting them in V2 order, and mark the dropped
#    deviations domain "NA", which robvis renders as N/A.
#
# 2. Its `tool="Generic"` path looks more accommodating — arbitrary columns,
#    header row as labels — but its preprocessing is ROB1's:
#        substr(x,0,2); gsub("se","h"); substr(x,0,1); gsub("m","s")
#    which renames Moderate to "Some concerns" and Serious to "High". That is
#    the wrong vocabulary for ROBINS-I, so it is offered but not the default.
#
# Both paths share a hard limit: robvis reduces every cell to its first initial
# and defines fills only for l/m/s/c/n/x. "Low" and "Low except for concerns
# about uncontrolled confounding" both collapse to "l", so the qualified level
# CANNOT be represented in robvis by any cell string. The loss is reported by
# `robvis_table`, not hidden; our own review figure keeps the sixth level.
# --------------------------------------------------------------------------- #

#: V1's seven domains, in V1's order — the header robvis's ROBINS-I template
#: expects. Kept verbatim as the interoperability contract, NOT as a claim about
#: what V2's domains are.
ROBVIS_V1_HEADER: tuple[str, ...] = (
    "Study",
    "D1",  # bias due to confounding
    "D2",  # bias due to selection of participants          <- V2 domain 3
    "D3",  # bias in classification of interventions        <- V2 domain 2
    "D4",  # bias due to deviations from intended interventions — absent in V2
    "D5",  # bias due to missing data                       <- V2 domain 4
    "D6",  # bias in measurement of outcomes                <- V2 domain 5
    "D7",  # bias in selection of the reported result       <- V2 domain 6
    "Overall",
    "Weight",
)

#: V1 slot -> V2 domain number. None means the slot has no V2 counterpart.
_V1_SLOT_TO_V2_DOMAIN: tuple[int | None, ...] = (1, 3, 2, None, 4, 5, 6)

#: What robvis renders for a slot with no V2 counterpart. Its `clean_data`
#: maps "na" to "x", which the palette draws as N/A.
ROBVIS_NOT_APPLICABLE = "NA"

#: Judgement -> the cell string robvis parses. Note LOW and
#: LOW_EXCEPT_CONFOUNDING map to the same value; see the module note.
JUDGEMENT_TO_ROBVIS: Mapping[Judgement, str] = {
    Judgement.LOW: "Low",
    Judgement.LOW_EXCEPT_CONFOUNDING: "Low",
    Judgement.MODERATE: "Moderate",
    Judgement.SERIOUS: "Serious",
    Judgement.CRITICAL: "Critical",
}

ROBVIS_LAYOUTS = ("robins_i", "generic")


def _label(assessment: Assessment, labels: Mapping[str, str] | None) -> str:
    if labels and assessment.result_id in labels:
        return labels[assessment.result_id]
    return assessment.result_id


def review_rows(
    assessments: Sequence[Assessment],
    labels: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One row per assessed result, in the order supplied."""
    rows = []
    for a in assessments:
        judgements = a.domain_judgements
        rows.append({
            "result_id": a.result_id,
            "label": _label(a, labels),
            "citation": a.citation,
            "outcome": a.outcome,
            "result_assessed": a.result_assessed,
            "variant": "B" if a.per_protocol else "A",
            "variant_label": (
                "per-protocol — baseline and time-varying confounding"
                if a.per_protocol else
                "intention-to-treat — baseline confounding only"
            ),
            "screening_terminated": a.screening_terminated,
            "domains": {
                d: {
                    "judgement": judgements[d].value,
                    "label": JUDGEMENT_LABELS[judgements[d]],
                    "domain_label": DOMAIN_LABELS[d],
                    "overridden": next(
                        (o.overridden for o in a.domains if o.domain == d), False),
                }
                for d in sorted(judgements)
            },
            "overall": a.overall.value,
            "overall_label": JUDGEMENT_LABELS[a.overall],
            "overall_overridden": a.overall_overridden,
            "ratification_queue": list(a.ratification_queue),
            "text_sha256": a.text_sha256,
            "spec_version": a.spec_version,
        })
    return rows


def review_summary(assessments: Sequence[Assessment]) -> dict[str, Any]:
    """Counts that a review-level figure has to state to be honest."""
    studies = {a.text_sha256 for a in assessments if a.text_sha256}
    per_domain: dict[int, dict[str, int]] = {}
    for a in assessments:
        for domain, judgement in a.domain_judgements.items():
            tally = per_domain.setdefault(domain, {})
            tally[judgement.value] = tally.get(judgement.value, 0) + 1
    overall: dict[str, int] = {}
    for a in assessments:
        overall[a.overall.value] = overall.get(a.overall.value, 0) + 1
    fingerprints = {algorithm_fingerprint()}
    return {
        "n_results": len(assessments),
        "n_studies": len(studies),
        "n_variant_a": sum(1 for a in assessments if not a.per_protocol),
        "n_variant_b": sum(1 for a in assessments if a.per_protocol),
        "per_domain": per_domain,
        "overall": overall,
        "n_unratified": sum(1 for a in assessments if a.ratification_queue),
        "spec_versions": sorted({a.spec_version for a in assessments}),
        "algorithm_fingerprints": sorted(fingerprints),
    }


def robvis_table(
    assessments: Sequence[Assessment],
    layout: str = "robins_i",
    labels: Mapping[str, str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build a robvis-ready table, with its losses reported rather than hidden.

    layout='robins_i' (default) writes V1's seven-column template with our V2
    judgements placed in V1's slots and the deviations slot marked NA. Use
    `tool = "ROBINS-I"` in robvis: the judgement vocabulary then matches
    ROBINS-I's own (Low / Moderate / Serious / Critical).

    layout='generic' writes six columns headed with V2's own domain names. Use
    `tool = "Generic"`. The columns are labelled correctly, but robvis will
    relabel the judgements into ROB1's vocabulary — Moderate becomes "Some
    concerns", Serious becomes "High" — unless you override `judgement_labels`
    in the R package. Prefer 'robins_i' unless you need the V2 headings.
    """
    if layout not in ROBVIS_LAYOUTS:
        raise ValueError(f"layout must be one of {list(ROBVIS_LAYOUTS)}, not {layout!r}")

    losses: list[str] = []
    if any(
        j is Judgement.LOW_EXCEPT_CONFOUNDING
        for a in assessments for j in a.domain_judgements.values()
    ) or any(a.overall is Judgement.LOW_EXCEPT_CONFOUNDING for a in assessments):
        losses.append(
            "'Low, except for concerns about uncontrolled confounding' is written "
            "as 'Low'. robvis reduces every cell to its first initial and defines "
            "fills only for low/moderate/serious/critical/no-information/NA, so "
            "the qualified level cannot be represented in it by any cell string. "
            "State the qualification in the figure caption, or use render_review "
            "which keeps it as a distinct level."
        )
    if any(a.per_protocol for a in assessments) and any(
            not a.per_protocol for a in assessments):
        losses.append(
            "This set mixes domain 1 variants (A and B). The D1 column therefore "
            "does not mean one thing across rows: variant A concerns baseline "
            "confounding, variant B baseline and time-varying. Split the figure "
            "by variant, or say so in the caption."
        )
    if weights is None:
        losses.append(
            "Weight is 1 for every row (equal weighting). robvis's weighted bar "
            "chart implies precision weighting; do not present it as such without "
            "supplying real meta-analysis weights."
        )

    header: tuple[str, ...]
    rows: list[list[str]] = []
    if layout == "robins_i":
        header = ROBVIS_V1_HEADER
        for a in assessments:
            judgements = a.domain_judgements
            cells = [_label(a, labels)]
            for v2_domain in _V1_SLOT_TO_V2_DOMAIN:
                if v2_domain is None or v2_domain not in judgements:
                    cells.append(ROBVIS_NOT_APPLICABLE)
                else:
                    cells.append(JUDGEMENT_TO_ROBVIS[judgements[v2_domain]])
            cells.append(JUDGEMENT_TO_ROBVIS[a.overall])
            cells.append(str((weights or {}).get(a.result_id, 1)))
            rows.append(cells)
    else:
        header = ("Study",) + tuple(DOMAIN_LABELS[d] for d in range(1, 7)) + (
            "Overall", "Weight")
        for a in assessments:
            judgements = a.domain_judgements
            cells = [_label(a, labels)]
            for domain in range(1, 7):
                cells.append(
                    JUDGEMENT_TO_ROBVIS[judgements[domain]]
                    if domain in judgements else ROBVIS_NOT_APPLICABLE
                )
            cells.append(JUDGEMENT_TO_ROBVIS[a.overall])
            cells.append(str((weights or {}).get(a.result_id, 1)))
            rows.append(cells)

    return {
        "layout": layout,
        "robvis_tool": "ROBINS-I" if layout == "robins_i" else "Generic",
        "header": list(header),
        "rows": rows,
        "n_results": len(rows),
        "losses": losses,
        "slot_mapping": (
            {f"V1 {ROBVIS_V1_HEADER[i + 1]}":
                (f"V2 domain {d} — {DOMAIN_LABELS[d]}" if d else
                 "no V2 counterpart (deviations domain dropped in V2) — written NA")
             for i, d in enumerate(_V1_SLOT_TO_V2_DOMAIN)}
            if layout == "robins_i" else None
        ),
    }


def robvis_csv(
    assessments: Sequence[Assessment],
    layout: str = "robins_i",
    labels: Mapping[str, str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """`robvis_table` serialized as CSV text, ready to upload to robvis."""
    table = robvis_table(assessments, layout=layout, labels=labels, weights=weights)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(table["header"])
    writer.writerows(table["rows"])
    table["csv"] = buf.getvalue()
    return table
