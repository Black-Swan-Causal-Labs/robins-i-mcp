"""Tests for the assessment record and the robvis export.

Two things carry the weight here.

`test_robins_i_layout_transposes_d2_and_d3` — every other kind of export bug is
loud. That one is silent: robvis's ROBINS-I template is V1, which orders
selection of participants before classification of interventions, and V2 swaps
them. Writing V2's columns out in order produces a file that parses, plots, and
lies.

`test_records_survive_a_round_trip_through_json` — the record is the interchange
format between sessions. A review of 200 studies is 200 runs and this server
keeps no state between them, so if the record does not survive serialization
there is no review-level output at all.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from robins_i_mcp import review
from robins_i_mcp.algorithms import AlgorithmResult, Judgement
from robins_i_mcp.report import Assessment, DomainOutcome
from robins_i_mcp.review import RECORD_VERSION, RecordError


def _assessment(result_id: str, judgements: dict[int, Judgement], *,
                per_protocol: bool = False, ratified: bool = True,
                overall: Judgement | None = None,
                text_sha256: str = "a" * 64) -> Assessment:
    """An Assessment with judgements set directly, bypassing the algorithms.

    Legitimate here: this module projects already-computed judgements, so its
    tests should not depend on which answers happen to produce them.
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
        text_sha256=text_sha256,
    )


def _record(*args, **kwargs) -> dict:
    return review.assessment_record(_assessment(*args, **kwargs))


ALL_LOW = {d: Judgement.LOW for d in range(1, 7)}
MIXED = {**ALL_LOW, 4: Judgement.MODERATE}   # so the overall is plain 'moderate'


# --------------------------------------------------------------------------- #
# The record as an interchange format
# --------------------------------------------------------------------------- #

def test_records_survive_a_round_trip_through_json():
    """The record crosses a session boundary as a file. If it cannot survive
    json.dumps/loads there is no cross-session review output."""
    original = _record("r", MIXED)
    restored = json.loads(json.dumps(original))
    assert restored == original
    assert review.as_record(restored) == original


def test_record_carries_enough_to_audit_a_row():
    record = _record("r", MIXED, text_sha256="b" * 64)
    prov = record["provenance"]
    assert prov["text_sha256"] == "b" * 64          # which document
    assert prov["algorithm_fingerprint"].startswith("sha256:")  # which transcription
    assert prov["spec_version"]
    assert "draft" in prov["source_status"]
    assert record["domain1_variant"] in ("A", "B")  # what D1 even means here
    assert record["ratification"]["is_final"] is True


def test_record_reports_when_it_is_not_final():
    record = _record("r", MIXED, ratified=False)
    assert record["ratification"]["is_final"] is False
    assert any("P1" in item for item in record["ratification"]["outstanding"])


def test_a_live_assessment_is_accepted_wherever_a_record_is():
    assessment = _assessment("r", MIXED)
    assert review.as_record(assessment) == review.assessment_record(assessment)


def test_unversioned_input_is_refused():
    with pytest.raises(RecordError, match="missing 'record_version'"):
        review.as_record({"result_id": "r", "domains": [], "overall": {}})


def test_a_record_from_a_future_version_is_refused():
    record = _record("r", MIXED)
    record["record_version"] = "robins-i-record-99"
    with pytest.raises(RecordError, match="this build reads"):
        review.as_record(record)


def test_a_truncated_record_is_refused():
    record = _record("r", MIXED)
    del record["provenance"]
    with pytest.raises(RecordError, match="missing 'provenance'"):
        review.as_record(record)


def test_empty_input_is_refused():
    with pytest.raises(RecordError, match="no assessment records"):
        review.as_records([])


# --------------------------------------------------------------------------- #
# The silent failure mode
# --------------------------------------------------------------------------- #

def test_robins_i_layout_transposes_d2_and_d3():
    """V2 domain 2 (classification) must land in V1 slot D3, and V2 domain 3
    (selection) in V1 slot D2. Getting this backwards is undetectable in the
    resulting figure."""
    judgements = dict(MIXED)
    judgements[2] = Judgement.CRITICAL   # classification of interventions
    judgements[3] = Judgement.MODERATE   # selection of participants
    table = review.robvis_table([_record("r", judgements)], layout="robins_i")

    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["D2"] == "Moderate", "V1 D2 is selection of participants -> V2 domain 3"
    assert cells["D3"] == "Critical", "V1 D3 is classification of interventions -> V2 domain 2"


def test_generic_layout_keeps_v2_order_and_labels():
    """The other layout must NOT transpose — its headers are V2's own."""
    judgements = dict(MIXED)
    judgements[2] = Judgement.CRITICAL
    judgements[3] = Judgement.MODERATE
    table = review.robvis_table([_record("r", judgements)], layout="generic")
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["Bias in classification of interventions"] == "Critical"
    assert cells["Bias in selection of participants"] == "Moderate"


