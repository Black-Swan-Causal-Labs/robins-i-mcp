"""The assessment record, and what you can build from a pile of them.

ROBINS-I assesses ONE result at a time, and each assessment costs a session:
the model reads a paper and answers signalling questions against it. A review of
200 studies is therefore 200 runs, and nothing about the server's in-process
state survives between them.

So the unit of interchange is not an `Assessment` object and not this server's
memory — it is a **record**: a small, flat, self-describing summary that one run
emits and any later agent can read. A record is a few hundred bytes, so a
review's worth fits comfortably in one context, and it carries no dependency on
this codebase.

What a record must carry, and why:

* the judgements, obviously — that is what a figure plots;
* enough identity to label a row (citation, outcome, the result assessed);
* the C4 variant, because domain 1 means something different under each;
* whether anything was overridden, and whether ratification is outstanding —
  an unratified assessment is not final and a figure must not imply it is;
* the provenance stamp: text hash, algorithm fingerprint, spec version, source
  status. Without these a row in a summary figure is an anonymous coloured
  square. With them it can be traced back to the document it came from and the
  transcription that produced it.

`RECORD_VERSION` is a compatibility surface: anything consuming records should
check it rather than assume shape.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping, Sequence

from .algorithms import Judgement
from .report import DOMAIN_LABELS, JUDGEMENT_LABELS, Assessment

#: Bump when the record shape changes in a way a consumer would notice.
RECORD_VERSION = "robins-i-record-1"


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #

def assessment_record(assessment: Assessment) -> dict[str, Any]:
    """The portable summary of one finalized assessment.

    This is what a run should hand on: write it to disk, return it to an
    orchestrator, paste it into the next session. It is deliberately flat and
    JSON-native — no dataclasses, no int keys — so it survives a round trip
    through anything.
    """
    a = assessment
    per_domain = []
    for outcome in sorted(a.domains, key=lambda d: d.domain):
        per_domain.append({
            "domain": outcome.domain,
            "label": DOMAIN_LABELS[outcome.domain],
            "judgement": outcome.judgement.value,
            "judgement_label": JUDGEMENT_LABELS[outcome.judgement],
            "algorithm_judgement": outcome.algorithm.judgement.value,
            "overridden": outcome.overridden,
            "override_justification": outcome.override_justification,
            "direction_of_bias": outcome.direction_of_bias,
        })
    queue = list(a.ratification_queue)
    return {
        "record_version": RECORD_VERSION,
        "result_id": a.result_id,
        "citation": a.citation,
        "result_assessed": a.result_assessed,
        "outcome": a.outcome,
        "result_location": a.result_location,
        "estimand": "yes_pp" if a.per_protocol else "no_itt",
        "domain1_variant": "B" if a.per_protocol else "A",
        "screening_terminated": a.screening_terminated,
        "domains": per_domain,
        "overall": {
            "judgement": a.overall.value,
            "judgement_label": JUDGEMENT_LABELS[a.overall],
            "algorithm_judgement": a.overall_algorithm.judgement.value,
            "overridden": a.overall_overridden,
            "override_justification": a.overall_override_justification,
            "direction_of_bias": a.direction_of_bias,
            "notes": list(a.overall_algorithm.notes),
        },
        "ratification": {
            "outstanding": queue,
            "is_final": not queue,
        },
        "prespecified_confounders": list(a.prespecified_confounders),
        "information_sources": list(a.information_sources),
        "provenance": a.provenance(),
    }


class RecordError(ValueError):
    """A supplied record is not one, or is of a shape this version cannot read."""


def as_record(obj: Assessment | Mapping[str, Any]) -> dict[str, Any]:
    """Accept either a live Assessment or an already-emitted record."""
    if isinstance(obj, Assessment):
        return assessment_record(obj)
    if not isinstance(obj, Mapping):
        raise RecordError(f"expected an assessment record (a mapping), got {type(obj).__name__}")
    version = obj.get("record_version")
    if version is None:
        raise RecordError(
            "record is missing 'record_version'. Records are produced by "
            "submit_answers(domain=0) — see its `record` field — not hand-built."
        )
    if version != RECORD_VERSION:
        raise RecordError(
            f"record_version {version!r} but this build reads {RECORD_VERSION!r}. "
            "Re-export the records, or read them with the matching version."
        )
    for required in ("result_id", "domains", "overall", "provenance"):
        if required not in obj:
            raise RecordError(f"record for {obj.get('result_id', '?')!r} is missing {required!r}")
    return dict(obj)


def as_records(objs: Iterable[Assessment | Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [as_record(o) for o in objs]
    if not records:
        raise RecordError("no assessment records supplied")
    return records


def _judgements(record: Mapping[str, Any]) -> dict[int, str]:
    return {int(d["domain"]): d["judgement"] for d in record["domains"]}


# --------------------------------------------------------------------------- #
# Summaries over a pile of records
# --------------------------------------------------------------------------- #

def review_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts a review-level output has to state to avoid overstating itself."""
    documents = {r["provenance"].get("text_sha256") for r in records}
    documents.discard("")
    documents.discard(None)
    per_domain: dict[int, dict[str, int]] = {}
    for record in records:
        for domain, judgement in _judgements(record).items():
            tally = per_domain.setdefault(domain, {})
            tally[judgement] = tally.get(judgement, 0) + 1
    overall: dict[str, int] = {}
    for record in records:
        value = record["overall"]["judgement"]
        overall[value] = overall.get(value, 0) + 1
    return {
        "n_results": len(records),
        "n_documents": len(documents),
        "n_variant_a": sum(1 for r in records if r.get("domain1_variant") == "A"),
        "n_variant_b": sum(1 for r in records if r.get("domain1_variant") == "B"),
        "n_not_final": sum(1 for r in records if not r["ratification"]["is_final"]),
        "per_domain": per_domain,
        "overall": overall,
        "spec_versions": sorted({r["provenance"].get("spec_version", "?") for r in records}),
        "algorithm_fingerprints": sorted(
            {r["provenance"].get("algorithm_fingerprint", "?") for r in records}),
        "source_status": sorted({r["provenance"].get("source_status", "?") for r in records}),
    }


