# Copyright 2026 Black Swan Causal Labs
# SPDX-License-Identifier: Apache-2.0
"""ROBINS-I V2 (follow-up/cohort) risk-of-bias algorithms.

Transcribed from the flowchart figures in the 20 November 2025 cribsheet:

    p.20  domain 1, variant A (intention-to-treat)
    p.24  domain 1, variant B (per-protocol)
    p.28  domain 2
    p.32  domain 3
    p.38  domain 4
    p.41  domain 5
    p.47  domain 6
    p.49  overall (this one is a text table, not a figure)

The figures are raster images with no machine-readable structure, so every edge
below was read off the drawing by hand. Each graph is written as an explicit
node/edge list rather than as condensed logic, so that a reviewer can hold the
code next to the figure and check it arrow by arrow. Where a domain turns out to
obey a simpler rule (domains 2 and 4 are additive severity ladders), that is
noted in a comment and asserted in the tests, but the edge list stays the source
of truth.

See TRANSCRIPTION-NOTES.md for the points that still need verification against
the forthcoming riskofbias.info implementation.

Decision logic is not copyrightable prose; no signalling-question wording from
the CC BY-NC-ND tool is reproduced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

__all__ = [
    "Judgement",
    "AlgorithmResult",
    "UnansweredQuestion",
    "domain1_variant_a",
    "domain1_variant_b",
    "domain2",
    "domain3",
    "domain4",
    "domain5",
    "domain6",
    "overall",
    "RESPONSE_OPTIONS",
]


class Judgement(str, Enum):
    LOW = "low"
    LOW_EXCEPT_CONFOUNDING = "low_except_confounding"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"

    @property
    def severity(self) -> int:
        return _SEVERITY[self]


_SEVERITY = {
    Judgement.LOW: 0,
    Judgement.LOW_EXCEPT_CONFOUNDING: 0,
    Judgement.MODERATE: 1,
    Judgement.SERIOUS: 2,
    Judgement.CRITICAL: 3,
}

_LADDER = (Judgement.LOW, Judgement.MODERATE, Judgement.SERIOUS, Judgement.CRITICAL)


class UnansweredQuestion(KeyError):
    """The traversal reached a question with no answer supplied."""

    def __init__(self, question: str, node: str) -> None:
        super().__init__(question)
        self.question = question
        self.node = node

    def __str__(self) -> str:
        return f"reached node {self.node!r} but question {self.question!r} was not answered"


@dataclass(frozen=True)
class AlgorithmResult:
    """Outcome of one domain traversal."""

    judgement: Judgement
    #: (question_id, answer, node_id) in the order visited — the audit trail.
    path: tuple[tuple[str, str, str], ...] = ()
    #: Questions the traversal never reached; these are legitimately NA.
    not_reached: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Response option sets, for validating submitted answers.
# --------------------------------------------------------------------------- #

_STANDARD = ("Y", "PY", "PN", "N", "NI")
_STANDARD_NA = ("NA",) + _STANDARD
_WS_NO = ("Y", "PY", "WN", "SN", "NI")
_WS_NO_NA = ("NA",) + _WS_NO
_WS_YES = ("SY", "WY", "PN", "N", "NI")
_WS_YES_NA = ("NA",) + _WS_YES
_NO_NI = ("Y", "PY", "PN", "N")
_NO_NI_NA = ("NA",) + _NO_NI

RESPONSE_OPTIONS: Mapping[str, tuple[str, ...]] = {
    # domain 1 variant A
    "1.1A": _WS_NO, "1.2A": _WS_NO_NA, "1.3A": _STANDARD_NA, "1.4A": _NO_NI,
    # domain 1 variant B
    "1.1B": _STANDARD, "1.2B": _WS_NO_NA, "1.3B": _WS_NO_NA,
    "1.4B": _STANDARD_NA, "1.5B": _NO_NI,
    # domain 2
    "2.1": _STANDARD, "2.2": _STANDARD_NA, "2.3": _WS_YES_NA,
    "2.4": _WS_YES, "2.5": _STANDARD,
    # domain 3
    "3.1": _WS_NO, "3.2": _STANDARD, "3.3": _STANDARD, "3.4": _STANDARD_NA,
    "3.5": _STANDARD_NA, "3.6": _STANDARD_NA, "3.7": _STANDARD_NA, "3.8": _STANDARD_NA,
    # domain 4
    "4.1": _STANDARD, "4.2": _STANDARD, "4.3": _STANDARD, "4.4": _STANDARD_NA,
    "4.5": _STANDARD_NA, "4.6": _WS_NO_NA, "4.7": _STANDARD_NA, "4.8": _STANDARD_NA,
    "4.9": _WS_NO_NA, "4.10": _WS_NO_NA, "4.11": _NO_NI_NA,
    # domain 5
    "5.1": _STANDARD, "5.2": _STANDARD, "5.3": _WS_YES_NA,
    # domain 6
    "6.1": _STANDARD, "6.2": _STANDARD, "6.3": _STANDARD, "6.4": _STANDARD,
}


# --------------------------------------------------------------------------- #
# Graph machinery
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Node:
    question: str
    #: ordered (accepted answers, destination) pairs; destination is a node id
    #: or a Judgement. Order is irrelevant — the answer sets must be disjoint.
    edges: tuple[tuple[frozenset[str], "str | Judgement"], ...]


def _n(question: str, *edges: tuple[Sequence[str], "str | Judgement"]) -> _Node:
    return _Node(question, tuple((frozenset(opts), dest) for opts, dest in edges))


def _walk(
    graph: Mapping[str, _Node],
    start: str,
    answers: Mapping[str, str],
    *,
    all_questions: Iterable[str],
    prefix_path: Sequence[tuple[str, str, str]] = (),
    notes: Sequence[str] = (),
) -> AlgorithmResult:
    path = list(prefix_path)
    node_id = start
    seen_nodes: set[str] = set()

    while not isinstance(node_id, Judgement):
        if node_id in seen_nodes:  # pragma: no cover - guards a transcription slip
            raise RuntimeError(f"cycle in graph at {node_id!r}")
        seen_nodes.add(node_id)

        node = graph[node_id]
        answer = answers.get(node.question)
        if answer is None or answer == "NA":
            raise UnansweredQuestion(node.question, node_id)

        for accepted, dest in node.edges:
            if answer in accepted:
                path.append((node.question, answer, node_id))
                node_id = dest
                break
        else:  # pragma: no cover - guards a transcription slip
            raise ValueError(
                f"answer {answer!r} to {node.question} has no outgoing edge at node {node_id!r}"
            )

    reached = {q for q, _, _ in path}
    return AlgorithmResult(
        judgement=node_id,
        path=tuple(path),
        not_reached=tuple(q for q in all_questions if q not in reached),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Domain 1 — bias due to confounding
# --------------------------------------------------------------------------- #
#
# Both variants terminate at LOW_EXCEPT_CONFOUNDING rather than LOW: residual
# confounding can never be excluded in a non-randomized study.
#
# Variant B's figure also draws a plain green "LOW RISK OF BIAS" box, but no
# arrow reaches it. Treated as a legend artefact — see TRANSCRIPTION-NOTES.md.

_D1A_QUESTIONS = ("1.1", "1.2", "1.3", "1.4")

_D1A: Mapping[str, _Node] = {
    # 1.1 splits into three tracks by how well confounders were controlled.
    "1.1": _n(
        "1.1",
        (["Y", "PY"], "1.3@full"),
        (["WN"], "1.3@partial"),
        (["SN", "NI"], "1.4@uncontrolled"),
    ),
    # Over-adjustment on either track collapses to the same bad branch.
    "1.3@full": _n("1.3", (["N", "PN", "NI"], "1.2@full"), (["Y", "PY"], "1.4@postint")),
    "1.3@partial": _n("1.3", (["N", "PN", "NI"], "1.2@partial"), (["Y", "PY"], "1.4@postint")),
    "1.2@full": _n(
        "1.2",
        (["Y", "PY"], "1.4@clean"),
        (["WN"], "1.4@minor"),
        (["SN", "NI"], Judgement.SERIOUS),
    ),
    "1.2@partial": _n(
        "1.2",
        (["Y", "PY", "WN"], "1.4@minor"),
        (["SN", "NI"], Judgement.SERIOUS),
    ),
    "1.4@clean": _n("1.4", (["N", "PN"], Judgement.LOW_EXCEPT_CONFOUNDING), (["Y", "PY"], Judgement.SERIOUS)),
    "1.4@minor": _n("1.4", (["N", "PN"], Judgement.MODERATE), (["Y", "PY"], Judgement.SERIOUS)),
    "1.4@uncontrolled": _n("1.4", (["N", "PN"], Judgement.SERIOUS), (["Y", "PY"], Judgement.CRITICAL)),
    # Post-intervention adjustment branch: 1.4 first, then 1.2.
    "1.4@postint": _n("1.4", (["Y", "PY"], Judgement.CRITICAL), (["N", "PN"], "1.2@postint")),
    "1.2@postint": _n(
        "1.2",
        (["Y", "PY"], Judgement.SERIOUS),
        (["WN", "SN", "NI"], Judgement.CRITICAL),
    ),
}


def domain1_variant_a(answers: Mapping[str, str]) -> AlgorithmResult:
    """Domain 1 where the analysis estimates the intention-to-treat effect (C4 = no)."""
    return _walk(_D1A, "1.1", answers, all_questions=_D1A_QUESTIONS)


_D1B_QUESTIONS = ("1.1", "1.2", "1.3", "1.4", "1.5")

_D1B: Mapping[str, _Node] = {
    "1.1": _n("1.1", (["Y", "PY"], "1.2"), (["PN", "N", "NI"], "1.4@nomethod")),
    "1.2": _n(
        "1.2",
        (["Y", "PY"], "1.3@full"),
        (["WN"], "1.3@partial"),
        (["SN", "NI"], Judgement.SERIOUS),
    ),
    "1.3@full": _n(
        "1.3",
        (["Y", "PY"], "1.5@clean"),
        (["WN"], "1.5@minor"),
        (["SN", "NI"], Judgement.SERIOUS),
    ),
    "1.3@partial": _n(
        "1.3",
        (["Y", "PY", "WN"], "1.5@minor"),
        (["SN", "NI"], Judgement.SERIOUS),
    ),
    "1.5@clean": _n("1.5", (["N", "PN"], Judgement.LOW_EXCEPT_CONFOUNDING), (["Y", "PY"], Judgement.SERIOUS)),
    "1.5@minor": _n("1.5", (["N", "PN"], Judgement.MODERATE), (["Y", "PY"], Judgement.SERIOUS)),
    "1.4@nomethod": _n("1.4", (["N", "PN", "NI"], "1.5@nomethod"), (["Y", "PY"], Judgement.CRITICAL)),
    "1.5@nomethod": _n("1.5", (["N", "PN"], Judgement.SERIOUS), (["Y", "PY"], Judgement.CRITICAL)),
}


def domain1_variant_b(answers: Mapping[str, str]) -> AlgorithmResult:
    """Domain 1 where the analysis estimates the per-protocol effect (C4 = yes)."""
    return _walk(_D1B, "1.1", answers, all_questions=_D1B_QUESTIONS)


def domain1(answers: Mapping[str, str], *, per_protocol: bool) -> AlgorithmResult:
    """Dispatch on C4."""
    return domain1_variant_b(answers) if per_protocol else domain1_variant_a(answers)


# --------------------------------------------------------------------------- #
# Domain 2 — bias in classification of interventions
# --------------------------------------------------------------------------- #
#
# The figure is three parallel tracks through 2.4 and 2.5. It is equivalent to
# an additive severity ladder: entry level L from 2.1/2.2/2.3, then 2.4 adds
# 0 (N/PN), 1 (WY/NI) or 2 (SY), then 2.5 adds 0 (N/PN) or 1 (Y/PY/NI),
# saturating at critical. test_domain2_is_additive asserts the equivalence.

_D2_QUESTIONS = ("2.1", "2.2", "2.3", "2.4", "2.5")

_D2: Mapping[str, _Node] = {
    "2.1": _n("2.1", (["Y", "PY"], "2.4@0"), (["PN", "N", "NI"], "2.2")),
    "2.2": _n("2.2", (["Y", "PY"], "2.4@0"), (["PN", "N", "NI"], "2.3")),
    "2.3": _n("2.3", (["SY"], "2.4@0"), (["WY", "NI"], "2.4@1"), (["PN", "N"], "2.4@2")),
    "2.4@0": _n("2.4", (["PN", "N"], "2.5@0"), (["WY", "NI"], "2.5@1"), (["SY"], "2.5@2")),
    "2.4@1": _n("2.4", (["PN", "N"], "2.5@1"), (["WY", "NI"], "2.5@2"), (["SY"], Judgement.CRITICAL)),
    "2.4@2": _n("2.4", (["PN", "N"], "2.5@2"), (["WY", "NI", "SY"], Judgement.CRITICAL)),
    "2.5@0": _n("2.5", (["PN", "N"], Judgement.LOW), (["Y", "PY", "NI"], Judgement.MODERATE)),
    "2.5@1": _n("2.5", (["PN", "N"], Judgement.MODERATE), (["Y", "PY", "NI"], Judgement.SERIOUS)),
    "2.5@2": _n("2.5", (["PN", "N"], Judgement.SERIOUS), (["Y", "PY", "NI"], Judgement.CRITICAL)),
}


def domain2(answers: Mapping[str, str]) -> AlgorithmResult:
    return _walk(_D2, "2.1", answers, all_questions=_D2_QUESTIONS)


# --------------------------------------------------------------------------- #
# Domain 3 — bias in selection of participants
# --------------------------------------------------------------------------- #
#
# Structurally unlike the others: two independent panels scored separately,
# combined worst-of, and an escalation ladder entered only when a panel lands on
# serious. Panel A covers follow-up start and immortal time; panel B covers
# other selection. The ladder gate in the tool's text ("if SN to 3.1 or Y/PY to
# 3.5") is exactly the condition "some panel came out serious".

_D3_QUESTIONS = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8")

_D3_PANEL_A: Mapping[str, _Node] = {
    "3.1": _n(
        "3.1",
        (["Y", "PY"], "3.2"),
        (["WN", "NI"], Judgement.MODERATE),
        (["SN"], Judgement.SERIOUS),
    ),
    "3.2": _n("3.2", (["PN", "N", "NI"], Judgement.LOW), (["Y", "PY"], Judgement.MODERATE)),
}

_D3_PANEL_B: Mapping[str, _Node] = {
    "3.3": _n("3.3", (["PN", "N"], Judgement.LOW), (["NI"], Judgement.MODERATE), (["Y", "PY"], "3.4")),
    "3.4": _n("3.4", (["PN", "N"], Judgement.LOW), (["NI"], Judgement.MODERATE), (["Y", "PY"], "3.5")),
    "3.5": _n("3.5", (["PN", "N", "NI"], Judgement.MODERATE), (["Y", "PY"], Judgement.SERIOUS)),
}

_D3_LADDER: Mapping[str, _Node] = {
    "3.6": _n("3.6", (["Y", "PY"], Judgement.MODERATE), (["PN", "N", "NI"], "3.7")),
    "3.7": _n("3.7", (["Y", "PY"], Judgement.MODERATE), (["PN", "N", "NI"], "3.8")),
    "3.8": _n("3.8", (["PN", "N", "NI"], Judgement.SERIOUS), (["Y", "PY"], Judgement.CRITICAL)),
}


def domain3(answers: Mapping[str, str]) -> AlgorithmResult:
    panel_a = _walk(_D3_PANEL_A, "3.1", answers, all_questions=("3.1", "3.2"))
    panel_b = _walk(_D3_PANEL_B, "3.3", answers, all_questions=("3.3", "3.4", "3.5"))

    path = panel_a.path + panel_b.path
    worst = max(panel_a.judgement, panel_b.judgement, key=lambda j: j.severity)
    notes = (
        f"panel A (follow-up start / immortal time) = {panel_a.judgement.value}",
        f"panel B (other selection) = {panel_b.judgement.value}",
    )

    if worst.severity < Judgement.SERIOUS.severity:
        reached = {q for q, _, _ in path}
        return AlgorithmResult(
            judgement=worst,
            path=path,
            not_reached=tuple(q for q in _D3_QUESTIONS if q not in reached),
            notes=notes + ("escalation ladder 3.6-3.8 not entered",),
        )

    return _walk(
        _D3_LADDER,
        "3.6",
        answers,
        all_questions=_D3_QUESTIONS,
        prefix_path=path,
        notes=notes + ("at least one panel serious: escalation ladder entered",),
    )


# --------------------------------------------------------------------------- #
# Domain 4 — bias due to missing data
# --------------------------------------------------------------------------- #
#
# Also an additive ladder underneath: the handling question (4.6, 4.9 or 4.10)
# sets level 0/1/2 from Y-PY / WN-NI / SN, and 4.11 adds 1 if there is no
# evidence of robustness. Encoded as the drawn graph regardless.

_D4_QUESTIONS = ("4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11")
_D4_COMPLETENESS = ("4.1", "4.2", "4.3")

_D4: Mapping[str, _Node] = {
    "4.4": _n("4.4", (["Y", "PY", "NI"], "4.5"), (["PN", "N"], "4.7")),
    # complete-case branch
    "4.5": _n("4.5", (["PN", "N"], Judgement.LOW), (["Y", "PY", "NI"], "4.6")),
    "4.6": _n("4.6", (["Y", "PY"], "4.11@0"), (["WN", "NI"], "4.11@1"), (["SN"], "4.11@2")),
    # imputation branch
    "4.7": _n("4.7", (["Y", "PY"], "4.8"), (["PN", "N", "NI"], "4.10")),
    "4.8": _n("4.8", (["Y", "PY"], "4.9"), (["PN", "N", "NI"], Judgement.SERIOUS)),
    "4.9": _n("4.9", (["Y", "PY"], Judgement.LOW), (["WN", "NI"], "4.11@1"), (["SN"], "4.11@2")),
    # neither complete-case nor imputation
    "4.10": _n("4.10", (["Y", "PY"], Judgement.LOW), (["WN", "NI"], "4.11@1"), (["SN"], "4.11@2")),
    # robustness evidence
    "4.11@0": _n("4.11", (["Y", "PY"], Judgement.LOW), (["PN", "N"], Judgement.MODERATE)),
    "4.11@1": _n("4.11", (["Y", "PY"], Judgement.MODERATE), (["PN", "N"], Judgement.SERIOUS)),
    "4.11@2": _n("4.11", (["Y", "PY"], Judgement.SERIOUS), (["PN", "N"], Judgement.CRITICAL)),
}


def domain4(answers: Mapping[str, str]) -> AlgorithmResult:
    missing = [q for q in _D4_COMPLETENESS if answers.get(q) in (None, "NA")]
    if missing:
        raise UnansweredQuestion(missing[0], "entry")

    prefix = tuple((q, answers[q], "entry") for q in _D4_COMPLETENESS)

    if all(answers[q] in ("Y", "PY") for q in _D4_COMPLETENESS):
        return AlgorithmResult(
            judgement=Judgement.LOW,
            path=prefix,
            not_reached=tuple(q for q in _D4_QUESTIONS if q not in _D4_COMPLETENESS),
            notes=("data complete on intervention, outcome and important confounders",),
        )

    return _walk(_D4, "4.4", answers, all_questions=_D4_QUESTIONS, prefix_path=prefix)


# --------------------------------------------------------------------------- #
# Domain 5 — bias in measurement of the outcome
# --------------------------------------------------------------------------- #
#
# The only domain with no critical terminal. NI at 5.1 does not behave like
# N/PN: it demotes the whole track by one level, so low becomes unreachable.

_D5_QUESTIONS = ("5.1", "5.2", "5.3")

_D5: Mapping[str, _Node] = {
    "5.1": _n(
        "5.1",
        (["PN", "N"], "5.2@comparable"),
        (["NI"], "5.2@unknown"),
        (["Y", "PY"], Judgement.SERIOUS),
    ),
    "5.2@comparable": _n("5.2", (["PN", "N"], Judgement.LOW), (["Y", "PY", "NI"], "5.3@comparable")),
    "5.2@unknown": _n("5.2", (["PN", "N"], Judgement.MODERATE), (["Y", "PY", "NI"], "5.3@unknown")),
    "5.3@comparable": _n(
        "5.3",
        (["PN", "N"], Judgement.LOW),
        (["WY", "NI"], Judgement.MODERATE),
        (["SY"], Judgement.SERIOUS),
    ),
    "5.3@unknown": _n(
        "5.3",
        (["WY", "PN", "N", "NI"], Judgement.MODERATE),
        (["SY"], Judgement.SERIOUS),
    ),
}


def domain5(answers: Mapping[str, str]) -> AlgorithmResult:
    return _walk(_D5, "5.1", answers, all_questions=_D5_QUESTIONS)


# --------------------------------------------------------------------------- #
# Domain 6 — bias in selection of the reported result
# --------------------------------------------------------------------------- #
#
# Not a graph: 6.2/6.3/6.4 are evaluated jointly by counting. The published
# bands overlap on "all NI" (it satisfies both the moderate and the serious
# band), so the more specific serious band is applied first.

_D6_QUESTIONS = ("6.1", "6.2", "6.3", "6.4")
_D6_SELECTION = ("6.2", "6.3", "6.4")


def domain6(answers: Mapping[str, str]) -> AlgorithmResult:
    a61 = answers.get("6.1")
    if a61 is None or a61 == "NA":
        raise UnansweredQuestion("6.1", "6.1")

    if a61 in ("Y", "PY"):
        return AlgorithmResult(
            judgement=Judgement.LOW,
            path=(("6.1", a61, "6.1"),),
            not_reached=_D6_SELECTION,
            notes=("result reported in line with a prespecified plan",),
        )

    missing = [q for q in _D6_SELECTION if answers.get(q) in (None, "NA")]
    if missing:
        raise UnansweredQuestion(missing[0], "6.2-6.4")

    picks = [answers[q] for q in _D6_SELECTION]
    n_yes = sum(1 for a in picks if a in ("Y", "PY"))
    n_ni = sum(1 for a in picks if a == "NI")

    if n_yes >= 2:
        judgement, why = Judgement.CRITICAL, "two or more of 6.2-6.4 answered Y/PY"
    elif n_yes == 1 or n_ni == 3:
        judgement, why = Judgement.SERIOUS, "exactly one Y/PY, or no information on all three"
    elif n_ni >= 1:
        judgement, why = Judgement.MODERATE, "at least one NI and no Y/PY"
    else:
        judgement, why = Judgement.LOW, "all of 6.2-6.4 answered N/PN"

    path = ((("6.1", a61, "6.1"),) + tuple((q, answers[q], "6.2-6.4") for q in _D6_SELECTION))
    return AlgorithmResult(judgement=judgement, path=path, not_reached=(), notes=(why,))


# --------------------------------------------------------------------------- #
# Overall (p.49)
# --------------------------------------------------------------------------- #


def overall(
    domain_judgements: Mapping[int, Judgement],
    *,
    escalate: bool = False,
    escalation_justification: str | None = None,
) -> AlgorithmResult:
    """Combine the six domain judgements.

    The default is worst-of. The tool additionally permits escalating several
    moderates to serious, or several seriouses to critical, when the problems
    are judged to compound — an explicit judgement call, so ``escalate`` must be
    requested and justified rather than inferred.
    """
    missing = [d for d in range(1, 7) if d not in domain_judgements]
    if missing:
        raise KeyError(f"missing domain judgement(s): {missing}")

    worst = max(domain_judgements.values(), key=lambda j: j.severity)
    worst_domains = sorted(d for d, j in domain_judgements.items() if j is worst)
    notes = [
        "worst domain judgement = "
        + worst.value.replace("_", " ")
        + " (domain " + ", ".join(str(d) for d in worst_domains) + ")"
    ]

    # Domain 1's "low" is the confounding-qualified one; if every domain is at
    # its best level the overall judgement inherits that qualification.
    if worst.severity == 0:
        result = Judgement.LOW_EXCEPT_CONFOUNDING
        notes.append("all domains at their lowest level; overall keeps the domain 1 qualification")
    else:
        result = worst

    if escalate:
        if not escalation_justification:
            raise ValueError("escalation requires a recorded justification")
        n_moderate = sum(1 for j in domain_judgements.values() if j is Judgement.MODERATE)
        n_serious = sum(1 for j in domain_judgements.values() if j is Judgement.SERIOUS)
        if result is Judgement.SERIOUS and n_serious > 1:
            result = Judgement.CRITICAL
            notes.append(f"escalated: {n_serious} serious domains judged to compound")
        elif result is Judgement.MODERATE and n_moderate > 1:
            result = Judgement.SERIOUS
            notes.append(f"escalated: {n_moderate} moderate domains judged to compound")
        else:
            raise ValueError("escalation requested but no permitted escalation applies")
        notes.append(f"justification: {escalation_justification}")

    return AlgorithmResult(judgement=result, path=(), not_reached=(), notes=tuple(notes))


# --------------------------------------------------------------------------- #
# Preliminary screening (section B) — short-circuits everything above.
# --------------------------------------------------------------------------- #


def screening_terminates(answers: Mapping[str, str]) -> bool:
    """True when section B sends the result straight to critical."""
    return answers.get("B2") in ("Y", "PY") or answers.get("B3") in ("Y", "PY")
