"""Tests for the transcribed ROBINS-I V2 algorithms.

Three kinds of test here, in increasing order of how much they would catch:

1. Structural — every node's outgoing edges partition its question's response
   options exactly. This is what catches a transcription slip where an arrow was
   missed or an option landed on two arrows.
2. Path — specific routes read off the figures, terminal by terminal.
3. Property — the invariants the figures imply (domain 1 never reaches plain
   low, domain 5 never reaches critical, domain 2 is an additive ladder).
"""

from __future__ import annotations

import itertools

import pytest

from robins_mcp import algorithms as alg
from robins_mcp.algorithms import Judgement as J


# --------------------------------------------------------------------------- #
# 1. Structural
# --------------------------------------------------------------------------- #

# Each graph, with the response-option key that applies to each of its questions.
GRAPHS = {
    "d1a": (alg._D1A, {"1.1": "1.1A", "1.2": "1.2A", "1.3": "1.3A", "1.4": "1.4A"}),
    "d1b": (alg._D1B, {"1.1": "1.1B", "1.2": "1.2B", "1.3": "1.3B", "1.4": "1.4B", "1.5": "1.5B"}),
    "d2": (alg._D2, {q: q for q in ("2.1", "2.2", "2.3", "2.4", "2.5")}),
    "d3a": (alg._D3_PANEL_A, {q: q for q in ("3.1", "3.2")}),
    "d3b": (alg._D3_PANEL_B, {q: q for q in ("3.3", "3.4", "3.5")}),
    "d3c": (alg._D3_LADDER, {q: q for q in ("3.6", "3.7", "3.8")}),
    "d4": (alg._D4, {q: q for q in ("4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11")}),
    "d5": (alg._D5, {q: q for q in ("5.1", "5.2", "5.3")}),
}


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_edges_partition_the_response_options(name):
    """Every answer leads somewhere, and never to two places."""
    graph, option_key = GRAPHS[name]
    for node_id, node in graph.items():
        expected = set(alg.RESPONSE_OPTIONS[option_key[node.question]]) - {"NA"}

        covered: set[str] = set()
        for accepted, _dest in node.edges:
            overlap = covered & accepted
            assert not overlap, f"{name}:{node_id} sends {sorted(overlap)} down two edges"
            covered |= accepted

        assert covered == expected, (
            f"{name}:{node_id} ({node.question}) covers {sorted(covered)}, "
            f"expected {sorted(expected)}"
        )


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_every_edge_is_traversable(name):
    """DFS every edge; no cycles, no dead ends, no unreachable nodes."""
    graph, _ = GRAPHS[name]
    entry = next(iter(graph))
    reached_nodes: set[str] = set()
    edges_walked = 0

    def visit(node_id, answers):
        nonlocal edges_walked
        if isinstance(node_id, J):
            return
        reached_nodes.add(node_id)
        node = graph[node_id]
        for accepted, dest in node.edges:
            edges_walked += 1
            visit(dest, {**answers, node.question: sorted(accepted)[0]})

    visit(entry, {})
    assert edges_walked > 0
    # Every node in the graph must be reachable from the entry node.
    assert reached_nodes == set(graph), f"unreachable nodes: {set(graph) - reached_nodes}"


# --------------------------------------------------------------------------- #
# 2. Paths read off the figures
# --------------------------------------------------------------------------- #

