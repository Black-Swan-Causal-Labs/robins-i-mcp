# Copyright 2026 Black Swan Causal Labs
# SPDX-License-Identifier: Apache-2.0
"""MCP composition layer: the ROBINS-I V2 tool surface.

Nine tools. The unit of assessment is ONE numerical result, not one manuscript,
and two things must be settled before any domain can be scored:

    parse_document / parse_pmcid        the bundle (article + supplements)
    set_prespecified_confounders        P1 — blocking for domain 1
    specify_result                      A1/A3 + C4 — C4 selects domain 1's variant
    assess_result(domain=N)             per-domain scaffold
    submit_answers(domain=N, ...)       answers -> computed domain judgement
    submit_answers(domain=0)            finalize; stamped report + portable record
    render_report                       re-render the same stamped artifact
    export_robvis                       many runs' records -> one robvis CSV

The model's contribution is bounded at answering signalling questions. It cannot
compute a judgement — `algorithms.py` does, from an edge graph traced off the
published flowcharts — and it cannot invent evidence: quotes are resolved to
character offsets in the ingested bundle and an unresolvable quote is rejected,
while claims of absence are backed by a search the SERVER runs, not by prose.

Tools take structured inputs and declare structured output schemas. Output
TypedDicts are `total=False` so they document the result shape without forcing
every optional field onto every return path.
"""

from __future__ import annotations

import base64
from typing import Any, TypedDict

from mcp.server.fastmcp import FastMCP

from . import algorithms as alg
from . import render_html as _render_html
from . import retrieve as _retrieve
from . import review as _review
from . import scaffold as _scaffold
from . import spec as _spec
from .algorithms import Judgement, UnansweredQuestion
from .ingest import (
    CUES,
    CUES_BY_KEY,
    SUPPLEMENT_STATES,
    QuoteNotFound,
    SectionMap,
    build_bundle,
    extract_file,
    parse_document as _parse_document,
)
from .report import (
    ATTRIBUTION,
    DOMAIN_LABELS,
    JUDGEMENT_LABELS,
    NON_ENDORSEMENT,
    Answer,
    Assessment,
    DomainOutcome,
    algorithm_fingerprint,
)

mcp = FastMCP(
    "robins-i",
    instructions=(
        "ROBINS-I V2 (follow-up/cohort variant, 20 November 2025) as a "
        "deterministic, provenanced risk-of-bias engine. The unit of assessment "
        "is ONE numerical result — a paper reporting three outcomes across two "
        "analyses is six assessments, not one. "
        "Flow: parse_document (or parse_pmcid) -> set_prespecified_confounders "
        "-> specify_result -> assess_result(domain=N) -> submit_answers(domain=N) "
        "for each of the six domains -> submit_answers(domain=0) to finalize, "
        "which returns the provenance-STAMPED report inline. That stamped render "
        "is the ARTIFACT OF RECORD; render_report re-renders it on demand. Do NOT "
        "hand-build your own risk-of-bias table — it lacks the stamp and cannot "
        "be verified. "
        "TWO GATES, both deliberate. set_prespecified_confounders supplies P1, the "
        "review's list of important confounding factors; domain 1 is UNANSWERABLE "
        "without it, because question 1.1 asks whether all IMPORTANT confounders "
        "were controlled and 'important' is the reviewer's judgement, not the "
        "paper's covariate table — the server refuses to score domain 1 rather "
        "than silently substituting one for the other. specify_result must settle "
        "C4 (does the analysis account for protocol deviations / treatment "
        "switching?) before anything is scored, because C4 swaps domain 1's entire "
        "question set and algorithm. Judge C4 on what the ANALYSIS does, not on "
        "the label the authors give their estimand. "
        "You answer signalling questions; the server computes every judgement. "
        "Answers carry one of three evidence modes: manuscript_positive (needs a "
        "verbatim quote, resolved to offsets or rejected), manuscript_absent "
        "(needs a search — name a cue and the server runs it), reviewer_prior "
        "(needs the prespecified item invoked, and enters the human ratification "
        "queue). Supplements matter: the target-trial specification that settles "
        "C1-C4 and the analysis detail domains 1 and 4 turn on routinely live only "
        "in the appendix, so pass it to parse_document when you have it. "
        "get_spec introspects the encoded specification and is OPTIONAL — "
        "assess_result already carries the rubric for the domain in hand. "
        "ACROSS RUNS: a review of many studies is many separate runs, and this "
        "server keeps NO state between them. submit_answers(domain=0) returns a "
        "small portable `record` alongside the report — save it. export_robvis "
        "takes any number of those records, from any number of sessions, and "
        "combines them into one figure-ready CSV."
    ),
)

# --- session state ---------------------------------------------------------- #

_parsed: dict[str, SectionMap] = {}                     # text_sha256 -> bundle
_priors: dict[str, dict[str, Any]] = {}                 # review_id -> P1 record
_results: dict[str, dict[str, Any]] = {}                # result_id -> result spec
_answers: dict[str, dict[str, Answer]] = {}             # result_id -> answers
_outcomes: dict[str, dict[int, DomainOutcome]] = {}     # result_id -> domain outcomes
_assessments: dict[str, Assessment] = {}                # result_id -> finalized

_C4_VALUES = {"no_itt": False, "yes_pp": True}


# --- output schemas --------------------------------------------------------- #

class SpecDoc(TypedDict, total=False):
    spec_version: str
    tool_version: str
    source_status: str
    source_status_note: str
    variant_scope: str
    variant_scope_note: str
    guideline_scope: str
    assessment_unit: str
    assessment_unit_note: str
    judgement_source: str
    judgement_source_note: str
    judgements: list
    response_vocabularies: dict
    response_semantics: dict
    evidence_policy: str
    override_policy: str
    human_ratification: dict
    algorithm_fingerprint: str
    preliminaries: list
    domains: list
    attribution: dict


class BundleSummary(TypedDict, total=False):
    source: str
    manuscript_id: str
    extractor_version: str
    text_sha256: str
    full_text: str
    sections: list
    n_pages: int | None
    warnings: list
    supplement_status: str
    documents: list
    citation: str
    cue_survey: list
    next_step: str


class PriorsRecord(TypedDict, total=False):
    review_id: str
    prespecified_confounders: list
    n_factors: int
    rationale: str
    ratified_by: str
    ratified: bool
    note: str