def test_robins_i_layout_marks_the_dropped_domain_not_applicable():
    table = review.robvis_table([_record("r", MIXED)], layout="robins_i")
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["D4"] == review.ROBVIS_NOT_APPLICABLE
    assert "no V2 counterpart" in table["slot_mapping"]["V1 D4"]


def test_robins_i_layout_has_v1s_seven_domain_slots():
    table = review.robvis_table([_record("r", MIXED)], layout="robins_i")
    assert table["header"] == ["Study", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
                               "Overall", "Weight"]
    assert table["robvis_tool"] == "ROBINS-I"


def test_unknown_layout_is_refused():
    with pytest.raises(ValueError, match="layout must be one of"):
        review.robvis_table([_record("r", MIXED)], layout="rob2")


# --------------------------------------------------------------------------- #
# Losses are declared, not hidden
# --------------------------------------------------------------------------- #

def test_qualified_low_is_flagged_as_unrepresentable():
    judgements = dict(MIXED)
    judgements[1] = Judgement.LOW_EXCEPT_CONFOUNDING
    table = review.robvis_table([_record("r", judgements)])
    assert dict(zip(table["header"], table["rows"][0]))["D1"] == "Low"
    assert any("cannot be carried" in loss for loss in table["losses"])


def test_all_low_overall_is_itself_a_loss():
    """When every domain sits at its lowest level the overall inherits domain
    1's qualification, so the export loses something even though no domain cell
    is qualified."""
    table = review.robvis_table([_record("r", ALL_LOW)], weights={"r": 1})
    cells = dict(zip(table["header"], table["rows"][0]))
    assert cells["Overall"] == "Low"
    assert any("cannot be carried" in loss for loss in table["losses"])


def test_no_spurious_loss_when_nothing_is_lost():
    table = review.robvis_table([_record("r", MIXED)], weights={"r": 2.5})
    assert table["losses"] == []


def test_mixed_c4_variants_are_flagged():
    table = review.robvis_table([
        _record("a", MIXED, per_protocol=False),
        _record("b", MIXED, per_protocol=True),
    ], weights={"a": 1, "b": 1})
    assert any("mixes domain 1 variants" in loss for loss in table["losses"])


def test_unratified_records_are_flagged_by_name():
    table = review.robvis_table([
        _record("solid", MIXED, ratified=True),
        _record("shaky", MIXED, ratified=False),
    ], weights={"solid": 1, "shaky": 1})
    loss = next(l for l in table["losses"] if "NOT final" in l)
    assert "1 of 2" in loss and "shaky" in loss


def test_differing_algorithm_fingerprints_are_flagged():
    """Records built under different transcriptions are not comparable."""
    stale = _record("old", MIXED)
    stale["provenance"]["algorithm_fingerprint"] = "sha256:000000000000"
    table = review.robvis_table([stale, _record("new", MIXED)],
                                weights={"old": 1, "new": 1})
    assert any("DIFFERENT algorithm transcriptions" in loss for loss in table["losses"])


def test_equal_weighting_is_declared_and_overridable():
    one = review.robvis_table([_record("r", MIXED)])
    assert any("equal weighting" in loss for loss in one["losses"])
    assert dict(zip(one["header"], one["rows"][0]))["Weight"] == "1"
    two = review.robvis_table([_record("r", MIXED)], weights={"r": 0.4})
    assert dict(zip(two["header"], two["rows"][0]))["Weight"] == "0.4"


# --------------------------------------------------------------------------- #
# Combining records from many runs
# --------------------------------------------------------------------------- #

def test_records_from_separate_runs_combine():
    """The whole point: records made in different sessions, combined later."""
    saved = [
        json.loads(json.dumps(_record(f"study-{i}", MIXED, text_sha256=str(i) * 64)))
        for i in range(1, 6)
    ]
    out = review.robvis_csv(review.as_records(saved))
    parsed = list(csv.reader(io.StringIO(out["csv"])))
    assert len(parsed) == 6                       # header + 5 studies
    assert out["summary"]["n_results"] == 5
    assert out["summary"]["n_documents"] == 5


def test_results_and_documents_are_counted_separately():
    """Three results from one paper is not three studies' worth of evidence."""
    same_doc = [_record(x, MIXED, text_sha256="a" * 64) for x in "abc"]
    summary = review.review_summary(same_doc)
    assert summary["n_results"] == 3
    assert summary["n_documents"] == 1


def test_summary_counts_variants_and_unratified():
    summary = review.review_summary([
        _record("a", MIXED, per_protocol=False, ratified=True),
        _record("b", MIXED, per_protocol=True, ratified=False),
    ])
    assert (summary["n_variant_a"], summary["n_variant_b"]) == (1, 1)
    assert summary["n_not_final"] == 1


def test_labels_override_result_ids_and_survive_quoting():
    out = review.robvis_csv(
        [_record("long/ugly/id", MIXED), _record("b", MIXED)],
        labels={"long/ugly/id": "Author A, 2026"})
    parsed = list(csv.reader(io.StringIO(out["csv"])))
    assert parsed[1][0] == "Author A, 2026"       # comma survives CSV quoting
    assert parsed[2][0] == "b"
