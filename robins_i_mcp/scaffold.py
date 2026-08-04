"""Per-domain assessment scaffolds.

The model's whole contribution to a ROBINS-I assessment is answering signalling
questions from the text (pipeline step 3). A scaffold is what that step is
handed: the questions actually in play, their own-words intent, the response
vocabulary each one accepts, the evidence a given answer will be required to
carry, and — because ROBINS-I answers so often rest on absence — the cue
searches already run against this bundle, with their hits.

Scaffolds are built PER DOMAIN, never as one flat rubric. Most of the 40
signalling questions are unreachable on any given path (24 of 41 were never
reached on the Dickerman run), and which of domain 1's two question sets exists
at all is decided by C4. A flat rubric would ask for answers the algorithm will
throw away and would misstate the domain 1 question set half the time.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import spec as _spec
from .algorithms import RESPONSE_OPTIONS
from .ingest import CUES, Cue, SectionMap
from .report import DOMAIN_LABELS

#: How many search hits to carry into a scaffold. The search itself is
#: exhaustive; this caps only how many excerpts ride along in the payload.
CUE_EXCERPTS = 6

EVIDENCE_REQUIREMENTS = {
    "manuscript_positive": (
        "The answer asserts the study DID something. Requires >=1 verbatim quote "
        "from this bundle. Quotes are resolved to character offsets on submission "
        "and an unresolvable quote is rejected, so copy them exactly."
    ),
    "manuscript_absent": (
        "The answer rests on the study NOT reporting something. Requires a search: "
        "pass `search_cue` (a cue key from this scaffold) or `search_terms`. The "
        "SERVER runs the search and attaches the record — do not describe a search "
        "in prose, it cannot be audited."
    ),
    "reviewer_prior": (
        "The answer is judged against the review's prespecified position rather "
        "than against the paper. Requires `prior_ref` naming the item invoked "
        "(e.g. 'P1 item 7'). Every such answer enters the ratification queue and "
        "blocks finalization until a human signs it off."
    ),
}


def _variant_key(question: str, per_protocol: bool) -> str:
    """Response-option key: domain 1 ids are variant-suffixed, everything else isn't."""
    if question.startswith("1."):
        return f"{question}{'B' if per_protocol else 'A'}"
    return question


def _split_suffix(question: str) -> tuple[str, str]:
    if len(question) > 1 and question[-1] in "AB" and question[:-1].replace(".", "").isdigit():
        return question[:-1], question[-1]
    return question, ""


def cues_for_domain(domain: int, per_protocol: bool) -> list[Cue]:
    """Cues informing any question in this domain, honouring the domain 1 variant."""
    want = "B" if per_protocol else "A"
    out: list[Cue] = []
    for cue in CUES:
        for q in cue.questions:
            base, suffix = _split_suffix(q)
            if not base.startswith(f"{domain}."):
                continue
            if suffix and suffix != want:
                continue
            out.append(cue)
            break
    return out


def cues_for_preliminaries() -> list[Cue]:
    """Cues informing the lettered preliminaries (A/B/C/D), not a numbered domain."""
    return [
        cue for cue in CUES
        if any(not _split_suffix(q)[0][0].isdigit() for q in cue.questions)
    ]


def _cue_payload(sm: SectionMap, cues: Sequence[Cue]) -> list[dict[str, Any]]:
    rows = []
    for cue in cues:
        record = sm.search_cue(cue.key, max_hits=CUE_EXCERPTS)
        rows.append({
            "cue": cue.key,
            "informs": list(cue.questions),
            "note": cue.note,
            "terms": list(record.terms),
            "sections_searched": list(record.sections_searched),
            "n_hits": record.n_hits,
            "hits": [
                {"term": h.term, "section": h.section, "source": h.source,
                 "excerpt": h.excerpt}
                for h in record.hits[:CUE_EXCERPTS]
            ],
        })
    return rows


def domain_block(domain: int, per_protocol: bool,
                 spec_version: str = _spec.DEFAULT_SPEC) -> dict[str, Any]:
    """The spec's entry for one domain, with domain 1's variant already resolved."""
    doc = _spec.load(spec_version)
    entry = next(d for d in doc["domains"] if d["domain"] == domain)
    if "variants" not in entry:
        return entry
    want = "B" if per_protocol else "A"
    block = next(v for v in entry["variants"] if v["variant"] == want)
    merged = {k: v for k, v in entry.items() if k != "variants"}
    merged["variant"] = want
    merged["variant_label"] = block.get("label", "")
    merged["applies_if"] = block.get("applies_if", "")
    merged["questions"] = block["questions"]
    return merged


def question_rows(domain: int, per_protocol: bool,
                  spec_version: str = _spec.DEFAULT_SPEC) -> list[dict[str, Any]]:
    """One row per signalling question in play for this domain."""
    doc = _spec.load(spec_version)
    semantics = doc["response_semantics"]
    block = domain_block(domain, per_protocol, spec_version)
    rows = []
    for q in block["questions"]:
        key = _variant_key(q["id"], per_protocol)
        options = list(RESPONSE_OPTIONS[key])
        mode = q.get("evidence_mode_override") or q.get("evidence_mode", "manuscript_positive")
        row: dict[str, Any] = {
            "id": q["id"],
            "label": q.get("label", ""),
            "intent": q.get("intent", ""),
            "response_options": options,
            "response_semantics": {o: semantics[o] for o in options},
            "evidence_mode": mode,
            "evidence_requirement": EVIDENCE_REQUIREMENTS[mode],
        }
        for optional in ("asked_if", "assessor_notes", "polarity", "note", "panel",
                         "depends_on"):
            if q.get(optional):
                row[optional] = q[optional]
        rows.append(row)
    return rows