class ResultSpec(TypedDict, total=False):
    result_id: str
    review_id: str
    text_sha256: str
    citation: str
    result_assessed: str
    outcome: str
    result_location: str
    estimand: str
    per_protocol: bool
    domain1_variant: str
    domain1_questions: list
    target_trial: dict
    information_sources: list
    screening: dict
    screening_terminated: bool
    prespecified_confounders: list
    warnings: list
    next_step: str


class Scaffold(TypedDict, total=False):
    result_id: str
    domain: int
    domain_label: str
    algorithm: str
    spec_version: str
    text_sha256: str
    supplement_status: str
    variant: str
    variant_label: str
    applies_if: str
    structure: str
    low_label: str
    low_label_note: str
    max_judgement: str
    max_judgement_note: str
    depends_on: list
    questions: list
    cues: list
    evidence_modes: dict
    prespecified_confounders: list
    confounding_note: str
    answer_schema: dict
    instructions: str
    # domain=0 (overview) fields
    assessment_unit: str
    assessment_unit_note: str
    citation: str
    preliminaries: list
    domains_outstanding: list
    domains_complete: list


class SubmitResult(TypedDict, total=False):
    result_id: str
    status: str
    domain: int
    judgement: str
    judgement_label: str
    algorithm_judgement: str
    overridden: bool
    path: list
    not_reached: list
    notes: list
    accepted: list
    needs_answer: str
    needs_answer_at_node: str
    evidence_warnings: list
    domains_complete: list
    domains_outstanding: list
    ratification_queue: list
    next_step: str
    # finalization fields
    overall: str
    overall_label: str
    overall_algorithm: dict | None
    domains: list
    provenance: dict | None
    evidence: dict | None
    report: dict | None
    record: dict | None
    attribution: dict | None


class RobvisExport(TypedDict, total=False):
    review_id: str
    layout: str
    robvis_tool: str
    header: list
    rows: list
    n_results: int
    losses: list
    summary: dict
    slot_mapping: dict | None
    csv: str
    content_base64: str
    content_type: str
    filename: str
    usage: str


class Report(TypedDict, total=False):
    result_id: str
    citation: str
    overall: str
    overall_label: str
    domains: list
    provenance: dict
    ratification_queue: list
    html: str
    content_base64: str
    content_type: str
    filename: str
    attribution: dict


# --- helpers ---------------------------------------------------------------- #

def _attribution() -> dict[str, str]:
    return {"attribution": ATTRIBUTION, "non_endorsement": NON_ENDORSEMENT}


def _summarize(sm: SectionMap) -> dict[str, Any]:
    out = sm.to_dict(include_text=False)
    out["sections"] = [
        {"name": s.name, "heading": s.heading, "source": s.source,
         "start": s.start, "end": s.end, "chars": s.end - s.start}
        for s in sm.sections
    ]
    return out


def _cue_survey(sm: SectionMap) -> list[dict[str, Any]]:
    """Hit counts only — a map of where the evidence for each domain is likely to
    be, and which absences are already looking real. Excerpts come later, in the
    per-domain scaffold, so this stays cheap."""
    return [
        {"cue": c.key, "informs": list(c.questions), "n_hits": sm.search_cue(c.key).n_hits,
         "note": c.note}
        for c in CUES
    ]


def _resolve_bundle(text_sha256: str, document: str = "", manuscript_id: str = "") -> SectionMap:
    sm = _parsed.get(text_sha256)
    if sm is not None:
        return sm
    if document:
        fresh = _parse_document(document, manuscript_id or None)
        return _parsed.setdefault(fresh.text_sha256, fresh)
    raise ValueError(
        f"No parsed bundle with text_sha256 {text_sha256!r}. The parse cache does "
        "not survive a server restart — re-run parse_document, or pass document= "
        "to re-parse in this call."
    )


def _require_result(result_id: str) -> dict[str, Any]:
    if result_id not in _results:
        known = ", ".join(sorted(_results)) or "none this session"
        raise ValueError(
            f"Unknown result_id {result_id!r} — call specify_result first. "
            f"Known results: {known}."
        )
    return _results[result_id]


def _bundle_for(result_id: str) -> SectionMap:
    spec = _require_result(result_id)
    return _resolve_bundle(spec["text_sha256"])


def _confounders_for(result_id: str) -> list[str]:
    spec = _require_result(result_id)
    return list(_priors.get(spec["review_id"], {}).get("confounders", []))


def _domain_of(question: str) -> int:
    head = question.split(".")[0]
    if not head.isdigit():
        raise ValueError(
            f"{question!r} is not a signalling question id. Preliminaries "
            "(P1, A1-A3, B1-B3, C1-C4, D1) are set through "
            "set_prespecified_confounders and specify_result, not submit_answers."
        )
    return int(head)


def _run_domain(domain: int, flat: dict[str, str], per_protocol: bool) -> alg.AlgorithmResult:
    if domain == 1:
        return alg.domain1(flat, per_protocol=per_protocol)
    return {
        2: alg.domain2, 3: alg.domain3, 4: alg.domain4,
        5: alg.domain5, 6: alg.domain6,
    }[domain](flat)


def _judgement(value: str) -> Judgement:
    try:
        return Judgement(value)
    except ValueError:
        raise ValueError(
            f"Unknown judgement {value!r}; use one of "
            f"{[j.value for j in Judgement]}."
        ) from None