# ---- domain 1 variant A (p.20) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        # best case: everything controlled, well measured, no over-adjustment,
        # nothing suggesting residual confounding
        ({"1.1": "Y", "1.3": "N", "1.2": "Y", "1.4": "N"}, J.LOW_EXCEPT_CONFOUNDING),
        # same but measurement only weakly adequate
        ({"1.1": "Y", "1.3": "N", "1.2": "WN", "1.4": "N"}, J.MODERATE),
        # negative controls fire on an otherwise clean analysis
        ({"1.1": "Y", "1.3": "N", "1.2": "Y", "1.4": "Y"}, J.SERIOUS),
        # substantial measurement error in the confounders
        ({"1.1": "Y", "1.3": "N", "1.2": "SN"}, J.SERIOUS),
        ({"1.1": "Y", "1.3": "N", "1.2": "NI"}, J.SERIOUS),
        # weak-no at 1.1 caps the best attainable judgement at moderate
        ({"1.1": "WN", "1.3": "N", "1.2": "Y", "1.4": "N"}, J.MODERATE),
        ({"1.1": "WN", "1.3": "N", "1.2": "WN", "1.4": "N"}, J.MODERATE),
        ({"1.1": "WN", "1.3": "N", "1.2": "SN"}, J.SERIOUS),
        # important confounders left uncontrolled
        ({"1.1": "SN", "1.4": "N"}, J.SERIOUS),
        ({"1.1": "SN", "1.4": "Y"}, J.CRITICAL),
        ({"1.1": "NI", "1.4": "N"}, J.SERIOUS),
        # over-adjustment branch: 1.4 asked before 1.2
        ({"1.1": "Y", "1.3": "Y", "1.4": "Y"}, J.CRITICAL),
        ({"1.1": "Y", "1.3": "Y", "1.4": "N", "1.2": "Y"}, J.SERIOUS),
        ({"1.1": "Y", "1.3": "Y", "1.4": "N", "1.2": "WN"}, J.CRITICAL),
        ({"1.1": "WN", "1.3": "Y", "1.4": "N", "1.2": "SN"}, J.CRITICAL),
    ],
)
def test_domain1_variant_a_paths(answers, expected):
    assert alg.domain1_variant_a(answers).judgement is expected


def test_domain1_variant_a_skips_unreached_questions():
    result = alg.domain1_variant_a({"1.1": "SN", "1.4": "N"})
    assert set(result.not_reached) == {"1.2", "1.3"}


# ---- domain 1 variant B (p.24) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        ({"1.1": "Y", "1.2": "Y", "1.3": "Y", "1.5": "N"}, J.LOW_EXCEPT_CONFOUNDING),
        ({"1.1": "Y", "1.2": "Y", "1.3": "WN", "1.5": "N"}, J.MODERATE),
        ({"1.1": "Y", "1.2": "Y", "1.3": "Y", "1.5": "Y"}, J.SERIOUS),
        ({"1.1": "Y", "1.2": "Y", "1.3": "SN"}, J.SERIOUS),
        ({"1.1": "Y", "1.2": "WN", "1.3": "Y", "1.5": "N"}, J.MODERATE),
        ({"1.1": "Y", "1.2": "WN", "1.3": "WN", "1.5": "N"}, J.MODERATE),
        ({"1.1": "Y", "1.2": "SN"}, J.SERIOUS),
        # no appropriate time-varying method at all
        ({"1.1": "N", "1.4": "N", "1.5": "N"}, J.SERIOUS),
        ({"1.1": "N", "1.4": "N", "1.5": "Y"}, J.CRITICAL),
        ({"1.1": "NI", "1.4": "Y"}, J.CRITICAL),
    ],
)
def test_domain1_variant_b_paths(answers, expected):
    assert alg.domain1_variant_b(answers).judgement is expected


def test_domain1_never_reaches_plain_low():
    """Both variants qualify their best judgement with the confounding caveat."""
    for graph in (alg._D1A, alg._D1B):
        terminals = {d for node in graph.values() for _, d in node.edges if isinstance(d, J)}
        assert J.LOW not in terminals
        assert J.LOW_EXCEPT_CONFOUNDING in terminals


