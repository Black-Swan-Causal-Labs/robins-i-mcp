"""Tests for the MCP tool surface.

The library below it is already covered; what is tested here is what the server
layer adds and is therefore the only place it can go wrong: the two setup gates
(P1 blocks domain 1, C4 selects domain 1's question set), the three evidence
rules enforced at submission, per-domain traversal with a partial answer set,
and the finalization that turns six domain outcomes into one stamped artifact.

Everything runs against a synthetic paper so the suite needs no PDF on disk.
"""

from __future__ import annotations

import pytest

from robins_i_mcp import server as srv

# A miniature cohort study carrying just enough text for quotes to resolve and
# for the absence searches to have something to fail to find.
PAPER = """Emulated trial of drug A versus drug B in older adults

Methods
We identified new users of drug A and drug B and matched them on age and sex.
Follow-up began on the day of the first dispensing for both groups. Vital status
was obtained from a national death registry for every participant, identically in
both groups. No trial protocol or statistical analysis plan was registered for
this analysis.

Results
The hazard ratio for death at 12 months was 1.24 (95% CI 1.05 to 1.47).
Baseline characteristics were balanced after matching.
"""

CONFOUNDERS = ["Age", "Sex", "Frailty", "Baseline renal function"]


@pytest.fixture(autouse=True)
def clean_state():
    """Server state is process-global; each test gets a clean one."""
    for store in (srv._parsed, srv._priors, srv._results, srv._answers,
                  srv._outcomes, srv._assessments):
        store.clear()
    yield


@pytest.fixture
def sha() -> str:
    return srv.parse_document(PAPER, manuscript_id="toy",
                              citation="Toy A. (2026). Toy study. J Toy, 1, 1-9.")["text_sha256"]


def specify(sha: str, *, c4: str = "no_itt", review_id: str = "default", **kw) -> str:
    return srv.specify_result(
        result_id=kw.pop("result_id", "toy/hr"),
        text_sha256=sha,
        result_assessed="HR 1.24 (95% CI 1.05 to 1.47) at 12 months",
        outcome="All-cause death",
        accounts_for_deviations=c4,
        review_id=review_id,
        b1=kw.pop("b1", "Y"),
        b3=kw.pop("b3", "N"),
        **kw,
    )["result_id"]


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def test_parse_document_returns_hash_and_cue_survey(sha):
    bundle = srv._parsed[sha]
    assert bundle.citation.startswith("Toy A.")
    survey = srv._cue_survey(bundle)
    assert len(survey) == 15
    # the paper registers no protocol, so that cue's terms do appear (the word
    # "protocol" is present) — what matters is the survey is per-cue and counted
    assert all(isinstance(row["n_hits"], int) for row in survey)


def test_unparsed_hash_is_a_clear_error():
    with pytest.raises(ValueError, match="does not survive a server restart"):
        srv._resolve_bundle("deadbeef")


# --------------------------------------------------------------------------- #
# Gate 1 — P1 blocks domain 1
# --------------------------------------------------------------------------- #

def test_domain1_scaffold_refused_without_p1(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="P1"):
        srv.assess_result(rid, 1)


def test_domain1_submission_refused_without_p1(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="P1"):
        srv.submit_answers(rid, 1, [{"question": "1.4", "response": "N",
                                     "evidence_mode": "manuscript_absent",
                                     "search_cue": "negative_control"}])


def test_other_domains_are_not_blocked_by_p1(sha):
    rid = specify(sha)
    out = srv.assess_result(rid, 5)
    assert [q["id"] for q in out["questions"]] == ["5.1", "5.2", "5.3"]


def test_p1_is_review_scoped_not_result_scoped(sha):
    srv.set_prespecified_confounders(CONFOUNDERS, review_id="rev-1")
    rid = specify(sha, review_id="rev-1")
    assert srv._confounders_for(rid) == CONFOUNDERS
    other = specify(sha, review_id="rev-2", result_id="toy/rd")
    assert srv._confounders_for(other) == []


def test_empty_p1_is_refused():
    with pytest.raises(ValueError, match="cannot be empty"):
        srv.set_prespecified_confounders([])


def test_p1_is_unratified_unless_a_human_signs_it(sha):
    record = srv.set_prespecified_confounders(CONFOUNDERS)
    assert record["ratified"] is False
    assert "NOT RATIFIED" in record["note"]
    signed = srv.set_prespecified_confounders(CONFOUNDERS, ratified_by="J. Reviewer")
    assert signed["ratified"] is True