def _build_answer(raw: dict[str, Any], sm: SectionMap, per_protocol: bool) -> Answer:
    question = str(raw.get("question", "")).strip()
    if not question:
        raise ValueError("every answer needs a `question` id")
    key = _scaffold._variant_key(question, per_protocol)
    if key not in alg.RESPONSE_OPTIONS:
        if not question.split(".")[0].isdigit():
            raise ValueError(
                f"{question}: not a signalling question. The preliminaries "
                "(P1, A1-A3, B1-B3, C1-C4, D1) are settled through "
                "set_prespecified_confounders and specify_result, not here."
            )
        raise ValueError(
            f"{question}: not a signalling question in this spec. Domain 1 under "
            f"variant {'B' if per_protocol else 'A'} has questions "
            f"{[q['id'] for q in _scaffold.question_rows(1, per_protocol)]}."
            if question.startswith("1.") else
            f"{question}: not a signalling question in this spec."
        )
    response = str(raw.get("response", "")).strip()
    allowed = alg.RESPONSE_OPTIONS[key]
    if response not in allowed:
        raise ValueError(
            f"{question}: response {response!r} is not in this question's "
            f"vocabulary {list(allowed)}."
        )
    if response == "NA":
        raise ValueError(
            f"{question}: do not answer NA. Questions the algorithm does not reach "
            "are recorded as not-reached by the traversal — simply omit them."
        )

    mode = str(raw.get("evidence_mode", "")).strip()
    search_record: Any = ""
    if mode == "manuscript_absent":
        cue = str(raw.get("search_cue", "")).strip()
        terms = raw.get("search_terms") or ()
        if cue:
            if cue not in CUES_BY_KEY:
                raise ValueError(
                    f"{question}: unknown search_cue {cue!r}; the scaffold lists "
                    "the cue keys available for this domain."
                )
            search_record = sm.search_cue(cue)
        elif terms:
            search_record = sm.search(terms, raw.get("search_sections") or ())
        else:
            raise ValueError(
                f"{question}: manuscript_absent requires `search_cue` or "
                "`search_terms`. The server runs the search so the absence is "
                "reproducible; a prose claim that you looked cannot be audited."
            )

    answer = Answer(
        question=question,
        response=response,
        evidence_mode=mode,
        rationale=str(raw.get("rationale", "")),
        quotes=tuple(raw.get("quotes") or ()),
        search_record=search_record,
        prior_ref=str(raw.get("prior_ref", "")),
    )

    failures = []
    for quote in answer.quotes:
        try:
            sm.resolve(quote, question)
        except QuoteNotFound as exc:
            failures.append(str(exc))
    if failures:
        raise ValueError(
            f"{question}: {len(failures)} quote(s) do not appear in the ingested "
            "bundle. Copy them verbatim from the text you were given, or drop the "
            "claim.\n" + "\n".join(failures)
        )
    return answer


def _domain_rows(assessment: Assessment) -> list[dict[str, Any]]:
    return [
        {
            "domain": d.domain,
            "label": d.label,
            "judgement": d.judgement.value,
            "judgement_label": JUDGEMENT_LABELS[d.judgement],
            "algorithm_judgement": d.algorithm.judgement.value,
            "overridden": d.overridden,
            "override_justification": d.override_justification,
            "direction_of_bias": d.direction_of_bias,
            "support": d.support,
            "path": [
                {"question": q, "response": r, "node": n} for q, r, n in d.algorithm.path
            ],
            "not_reached": list(d.algorithm.not_reached),
            "notes": list(d.algorithm.notes),
        }
        for d in sorted(assessment.domains, key=lambda x: x.domain)
    ]


def _evidence_summary(assessment: Assessment) -> dict[str, Any]:
    spans = [s for a in assessment.answers.values() for s in a.spans]
    passes: dict[str, int] = {}
    for s in spans:
        passes[s.match] = passes.get(s.match, 0) + 1
    modes: dict[str, int] = {}
    for a in assessment.answers.values():
        modes[a.evidence_mode] = modes.get(a.evidence_mode, 0) + 1
    return {
        "n_answers": len(assessment.answers),
        "n_quotes_bound": len(spans),
        "match_passes": passes,
        "evidence_modes": modes,
        "unauditable_absence_claims": _scaffold.missing_evidence(assessment.answers),
    }


def _render_bundle(assessment: Assessment, title: str = "") -> dict[str, Any]:
    html = _render_html.render(assessment, title=title or None)
    stem = assessment.result_id.replace("/", "_").replace(" ", "_")[:80] or "assessment"
    return {
        "html": html,
        "content_base64": base64.b64encode(html.encode("utf-8")).decode("ascii"),
        "content_type": "text/html; charset=utf-8",
        "filename": f"{stem}_ROBINS-I.html",
    }


def _finalize(result_id: str, *, render: bool, title: str = "") -> dict[str, Any]:
    spec = _require_result(result_id)
    sm = _bundle_for(result_id)
    outcomes = _outcomes.get(result_id, {})
    terminated = spec["screening_terminated"]

    if not terminated:
        outstanding = [d for d in range(1, 7) if d not in outcomes]
        if outstanding:
            raise ValueError(
                f"cannot finalize {result_id!r}: domains {outstanding} not yet "
                "scored. Submit each domain's answers first."
            )

    assessment = Assessment(
        result_id=result_id,
        citation=spec["citation"],
        result_assessed=spec["result_assessed"],
        outcome=spec["outcome"],
        result_location=spec["result_location"],
        per_protocol=spec["per_protocol"],
        domains=[outcomes[d] for d in sorted(outcomes)],
        answers=dict(_answers.get(result_id, {})),
        prespecified_confounders=_confounders_for(result_id),
        prespecified_confounders_ratified=bool(
            _priors.get(spec["review_id"], {}).get("ratified_by")
        ),
        information_sources=spec["information_sources"],
        target_trial=spec["target_trial"],
        model=spec["model"],
        screening_terminated=terminated,
        overall_final=spec.get("overall_final"),
        overall_override_justification=spec.get("overall_override_justification", ""),
        overall_escalated=spec.get("overall_escalated", False),
        direction_of_bias=spec.get("direction_of_bias"),
    )
    assessment.bind_evidence(sm)
    overall_alg = assessment.overall_algorithm  # raises if an escalation is invalid
    _assessments[result_id] = assessment

    out: dict[str, Any] = {
        "result_id": result_id,
        "status": "finalized",
        "citation": assessment.citation,
        "overall": assessment.overall.value,
        "overall_label": JUDGEMENT_LABELS[assessment.overall],
        "overall_algorithm": {
            "judgement": overall_alg.judgement.value,
            "notes": list(overall_alg.notes),
            "overridden": assessment.overall_overridden,
        },
        "domains": _domain_rows(assessment),
        "ratification_queue": list(assessment.ratification_queue),
        "provenance": assessment.provenance(),
        "evidence": _evidence_summary(assessment),
        # The portable summary. SAVE THIS: it is what a later session or agent
        # needs to build a review-level figure, and it is the only part of this
        # return that survives the server process.
        "record": _review.assessment_record(assessment),
        "attribution": _attribution(),
        "next_step": (
            "Present the rendered report as the assessment. It carries the "
            "provenance stamp; a hand-built table does not. Save the `record` "
            "too — it is the portable summary a review-level figure is built "
            "from, and it does not survive this server process otherwise. "
            + (
                "The ratification queue is NOT empty: this is not a final "
                "assessment until a human signs off every item in it. Say so "
                "when you present it."
                if assessment.ratification_queue
                else "The ratification queue is empty."
            )
        ),
    }
    if terminated:
        out["screening_note"] = (
            "Preliminary screening (B2/B3) terminated the assessment at critical; "
            "no domain was scored."
        )
    if render:
        out["report"] = _render_bundle(assessment, title)
    return out


