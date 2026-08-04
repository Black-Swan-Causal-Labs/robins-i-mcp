"""Tests for review-level aggregation and the robvis export.

The load-bearing test here is `test_robins_i_layout_transposes_d2_and_d3`. Every
other kind of export bug is loud; that one is silent. robvis's ROBINS-I template
is V1, which orders selection of participants before classification of
interventions, and V2 swaps them. Writing V2's columns out in order produces a
file that parses, plots, and lies.
"""

from __future__ import annotations

import csv
import io

import pytest

from robins_mcp import render_review, review
from robins_mcp.algorithms import AlgorithmResult, Judgement
from robins_mcp.report import Answer, Assessment, DomainOutcome


def _assessment(result_id: str, judgements: dict[int, Judgement], *,
                per_protocol: bool = False, ratified: bool = True,
                overall: Judgement | None = None) -> Assessment:
    """An Assessment with judgements set directly, bypassing the algorithms.

    Legitimate here: this module is a projection of already-computed judgements,
    so its tests should not depend on which answers happen to produce them.
    """
    return Assessment(
        result_id=result_id,
        citation="Author A. (2026). A study. J Test, 1, 1-9.",
        result_assessed="HR 1.0",
        outcome=f"outcome for {result_id}",
        per_protocol=per_protocol,
        domains=[
            DomainOutcome(d, AlgorithmResult(judgement=j))
            for d, j in sorted(judgements.items())
        ],
        answers={},
        prespecified_confounders=["Age"],
        prespecified_confounders_ratified=ratified,
        overall_final=overall,
        overall_override_justification="stated" if overall else "",
        text_sha256="a" * 64,
    )


ALL_LOW = {d: Judgement.LOW for d in range(1, 7)}


# --------------------------------------------------------------------------- #
# The silent failure mode
# --------------------------------------------------------------------------- #

def test_robins_i_layout_transposes_d2_and_d3():
    """V2 domain 2 (classification) must land in V1 slot D3, and V2 domain 3
    (selection) in V1 slot D2. Getting this backwards is undetectable in the
    resulting figure."""
    judgements = dict(ALL_LOW)
    judgements[2] = Judgement.CRITICAL   # classification of interventions
    judgements[3] = Judgement.MODERATE   # selection of participants
    table = review.robvis_table([_assessment("r", judgements)], layout="robins_i")

    header = table["header"]
    row = table["rows"][0]
    cells = dict(zip(header, row))
    assert cells["D2"] == "Moderate", "V1 D2 is selection of participants -> V2 domain 3"
    assert cells["D3"] == "Critical", "V1 D3 is classification of interventions -> V2 domain 2"


def test_generic_layout_keeps_v2_order_and_labels():
    """The other layout must NOT transpose — its headers are V2's own."""
    judgements = dict(ALL_LOW)
    judgements[2] = Judgement.CRITICAL
    judgements[3] = Judgement.MODERATE
    table = review.robvis_table([_assessment("r", judgements)], layout="generic")
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["Bias in classification of interventions"] == "Critical"
    assert cells["Bias in selection of participants"] == "Moderate"


def test_robins_i_layout_marks_the_dropped_domain_not_applicable():
    """V1's deviations domain has no V2 counterpart; NA renders as N/A in robvis
    rather than silently inheriting a neighbouring judgement."""
    table = review.robvis_table([_assessment("r", ALL_LOW)], layout="robins_i")
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["D4"] == review.ROBVIS_NOT_APPLICABLE
    assert "no V2 counterpart" in table["slot_mapping"]["V1 D4"]


def test_robins_i_layout_has_v1s_seven_domain_slots():
    table = review.robvis_table([_assessment("r", ALL_LOW)], layout="robins_i")
    assert table["header"] == ["Study", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
                               "Overall", "Weight"]
    assert table["robvis_tool"] == "ROBINS-I"


def test_unknown_layout_is_refused():
    with pytest.raises(ValueError, match="layout must be one of"):
        review.robvis_table([_assessment("r", ALL_LOW)], layout="rob2")


# --------------------------------------------------------------------------- #
# Losses are reported, not hidden
# --------------------------------------------------------------------------- #

def test_qualified_low_is_flagged_as_unrepresentable():
    """robvis reduces cells to a first initial over a five-fill palette, so
    'Low, except...' cannot be carried. It must be written as Low AND declared."""
    judgements = dict(ALL_LOW)
    judgements[1] = Judgement.LOW_EXCEPT_CONFOUNDING
    table = review.robvis_table([_assessment("r", judgements)], layout="robins_i")
    assert dict(zip(table["header"], table["rows"][0]))["D1"] == "Low"
    assert any("cannot be represented" in loss for loss in table["losses"])


