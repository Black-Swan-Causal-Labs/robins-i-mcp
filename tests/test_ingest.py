"""Tests for ingestion, quote resolution and absence searching.

The cases here are the ones that actually bit when the layer was first run
against a real NEJM PDF: structured-abstract labels captured as body sections,
hyphenation with a space before the break, inline superscript reference
numbers, and short acronyms matching inside ordinary words.
"""

from __future__ import annotations

import pytest

from robins_i_mcp import ingest
from robins_i_mcp.ingest import QuoteNotFound

# A miniature paper with the same pathologies as a real one.
PAPER = """Comparative effectiveness of drug A versus drug B

BACKGROUND
Some background prose in the structured abstract.

METHODS
We emulated a target trial using routine data.

RESULTS
Drug A was associated with lower risk.

CONCLUSIONS
Drug A appears preferable.

Introduction
The wider literature is inconsistent, and the period was marked by change.

Methods
Patients were matched on age and sex. Confound -
ing was addressed by inverse probability weighting. We excluded those with
missing data on smoking. Data were assumed missing at random (MAR).

Results
The adjusted hazard ratio was 0.88. A negative control 12 suggested little
residual confounding.

Discussion
This study has limitations.
"""


@pytest.fixture(scope="module")
def sm():
    return ingest.parse_text(PAPER, manuscript_id="mini")


# --------------------------------------------------------------------------- #
# Normalization and sectioning
# --------------------------------------------------------------------------- #

def test_dehyphenation_handles_space_before_the_break():
    assert "Confounding" in ingest._normalize("Confound -\ning")
    assert "Confounding" in ingest._normalize("Confound-\ning")
    # A hyphen not at a line break is left alone.
    assert ingest._normalize("well-balanced") == "well-balanced"


def test_structured_abstract_labels_do_not_become_body_sections(sm):
    methods = [s for s in sm.sections if s.name == "methods"]
    assert len(methods) == 1
    body = sm.full_text[methods[0].start:methods[0].end]
    assert "Patients were matched on age and sex" in body
    assert "We emulated a target trial" not in body   # that was the abstract's METHODS
    assert any("Structured-abstract labels" in w for w in sm.warnings)


def test_short_paper_without_repeats_keeps_its_headings():
    """The abstract-label heuristic must not fire when the headings are real."""
    short = "Title\n\nIntroduction\nBackground prose.\n\nMethods\nWhat we did.\n\nResults\nWhat happened.\n"
    m = ingest.parse_text(short)
    names = [s.name for s in m.sections]
    assert "methods" in names and "results" in names
    assert not any("Structured-abstract" in w for w in m.warnings)


def test_section_and_source_lookup(sm):
    pos = sm.full_text.index("inverse probability weighting")
    assert sm.section_at(pos) == "methods"
    assert sm.source_at(pos) == "main"


# --------------------------------------------------------------------------- #
# Quote resolution
# --------------------------------------------------------------------------- #

def test_exact_quote_resolves_and_is_labelled_exact(sm):
    span = sm.resolve("Patients were matched on age and sex.")
    assert span.match == "exact"
    assert sm.full_text[span.start:span.end] == "Patients were matched on age and sex."
    assert span.section == "methods"
    assert span.locator == "methods — main text"


def test_quote_is_whitespace_and_case_insensitive(sm):
    span = sm.resolve("patients   were\n matched on AGE and sex")
    assert span.match == "exact"


def test_quote_spanning_a_hyphenated_line_break_resolves(sm):
    """The source reads 'Confound -\\ning'; the assessor quotes it joined."""
    span = sm.resolve("Confounding was addressed by inverse probability weighting.")
    assert span.match == "exact"     # normalization already joined it


def test_hyphen_relaxed_pass_catches_a_stray_hyphen(sm):
    span = sm.resolve("inverse-probability-weighting")
    assert span.match == "hyphen_relaxed"


def test_reference_superscript_is_stripped_on_the_last_pass(sm):
    span = sm.resolve("A negative control suggested little residual confounding.")
    assert span.match == "refs_stripped"
    # the span still covers the real text, superscript included
    assert "12" in sm.full_text[span.start:span.end]


def test_passes_are_tried_in_order(sm):
    """An exact match is never reported as a loose one."""
    span = sm.resolve("The adjusted hazard ratio was 0.88.")
    assert span.match == "exact"