# --- tools: spec ------------------------------------------------------------ #

@mcp.tool()
def get_spec(spec_version: str = _spec.DEFAULT_SPEC, detail: str = "compact") -> SpecDoc:
    """Return the encoded ROBINS-I V2 specification: 13 preliminaries, 40
    signalling questions across 6 domains (domain 1 in two variants), the
    response vocabularies, the evidence policy, and the algorithm fingerprint.

    OPTIONAL in the assessment flow — introspection only. assess_result already
    carries the rubric for the domain in hand, so calling both duplicates the
    payload. detail='compact' (default) gives question ids, own-words labels,
    response options and evidence modes; detail='full' adds every intent and
    assessor note.

    The descriptions are this implementation's own wording, NOT the published
    signalling-question text, which is not redistributable. The published
    question IDs are what make the output interoperable."""
    if detail not in ("compact", "full"):
        raise ValueError(f"Unknown detail {detail!r}; use 'compact' or 'full'.")
    doc = _spec.load(spec_version)

    def question(q: dict[str, Any], variant: str = "") -> dict[str, Any]:
        key = f"{q['id']}{variant}" if variant else q["id"]
        row = {
            "id": q["id"],
            "label": q.get("label", ""),
            "response_options": list(alg.RESPONSE_OPTIONS.get(key, ())),
            "evidence_mode": q.get("evidence_mode_override") or q.get("evidence_mode", ""),
        }
        for optional in ("asked_if", "polarity", "panel"):
            if q.get(optional):
                row[optional] = q[optional]
        if detail == "full":
            for optional in ("intent", "assessor_notes", "note", "depends_on"):
                if q.get(optional):
                    row[optional] = q[optional]
        return row

    domains = []
    for d in doc["domains"]:
        row: dict[str, Any] = {
            "domain": d["domain"],
            "label": d["label"],
            "algorithm": d.get("algorithm", ""),
        }
        for optional in ("structure", "low_label", "low_label_note",
                         "max_judgement", "max_judgement_note", "depends_on"):
            if d.get(optional):
                row[optional] = d[optional]
        if "variants" in d:
            row["variants"] = [
                {"variant": v["variant"], "label": v.get("label", ""),
                 "applies_if": v.get("applies_if", ""),
                 "questions": [question(q, v["variant"]) for q in v["questions"]]}
                for v in d["variants"]
            ]
        else:
            row["questions"] = [question(q) for q in d["questions"]]
        domains.append(row)

    prelims = []
    for p in doc["preliminaries"]:
        keep = ("id", "label", "kind", "scope", "evidence_mode", "required",
                "blocking", "asked_if", "response_options", "options",
                "selects_variant", "terminates_assessment_if", "rule")
        if detail == "full":
            keep += ("intent", "note", "blocking_note")
        prelims.append({k: v for k, v in p.items() if k in keep})

    out: SpecDoc = {
        "spec_version": doc["spec_version"],
        "tool_version": doc["tool_version"],
        "source_status": doc["source_status"],
        "source_status_note": doc["source_status_note"],
        "variant_scope": doc["variant_scope"],
        "variant_scope_note": doc["variant_scope_note"],
        "guideline_scope": doc["guideline_scope"],
        "assessment_unit": doc["assessment_unit"],
        "assessment_unit_note": doc["assessment_unit_note"],
        "judgement_source": doc["judgement_source"],
        "judgement_source_note": doc["judgement_source_note"],
        "judgements": list(doc["judgements"]),
        "response_vocabularies": doc["response_vocabularies"],
        "response_semantics": doc["response_semantics"],
        "evidence_policy": doc["evidence_policy"],
        "override_policy": doc["override_policy"],
        "human_ratification": doc["human_ratification"],
        "algorithm_fingerprint": algorithm_fingerprint(),
        "preliminaries": prelims,
        "domains": domains,
        "attribution": _attribution(),
    }
    return out


# --- tools: ingest ---------------------------------------------------------- #

@mcp.tool()
def parse_document(
    document: str,
    manuscript_id: str = "",
    supplements: list[str] | None = None,
    supplement_status: str = "",
    citation: str = "",
) -> BundleSummary:
    """PRIMARY entry point: parse a study report into a bundle with
    character-offset, source-tagged section spans. Every quote you later cite is
    resolved against THIS text, and every claim of absence is searched in it.

    PASS `citation=`: the full bibliographic reference in APA style. It appears
    on the rendered assessment so the study being judged is unambiguous.

    `document` is EITHER the raw text OR a file path — but the path must be
    readable on the SERVER host. If your files live on your own filesystem, paste
    the TEXT instead, or use parse_pmcid for an open-access PMCID. A path-looking
    string the server cannot find raises rather than being ingested as its own
    text.

    PASS THE SUPPLEMENT WHEN YOU HAVE IT. `supplements` is a list of
    server-readable paths merged as supplementary material. This matters more for
    ROBINS-I than for a reporting audit: the target-trial specification that
    settles C1-C4, and the analysis detail domains 1 and 4 turn on, routinely live
    only in the appendix. Without it those questions read NI when the answer was
    merely in a file nobody passed. supplement_status defaults to 'user_provided'
    when supplements are given; pass 'none_exists' to assert the article has none.

    Returns the section map, the text hash that keys later calls, and a cue survey
    — hit counts for the 15 evidence patterns, so you can see before reading where
    each domain's evidence lives and which absences already look real."""
    main = _parse_document(document, manuscript_id or None)
    if supplements:
        docs = []
        for path in supplements:
            from pathlib import Path
            text, n_pages = extract_file(path)
            docs.append((Path(path).name, text, n_pages))
        sm = build_bundle(main, docs, supplement_status=supplement_status or "user_provided")
    else:
        if supplement_status:
            if supplement_status not in SUPPLEMENT_STATES:
                raise ValueError(
                    f"Unknown supplement_status {supplement_status!r}; use one of "
                    f"{list(SUPPLEMENT_STATES)}."
                )
            main.supplement_status = supplement_status
        sm = main
    if citation:
        sm.citation = citation
    _parsed[sm.text_sha256] = sm
    out: BundleSummary = _summarize(sm)  # type: ignore[assignment]
    out["cue_survey"] = _cue_survey(sm)
    out["next_step"] = (
        "Set P1 with set_prespecified_confounders (blocking for domain 1), then "
        "call specify_result to name the ONE numerical result you are assessing "
        "and settle C4."
    )
    return out


