"""Assembly of a finalized ROBINS-I assessment, ready for rendering.

Nothing here scores anything. It takes answers that were already produced, runs
them through `algorithms`, records any human override, and packages the result
with a provenance stamp.

Two design points carried over from the licensing analysis:

* No wording from the ROBINS-I document appears in any output. Question text in
  a rendered report comes from the own-words `label` fields in the spec; the
  interoperability layer is the question IDs, which are functional identifiers.
* The report is branded as a Black Swan Causal Labs assessment *following*
  ROBINS-I V2, never as an official or endorsed ROBINS-I output. `ATTRIBUTION`
  and `NON_ENDORSEMENT` below are the fixed wording for that, and the renderers
  are required to show both.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Mapping, Sequence

from . import algorithms as alg
from .algorithms import AlgorithmResult, Judgement
from .ingest import EvidenceSpan, QuoteNotFound, SearchRecord, SectionMap

INSTRUMENT = "ROBINS-I V2 (follow-up/cohort)"
IMPLEMENTATION = "Black Swan Causal Labs"

#: The published tool is a draft. riskofbias.info presents the 20 November 2025
#: release as subject to change, so an assessment made against it is provisional
#: in a way the algorithm fingerprint cannot express — that hash covers OUR
#: transcription, not THEIR document. Stamped on every report so the reader sees
#: it without having to know the tool's release history.
SOURCE_STATUS = "draft (20 Nov 2025 release, subject to change)"

FRAMEWORK_CITATION = (
    "Sterne JAC, Mathur MB, Elbers R, Hróbjartsson A, McAleenan A, Reeves B, "
    "Shrier I, Tilling K, et al. The Risk Of Bias In Non-randomized Studies – "
    "of Interventions, Version 2 (ROBINS-I V2) assessment tool (for follow-up "
    "studies), 20 November 2025. https://www.riskofbias.info/"
)

ATTRIBUTION = (
    f"Framework: {INSTRUMENT}, Sterne et al. 2025. "
    f"Implementation: {IMPLEMENTATION}."
)

NON_ENDORSEMENT = (
    "This is a Black Swan Causal Labs assessment following the ROBINS-I V2 "
    "framework. It is not an official ROBINS-I output and is not endorsed by, "
    "affiliated with, or certified by the ROBINS-I development group or "
    "Cochrane. Signalling questions are identified by their published "
    "identifiers; the descriptions shown are this implementation's own wording, "
    "not the wording of the published tool. Consult the published tool for the "
    "authoritative text."
)

DOMAIN_LABELS: Mapping[int, str] = {
    1: "Bias due to confounding",
    2: "Bias in classification of interventions",
    3: "Bias in selection of participants",
    4: "Bias due to missing data",
    5: "Bias in measurement of the outcome",
    6: "Bias in selection of the reported result",
}

JUDGEMENT_LABELS: Mapping[Judgement, str] = {
    Judgement.LOW: "Low",
    Judgement.LOW_EXCEPT_CONFOUNDING: "Low, except for concerns about uncontrolled confounding",
    Judgement.MODERATE: "Moderate",
    Judgement.SERIOUS: "Serious",
    Judgement.CRITICAL: "Critical",
}

EVIDENCE_MODES = ("manuscript_positive", "manuscript_absent", "reviewer_prior")


class RatificationRequired(RuntimeError):
    """Finalization attempted while reviewer-prior answers or overrides are unratified."""


@dataclass(frozen=True)
class Answer:
    """One signalling-question answer with its evidential basis."""

    question: str
    response: str
    evidence_mode: str
    rationale: str = ""
    #: verbatim spans from the assessed manuscript — required for manuscript_positive
    quotes: tuple[str, ...] = ()
    #: what was searched, and how — required for manuscript_absent. A
    #: SearchRecord from ingest carries the terms, sections and hit count; a
    #: bare string is accepted but cannot be audited.
    search_record: "str | SearchRecord" = ""
    #: which prespecified item was invoked — required for reviewer_prior
    prior_ref: str = ""
    ratified: bool = False
    #: populated by Assessment.bind_evidence() — quotes resolved to offsets
    spans: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_mode not in EVIDENCE_MODES:
            raise ValueError(f"{self.question}: unknown evidence_mode {self.evidence_mode!r}")
        if self.evidence_mode == "manuscript_positive" and not self.quotes:
            raise ValueError(f"{self.question}: manuscript_positive requires at least one quote")
        if self.evidence_mode == "manuscript_absent" and not self.search_record:
            raise ValueError(f"{self.question}: manuscript_absent requires a search_record")
        if self.evidence_mode == "reviewer_prior" and not self.prior_ref:
            raise ValueError(f"{self.question}: reviewer_prior requires a prior_ref")

    @property
    def needs_ratification(self) -> bool:
        return self.evidence_mode == "reviewer_prior" and not self.ratified

    @property
    def search_summary(self) -> str:
        if isinstance(self.search_record, SearchRecord):
            return self.search_record.describe()
        return str(self.search_record)

    @property
    def search_is_auditable(self) -> bool:
        """True when the absence claim carries a machine-generated search record
        rather than a free-text assertion."""
        return isinstance(self.search_record, SearchRecord)


@dataclass(frozen=True)
class DomainOutcome:
    domain: int
    algorithm: AlgorithmResult
    support: str = ""
    final: Judgement | None = None
    override_justification: str = ""
    direction_of_bias: str | None = None

    def __post_init__(self) -> None:
        if self.final is not None and self.final is not self.algorithm.judgement:
            if not self.override_justification:
                raise ValueError(
                    f"domain {self.domain}: overriding "
                    f"{self.algorithm.judgement.value} -> {self.final.value} "
                    "requires a justification"
                )

    @property
    def judgement(self) -> Judgement:
        return self.final or self.algorithm.judgement

    @property
    def overridden(self) -> bool:
        return self.final is not None and self.final is not self.algorithm.judgement

    @property
    def label(self) -> str:
        return DOMAIN_LABELS[self.domain]


@dataclass
class Assessment:
    """One ROBINS-I assessment of ONE study result."""

    result_id: str
    #: APA reference for the assessed study
    citation: str
    #: the specific numerical result under assessment (preliminary A1)
    result_assessed: str
    #: the outcome it relates to (A3)
    outcome: str
    #: C4 — True selects domain 1 variant B
    per_protocol: bool
    domains: Sequence[DomainOutcome]
    answers: Mapping[str, Answer]
    prespecified_confounders: Sequence[str]
    #: whether a human accepted the P1 list. A list proposed by an agent is a
    #: candidate, not a prespecification, and the difference has to be visible.
    prespecified_confounders_ratified: bool = False
    information_sources: Sequence[str] = ()
    #: A2, optional
    result_location: str = ""
    target_trial: Mapping[str, str] = field(default_factory=dict)
    spec_version: str = "robins-i-v2-cohort-0.1.0"
    model: str = "unspecified"
    #: sha256 of the ingested source bundle — set by bind_evidence()
    text_sha256: str = ""
    extractor_version: str = ""
    supplement_status: str = "not_checked"
    evidence_bound: bool = False
    screening_terminated: bool = False
    overall_final: Judgement | None = None
    overall_override_justification: str = ""
    overall_escalated: bool = False
    direction_of_bias: str | None = None
    generated_at: datetime | None = None

    # -- derived ---------------------------------------------------------- #

    @property
    def domain_judgements(self) -> dict[int, Judgement]:
        return {d.domain: d.judgement for d in self.domains}

    @property
    def overall_algorithm(self) -> AlgorithmResult:
        if self.screening_terminated:
            return AlgorithmResult(
                judgement=Judgement.CRITICAL,
                notes=("preliminary screening (B2/B3) terminated the assessment",),
            )
        return alg.overall(
            self.domain_judgements,
            escalate=self.overall_escalated,
            escalation_justification=self.overall_override_justification or None,
        )

    @property
    def overall(self) -> Judgement:
        return self.overall_final or self.overall_algorithm.judgement

    @property
    def overall_overridden(self) -> bool:
        return (
            self.overall_final is not None
            and self.overall_final is not self.overall_algorithm.judgement
        )

    @property
    def ratification_queue(self) -> tuple[str, ...]:
        """Everything a human must sign off before this can be called final."""
        items = [
            f"{a.question} — judged against reviewer priors ({a.prior_ref})"
            for a in self.answers.values()
            if a.needs_ratification
        ]
        items += [
            f"domain {d.domain} — algorithm said {d.algorithm.judgement.value}, "
            f"overridden to {d.judgement.value}"
            for d in self.domains
            if d.overridden
        ]
        if self.overall_overridden:
            items.append(
                f"overall — algorithm said {self.overall_algorithm.judgement.value}, "
                f"overridden to {self.overall.value}"
            )
        if not self.prespecified_confounders:
            items.append("P1 — no prespecified confounding factors supplied")
        elif not self.prespecified_confounders_ratified:
            items.append(
                f"P1 — {len(self.prespecified_confounders)} confounding factors "
                "proposed but not ratified by a human"
            )
        return tuple(items)

    def require_ratified(self) -> None:
        if self.ratification_queue:
            raise RatificationRequired("; ".join(self.ratification_queue))

    # -- evidence binding ------------------------------------------------- #

    def bind_evidence(self, section_map: SectionMap, *, strict: bool = True) -> tuple[str, ...]:
        """Resolve every quote to character offsets in the ingested bundle.

        This is what converts a quote from an assertion into a locator. Each
        resolved span carries the section and source document it landed in, so
        the report can say *where* the evidence is rather than only what it
        says.

        With ``strict`` (the default) an unresolvable quote raises: a quote that
        cannot be found is either not verbatim or not from this document, and
        both are reasons to stop rather than to publish. ``strict=False``
        collects the failures and returns them, for triage during development.

        Also stamps ``text_sha256`` from the bundle, so the provenance line
        describes the document that was actually read.
        """
        bound: dict[str, Answer] = {}
        failures: list[str] = []
        for key, answer in self.answers.items():
            spans: list[EvidenceSpan] = []
            for quote in answer.quotes:
                try:
                    spans.append(section_map.resolve(quote, answer.question))
                except QuoteNotFound as exc:
                    if strict:
                        raise
                    failures.append(f"{answer.question}: {exc.quote[:70]!r}")
            bound[key] = replace(answer, spans=tuple(spans))

        self.answers = bound
        self.text_sha256 = section_map.text_sha256
        self.extractor_version = section_map.extractor_version
        self.supplement_status = section_map.supplement_status
        self.evidence_bound = True
        return tuple(failures)

    # -- audit trail ------------------------------------------------------ #

    def trail(self, domain: int) -> tuple[dict[str, object], ...]:
        """Questions actually reached in this domain, in order, with evidence."""
        outcome = next(d for d in self.domains if d.domain == domain)
        rows = []
        for question, response, node in outcome.algorithm.path:
            answer = self.answers.get(question)
            rows.append(
                {
                    "question": question,
                    "response": response,
                    "node": node,
                    "evidence_mode": answer.evidence_mode if answer else None,
                    "rationale": answer.rationale if answer else "",
                    "quotes": [
                        {"text": q,
                         "locator": next((s.locator for s in answer.spans if s.quote == q), ""),
                         "span": next(((s.start, s.end) for s in answer.spans if s.quote == q), None)}
                        for q in answer.quotes
                    ] if answer else [],
                    "search_record": answer.search_summary if answer else "",
                    "search_auditable": answer.search_is_auditable if answer else False,
                    "prior_ref": answer.prior_ref if answer else "",
                    "needs_ratification": answer.needs_ratification if answer else False,
                }
            )
        return tuple(rows)

    # -- provenance ------------------------------------------------------- #

    def provenance(self) -> dict[str, str]:
        when = self.generated_at or datetime.now(timezone.utc)
        return {
            "instrument": INSTRUMENT,
            "implementation": IMPLEMENTATION,
            "source_status": SOURCE_STATUS,
            "spec_version": self.spec_version,
            "algorithm_fingerprint": algorithm_fingerprint(),
            "text_sha256": self.text_sha256,
            "extractor_version": self.extractor_version or "not bound",
            "supplement_status": self.supplement_status,
            "model": self.model,
            "domain1_variant": "B (per-protocol)" if self.per_protocol else "A (intention-to-treat)",
            "generated_at": when.strftime("%Y-%m-%d %H:%M UTC"),
        }

    def provenance_line(self) -> str:
        p = self.provenance()
        return (
            f"Provenance — {p['instrument']}, source {p['source_status']} · "
            f"impl {p['implementation']} · "
            f"spec {p['spec_version']} · algorithms {p['algorithm_fingerprint']} · "
            f"text sha256:{(p['text_sha256'] or '—')[:12]} · "
            f"{p['extractor_version']} · supplements {p['supplement_status']} · "
            f"model {p['model']} · {p['generated_at']}"
        )


def algorithm_fingerprint() -> str:
    """Stable short hash of the transcribed decision graphs.

    The algorithms were traced by hand from raster flowcharts, so the exact
    edge set is a load-bearing artifact. Stamping a fingerprint of it means a
    corrected transcription is visible on every report that used the old one.
    """
    graphs = {
        "d1a": alg._D1A, "d1b": alg._D1B, "d2": alg._D2,
        "d3a": alg._D3_PANEL_A, "d3b": alg._D3_PANEL_B, "d3c": alg._D3_LADDER,
        "d4": alg._D4, "d5": alg._D5,
    }
    shape = {
        name: {
            node_id: [
                [sorted(opts), dest.value if isinstance(dest, Judgement) else dest]
                for opts, dest in node.edges
            ]
            for node_id, node in sorted(graph.items())
        }
        for name, graph in sorted(graphs.items())
    }
    blob = json.dumps(shape, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:12]
