"""ROBINS-I V2 assessment of a real study.

    Dickerman BA, Gerlovin H, Madenci AL, et al. Comparative Effectiveness of
    BNT162b2 and mRNA-1273 Vaccines in U.S. Veterans.
    N Engl J Med 2022;386:105-15. doi:10.1056/NEJMoa2115463

Scored from the published article plus its Supplementary Appendix. Every quote
below is verbatim from that bundle (whitespace normalized, PDF hyphenation
joined).

The result under assessment is ONE estimate — the 24-week risk difference for
documented SARS-CoV-2 infection in the alpha-predominant period. Other results
in the same paper (other outcomes, the subgroup analyses, the delta-period
trial) are separate assessments and are not covered here.

    python examples/dickerman_2022.py [outfile.html]
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robins_mcp import algorithms as alg, ingest, render_html
from robins_mcp.report import Answer, Assessment, DomainOutcome

# --------------------------------------------------------------------------- #
# Ingest the bundle first: quotes are resolved against THIS text, and the
# absence checks below are generated from it rather than asserted by hand.
# --------------------------------------------------------------------------- #
PAPERS = Path("/Users/jddmacbook/Desktop/Testing Folder for AI/TARGET Checklist MCP/other pubs")

def load_bundle() -> ingest.SectionMap:
    main = ingest.parse_pdf(PAPERS / "Dickerman 2022.pdf", manuscript_id="NEJMoa2115463")
    text, pages = ingest.extract_file(PAPERS / "Dickerman 2022 SUPPLEMENT.pdf")
    return ingest.build_bundle(
        main, [("Dickerman 2022 SUPPLEMENT.pdf", text, pages)],
        supplement_status="user_provided",
    )

BUNDLE = load_bundle()

# --------------------------------------------------------------------------- #
# P1 — prespecified important confounding factors.
#
# AGENT-PROPOSED, NOT RATIFIED. In a real review this list comes from the
# protocol, before any study is assessed. It is proposed here from domain
# knowledge of what drives brand allocation in a head-to-head mRNA vaccine
# comparison, and it is what question 1.1 is judged against.
# --------------------------------------------------------------------------- #
PRESPECIFIED_CONFOUNDERS = [
    "Calendar date of vaccination (variant circulation and supply)",
    "Age",
    "Sex",
    "Race and ethnicity",
    "Geographic location / administering facility",
    "Urbanicity of residence",
    "Local vaccine brand availability at the administering site",
    "Comorbidity burden",
    "Immunocompromised status",
    "Obesity (body-mass index)",
    "Smoking status",
    "Health care–seeking behaviour and prior utilization",
    "Occupational / vaccination priority group",
]

ANSWERS = {
    # ---------------- domain 1 — confounding (variant A, ITT) --------------
    "1.1": Answer(
        "1.1", "PY", "reviewer_prior",
        "Matching covered the factors that actually drive which mRNA brand a veteran "
        "received — date, site region and demographics — and the remaining prespecified "
        "factors (comorbidity, immunocompromise, BMI, smoking, utilization) were shown "
        "balanced after matching, which is evidence that controlling for them was "
        "unnecessary in this sample. The residual concern is that the matching set was "
        "deliberately coarsened from VA station to VISN, and brand availability is a "
        "station-level phenomenon.",
        quotes=(
            "The matching factors (calendar date, age, sex, race, urbanicity of residence, "
            "and geographic location) are associated with the probability of receiving a "
            "particular vaccine, as well as with the risk of SARS-CoV-2 infection or severe "
            "Covid-19.",
            "All measured variables were well-balanced between the two vaccine groups",
            "Second, this set was gradually coarsened while ensuring that exchangeability "
            "was maintained.",
        ),
        prior_ref="P1 items 7, 8, 9, 12 — site-level availability, comorbidity, "
                  "immunocompromise, health care–seeking behaviour",
    ),
    "1.2": Answer(
        "1.2", "Y", "manuscript_positive",
        "The matching variables are administrative fields — date of administration, age, "
        "sex, race, urbanicity, VISN — recorded directly in the VA databases rather than "
        "derived or self-reported at interview.",
        quotes=(
            "Calendar date of first vaccine dose – coarsened exact matching (5-day bins)",
            "the VA health care databases capture rich data on demographic factors, medical "
            "records, laboratory test results",
        ),
    ),
    "1.3": Answer(
        "1.3", "N", "manuscript_positive",
        "Every matching variable is fixed at or before the day of first dose; nothing "
        "measured after vaccination enters the matching or the analysis.",
        quotes=(
            "Individuals are randomly assigned to a strategy at baseline within strata "
            "defined by calendar date (5-day bins), age (5-year bins), sex (male, female), "
            "race (white, black, other, unknown), urbanicity of",
        ),
    ),
    "1.4": Answer(
        "1.4", "N", "manuscript_positive",
        "Two negative outcome controls were run specifically to detect residual "
        "confounding, and both were reassuring.",
        quotes=(
            "To explore the possibility of residual confounding (e.g., by underlying health "
            "status or health care–seeking behavior), we used two negative outcome controls "
            "that are not directly affected by vaccination but for which the effect of "
            "vaccination might be similarly confounded.",
            # NB shortened: the full sentence begins "In addition," at the foot of
            # p.7 and resumes on p.8 across a table float, so it never appears
            # contiguously in the extracted text. bind_evidence() caught this.
            "two analyses involving negative outcome controls 13 suggested little "
            "confounding.",
        ),
    ),

    # ---------------- domain 2 — classification of interventions -----------
    "2.1": Answer(
        "2.1", "Y", "manuscript_positive",
        "Both strategies are point interventions delivered on day 0, so group membership "
        "is fully determined by the brand administered at baseline.",
        quotes=(
            "For each eligible participant, follow-up started on the day the first dose of "
            "vaccine was received (baseline)",
        ),
    ),
    "2.4": Answer(
        "2.4", "N", "manuscript_positive",
        "Brand is taken from immunization and procedure records written at the moment of "
        "administration, before any follow-up time elapsed, so the outcome cannot have "
        "influenced classification.",
        quotes=(
            "Vaccination was identified with the use of records in the Immunization domain "
            "and procedures recorded in the Outpatient or Inpatient domain of the database.",
        ),
    ),
    "2.5": Answer(
        "2.5", "PN", "manuscript_positive",
        "Brand is recorded at administration in a registry field. Veterans with an "
        "incomplete vaccination record were excluded at eligibility, removing the main "
        "route to misclassification.",
        quotes=(
            "399,315 Had an incomplete Covid-19 vaccination record",
        ),
    ),

    # ---------------- domain 3 — selection ---------------------------------
    "3.1": Answer(
        "3.1", "Y", "manuscript_positive",
        "Follow-up starts on the day of first dose for both groups — the moment the "
        "strategies begin — with no landmark or run-in.",
        quotes=(
            "For each person, follow-up starts on the day of vaccination (baseline) and ends "
            "on the day of the outcome of interest, death, 168 days (24 weeks) after "
            "baseline, or the end of the study period (July 1, 2021), whichever happens first.",
        ),
    ),
    "3.2": Answer(
        "3.2", "N", "manuscript_absent",
        "No blanking or immortal-time window: risks are estimated by Kaplan-Meier with "
        "daily events from day 0. The first 10 days are used as a negative control but "
        "are not excluded from the primary analysis.",
        search_record=BUNDLE.search(
            ("landmark", "immortal", "blanking", "run-in", "washout", "excluded from the analysis"),
            cue="followup_start"),
    ),
    "3.3": Answer(
        "3.3", "N", "manuscript_positive",
        "Every eligibility criterion and every matching variable is measured at or before "
        "baseline. The large exclusion for missing BMI and smoking status uses data from "
        "the previous year, so it is pre-baseline selection, not post-intervention.",
        quotes=(
            "Eligibility criteria included veteran status, an age of at least 18 years "
            "between January 4 and May 14, 2021, no previously documented SARS-CoV-2 "
            "infection, no previous Covid-19 vaccination, and a known residential address "
            "outside of a long-term care facility, as well as known smoking status and "
            "body-mass index recorded within the previous year.",
        ),
    ),

    # ---------------- domain 4 — missing data ------------------------------
    "4.1": Answer(
        "4.1", "Y", "manuscript_positive",
        "Intervention status is complete by construction — the cohort is defined by having "
        "a recorded first dose.",
        quotes=(
            "Vaccination was identified with the use of records in the Immunization domain "
            "and procedures recorded in the Outpatient or Inpatient domain of the database.",
        ),
    ),
    "4.2": Answer(
        "4.2", "PY", "manuscript_positive",
        "Outcomes are ascertained continuously from national VA surveillance for everyone "
        "in the cohort; the shortfall from 168 days (median follow-up 126 days) is "
        "administrative censoring driven by the recruitment window, which Kaplan-Meier "
        "handles. Care obtained outside the VA is a misclassification concern, judged in "
        "domain 5, rather than missing data.",
        quotes=(
            "The median follow-up period was 126 days (interquartile range, 107 to 147).",
            "SARS-CoV-2 infections were identified with the use of the VA Covid-19 National "
            "Surveillance Tool,",
        ),
    ),
    "4.3": Answer(
        "4.3", "Y", "manuscript_positive",
        "Complete within the analysed cohort — but completeness was bought by requiring "
        "recorded BMI and smoking status at eligibility, which excluded 1,237,833 "
        "otherwise-eligible vaccinees. That is a restriction of the population, not "
        "missing data within it, and bears on generalizability rather than bias.",
        quotes=(
            "1,237,833 Did not have recent data on body-mass index or smoking status",
            "as well as known smoking status and body-mass index recorded within the "
            "previous year",
        ),
    ),

    # ---------------- domain 5 — measurement of the outcome ----------------
    "5.1": Answer(
        "5.1", "N", "manuscript_positive",
        "Identical ascertainment machinery for both arms — the same national surveillance "
        "tool, the same case definitions. There is no reason detection intensity would "
        "differ between two mRNA vaccines given in the same system on the same dates.",
        quotes=(
            "SARS-CoV-2 infections were identified with the use of the VA Covid-19 National "
            "Surveillance Tool, which integrates data on polymerase-chain-reaction (PCR) "
            "laboratory tests with natural language processing of clinical notes to capture "
            "diagnoses inside and outside the VA health care system.",
            "Even in the presence of residual misclassification, we would expect this to be "
            "nondifferential between the vaccination groups under comparison",
        ),
    ),
    "5.2": Answer(
        "5.2", "Y", "manuscript_absent",
        "No blinding is described, and none is plausible: outcomes are derived from the "
        "same electronic record that carries the vaccination entry.",
        search_record=BUNDLE.search_cue("blinding"),
    ),
    "5.3": Answer(
        "5.3", "N", "manuscript_positive",
        "The outcome is a documented PCR-confirmed infection, not a rated or adjudicated "
        "judgement, so knowing the brand cannot colour the assessment itself.",
        quotes=(
            "which integrates data on polymerase-chain-reaction (PCR) laboratory tests with "
            "natural language processing of clinical notes",
        ),
    ),

    # ---------------- domain 6 — selection of the reported result ----------
    "6.1": Answer(
        "6.1", "NI", "manuscript_absent",
        "The Supplementary Appendix carries a full target-trial protocol table, but it is "
        "published alongside the results rather than registered beforehand, and no "
        "registration or analysis plan is cited. Prespecification therefore cannot be "
        "verified either way.",
        search_record=BUNDLE.search_cue("prespecification"),
    ),
    "6.2": Answer(
        "6.2", "N", "manuscript_positive",
        "One definition per outcome, fixed in the protocol table, and all five outcomes "
        "are reported in Table 2 rather than a selection of them.",
        quotes=(
            "The five outcomes of interest were documented SARS-CoV-2 infection, documented "
            "symptomatic Covid-19, hospital admission for Covid-19, ICU admission for "
            "Covid-19, and death from Covid-19.",
        ),
    ),
    "6.3": Answer(
        "6.3", "N", "manuscript_positive",
        "A single analytic strategy throughout — match, then Kaplan-Meier, then bootstrap "
        "intervals. No competing model specifications are presented from which this result "
        "could have been picked.",
        quotes=(
            "Cumulative incidence (risk) curves for the vaccination groups were estimated "
            "with the Kaplan–Meier estimator.",
            "Nonparametric bootstrapping with 500 samples was used to calculate "
            "percentile-based 95% confidence intervals for all estimates.",
        ),
    ),
    "6.4": Answer(
        "6.4", "N", "manuscript_positive",
        "Two subgroup analyses only, both named in the protocol table's statistical "
        "analysis row, and both reported in full.",
        quotes=(
            "Subgroup analyses by baseline age and race.",
            "We conducted subgroup analyses according to age (<70 or ≥70 years) and race "
            "(Black or White).",
        ),
    ),
}

FLAT = {q: a.response for q, a in ANSWERS.items()}

DOMAINS = [
    DomainOutcome(
        1, alg.domain1_variant_a(FLAT),
        support="Matching covers the real drivers of brand allocation and the remaining "
                "prespecified confounders are balanced after matching. The residual concern "
                "is the deliberate coarsening of the matching set from VA station to VISN, "
                "since brand availability is a station-level phenomenon — but the negative "
                "outcome controls were run after that coarsening and were reassuring.",
        direction_of_bias="No information or unpredictable",
    ),
    DomainOutcome(
        2, alg.domain2(FLAT),
        support="Point interventions distinguishable on day 0, with brand taken from "
                "administration-time records that the outcome cannot have influenced.",
    ),
    DomainOutcome(
        3, alg.domain3(FLAT),
        support="Follow-up begins at first dose with no immortal time, and all selection is "
                "on pre-baseline information. The large exclusion for unrecorded BMI and "
                "smoking status restricts the population rather than biasing the contrast.",
    ),
    DomainOutcome(
        4, alg.domain4(FLAT),
        support="Intervention, outcome and confounder data are complete within the analysed "
                "cohort; the shortfall in follow-up time is administrative censoring handled "
                "by the estimator.",
    ),
    DomainOutcome(
        5, alg.domain5(FLAT),
        support="Identical ascertainment in both arms through one national surveillance "
                "system, and a PCR-documented outcome that admits no assessor judgement, so "
                "the absence of blinding cannot operate.",
    ),
    DomainOutcome(
        6, alg.domain6(FLAT),
        support="No registered protocol, so prespecification is unverifiable — but there is "
                "no sign of selection from multiple outcomes, analyses or subgroups, which "
                "is what the algorithm weighs. A reviewer who treats the absence of "
                "registration as itself a concern should override upward and say so.",
    ),
]

assessment = Assessment(
    result_id="NEJMoa2115463 / alpha / documented-infection / RD",
    citation="Dickerman BA, Gerlovin H, Madenci AL, Kurgansky KE, Ferolito BR, Figueroa "
             "Muñiz MJ, Gagnon DR, Gaziano JM, Cho K, Casas JP, Hernán MA. Comparative "
             "Effectiveness of BNT162b2 and mRNA-1273 Vaccines in U.S. Veterans. "
             "N Engl J Med. 2022;386(2):105-115. doi:10.1056/NEJMoa2115463",
    result_assessed="24-week risk difference 1.23 excess events per 1000 persons "
                    "(95% CI 0.72 to 1.81) for BNT162b2 vs mRNA-1273; corresponding risk "
                    "ratio 1.27 (95% CI 1.15 to 1.42)",
    outcome="Documented SARS-CoV-2 infection over 24 weeks, alpha-variant-predominant period",
    result_location="Table 2, row 1 (documented infection), risk-difference column",
    per_protocol=False,
    domains=DOMAINS,
    answers=ANSWERS,
    prespecified_confounders=PRESPECIFIED_CONFOUNDERS,
    information_sources=["Journal article(s)", "Supplementary appendix"],
    target_trial={
        "Eligible participants": "Veterans aged >=18 between 4 Jan and 14 May 2021, no prior "
                                 "documented SARS-CoV-2 infection, no prior Covid-19 "
                                 "vaccination, known residential address outside long-term "
                                 "care, recorded smoking status and BMI in the previous year, "
                                 "VA users with no health-system contact in the previous 3 days",
        "Intervention strategy": "Receive BNT162b2 at baseline, second dose scheduled 21 days later",
        "Comparator strategy": "Receive mRNA-1273 at baseline, second dose scheduled 28 days later",
        "Estimand (C4)": "No censoring or follow-up partitioning at deviation, so C4 = No and "
                         "domain 1 variant A applies. Note the paper's own protocol table "
                         "labels the emulation the 'observational analogue of the per-protocol "
                         "effect'; with a point intervention and 98-99% second-dose adherence "
                         "the two estimands nearly coincide, but the ANALYSIS is intention-to-treat.",
    },
    model="claude-opus-5",
    direction_of_bias="Unpredictable",
    generated_at=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
)

assessment.bind_evidence(BUNDLE)   # raises if any quote fails to resolve

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dickerman_2022_robins.html"
    render_html.write(assessment, out)
    print(f"OVERALL: {assessment.overall.value}\n")
    for d in assessment.domains:
        trail = " -> ".join(f"{q}={r}" for q, r, _ in d.algorithm.path)
        print(f"  D{d.domain} {d.judgement.value:26s} {trail}")
    print(f"\nratification queue ({len(assessment.ratification_queue)}):")
    for item in assessment.ratification_queue:
        print(f"  - {item}")
    print(f"\nwrote {out}")