@mcp.tool()
def parse_pmcid(pmcid: str, include_supplements: bool = True,
                citation: str = "") -> BundleSummary:
    """CONVENIENCE entry point: retrieve an open-access article from Europe PMC by
    PMCID and parse it, main text plus PMC-hosted supplements, merged into one
    source-tagged bundle. Use it when you have no file in hand, or to auto-fetch
    an open-access paper's supplement; for a manuscript you were given, use
    parse_document.

    supplement_status is 'retrieved' when a supplement was obtained, else
    'not_retrieved' — a supplement may still exist on the publisher site, so
    absence of retrieval is never proof of absence. Raises if no open-access full
    text is available. An APA-style citation is built from the article's JATS
    metadata; pass citation= to override it."""
    sm = _retrieve.retrieve_bundle(pmcid, include_supplements=include_supplements)
    if citation:
        sm.citation = citation
    _parsed[sm.text_sha256] = sm
    out: BundleSummary = _summarize(sm)  # type: ignore[assignment]
    out["cue_survey"] = _cue_survey(sm)
    out["next_step"] = (
        "Set P1 with set_prespecified_confounders, then specify_result."
    )
    return out


# --- tools: setup (both gate scoring) --------------------------------------- #

@mcp.tool()
def set_prespecified_confounders(
    confounders: list[str],
    review_id: str = "default",
    rationale: str = "",
    ratified_by: str = "",
) -> PriorsRecord:
    """Supply P1 — the confounding factors this REVIEW judges important for the
    intervention-outcome relationship, listed before any study is assessed.

    THIS IS BLOCKING. Domain 1 will not be scored without it. Question 1.1 asks
    whether all IMPORTANT confounding factors were controlled for, and 'important'
    is defined by this list, not by the paper's covariate table. Substituting the
    paper's own list would let the study grade its own confounding control, which
    is exactly the judgement ROBINS-I asks the reviewer to make independently.

    'Important' means adjustment would be expected to change the estimate
    meaningfully; factors with only very weak associations are excluded.

    You MAY propose a list from domain knowledge or a DAG — that is useful and is
    what this parameter is for — but a proposed list is not a ratified one. Leave
    `ratified_by` empty unless a human in this conversation has actually reviewed
    and accepted the list; the assessment then carries P1 in its ratification
    queue and is explicitly not final until they do. Do not sign it off on their
    behalf.

    Scoped by `review_id` because P1 belongs to the review, not to one study: the
    same list applies to every result assessed under it."""
    factors = [str(c).strip() for c in confounders if str(c).strip()]
    if not factors:
        raise ValueError(
            "P1 cannot be empty. If you genuinely believe no factor confounds this "
            "relationship, that itself is a reviewer judgement — state it as one "
            "factor with that rationale rather than passing an empty list."
        )
    record = {
        "confounders": factors,
        "rationale": rationale,
        "ratified_by": ratified_by,
    }
    _priors[review_id] = record
    return {
        "review_id": review_id,
        "prespecified_confounders": factors,
        "n_factors": len(factors),
        "rationale": rationale,
        "ratified_by": ratified_by,
        "ratified": bool(ratified_by),
        "note": (
            "Ratified by a human; domain 1 answers may rely on it as settled."
            if ratified_by else
            "NOT RATIFIED. Domain 1 can now be scored, but P1 stays in the "
            "ratification queue and the assessment is not final until a human "
            "accepts this list. Say so when you present the result."
        ),
    }