# --------------------------------------------------------------------------- #
# Gate 2 — C4 selects domain 1's question set
# --------------------------------------------------------------------------- #

def test_c4_has_no_default(sha):
    with pytest.raises(ValueError, match="no safe default"):
        srv.specify_result("x", sha, "HR", "death", "probably per protocol")


def test_c4_no_itt_selects_variant_a(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha, c4="no_itt")
    out = srv.assess_result(rid, 1)
    assert out["variant"] == "A"
    assert [q["id"] for q in out["questions"]] == ["1.1", "1.2", "1.3", "1.4"]
    # 1.1 in variant A is the confounder-coverage question, judged against P1
    assert out["questions"][0]["evidence_mode"] == "reviewer_prior"


def test_c4_yes_pp_selects_variant_b(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha, c4="yes_pp")
    out = srv.assess_result(rid, 1)
    assert out["variant"] == "B"
    assert [q["id"] for q in out["questions"]] == ["1.1", "1.2", "1.3", "1.4", "1.5"]
    # 1.1 in variant B asks about the time-varying method, read off the paper
    assert out["questions"][0]["evidence_mode"] == "manuscript_positive"


def test_variant_changes_the_accepted_vocabulary(sha):
    """1.1 takes weak/strong-no under A and the standard set under B; an answer
    valid in one variant must be rejected in the other."""
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid_a = specify(sha, c4="no_itt")
    with pytest.raises(ValueError, match="vocabulary"):
        srv.submit_answers(rid_a, 1, [{"question": "1.1", "response": "PN",
                                       "evidence_mode": "reviewer_prior",
                                       "prior_ref": "P1"}])
    rid_b = specify(sha, c4="yes_pp", result_id="toy/pp")
    ok = srv.submit_answers(rid_b, 1, [{"question": "1.1", "response": "PN",
                                        "evidence_mode": "manuscript_positive",
                                        "quotes": ["matched them on age and sex"]}])
    assert ok["status"] in ("domain_scored", "incomplete")


# --------------------------------------------------------------------------- #
# Evidence rules
# --------------------------------------------------------------------------- #

def test_unresolvable_quote_is_rejected_with_the_nearest_text(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="do not appear in the ingested bundle"):
        srv.submit_answers(rid, 5, [{"question": "5.1", "response": "N",
                                     "evidence_mode": "manuscript_positive",
                                     "quotes": ["participants were randomly assigned"]}])


def test_resolvable_quote_is_accepted(sha):
    rid = specify(sha)
    out = srv.submit_answers(rid, 5, [
        {"question": "5.1", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["obtained from a national death registry for every participant, "
                    "identically in both groups"]},
        {"question": "5.2", "response": "Y", "evidence_mode": "manuscript_absent",
         "search_cue": "blinding"},
        {"question": "5.3", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["Vital status"]},
    ])
    assert out["status"] == "domain_scored"
    assert out["judgement"] == "low"


def test_absence_asserted_in_prose_is_rejected(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="cannot be audited"):
        srv.submit_answers(rid, 6, [{"question": "6.1", "response": "NI",
                                     "evidence_mode": "manuscript_absent",
                                     "rationale": "I looked, there is no protocol"}])


def test_absence_search_is_run_by_the_server(sha):
    rid = specify(sha)
    srv.submit_answers(rid, 6, [{"question": "6.1", "response": "NI",
                                 "evidence_mode": "manuscript_absent",
                                 "search_cue": "prespecification"}])
    record = srv._answers[rid]["6.1"].search_record
    assert record.cue == "prespecification"
    assert record.terms  # the server's terms, not the model's say-so
    assert srv._answers[rid]["6.1"].search_is_auditable


def test_unknown_search_cue_is_rejected(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="unknown search_cue"):
        srv.submit_answers(rid, 6, [{"question": "6.1", "response": "NI",
                                     "evidence_mode": "manuscript_absent",
                                     "search_cue": "vibes"}])


def test_reviewer_prior_needs_the_item_it_invokes(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha)
    with pytest.raises(ValueError, match="prior_ref"):
        srv.submit_answers(rid, 1, [{"question": "1.1", "response": "SN",
                                     "evidence_mode": "reviewer_prior"}])


def test_na_is_refused_as_an_answer(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="do not answer NA"):
        srv.submit_answers(rid, 5, [{"question": "5.3", "response": "NA",
                                     "evidence_mode": "manuscript_positive",
                                     "quotes": ["Vital status"]}])