def domain_scaffold(
    sm: SectionMap,
    domain: int,
    *,
    per_protocol: bool,
    prespecified_confounders: Sequence[str] = (),
    spec_version: str = _spec.DEFAULT_SPEC,
) -> dict[str, Any]:
    """Everything needed to answer one domain against one bundle."""
    block = domain_block(domain, per_protocol, spec_version)
    out: dict[str, Any] = {
        "domain": domain,
        "domain_label": DOMAIN_LABELS[domain],
        "algorithm": block.get("algorithm", ""),
        "spec_version": spec_version,
        "text_sha256": sm.text_sha256,
        "supplement_status": sm.supplement_status,
        "questions": question_rows(domain, per_protocol, spec_version),
        "cues": _cue_payload(sm, cues_for_domain(domain, per_protocol)),
        "evidence_modes": EVIDENCE_REQUIREMENTS,
    }
    for carried in ("variant", "variant_label", "applies_if", "structure",
                    "low_label", "low_label_note", "max_judgement",
                    "max_judgement_note", "depends_on"):
        if block.get(carried):
            out[carried] = block[carried]

    if domain == 1:
        out["prespecified_confounders"] = list(prespecified_confounders)
        out["confounding_note"] = (
            "Question 1.1 asks whether ALL IMPORTANT confounding factors were "
            "controlled for. 'Important' is defined by the prespecified list above "
            "(P1), not by the paper's own covariate table. Answer it against that "
            "list, cite which items you are invoking in `prior_ref`, and say plainly "
            "where the paper's control falls short of it."
        )
    out["instructions"] = (
        f"Answer only the questions above, and only those the algorithm actually "
        f"reaches — `asked_if` tells you the condition. Do not answer NA to skip "
        f"one; unreached questions are recorded as not-reached by the traversal "
        f"itself. Every answer needs an evidence mode and the evidence that mode "
        f"requires. Then call submit_answers(result_id, domain={domain}, answers=[...]) "
        f"with a `support` paragraph explaining the domain as a whole. The domain "
        f"judgement is COMPUTED from your answers; do not state one."
    )
    return out


def preliminaries_scaffold(
    sm: SectionMap,
    *,
    spec_version: str = _spec.DEFAULT_SPEC,
) -> dict[str, Any]:
    """The lettered preliminaries — what has to be settled before any domain."""
    doc = _spec.load(spec_version)
    semantics = doc["response_semantics"]
    rows = []
    for p in doc["preliminaries"]:
        row = {k: v for k, v in p.items() if k != "response_options"}
        options = p.get("response_options")
        if isinstance(options, list):
            row["response_options"] = options
            row["response_semantics"] = {
                o: semantics[o] for o in options if o in semantics
            }
        rows.append(row)
    return {
        "spec_version": spec_version,
        "assessment_unit": doc["assessment_unit"],
        "assessment_unit_note": doc["assessment_unit_note"],
        "text_sha256": sm.text_sha256,
        "supplement_status": sm.supplement_status,
        "citation": sm.citation,
        "preliminaries": rows,
        "cues": _cue_payload(sm, cues_for_preliminaries()),
        "instructions": (
            "Settle these before any domain is scored. Two of them gate the rest: "
            "P1 (the review's prespecified important confounding factors) via "
            "set_prespecified_confounders, and C4 (whether the analysis accounts "
            "for protocol deviations) via specify_result — C4 selects which of "
            "domain 1's two question sets exists, so it cannot be deferred. "
            "Read the target-trial cues below before answering C1-C4: a paper's "
            "own label for its estimand is not decisive, what the ANALYSIS does is."
        ),
    }


def answer_schema() -> dict[str, Any]:
    """The shape of one element of submit_answers' `answers` array."""
    return {
        "question": "signalling question id, e.g. '3.1' (no variant suffix)",
        "response": "one of the question's response_options",
        "evidence_mode": "manuscript_positive | manuscript_absent | reviewer_prior",
        "rationale": "why this response, in your own words",
        "quotes": ["verbatim span copied from the bundle — required for manuscript_positive"],
        "search_cue": "cue key from the scaffold — the server runs it (manuscript_absent)",
        "search_terms": ["alternative to search_cue: terms for the server to search"],
        "search_sections": ["optional section restriction for search_terms"],
        "prior_ref": "which prespecified item is invoked — required for reviewer_prior",
    }


def missing_evidence(answers: Mapping[str, Any]) -> list[str]:
    """Answers whose evidence is present but weak, for the caller to see."""
    weak = []
    for question, answer in answers.items():
        if answer.evidence_mode == "manuscript_absent" and not answer.search_is_auditable:
            weak.append(f"{question}: absence asserted in prose, not by a search record")
    return weak