@mcp.tool()
def specify_result(
    result_id: str,
    text_sha256: str,
    result_assessed: str,
    outcome: str,
    accounts_for_deviations: str,
    citation: str = "",
    result_location: str = "",
    target_trial: dict[str, str] | None = None,
    information_sources: list[str] | None = None,
    review_id: str = "default",
    model: str = "unspecified",
    b1: str = "",
    b2: str = "",
    b3: str = "",
    document: str = "",
) -> ResultSpec:
    """Name the ONE numerical result being assessed, and settle C4. Required
    before any domain can be scored.

    ROBINS-I assesses a single effect estimate, not a paper. A study reporting
    three outcomes across two analyses yields six assessments; give each its own
    `result_id` and run them separately.

    `accounts_for_deviations` IS C4, and it is the highest-leverage input here:
    it swaps domain 1's entire question set and algorithm, so it cannot be
    deferred until domain 1 is reached.
      'no_itt'  — the analysis does NOT account for switches between the compared
                  strategies or other protocol deviations. It targets the effect
                  of assignment. Domain 1 variant A (baseline confounding only).
      'yes_pp'  — the analysis DOES account for them, by censoring, follow-up
                  partitioning, or a g-method. It targets the effect of sustained
                  receipt. Domain 1 variant B (baseline AND time-varying
                  confounding).
    Judge this on what the ANALYSIS DOES, not on the label the authors give their
    estimand. A paper whose protocol table says 'observational analogue of the
    per-protocol effect' but which never censors at deviation is 'no_itt'. Getting
    this wrong means answering five questions that do not apply.

    `result_assessed` is A1: the estimate with its precision. `outcome` is A3.
    `result_location` (A2) is where it appears and why it was chosen.
    `target_trial` is C1-C3 as a dict of labelled strings — eligible participants,
    intervention strategy, comparator strategy, and any note on the estimand.
    `information_sources` is D1: what you actually read. An NI answer is only
    defensible relative to what was searched.

    `b1`/`b2`/`b3` are the section B screening answers (Y/PY/PN/N). b1: was any
    attempt made to control confounding in this result? b2 (asked only if b1 is
    PN/N): is the potential for confounding great enough that an unadjusted result
    should not be considered further? b3: is the outcome measurement method
    unsuitable for the outcome it is meant to capture? Y/PY on b2 or b3 sends the
    result straight to critical and no domain is scored."""
    if accounts_for_deviations not in _C4_VALUES:
        raise ValueError(
            f"accounts_for_deviations (C4) must be 'no_itt' or 'yes_pp', not "
            f"{accounts_for_deviations!r}. This selects domain 1's variant, so "
            "there is no safe default."
        )
    sm = _resolve_bundle(text_sha256, document)
    per_protocol = _C4_VALUES[accounts_for_deviations]

    screening = {}
    for name, value in (("B1", b1), ("B2", b2), ("B3", b3)):
        value = (value or "").strip().upper()
        if not value:
            continue
        if value not in ("Y", "PY", "PN", "N"):
            raise ValueError(f"{name}: expected Y, PY, PN or N, got {value!r}")
        screening[name] = value
    terminated = alg.screening_terminates(screening)

    warnings: list[str] = []
    if "B1" not in screening or "B3" not in screening:
        warnings.append(
            "Section B screening not fully recorded (B1 and B3 are unconditional). "
            "B3 in particular can terminate the assessment at critical, so an "
            "assessment that never asked it is incomplete."
        )
    if not _priors.get(review_id, {}).get("confounders"):
        warnings.append(
            f"P1 is not set for review {review_id!r} — domain 1 cannot be scored. "
            "Call set_prespecified_confounders first."
        )
    if sm.supplement_status in ("not_checked", "not_retrieved"):
        warnings.append(
            f"supplement_status is {sm.supplement_status!r}. C1-C4 and the domain 1 "
            "and 4 detail often live only in the appendix; answers of NI against a "
            "bundle with no supplement may be an artefact of what was ingested."
        )

    _results[result_id] = {
        "review_id": review_id,
        "text_sha256": sm.text_sha256,
        "citation": citation or sm.citation,
        "result_assessed": result_assessed,
        "outcome": outcome,
        "result_location": result_location,
        "per_protocol": per_protocol,
        "estimand": accounts_for_deviations,
        "target_trial": dict(target_trial or {}),
        "information_sources": list(information_sources or []),
        "model": model,
        "screening": screening,
        "screening_terminated": terminated,
        "spec_version": _spec.DEFAULT_SPEC,
    }
    _answers.setdefault(result_id, {})
    _outcomes.setdefault(result_id, {})

    variant = "B" if per_protocol else "A"
    return {
        "result_id": result_id,
        "review_id": review_id,
        "text_sha256": sm.text_sha256,
        "citation": _results[result_id]["citation"],
        "result_assessed": result_assessed,
        "outcome": outcome,
        "result_location": result_location,
        "estimand": accounts_for_deviations,
        "per_protocol": per_protocol,
        "domain1_variant": f"{variant} — "
                           f"{'per-protocol: baseline and time-varying confounding' if per_protocol else 'intention-to-treat: baseline confounding only'}",
        "domain1_questions": [q["id"] for q in _scaffold.question_rows(1, per_protocol)],
        "target_trial": dict(target_trial or {}),
        "information_sources": list(information_sources or []),
        "screening": screening,
        "screening_terminated": terminated,
        "prespecified_confounders": _confounders_for(result_id),
        "warnings": warnings,
        "next_step": (
            "Screening terminated the assessment at critical. Call "
            "submit_answers(result_id, domain=0) to finalize."
            if terminated else
            "Call assess_result(result_id, domain=N) for each domain 1-6, answer "
            "its questions, and submit them with submit_answers."
        ),
    }


# --- tools: assess ---------------------------------------------------------- #

@mcp.tool()
def assess_result(result_id: str, domain: int = 0) -> Scaffold:
    """Return the assessment scaffold for ONE domain: the questions actually in
    play, their own-words intent, the response vocabulary each accepts, what
    evidence each answer must carry, and the cue searches already run against
    this bundle with their hits.

    THE SCAFFOLD IS PER DOMAIN BY DESIGN. Most signalling questions are
    unreachable on any given path — 24 of 41 were never reached on the reference
    assessment — and which of domain 1's two question sets exists at all is
    decided by C4. There is no flat 41-question rubric to fetch, and asking for
    one would mean answering questions the algorithm discards.

    domain=0 (default) returns the overview: the preliminaries, what is settled,
    which domains are done, and which are outstanding. domain=1..6 returns that
    domain's scaffold. Domain 1 is refused until P1 is set.

    Work a domain at a time: read the cues to find where the evidence is, answer
    only the questions the algorithm reaches, then submit_answers. You do not
    state a judgement — the server computes it from your answers."""
    spec = _require_result(result_id)
    sm = _bundle_for(result_id)
    per_protocol = spec["per_protocol"]
    done = sorted(_outcomes.get(result_id, {}))

    if domain == 0:
        out: Scaffold = _scaffold.preliminaries_scaffold(sm)  # type: ignore[assignment]
        out["result_id"] = result_id
        out["domain"] = 0
        out["citation"] = spec["citation"]
        out["variant"] = "B" if per_protocol else "A"
        out["variant_label"] = (
            "per-protocol — baseline and time-varying confounding"
            if per_protocol else
            "intention-to-treat — baseline confounding only"
        )
        out["prespecified_confounders"] = _confounders_for(result_id)
        out["domains_complete"] = done
        out["domains_outstanding"] = [d for d in range(1, 7) if d not in done]
        out["answer_schema"] = _scaffold.answer_schema()
        return out

    if domain not in DOMAIN_LABELS:
        raise ValueError(f"domain must be 0 (overview) or 1-6, not {domain!r}")
    if spec["screening_terminated"]:
        raise ValueError(
            "Preliminary screening (B2/B3) terminated this assessment at critical; "
            "no domain is scored. Call submit_answers(result_id, domain=0) to "
            "finalize."
        )

    confounders = _confounders_for(result_id)
    if domain == 1 and not confounders:
        raise ValueError(
            "Domain 1 cannot be scored: P1 (the review's prespecified important "
            "confounding factors) has not been set for review "
            f"{spec['review_id']!r}. Question 1.1 asks whether all IMPORTANT "
            "confounders were controlled, and 'important' is defined by that list "
            "— not by this paper's covariate table. Call "
            "set_prespecified_confounders first. This refusal is deliberate: "
            "substituting the paper's own list would let the study grade its own "
            "confounding control."
        )

    out = _scaffold.domain_scaffold(  # type: ignore[assignment]
        sm, domain, per_protocol=per_protocol, prespecified_confounders=confounders,
    )
    out["result_id"] = result_id
    out["answer_schema"] = _scaffold.answer_schema()
    out["domains_complete"] = done
    out["domains_outstanding"] = [d for d in range(1, 7) if d not in done]
    return out