def test_no_spurious_loss_when_nothing_is_lost():
    # One moderate domain, so the overall is plain 'moderate'. With every domain
    # at its lowest level the overall would itself be low_except_confounding —
    # the library carries domain 1's qualification up — and the loss would then
    # be real. See test_all_low_overall_is_itself_a_loss.
    judgements = dict(ALL_LOW)
    judgements[4] = Judgement.MODERATE
    table = review.robvis_table(
        [_assessment("r", judgements)], layout="robins_i", weights={"r": 2.5})
    assert table["losses"] == []


def test_all_low_overall_is_itself_a_loss():
    """When every domain is at its lowest level the overall inherits domain 1's
    qualification, so the export loses something even if no domain cell does."""
    table = review.robvis_table([_assessment("r", ALL_LOW)], weights={"r": 1})
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["Overall"] == "Low"
    assert any("cannot be represented" in loss for loss in table["losses"])


def test_mixed_c4_variants_are_flagged():
    table = review.robvis_table([
        _assessment("a", ALL_LOW, per_protocol=False),
        _assessment("b", ALL_LOW, per_protocol=True),
    ], layout="robins_i")
    assert any("mixes domain 1 variants" in loss for loss in table["losses"])


def test_equal_weighting_is_declared_and_overridable():
    one = review.robvis_table([_assessment("r", ALL_LOW)])
    assert any("equal weighting" in loss for loss in one["losses"])
    assert dict(zip(one["header"], one["rows"][0]))["Weight"] == "1"
    two = review.robvis_table([_assessment("r", ALL_LOW)], weights={"r": 0.4})
    assert dict(zip(two["header"], two["rows"][0]))["Weight"] == "0.4"


def test_csv_round_trips():
    out = review.robvis_csv([
        _assessment("a", ALL_LOW), _assessment("b", ALL_LOW),
    ], labels={"a": "Study A, 2026"})
    parsed = list(csv.reader(io.StringIO(out["csv"])))
    assert parsed[0] == out["header"]
    assert len(parsed) == 3
    # a label containing a comma must survive quoting
    assert parsed[1][0] == "Study A, 2026"
    assert parsed[2][0] == "b"


# --------------------------------------------------------------------------- #
# Review summary
# --------------------------------------------------------------------------- #

def test_results_and_documents_are_counted_separately():
    """Three results from one paper is not three studies' worth of evidence."""
    a, b, c = (_assessment(x, ALL_LOW) for x in "abc")
    summary = review.review_summary([a, b, c])
    assert summary["n_results"] == 3
    assert summary["n_studies"] == 1


def test_summary_counts_variants_and_unratified():
    summary = review.review_summary([
        _assessment("a", ALL_LOW, per_protocol=False, ratified=True),
        _assessment("b", ALL_LOW, per_protocol=True, ratified=False),
    ])
    assert (summary["n_variant_a"], summary["n_variant_b"]) == (1, 1)
    assert summary["n_unratified"] == 1


def test_rows_carry_the_variant_each_was_scored_under():
    rows = review.review_rows([
        _assessment("a", ALL_LOW, per_protocol=False),
        _assessment("b", ALL_LOW, per_protocol=True),
    ])
    assert [r["variant"] for r in rows] == ["A", "B"]


def test_labels_override_result_ids():
    rows = review.review_rows([_assessment("long/ugly/id", ALL_LOW)],
                              labels={"long/ugly/id": "Author 2026"})
    assert rows[0]["label"] == "Author 2026"
    assert rows[0]["result_id"] == "long/ugly/id"


# --------------------------------------------------------------------------- #
# The figure
# --------------------------------------------------------------------------- #

def test_figure_keeps_the_sixth_level_robvis_cannot():
    judgements = dict(ALL_LOW)
    judgements[1] = Judgement.LOW_EXCEPT_CONFOUNDING
    html = render_review.render([_assessment("r", judgements)])
    assert "Low, except for concerns about uncontrolled confounding" in html
    assert "j-lowc" in html          # its own fill class, not collapsed to j-low


def test_figure_states_that_rows_are_results_not_studies():
    html = render_review.render([_assessment(x, ALL_LOW) for x in "abc"])
    assert "Rows are results, not studies" in html
    assert "3 rows come from 1 document" in html


def test_figure_warns_only_when_variants_are_mixed():
    mixed = render_review.render([
        _assessment("a", ALL_LOW, per_protocol=False),
        _assessment("b", ALL_LOW, per_protocol=True),
    ])
    assert "does not mean one thing" in mixed
    uniform = render_review.render([_assessment("a", ALL_LOW)])
    assert "does not mean one thing" not in uniform


def test_figure_carries_the_draft_status_and_fingerprint():
    html = render_review.render([_assessment("r", ALL_LOW)])
    assert "draft (20 Nov 2025 release, subject to change)" in html
    assert "sha256:" in html


def test_figure_marks_overrides():
    a = _assessment("r", ALL_LOW, overall=Judgement.SERIOUS)
    assert "&dagger;" in render_review.render([a])


def test_empty_review_is_refused():
    with pytest.raises(ValueError, match="at least one finalized assessment"):
        render_review.render([])