# ---- domain 2 (p.28) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        ({"2.1": "Y", "2.4": "N", "2.5": "N"}, J.LOW),
        ({"2.1": "Y", "2.4": "N", "2.5": "Y"}, J.MODERATE),
        ({"2.1": "Y", "2.4": "WY", "2.5": "N"}, J.MODERATE),
        ({"2.1": "Y", "2.4": "SY", "2.5": "N"}, J.SERIOUS),
        ({"2.1": "Y", "2.4": "SY", "2.5": "NI"}, J.CRITICAL),
        ({"2.1": "N", "2.2": "Y", "2.4": "N", "2.5": "N"}, J.LOW),
        ({"2.1": "N", "2.2": "N", "2.3": "SY", "2.4": "N", "2.5": "N"}, J.LOW),
        ({"2.1": "N", "2.2": "N", "2.3": "WY", "2.4": "N", "2.5": "N"}, J.MODERATE),
        ({"2.1": "N", "2.2": "N", "2.3": "N", "2.4": "N", "2.5": "N"}, J.SERIOUS),
        ({"2.1": "N", "2.2": "N", "2.3": "N", "2.4": "SY"}, J.CRITICAL),
        ({"2.1": "N", "2.2": "N", "2.3": "WY", "2.4": "SY"}, J.CRITICAL),
    ],
)
def test_domain2_paths(answers, expected):
    assert alg.domain2(answers).judgement is expected


def test_domain2_is_an_additive_severity_ladder():
    """The three drawn tracks are equivalent to entry level + 2.4 bump + 2.5 bump."""
    entry = {"SY": 0, "WY": 1, "NI": 1, "PN": 2, "N": 2}
    bump_24 = {"PN": 0, "N": 0, "WY": 1, "NI": 1, "SY": 2}
    bump_25 = {"PN": 0, "N": 0, "Y": 1, "PY": 1, "NI": 1}
    ladder = [J.LOW, J.MODERATE, J.SERIOUS, J.CRITICAL]

    for a23, a24, a25 in itertools.product(entry, bump_24, bump_25):
        answers = {"2.1": "N", "2.2": "N", "2.3": a23, "2.4": a24, "2.5": a25}
        level = entry[a23] + bump_24[a24]
        expected = ladder[3] if level >= 3 else ladder[min(3, level + bump_25[a25])]
        assert alg.domain2(answers).judgement is expected, answers

    # ...and the two shortcuts into the top track behave like entry level 0.
    for a24, a25 in itertools.product(bump_24, bump_25):
        expected = ladder[min(3, bump_24[a24] + (bump_25[a25] if bump_24[a24] < 3 else 0))]
        assert alg.domain2({"2.1": "Y", "2.4": a24, "2.5": a25}).judgement is expected


# ---- domain 3 (p.32) ----

@pytest.mark.parametrize(
    "answers,expected,ladder_entered",
    [
        # both panels clean
        ({"3.1": "Y", "3.2": "N", "3.3": "N"}, J.LOW, False),
        # panel A moderate via weak-no on follow-up start
        ({"3.1": "WN", "3.3": "N"}, J.MODERATE, False),
        # panel A moderate via immortal time
        ({"3.1": "Y", "3.2": "Y", "3.3": "N"}, J.MODERATE, False),
        # panel B moderate via no information
        ({"3.1": "Y", "3.2": "N", "3.3": "NI"}, J.MODERATE, False),
        ({"3.1": "Y", "3.2": "N", "3.3": "Y", "3.4": "NI"}, J.MODERATE, False),
        # panel B: selection on post-baseline vars associated with intervention
        # but not influenced by the outcome
        ({"3.1": "Y", "3.2": "N", "3.3": "Y", "3.4": "Y", "3.5": "N"}, J.MODERATE, False),
        # panel A serious -> ladder, corrected in the analysis
        ({"3.1": "SN", "3.3": "N", "3.6": "Y"}, J.MODERATE, True),
        # ...not corrected, but sensitivity analyses reassure
        ({"3.1": "SN", "3.3": "N", "3.6": "N", "3.7": "Y"}, J.MODERATE, True),
        # ...neither, and the bias is not severe
        ({"3.1": "SN", "3.3": "N", "3.6": "N", "3.7": "N", "3.8": "N"}, J.SERIOUS, True),
        # ...and it is
        ({"3.1": "SN", "3.3": "N", "3.6": "N", "3.7": "N", "3.8": "Y"}, J.CRITICAL, True),
        # panel B serious reaches the same ladder
        (
            {"3.1": "Y", "3.2": "N", "3.3": "Y", "3.4": "Y", "3.5": "Y", "3.6": "N",
             "3.7": "N", "3.8": "Y"},
            J.CRITICAL,
            True,
        ),
    ],
)
def test_domain3_paths(answers, expected, ladder_entered):
    result = alg.domain3(answers)
    assert result.judgement is expected
    assert ladder_entered == any("ladder entered" in n for n in result.notes)