@mcp.tool()
def submit_answers(
    result_id: str,
    domain: int,
    answers: list[dict[str, Any]] | None = None,
    support: str = "",
    direction_of_bias: str = "",
    override_judgement: str = "",
    override_justification: str = "",
    overall_override: str = "",
    overall_override_justification: str = "",
    overall_escalate: bool = False,
    overall_direction_of_bias: str = "",
    render: bool = True,
) -> SubmitResult:
    """Submit one domain's signalling-question answers and get back the COMPUTED
    domain judgement, or (domain=0) finalize the assessment.

    Each element of `answers` is one question: `question`, `response`,
    `evidence_mode`, `rationale`, plus the evidence that mode requires —
    `quotes` for manuscript_positive, `search_cue` or `search_terms` for
    manuscript_absent, `prior_ref` for reviewer_prior. Answer only the questions
    the algorithm reaches; omit the rest rather than answering NA. `support` is
    your narrative for the domain as a whole and appears in the report.

    Three things are enforced here, and all three are the point of the tool:
    every quote is resolved to character offsets in the ingested bundle and an
    unresolvable one is REJECTED with the nearest text found; every claim of
    absence is backed by a search THE SERVER runs, so it is reproducible; and the
    judgement is computed by the published algorithm from your answers, never
    asserted by you. If the traversal reaches a question you did not answer, the
    call returns status='incomplete' naming it — supply it and call again.

    `override_judgement` sets the domain judgement against the algorithm and
    REQUIRES `override_justification`. Overrides cannot hide: the report shows
    both values and the override enters the ratification queue.

    domain=0 finalizes: it computes the overall judgement (worst of the six
    domains by default), assembles the stamped assessment and returns the
    rendered report inline. `overall_escalate` applies the tool's permitted
    escalation — several moderates to serious, or several seriouses to critical —
    and requires a justification. The returned `report` is THE ARTIFACT OF
    RECORD: present that, not a table of your own, and repeat its ratification
    queue if it is non-empty, because an assessment with unratified items is not
    final."""
    spec = _require_result(result_id)
    sm = _bundle_for(result_id)
    per_protocol = spec["per_protocol"]

    if domain == 0:
        if overall_override:
            if not overall_override_justification:
                raise ValueError(
                    "overall_override requires overall_override_justification — an "
                    "override without a recorded reason is not auditable."
                )
            spec["overall_final"] = _judgement(overall_override)
            spec["overall_override_justification"] = overall_override_justification
        if overall_escalate:
            if not overall_override_justification:
                raise ValueError(
                    "overall_escalate requires overall_override_justification."
                )
            spec["overall_escalated"] = True
            spec["overall_override_justification"] = overall_override_justification
        if overall_direction_of_bias:
            spec["direction_of_bias"] = overall_direction_of_bias
        try:
            return _finalize(result_id, render=render)  # type: ignore[return-value]
        except ValueError as exc:
            if "escalation" in str(exc):
                spec["overall_escalated"] = False
                raise ValueError(
                    f"{exc} The permitted escalations are several moderate domains "
                    "to serious, or several serious domains to critical; neither "
                    "applies here."
                ) from None
            raise

    if domain not in DOMAIN_LABELS:
        raise ValueError(f"domain must be 0 (finalize) or 1-6, not {domain!r}")
    if spec["screening_terminated"]:
        raise ValueError(
            "Preliminary screening terminated this assessment at critical; no "
            "domain is scored. Call submit_answers(result_id, domain=0)."
        )
    if domain == 1 and not _confounders_for(result_id):
        raise ValueError(
            "Domain 1 cannot be scored without P1. Call "
            "set_prespecified_confounders first — see assess_result(domain=1)."
        )

    accepted: list[str] = []
    store = _answers.setdefault(result_id, {})
    for raw in answers or []:
        answer = _build_answer(raw, sm, per_protocol)
        found = _domain_of(answer.question)
        if found != domain:
            raise ValueError(
                f"{answer.question} belongs to domain {found}, not {domain}. "
                "Submit one domain at a time."
            )
        store[answer.question] = answer
        accepted.append(answer.question)

    flat = {q: a.response for q, a in store.items()}
    try:
        result = _run_domain(domain, flat, per_protocol)
    except UnansweredQuestion as exc:
        return {
            "result_id": result_id,
            "status": "incomplete",
            "domain": domain,
            "accepted": accepted,
            "needs_answer": exc.question,
            "needs_answer_at_node": exc.node,
            "next_step": (
                f"The traversal reached {exc.question} (node {exc.node!r}) and "
                "found no answer. Answer it and call submit_answers again — the "
                "answers already accepted are kept."
            ),
        }

    final = _judgement(override_judgement) if override_judgement else None
    if final is not None and final is not result.judgement and not override_justification:
        raise ValueError(
            f"domain {domain}: overriding {result.judgement.value} -> {final.value} "
            "requires override_justification. The report shows both values, so an "
            "unexplained override is visible but indefensible."
        )
    outcome = DomainOutcome(
        domain=domain,
        algorithm=result,
        support=support,
        final=final,
        override_justification=override_justification,
        direction_of_bias=direction_of_bias or None,
    )
    _outcomes.setdefault(result_id, {})[domain] = outcome
    done = sorted(_outcomes[result_id])
    outstanding = [d for d in range(1, 7) if d not in done]

    warnings = [
        f"{q}: absence asserted in prose, not by a search record"
        for q in accepted
        if store[q].evidence_mode == "manuscript_absent" and not store[q].search_is_auditable
    ]

    return {
        "result_id": result_id,
        "status": "domain_scored",
        "domain": domain,
        "judgement": outcome.judgement.value,
        "judgement_label": JUDGEMENT_LABELS[outcome.judgement],
        "algorithm_judgement": result.judgement.value,
        "overridden": outcome.overridden,
        "path": [{"question": q, "response": r, "node": n} for q, r, n in result.path],
        "not_reached": list(result.not_reached),
        "notes": list(result.notes),
        "accepted": accepted,
        "evidence_warnings": warnings,
        "domains_complete": done,
        "domains_outstanding": outstanding,
        "next_step": (
            f"Domains {outstanding} still outstanding — call "
            f"assess_result(result_id, domain={outstanding[0]})."
            if outstanding else
            "All six domains scored. Call submit_answers(result_id, domain=0) to "
            "finalize and get the stamped report."
        ),
    }