def test_answers_must_belong_to_the_submitted_domain(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="belongs to domain 5, not 6"):
        srv.submit_answers(rid, 6, [{"question": "5.1", "response": "N",
                                     "evidence_mode": "manuscript_positive",
                                     "quotes": ["Vital status"]}])


def test_preliminaries_are_not_submitted_as_answers(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="not a signalling question"):
        srv.submit_answers(rid, 5, [{"question": "C4", "response": "Y",
                                     "evidence_mode": "manuscript_positive",
                                     "quotes": ["Vital status"]}])


def test_variant_b_only_question_is_refused_under_variant_a(sha):
    """1.5 exists only in variant B; submitting it under A must not be silently
    stored, because the A traversal would never read it."""
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha, c4="no_itt")
    with pytest.raises(ValueError, match=r"variant A has questions"):
        srv.submit_answers(rid, 1, [{"question": "1.5", "response": "N",
                                     "evidence_mode": "manuscript_positive",
                                     "quotes": ["Vital status"]}])


# --------------------------------------------------------------------------- #
# Traversal
# --------------------------------------------------------------------------- #

def test_partial_answers_return_the_question_the_traversal_reached(sha):
    rid = specify(sha)
    out = srv.submit_answers(rid, 6, [{"question": "6.1", "response": "NI",
                                       "evidence_mode": "manuscript_absent",
                                       "search_cue": "prespecification"}])
    assert out["status"] == "incomplete"
    assert out["needs_answer"] == "6.2"
    # and the partial answer is kept, so the caller tops up rather than resubmits
    assert "6.1" in srv._answers[rid]


def test_unreached_questions_are_recorded_not_demanded(sha):
    rid = specify(sha)
    out = srv.submit_answers(rid, 5, [
        {"question": "5.1", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["Vital status"]},
        {"question": "5.2", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["Vital status"]},
    ])
    assert out["status"] == "domain_scored"
    assert out["not_reached"] == ["5.3"]     # 5.3 is asked only if 5.2 is Y/PY/NI


def test_judgement_is_computed_not_asserted(sha):
    """No tool takes a domain judgement as an input; it falls out of the path."""
    rid = specify(sha)
    out = srv.submit_answers(rid, 6, [
        {"question": "6.1", "response": "NI", "evidence_mode": "manuscript_absent",
         "search_cue": "prespecification"},
        {"question": "6.2", "response": "Y", "evidence_mode": "manuscript_positive",
         "quotes": ["hazard ratio"]},
        {"question": "6.3", "response": "Y", "evidence_mode": "manuscript_positive",
         "quotes": ["hazard ratio"]},
        {"question": "6.4", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["hazard ratio"]},
    ])
    assert out["judgement"] == "critical"    # two or more of 6.2-6.4 answered Y/PY
    assert out["notes"] == ["two or more of 6.2-6.4 answered Y/PY"]


# --------------------------------------------------------------------------- #
# Overrides
# --------------------------------------------------------------------------- #

def test_override_requires_a_justification(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="requires override_justification"):
        srv.submit_answers(rid, 5, [
            {"question": "5.1", "response": "N", "evidence_mode": "manuscript_positive",
             "quotes": ["Vital status"]},
            {"question": "5.2", "response": "N", "evidence_mode": "manuscript_positive",
             "quotes": ["Vital status"]},
        ], override_judgement="serious")


def test_override_shows_both_values_and_enters_the_queue(sha):
    rid = _complete_all_domains(sha)
    srv.submit_answers(rid, 5, _domain5(), override_judgement="moderate",
                       override_justification="outcome registry coverage is unknown")
    out = srv.submit_answers(rid, 0, render=False)
    row = next(d for d in out["domains"] if d["domain"] == 5)
    assert row["judgement"] == "moderate"
    assert row["algorithm_judgement"] == "low"
    assert row["overridden"] is True
    assert any("domain 5" in item for item in out["ratification_queue"])


def test_invalid_escalation_is_refused_and_not_left_set(sha):
    rid = _complete_all_domains(sha)
    with pytest.raises(ValueError, match="permitted escalation"):
        srv.submit_answers(rid, 0, overall_escalate=True,
                           overall_override_justification="they compound", render=False)
    # the failed escalation must not poison the next finalize
    assert srv.submit_answers(rid, 0, render=False)["overall"] == "low_except_confounding"


# --------------------------------------------------------------------------- #
# Finalization
# --------------------------------------------------------------------------- #