def test_domain3_ladder_gate_matches_the_published_condition():
    """The gate is 'SN to 3.1 or Y/PY to 3.5' — i.e. exactly 'a panel is serious'."""
    for a31, a35 in itertools.product(("Y", "PY", "WN", "SN", "NI"), ("PN", "N", "NI", "Y", "PY")):
        answers = {
            "3.1": a31, "3.2": "N",
            "3.3": "Y", "3.4": "Y", "3.5": a35,
            "3.6": "Y",  # supplied so the ladder can complete when entered
        }
        entered = any("ladder entered" in n for n in alg.domain3(answers).notes)
        assert entered == (a31 == "SN" or a35 in ("Y", "PY")), answers


# ---- domain 4 (p.38) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        # nothing missing
        ({"4.1": "Y", "4.2": "Y", "4.3": "PY"}, J.LOW),
        # complete-case, exclusion unrelated to the outcome
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "N"}, J.LOW),
        # complete-case, related, but the model explains it, and robust
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "Y", "4.11": "Y"}, J.LOW),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "Y", "4.11": "N"}, J.MODERATE),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "WN", "4.11": "Y"}, J.MODERATE),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "WN", "4.11": "N"}, J.SERIOUS),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "SN", "4.11": "Y"}, J.SERIOUS),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "Y", "4.5": "Y", "4.6": "SN", "4.11": "N"}, J.CRITICAL),
        # imputation branch
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "Y", "4.8": "N"}, J.SERIOUS),
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "Y", "4.8": "Y", "4.9": "Y"}, J.LOW),
        (
            {"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "Y", "4.8": "Y",
             "4.9": "SN", "4.11": "N"},
            J.CRITICAL,
        ),
        # neither complete-case nor imputation
        ({"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "N", "4.10": "Y"}, J.LOW),
        (
            {"4.1": "N", "4.2": "Y", "4.3": "Y", "4.4": "N", "4.7": "N",
             "4.10": "WN", "4.11": "N"},
            J.SERIOUS,
        ),
    ],
)
def test_domain4_paths(answers, expected):
    assert alg.domain4(answers).judgement is expected


def test_domain4_completeness_gate_needs_all_three():
    with pytest.raises(alg.UnansweredQuestion):
        alg.domain4({"4.1": "Y", "4.2": "Y"})


def test_domain4_411_is_a_uniform_one_step_bump():
    for level, node in enumerate(("4.11@0", "4.11@1", "4.11@2")):
        edges = dict(alg._D4[node].edges)
        by_answer = {a: d for opts, d in edges.items() for a in opts}
        assert by_answer["Y"] is alg._LADDER[level]
        assert by_answer["N"] is alg._LADDER[level + 1]


# ---- domain 5 (p.41) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        ({"5.1": "N", "5.2": "N"}, J.LOW),
        ({"5.1": "N", "5.2": "Y", "5.3": "N"}, J.LOW),
        ({"5.1": "N", "5.2": "Y", "5.3": "WY"}, J.MODERATE),
        ({"5.1": "N", "5.2": "Y", "5.3": "NI"}, J.MODERATE),
        ({"5.1": "N", "5.2": "Y", "5.3": "SY"}, J.SERIOUS),
        ({"5.1": "N", "5.2": "NI", "5.3": "N"}, J.LOW),
        # NI at 5.1 demotes the whole track: low becomes unreachable
        ({"5.1": "NI", "5.2": "N"}, J.MODERATE),
        ({"5.1": "NI", "5.2": "Y", "5.3": "N"}, J.MODERATE),
        ({"5.1": "NI", "5.2": "Y", "5.3": "WY"}, J.MODERATE),
        ({"5.1": "NI", "5.2": "Y", "5.3": "SY"}, J.SERIOUS),
        ({"5.1": "Y", "5.2": "N"}, J.SERIOUS),
    ],
)
def test_domain5_paths(answers, expected):
    assert alg.domain5(answers).judgement is expected