def test_unresolvable_quote_raises_with_a_near_miss(sm):
    with pytest.raises(QuoteNotFound) as exc:
        sm.resolve("Patients were matched on age, sex and blood pressure.", "1.1")
    assert exc.value.question == "1.1"
    assert "nearest text at offset" in exc.value.near_miss


def test_near_miss_slides_through_the_quote(sm):
    """A quote whose opening words are absent but whose middle is present —
    the page-break-with-float case — still gets a useful pointer."""
    with pytest.raises(QuoteNotFound) as exc:
        sm.resolve("Notwithstanding all of that, the adjusted hazard ratio was 0.88.")
    assert "matched from word" in exc.value.near_miss


def test_quote_from_another_document_says_so(sm):
    with pytest.raises(QuoteNotFound) as exc:
        sm.resolve("Zebrafish were reared in filtered seawater.")
    assert "may be from another document" in exc.value.near_miss


# --------------------------------------------------------------------------- #
# Absence searching
# --------------------------------------------------------------------------- #

def test_acronyms_are_word_anchored(sm):
    """'MAR' must not match inside 'marked'."""
    hits = sm.search(("MAR",)).hits
    assert len(hits) == 1
    assert "missing at random" in hits[0].excerpt


def test_stems_still_match_their_family(sm):
    assert sm.search(("confound",)).n_hits >= 2      # confounding, confounding
    assert sm.search(("weight",)).n_hits >= 1        # weighting


def test_search_record_reports_absence(sm):
    rec = sm.search(("landmark", "immortal time", "prevalent user"))
    assert rec.is_absent
    assert rec.n_hits == 0
    assert "0 hit(s)" in rec.describe()


def test_search_record_reports_presence(sm):
    rec = sm.search_cue("negative_control")
    assert not rec.is_absent
    assert "negative control" in rec.describe()


def test_section_restricted_search_stays_in_section(sm):
    rec = sm.search(("hazard ratio",), sections=("methods",))
    assert rec.n_hits == 0            # it is in Results
    assert sm.search(("hazard ratio",)).n_hits == 1


def test_every_registered_cue_runs(sm):
    cues = sm.detect_cues()
    assert set(cues) == {c.key for c in ingest.CUES}
    assert all(isinstance(r.n_hits, int) for r in cues.values())


# --------------------------------------------------------------------------- #
# Bundles
# --------------------------------------------------------------------------- #

def test_bundle_appends_supplement_and_tags_its_source(sm):
    bundle = ingest.build_bundle(
        ingest.parse_text(PAPER), [("appendix.pdf", "Table S1. Protocol component.", 1)],
        supplement_status="user_provided",
    )
    span = bundle.resolve("Table S1. Protocol component.")
    assert span.source == "supplement:appendix.pdf"
    assert span.locator == "supplement — appendix.pdf"
    assert bundle.supplement_status == "user_provided"


def test_bundle_preserves_main_text_offsets():
    main = ingest.parse_text(PAPER)
    before = main.resolve("Patients were matched on age and sex.")
    bundle = ingest.build_bundle(main, [("s.pdf", "extra", None)], "user_provided")
    after = bundle.resolve("Patients were matched on age and sex.")
    assert (before.start, before.end) == (after.start, after.end)


def test_bundle_sha_changes_when_a_supplement_is_added():
    main = ingest.parse_text(PAPER)
    bundle = ingest.build_bundle(ingest.parse_text(PAPER), [("s.pdf", "extra", None)], "user_provided")
    assert bundle.text_sha256 != main.text_sha256


def test_unknown_supplement_status_rejected():
    with pytest.raises(ValueError):
        ingest.build_bundle(ingest.parse_text(PAPER), [("s.pdf", "x", None)], "maybe")


def test_empty_supplement_list_just_stamps_status():
    m = ingest.build_bundle(ingest.parse_text(PAPER), [], "none_exists")
    assert m.supplement_status == "none_exists"


# --------------------------------------------------------------------------- #
# Loud failures
# --------------------------------------------------------------------------- #

def test_a_path_that_does_not_exist_raises_rather_than_being_ingested():
    with pytest.raises(FileNotFoundError):
        ingest.parse_document("/no/such/manuscript.pdf")


def test_raw_text_is_still_accepted_as_text():
    m = ingest.parse_document("Methods\nWe did things.\n")
    assert "We did things" in m.full_text