def _domain5() -> list[dict]:
    return [
        {"question": "5.1", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["identically in both groups"]},
        {"question": "5.2", "response": "N", "evidence_mode": "manuscript_positive",
         "quotes": ["national death registry"]},
    ]


def _complete_all_domains(sha: str) -> str:
    """Every domain answered on its shortest clean path."""
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha)
    q = lambda text: {"evidence_mode": "manuscript_positive", "quotes": [text]}  # noqa: E731
    srv.submit_answers(rid, 1, [
        {"question": "1.1", "response": "Y", "evidence_mode": "reviewer_prior",
         "prior_ref": "P1 items 1-4"},
        {"question": "1.3", "response": "N", **q("matched them on age and sex")},
        {"question": "1.2", "response": "Y", **q("matched them on age and sex")},
        {"question": "1.4", "response": "N", "evidence_mode": "manuscript_absent",
         "search_cue": "negative_control"},
    ], support="matching covers the prespecified factors")
    srv.submit_answers(rid, 2, [
        {"question": "2.1", "response": "Y", **q("new users of drug A and drug B")},
        {"question": "2.4", "response": "N", **q("day of the first dispensing")},
        {"question": "2.5", "response": "N", **q("first dispensing")},
    ])
    srv.submit_answers(rid, 3, [
        {"question": "3.1", "response": "Y", **q("Follow-up began on the day of the "
                                                 "first dispensing for both groups")},
        {"question": "3.2", "response": "N", "evidence_mode": "manuscript_absent",
         "search_cue": "followup_start"},
        {"question": "3.3", "response": "N", **q("matched them on age and sex")},
    ])
    srv.submit_answers(rid, 4, [
        {"question": "4.1", "response": "Y", **q("new users of drug A and drug B")},
        {"question": "4.2", "response": "Y", **q("for every participant")},
        {"question": "4.3", "response": "Y", "evidence_mode": "reviewer_prior",
         "prior_ref": "P1 items 1-4"},
    ])
    srv.submit_answers(rid, 5, _domain5())
    srv.submit_answers(rid, 6, [
        {"question": "6.1", "response": "NI", "evidence_mode": "manuscript_absent",
         "search_cue": "prespecification"},
        {"question": "6.2", "response": "N", **q("hazard ratio for death")},
        {"question": "6.3", "response": "N", **q("hazard ratio for death")},
        {"question": "6.4", "response": "N", **q("hazard ratio for death")},
    ])
    return rid


def test_cannot_finalize_before_every_domain_is_scored(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha)
    srv.submit_answers(rid, 5, _domain5())
    with pytest.raises(ValueError, match=r"domains \[1, 2, 3, 4, 6\] not yet scored"):
        srv.submit_answers(rid, 0, render=False)


def test_finalize_computes_overall_and_stamps_the_artifact(sha):
    rid = _complete_all_domains(sha)
    out = srv.submit_answers(rid, 0)
    assert out["status"] == "finalized"
    # every domain at its best level, so overall inherits domain 1's qualification
    assert out["overall"] == "low_except_confounding"
    assert len(out["domains"]) == 6
    prov = out["provenance"]
    assert prov["algorithm_fingerprint"].startswith("sha256:")
    assert prov["text_sha256"] == sha
    assert prov["domain1_variant"].startswith("A")
    assert "<!doctype html>" in out["report"]["html"]
    assert out["report"]["filename"].endswith("_ROBINS-I.html")


def test_reviewer_prior_answers_block_a_final_verdict(sha):
    rid = _complete_all_domains(sha)
    out = srv.submit_answers(rid, 0, render=False)
    # 1.1 and 4.3 are reviewer-prior, and P1 was never ratified
    assert any(item.startswith("1.1") for item in out["ratification_queue"])
    assert any(item.startswith("4.3") for item in out["ratification_queue"])
    assert any("P1" in item for item in out["ratification_queue"])
    assert "NOT empty" in out["next_step"]


def test_unratified_p1_is_queued_even_though_it_was_supplied(sha):
    """An agent-proposed confounder list is a candidate, not a prespecification.
    Supplying it unblocks domain 1 but must not read as settled."""
    rid = _complete_all_domains(sha)          # P1 supplied, ratified_by empty
    out = srv.submit_answers(rid, 0, render=False)
    assert any("proposed but not ratified" in item for item in out["ratification_queue"])
    # a human signing it off clears that one item, and only that one
    srv.set_prespecified_confounders(CONFOUNDERS, ratified_by="J. Reviewer")
    after = srv.submit_answers(rid, 0, render=False)
    assert not any(item.startswith("P1") for item in after["ratification_queue"])
    assert any(item.startswith("1.1") for item in after["ratification_queue"])