def test_domain5_has_no_critical_terminal():
    terminals = {d for node in alg._D5.values() for _, d in node.edges if isinstance(d, J)}
    assert J.CRITICAL not in terminals


# ---- domain 6 (p.47) ----

@pytest.mark.parametrize(
    "answers,expected",
    [
        ({"6.1": "Y"}, J.LOW),
        ({"6.1": "PY"}, J.LOW),
        ({"6.1": "N", "6.2": "N", "6.3": "PN", "6.4": "N"}, J.LOW),
        ({"6.1": "N", "6.2": "NI", "6.3": "N", "6.4": "N"}, J.MODERATE),
        ({"6.1": "NI", "6.2": "NI", "6.3": "NI", "6.4": "N"}, J.MODERATE),
        ({"6.1": "N", "6.2": "Y", "6.3": "N", "6.4": "N"}, J.SERIOUS),
        ({"6.1": "N", "6.2": "Y", "6.3": "NI", "6.4": "N"}, J.SERIOUS),
        # all-NI is the overlapping case: the serious band wins over moderate
        ({"6.1": "N", "6.2": "NI", "6.3": "NI", "6.4": "NI"}, J.SERIOUS),
        ({"6.1": "N", "6.2": "Y", "6.3": "PY", "6.4": "N"}, J.CRITICAL),
        ({"6.1": "N", "6.2": "Y", "6.3": "Y", "6.4": "Y"}, J.CRITICAL),
    ],
)
def test_domain6_paths(answers, expected):
    assert alg.domain6(answers).judgement is expected


def test_domain6_covers_every_combination():
    opts = ("Y", "PY", "PN", "N", "NI")
    for combo in itertools.product(opts, repeat=3):
        answers = {"6.1": "N", "6.2": combo[0], "6.3": combo[1], "6.4": combo[2]}
        assert isinstance(alg.domain6(answers).judgement, J)


# --------------------------------------------------------------------------- #
# 3. Overall + screening
# --------------------------------------------------------------------------- #


def _domains(overrides=None):
    base = {
        1: J.LOW_EXCEPT_CONFOUNDING,
        2: J.LOW, 3: J.LOW, 4: J.LOW, 5: J.LOW, 6: J.LOW,
    }
    base.update(overrides or {})
    return base


def test_overall_is_worst_of():
    assert alg.overall(_domains()).judgement is J.LOW_EXCEPT_CONFOUNDING
    assert alg.overall(_domains({3: J.MODERATE})).judgement is J.MODERATE
    assert alg.overall(_domains({2: J.MODERATE, 4: J.SERIOUS})).judgement is J.SERIOUS
    assert alg.overall(_domains({5: J.CRITICAL})).judgement is J.CRITICAL


def test_overall_requires_all_six_domains():
    with pytest.raises(KeyError):
        alg.overall({1: J.LOW_EXCEPT_CONFOUNDING, 2: J.LOW})


def test_overall_escalation_requires_justification():
    d = _domains({2: J.SERIOUS, 3: J.SERIOUS})
    with pytest.raises(ValueError):
        alg.overall(d, escalate=True)
    assert alg.overall(d, escalate=True, escalation_justification="compounding").judgement is J.CRITICAL


def test_overall_escalation_rejects_inapplicable_requests():
    with pytest.raises(ValueError):
        alg.overall(_domains({2: J.MODERATE}), escalate=True, escalation_justification="x")


def test_several_moderates_escalate_to_serious():
    d = _domains({2: J.MODERATE, 3: J.MODERATE, 4: J.MODERATE})
    assert alg.overall(d).judgement is J.MODERATE  # default is worst-of
    assert alg.overall(d, escalate=True, escalation_justification="compounding").judgement is J.SERIOUS


def test_screening_short_circuits():
    assert alg.screening_terminates({"B1": "N", "B2": "Y"})
    assert alg.screening_terminates({"B3": "PY"})
    assert not alg.screening_terminates({"B1": "Y", "B3": "N"})