# --------------------------------------------------------------------------- #
# robvis interoperability
#
# robvis (McGuinness & Higgins) is how risk-of-bias assessments become
# Cochrane-style figures, so it is the natural destination for a review's worth
# of records. Getting a file into it correctly is not a matter of writing our
# six columns out in order, for two reasons established by reading its source.
#
# 1. Its `tool="ROBINS-I"` template is ROBINS-I *V1*: seven domains, and V1
#    orders selection of participants BEFORE classification of interventions.
#    V2 has six and swaps that pair. A positional dump loses no data and raises
#    no error — it silently prints the classification judgement under the
#    heading "Bias due to selection of participants". So we place judgements
#    into V1's SLOTS, and mark the dropped deviations domain NA.
#
# 2. Its `tool="Generic"` looks more accommodating — arbitrary columns, header
#    row as labels — but is really its ROB1 path, and its preprocessing
#        substr(x,0,2); gsub("se","h"); substr(x,0,1); gsub("m","s")
#    renames Moderate to "Some concerns" and Serious to "High". Wrong
#    vocabulary for ROBINS-I, so it is offered but not the default.
#
# Both share a hard limit: robvis reduces every cell to its first initial and
# defines fills only for l/m/s/c/n/x. "Low" and "Low except for concerns about
# uncontrolled confounding" both collapse to "l", so the qualified level cannot
# be represented by any cell string. `robvis_table` reports that rather than
# degrading quietly.
# --------------------------------------------------------------------------- #

#: V1's seven domains in V1's order — the interoperability contract robvis's
#: ROBINS-I template expects, NOT a claim about what V2's domains are.
ROBVIS_V1_HEADER: tuple[str, ...] = (
    "Study", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "Overall", "Weight",
)

#: V1 slot -> V2 domain number. None means no V2 counterpart.
_V1_SLOT_TO_V2_DOMAIN: tuple[int | None, ...] = (1, 3, 2, None, 4, 5, 6)

#: robvis's clean_data maps "na" to "x", which its palette draws as N/A.
ROBVIS_NOT_APPLICABLE = "NA"

JUDGEMENT_TO_ROBVIS: Mapping[str, str] = {
    Judgement.LOW.value: "Low",
    Judgement.LOW_EXCEPT_CONFOUNDING.value: "Low",   # lossy; see module note
    Judgement.MODERATE.value: "Moderate",
    Judgement.SERIOUS.value: "Serious",
    Judgement.CRITICAL.value: "Critical",
}

ROBVIS_LAYOUTS = ("robins_i", "generic")


def _label(record: Mapping[str, Any], labels: Mapping[str, str] | None) -> str:
    if labels and record["result_id"] in labels:
        return labels[record["result_id"]]
    return record["result_id"]