# --- tools: render ---------------------------------------------------------- #

@mcp.tool()
def render_report(result_id: str, title: str = "") -> Report:
    """Re-render a finalized assessment as a self-contained HTML page — the
    meta panel, the six-domain summary strip, the per-domain judgement with its
    algorithm trail and the evidence behind every answer, styled to the Black Swan
    Causal Labs identity and carrying the provenance stamp.

    Returns the HTML in `html` (display it inline or publish it as an artifact)
    and the same bytes base64-encoded in `content_base64` (decode and save as
    .html). This is a pure re-render of the artifact submit_answers already
    stamped — nothing is re-scored. The assessment must have been finalized this
    session; the cache does not survive a server restart."""
    assessment = _assessments.get(result_id)
    if assessment is None:
        known = ", ".join(sorted(_assessments)) or "none this session"
        raise ValueError(
            f"No finalized assessment for {result_id!r}. Finalize it first with "
            f"submit_answers(result_id, domain=0). Finalized this session: {known}."
        )
    bundle = _render_bundle(assessment, title)
    return {
        "result_id": result_id,
        "citation": assessment.citation,
        "overall": assessment.overall.value,
        "overall_label": JUDGEMENT_LABELS[assessment.overall],
        "domains": _domain_rows(assessment),
        "provenance": assessment.provenance(),
        "ratification_queue": list(assessment.ratification_queue),
        "attribution": _attribution(),
        **bundle,
    }


# --- tools: review level ---------------------------------------------------- #

@mcp.tool()
def export_robvis(
    records: list[dict[str, Any]] | None = None,
    review_id: str = "",
    result_ids: list[str] | None = None,
    labels: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
    layout: str = "robins_i",
) -> RobvisExport:
    """Combine assessment RECORDS from any number of runs into a CSV for
    **robvis** (McGuinness & Higgins), the standard tool for Cochrane-style
    risk-of-bias figures.

    A review of 200 studies is 200 separate runs — each assessment costs a
    session, and nothing in this server survives between them. So pass
    `records`: the `record` object each submit_answers(domain=0) returns. They
    are small, flat and JSON-native, so a whole review's worth fits in one
    context, and they carry their own provenance so every row stays traceable
    to a document and an algorithm fingerprint. Omit `records` to use only what
    was assessed in THIS session (convenient, but session-scoped).

    READ THE RETURNED `losses` BEFORE PUBLISHING THE FIGURE. It reports records
    that are not yet ratified, mixed C4 variants, equal weighting, and records
    built under differing algorithm transcriptions — each of which would make
    the figure claim more than the assessments support.

    This is not a column dump, because robvis's ROBINS-I template is ROBINS-I
    **V1** and V2 is not drop-in compatible:

      * V1 has SEVEN domains and orders selection of participants BEFORE
        classification of interventions. V2 has six and swaps that pair. Writing
        V2's columns out in order loses no data and raises no error — it just
        prints your classification judgement under the heading "Bias due to
        selection of participants". layout='robins_i' (the default) places each
        V2 judgement into its correct V1 SLOT and marks the dropped deviations
        domain NA. Upload it with tool='ROBINS-I'.
      * layout='generic' writes six columns headed with V2's own domain names,
        for tool='Generic'. The headings are then right, but robvis relabels the
        judgements into ROB1's vocabulary — Moderate becomes "Some concerns",
        Serious becomes "High". Prefer 'robins_i'.

    Neither layout can carry 'Low, except for concerns about uncontrolled
    confounding': robvis reduces every cell to its first initial over a
    five-fill palette, so it collapses to Low whatever string is written. Say so
    in the figure caption."""
    if records:
        picked = _review.as_records(records)
    else:
        if result_ids:
            missing = [r for r in result_ids if r not in _assessments]
            if missing:
                raise ValueError(
                    f"not finalized in this session: {missing}. Either finalize them "
                    "here, or pass their saved `records` instead."
                )
            chosen = [_assessments[r] for r in result_ids]
        else:
            chosen = [
                _assessments[rid] for rid in _assessments
                if not review_id or _results.get(rid, {}).get("review_id") == review_id
            ]
        if not chosen:
            known = ", ".join(sorted(_assessments)) or "none this session"
            raise ValueError(
                f"No finalized assessments in this session for review {review_id!r}. "
                f"Finalized here: {known}. For results assessed in EARLIER sessions, "
                "pass their saved `records` — this server keeps no state between runs."
            )
        picked = _review.as_records(chosen)

    table = _review.robvis_csv(
        picked, layout=layout, labels=labels or None, weights=weights or None)
    stem = (review_id or "review").replace("/", "_").replace(" ", "_")[:80]
    table["review_id"] = review_id
    table["filename"] = f"{stem}_robvis_{layout}.csv"
    table["content_type"] = "text/csv; charset=utf-8"
    table["content_base64"] = base64.b64encode(
        table["csv"].encode("utf-8")).decode("ascii")
    table["usage"] = (
        f"Upload to https://mcguinlu.shinyapps.io/robvis/ and select "
        f"tool = '{table['robvis_tool']}'. Cite robvis: McGuinness LA, Higgins "
        "JPT. Risk-of-bias VISualization (robvis). Res Synth Methods 2021;12:55-61."
    )
    return table  # type: ignore[return-value]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