def test_evidence_summary_counts_what_actually_bound(sha):
    rid = _complete_all_domains(sha)
    out = srv.submit_answers(rid, 0, render=False)
    ev = out["evidence"]
    assert ev["n_answers"] == 19
    assert ev["n_quotes_bound"] == 14
    assert ev["match_passes"] == {"exact": 14}
    assert ev["evidence_modes"]["reviewer_prior"] == 2
    assert ev["evidence_modes"]["manuscript_absent"] == 3
    assert ev["unauditable_absence_claims"] == []


def test_render_report_reproduces_the_stamped_artifact(sha):
    rid = _complete_all_domains(sha)
    finalized = srv.submit_answers(rid, 0)
    again = srv.render_report(rid)
    assert again["html"] == finalized["report"]["html"]
    assert again["overall"] == finalized["overall"]


def test_render_before_finalize_is_a_clear_error(sha):
    rid = specify(sha)
    with pytest.raises(ValueError, match="No finalized assessment"):
        srv.render_report(rid)


# --------------------------------------------------------------------------- #
# Screening (section B)
# --------------------------------------------------------------------------- #

def test_screening_terminates_straight_to_critical(sha):
    rid = specify(sha, b1="N", b2="Y", b3="N")
    out = srv.submit_answers(rid, 0, render=False)
    assert out["overall"] == "critical"
    assert out["domains"] == []
    assert "terminated" in out["screening_note"]


def test_terminated_assessment_refuses_domain_work(sha):
    rid = specify(sha, b1="Y", b3="Y")
    with pytest.raises(ValueError, match="terminated"):
        srv.assess_result(rid, 2)


def test_unrecorded_screening_is_warned_about(sha):
    warnings = srv.specify_result("toy/hr", sha, "HR", "death", "no_itt")["warnings"]
    assert any("Section B screening not fully recorded" in w for w in warnings)


def test_bad_screening_response_is_rejected(sha):
    with pytest.raises(ValueError, match="B3: expected Y, PY, PN or N"):
        specify(sha, b3="maybe")


# --------------------------------------------------------------------------- #
# Scaffold shape
# --------------------------------------------------------------------------- #

def test_scaffold_is_per_domain_not_one_flat_rubric(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha)
    sizes = {d: len(srv.assess_result(rid, d)["questions"]) for d in range(1, 7)}
    assert sizes == {1: 4, 2: 5, 3: 8, 4: 11, 5: 3, 6: 4}
    overview = srv.assess_result(rid, 0)
    assert "questions" not in overview
    assert overview["domains_outstanding"] == [1, 2, 3, 4, 5, 6]


def test_scaffold_carries_only_its_own_cues(sha):
    rid = specify(sha)
    assert [c["cue"] for c in srv.assess_result(rid, 6)["cues"]] == [
        "prespecification", "multiplicity"]
    assert [c["cue"] for c in srv.assess_result(rid, 5)["cues"]] == [
        "outcome_ascertainment", "blinding"]


def test_domain1_cues_follow_the_variant(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid_a = specify(sha, c4="no_itt")
    rid_b = specify(sha, c4="yes_pp", result_id="toy/pp")
    cues_a = {c["cue"] for c in srv.assess_result(rid_a, 1)["cues"]}
    cues_b = {c["cue"] for c in srv.assess_result(rid_b, 1)["cues"]}
    # deviation_handling informs 1.1B only, so it appears under B and not under A
    assert "deviation_handling" in cues_b
    assert "deviation_handling" not in cues_a


def test_domain1_scaffold_states_what_important_means(sha):
    srv.set_prespecified_confounders(CONFOUNDERS)
    rid = specify(sha)
    out = srv.assess_result(rid, 1)
    assert out["prespecified_confounders"] == CONFOUNDERS
    assert "not by the paper's own covariate table" in out["confounding_note"]


def test_spec_carries_no_published_wording():
    """Own-words only: the spec ships intent, never the signalling-question text."""
    doc = srv.get_spec(detail="full")
    assert doc["spec_version"] == "robins-i-v2-cohort-0.1.0"
    assert doc["algorithm_fingerprint"].startswith("sha256:")
    assert "not the wording of the published tool" in doc["attribution"]["non_endorsement"]
    d1 = next(d for d in doc["domains"] if d["domain"] == 1)
    assert [v["variant"] for v in d1["variants"]] == ["A", "B"]