def robvis_table(
    records: Sequence[Mapping[str, Any]],
    layout: str = "robins_i",
    labels: Mapping[str, str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build a robvis-ready table from records, with its losses declared.

    layout='robins_i' (default) writes V1's seven-column template with each V2
    judgement in its correct V1 slot and the deviations slot marked NA. Upload
    with `tool = "ROBINS-I"`; the judgement vocabulary then matches ROBINS-I's.

    layout='generic' writes six columns headed with V2's own domain names, for
    `tool = "Generic"`. Correct headings, but robvis relabels the judgements
    into ROB1's vocabulary. Prefer 'robins_i'.
    """
    if layout not in ROBVIS_LAYOUTS:
        raise ValueError(f"layout must be one of {list(ROBVIS_LAYOUTS)}, not {layout!r}")

    losses: list[str] = []
    qualified = any(
        j == Judgement.LOW_EXCEPT_CONFOUNDING.value
        for r in records for j in _judgements(r).values()
    ) or any(
        r["overall"]["judgement"] == Judgement.LOW_EXCEPT_CONFOUNDING.value for r in records
    )
    if qualified:
        losses.append(
            "'Low, except for concerns about uncontrolled confounding' is written as "
            "'Low'. robvis reduces every cell to its first initial and defines fills "
            "only for low/moderate/serious/critical/no-information/NA, so the "
            "qualified level cannot be carried by any cell string. State it in the "
            "figure caption. (Note the OVERALL judgement is qualified whenever every "
            "domain sits at its lowest level, so this applies more often than the "
            "domain cells alone suggest.)"
        )
    variants = {r.get("domain1_variant") for r in records}
    if len(variants) > 1:
        losses.append(
            "This set mixes domain 1 variants (A and B), so the D1 column does not "
            "mean one thing across rows: variant A concerns baseline confounding, "
            "variant B baseline and time-varying. Split the figure by variant, or "
            "say so in the caption."
        )
    not_final = [r["result_id"] for r in records if not r["ratification"]["is_final"]]
    if not_final:
        losses.append(
            f"{len(not_final)} of {len(records)} records are NOT final — they carry "
            "unratified reviewer-prior answers, overrides, or an unratified P1. A "
            "published figure should not present them as settled: "
            f"{not_final[:5]}{' ...' if len(not_final) > 5 else ''}"
        )
    if weights is None:
        losses.append(
            "Weight is 1 for every row (equal weighting). robvis's weighted bar chart "
            "implies precision weighting; do not present it as such without supplying "
            "real meta-analysis weights."
        )
    fingerprints = {r["provenance"].get("algorithm_fingerprint") for r in records}
    if len(fingerprints) > 1:
        losses.append(
            "Records were produced under DIFFERENT algorithm transcriptions "
            f"({sorted(fingerprints)}). Their judgements are not strictly comparable; "
            "re-run the older ones before combining."
        )

    if layout == "robins_i":
        header = ROBVIS_V1_HEADER
        slots: Sequence[int | None] = _V1_SLOT_TO_V2_DOMAIN
    else:
        header = ("Study",) + tuple(DOMAIN_LABELS[d] for d in range(1, 7)) + (
            "Overall", "Weight")
        slots = tuple(range(1, 7))

    rows: list[list[str]] = []
    for record in records:
        judgements = _judgements(record)
        cells = [_label(record, labels)]
        for domain in slots:
            if domain is None or domain not in judgements:
                cells.append(ROBVIS_NOT_APPLICABLE)
            else:
                cells.append(JUDGEMENT_TO_ROBVIS[judgements[domain]])
        cells.append(JUDGEMENT_TO_ROBVIS[record["overall"]["judgement"]])
        cells.append(str((weights or {}).get(record["result_id"], 1)))
        rows.append(cells)

    return {
        "layout": layout,
        "robvis_tool": "ROBINS-I" if layout == "robins_i" else "Generic",
        "header": list(header),
        "rows": rows,
        "n_results": len(rows),
        "losses": losses,
        "summary": review_summary(records),
        "slot_mapping": (
            {f"V1 {ROBVIS_V1_HEADER[i + 1]}":
                (f"V2 domain {d} — {DOMAIN_LABELS[d]}" if d else
                 "no V2 counterpart (deviations domain dropped in V2) — written NA")
             for i, d in enumerate(_V1_SLOT_TO_V2_DOMAIN)}
            if layout == "robins_i" else None
        ),
    }


def robvis_csv(
    records: Sequence[Mapping[str, Any]],
    layout: str = "robins_i",
    labels: Mapping[str, str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """`robvis_table` serialized as CSV text, ready to upload to robvis."""
    table = robvis_table(records, layout=layout, labels=labels, weights=weights)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(table["header"])
    writer.writerows(table["rows"])
    table["csv"] = buf.getvalue()
    return table
