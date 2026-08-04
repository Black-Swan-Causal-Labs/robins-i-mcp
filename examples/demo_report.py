"""Render a sample ROBINS-I report.

The study below is SYNTHETIC — invented to exercise the renderer. It is not an
assessment of any real publication. It deliberately includes one algorithm
override, one unratified reviewer-prior answer, and one absence-based answer so
that all three flagging paths appear in the output.

    python examples/demo_report.py [outfile.html]
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robins_i_mcp import algorithms as alg, render_html
from robins_i_mcp.algorithms import Judgement as J
from robins_i_mcp.report import Answer, Assessment, DomainOutcome

ANSWERS = {
    # domain 1 (variant A — intention-to-treat)
    "1.1": Answer("1.1", "WN", "reviewer_prior",
                  "Frailty and baseline renal function were adjusted for. Socioeconomic "
                  "status was not, but is strongly correlated with the deprivation index "
                  "that was included, so residual confounding is unlikely to be material.",
                  prior_ref="P1 item 6 — socioeconomic status"),
    "1.2": Answer("1.2", "Y", "manuscript_positive",
                  "Confounders drawn from validated primary-care coding algorithms with "
                  "published positive predictive values.",
                  quotes=("Comorbidities were ascertained using previously validated Read "
                          "code lists (PPV 0.91-0.97).",)),
    "1.3": Answer("1.3", "N", "manuscript_positive",
                  "All covariates fixed at the index date; no post-baseline adjustment.",
                  quotes=("All covariates were measured in the 365 days prior to the index "
                          "date.",)),
    "1.4": Answer("1.4", "N", "manuscript_absent",
                  "No negative control analysis reported, and nothing else in the paper "
                  "points to material residual confounding.",
                  search_record="Methods, Results, Supplementary Appendix S3-S5; terms: "
                                "negative control, falsification, E-value, bias analysis"),
    # domain 2
    "2.1": Answer("2.1", "Y", "manuscript_positive",
                  "New-user design; both strategies identifiable from the index prescription.",
                  quotes=("Patients were classified by the first dispensed prescription on "
                          "the index date.",)),
    "2.4": Answer("2.4", "N", "manuscript_positive",
                  "Exposure taken from dispensing records written before follow-up began.",
                  quotes=("Exposure was derived from pharmacy dispensing records.",)),
    "2.5": Answer("2.5", "PN", "manuscript_positive",
                  "Dispensing records are a good but imperfect proxy for ingestion; any "
                  "resulting misclassification is non-differential.",
                  quotes=("Dispensing does not guarantee ingestion, a limitation shared by "
                          "all claims-based studies.",)),
    # domain 3
    "3.1": Answer("3.1", "Y", "manuscript_positive",
                  "Follow-up starts at the index prescription for both groups.",
                  quotes=("Follow-up began on the date of the first dispensed prescription.",)),
    "3.2": Answer("3.2", "N", "manuscript_positive",
                  "No blanking or run-in period; events counted from day 1.",
                  quotes=("Outcome events were counted from day 1 of follow-up.",)),
    "3.3": Answer("3.3", "N", "manuscript_positive",
                  "Cohort entry determined entirely by pre-index criteria.",
                  quotes=("Eligibility was assessed using data recorded before the index date.",)),
    # domain 4
    "4.1": Answer("4.1", "Y", "manuscript_positive", "Exposure complete by construction.",
                  quotes=("Exposure status was available for all included patients.",)),
    "4.2": Answer("4.2", "Y", "manuscript_positive", "Outcome captured via linked mortality data.",
                  quotes=("Mortality was ascertained through national death registration.",)),
    "4.3": Answer("4.3", "N", "manuscript_positive",
                  "Body-mass index missing for 22%; smoking status for 14%.",
                  quotes=("BMI was missing for 22.4% and smoking status for 13.8% of the "
                          "cohort.",)),
    "4.4": Answer("4.4", "N", "manuscript_positive", "Multiple imputation, not complete case.",
                  quotes=("Missing covariate data were handled using multiple imputation by "
                          "chained equations (20 imputations).",)),
    "4.7": Answer("4.7", "Y", "manuscript_positive", "MICE, 20 imputations.",
                  quotes=("multiple imputation by chained equations (20 imputations)",)),
    "4.8": Answer("4.8", "Y", "manuscript_positive",
                  "Missingness plausibly explained by recorded characteristics; no reason to "
                  "suspect MNAR.",
                  quotes=("Missingness was associated with age and practice, both included "
                          "in the imputation model.",)),
    "4.9": Answer("4.9", "WN", "manuscript_positive",
                  "The imputation model omits the outcome, which biases imputed values toward "
                  "the null, though the affected covariates are secondary.",
                  quotes=("The imputation model included all baseline covariates.",)),
    "4.11": Answer("4.11", "Y", "manuscript_positive",
                   "Complete-case sensitivity analysis reported, materially unchanged.",
                   quotes=("A complete-case analysis yielded a hazard ratio of 0.86 (95% CI "
                           "0.79-0.94), consistent with the primary analysis.",)),
    # domain 5
    "5.1": Answer("5.1", "N", "manuscript_positive",
                  "All-cause mortality from a single national registry, identical for both groups.",
                  quotes=("Mortality was ascertained through national death registration.",)),
    "5.2": Answer("5.2", "Y", "manuscript_absent",
                  "No blinding described; registry linkage is unblinded by construction.",
                  search_record="Methods and Supplementary Appendix S1; terms: blind, masked, "
                                "independent adjudication"),
    "5.3": Answer("5.3", "N", "manuscript_positive",
                  "All-cause mortality admits no assessor judgement.",
                  quotes=("The primary outcome was all-cause mortality.",)),
    # domain 6
    "6.1": Answer("6.1", "NI", "manuscript_absent",
                  "No protocol or analysis plan registered or referenced.",
                  search_record="Full text, Data Availability, Supplementary Appendix; terms: "
                                "protocol, prespecified, analysis plan, EUPAS, registration"),
    "6.2": Answer("6.2", "N", "manuscript_positive", "One outcome definition throughout.",
                  quotes=("The primary outcome was all-cause mortality.",)),
    "6.3": Answer("6.3", "Y", "manuscript_positive",
                  "Four model specifications are reported in the appendix with no statement "
                  "of which was prespecified as primary.",
                  quotes=("Supplementary Tables S6-S9 present the estimate under four "
                          "alternative adjustment sets.",)),
    "6.4": Answer("6.4", "N", "manuscript_positive",
                  "Two subgroups reported, both stated as planned.",
                  quotes=("Prespecified subgroup analyses by age and sex are reported in "
                          "Table 3.",)),
}

FLAT = {q: a.response for q, a in ANSWERS.items()}

DOMAINS = [
    DomainOutcome(
        1, alg.domain1_variant_a(FLAT),
        support="Most important confounders controlled using validated measures with no "
                "over-adjustment, but socioeconomic status was not adjusted for directly.",
        direction_of_bias="No information or unpredictable",
    ),
    DomainOutcome(
        2, alg.domain2(FLAT),
        support="New-user design with exposure taken from pre-follow-up dispensing records; "
                "residual misclassification is non-differential.",
    ),
    DomainOutcome(
        3, alg.domain3(FLAT),
        support="Follow-up begins at treatment initiation with no immortal time and no "
                "post-baseline selection.",
    ),
    DomainOutcome(
        4, alg.domain4(FLAT),
        support="Covariate data incomplete; imputation is broadly appropriate but omits the "
                "outcome from the imputation model. A complete-case sensitivity analysis "
                "supports the primary result.",
    ),
    DomainOutcome(
        5, alg.domain5(FLAT),
        support="Objective registry-ascertained outcome, identically captured in both groups; "
                "lack of blinding cannot influence it.",
    ),
    DomainOutcome(
        6, alg.domain6(FLAT),
        # demonstrates an override: algorithm says serious, assessor argues moderate
        final=J.MODERATE,
        override_justification="The algorithm reaches serious on a single Y to 6.3. The four "
                              "appendix specifications are presented as robustness checks "
                              "around one stated primary analysis and agree closely with it, "
                              "and there is no sign of outcome or subgroup selection. The "
                              "concern here is that prespecification is unverifiable, not that "
                              "selective reporting is demonstrated.",
        support="No registered protocol, so prespecification cannot be verified; multiple model "
                "specifications reported without designation. Downgraded from the algorithm "
                "default — see override.",
    ),
]

assessment = Assessment(
    result_id="SYNTHETIC-DEMO-01",
    citation="Example A, Example B, Example C. A synthetic cohort study of drug A versus "
             "drug B and all-cause mortality. Journal of Nonexistent Epidemiology. "
             "2026;1(1):1-12. [SYNTHETIC EXAMPLE — not a real publication]",
    result_assessed="Adjusted hazard ratio 0.88 (95% CI 0.81 to 0.96), drug A vs drug B",
    outcome="All-cause mortality within 5 years of treatment initiation",
    result_location="Table 2, primary analysis, row 1",
    per_protocol=False,
    domains=DOMAINS,
    answers=ANSWERS,
    prespecified_confounders=[
        "Age", "Sex", "Baseline renal function", "Frailty index",
        "Cardiovascular comorbidity", "Socioeconomic status",
        "Concomitant antihypertensive use", "Prior hospitalization",
        "Smoking status", "Body-mass index",
    ],
    information_sources=["Journal article(s)", "Supplementary appendix"],
    target_trial={
        "eligibility": "Adults initiating drug A or drug B with no prior use of either",
        "intervention": "Initiate drug A",
        "comparator": "Initiate drug B",
    },
    model="claude-opus-5",
    text_sha256="0" * 64,
    direction_of_bias="Unpredictable",
    generated_at=datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "robins_demo_report.html"
    render_html.write(assessment, out)
    print(f"overall: {assessment.overall.value}")
    for d in assessment.domains:
        flag = "  <- OVERRIDDEN" if d.overridden else ""
        print(f"  domain {d.domain}: {d.algorithm.judgement.value:24s}"
              f" final={d.judgement.value}{flag}")
    print(f"ratification queue: {len(assessment.ratification_queue)}")
    for item in assessment.ratification_queue:
        print(f"  - {item}")
    print(f"\nwrote {out}")
