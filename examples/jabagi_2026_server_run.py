"""End-to-end run of the MCP tool surface on a second real paper.

    Jabagi M-J, Bertrand M, Gabet A, et al. Maternal RSVpreF immunisation against
    infant RSV hospitalisation: nationwide population-based effectiveness and
    durability study. Lancet Reg Health Eur 2026;67:101756.

Unlike `dickerman_2022.py`, which builds an Assessment through the library
directly, this drives `server.py`'s tools in the order an MCP client would:
parse_document -> set_prespecified_confounders -> specify_result ->
assess_result/submit_answers per domain -> submit_answers(domain=0).

Result: SERIOUS, driven by domain 1. The path is worth reading — it does not go
through 1.1 (confounder coverage) but through 1.3 (post-intervention variables
controlled for), because gestational age at birth and birth weight are matched
and weighted on despite being realised after maternal vaccination. Domain 3 is
moderate on the exclusion of nirsevimab recipients, which is a post-baseline
event strongly associated with the intervention.

Run: python examples/jabagi_2026_server_run.py
"""
import json, sys

from robins_mcp import server as S

PUBS = "/Users/jddmacbook/Desktop/Testing Folder for AI/TARGET Checklist MCP/other pubs"
CITATION = (
    "Jabagi, M.-J., Bertrand, M., Gabet, A., Tréluyer, L., Kolla, E., Rachas, A., "
    "Olié, V., & Zureik, M. (2026). Maternal RSVpreF immunisation against infant RSV "
    "hospitalisation: nationwide population-based effectiveness and durability study. "
    "The Lancet Regional Health - Europe, 67, 101756. "
    "https://doi.org/10.1016/j.lanepe.2026.101756"
)

# --- P1: important confounders of maternal RSVpreF vaccination -> infant RSV
# hospitalisation. Proposed from domain knowledge of what drives both uptake of a
# newly introduced maternal vaccine and infant RSV hospitalisation risk. NOT ratified.
P1 = [
    "Calendar time of birth and intensity of RSV circulation at that time",
    "Gestational age at birth",
    "Birth weight",
    "Infant sex",
    "Congenital anomalies and neonatal vulnerability markers",
    "Maternal age and parity",
    "Maternal pre-existing and gestational comorbidities",
    "Maternal smoking and alcohol use",
    "Area-level socioeconomic deprivation",
    "Health-care access and engagement (insurance status, antenatal contacts, "
    "geographic accessibility of care)",
    "Maternal uptake of other recommended antenatal vaccines, as a marker of "
    "vaccine acceptance",
    "Household composition: older siblings and daycare attendance",
    "Breastfeeding",
    "Household tobacco smoke exposure",
    "Receipt of infant nirsevimab or other RSV immunoprophylaxis",
]

TARGET_TRIAL = {
    "Eligible participants (C1)":
        "Infants entering their first RSV season whose mothers were eligible for "
        "RSVpreF vaccination in pregnancy. Emulated as live births recorded in the "
        "SNDS 1 Sept-31 Dec 2024 in mainland France, public hospitals, mothers aged "
        "15-50 and linkable to the infant.",
    "Intervention strategy (C2)":
        "Maternal RSVpreF vaccination during pregnancy, ascertained from community "
        "pharmacy dispensing (ATC J07BX05).",
    "Comparator strategy (C3)":
        "No maternal RSV immunisation during pregnancy, and no infant RSV "
        "immunoprophylaxis at any point in follow-up.",
    "Estimand (C4)":
        "The appendix protocol table names the causal contrast as the "
        "intention-to-treat effect, and the analysis matches that label: exposure is "
        "a point intervention completed before time zero, and no censoring or "
        "follow-up partitioning at deviation occurs. C4 = No; domain 1 variant A.",
}

RESULT_ID = "lanepe-101756 / RSV-LRTI hospitalisation / weighted HR"

# --------------------------------------------------------------------------- #
ANSWERS = {
 1: [
  dict(question="1.1", response="WN", evidence_mode="reviewer_prior",
       prior_ref="P1 items 12, 13, 14 — older siblings and daycare attendance, "
                 "breastfeeding, household tobacco smoke; and the residual of item 10-11, "
                 "health-care engagement and vaccine acceptance, which is only proxied",
       rationale=(
        "Most of the prespecified list is controlled, and controlled well: exact matching "
        "on date of birth handles the strongest confounder here — calendar time and RSV "
        "circulation — and the propensity score covers maternal age, parity, comorbidity, "
        "smoking and alcohol proxies, deprivation, health-care access and antenatal "
        "vaccine uptake. What is not measured at all in the SNDS is the household: older "
        "siblings beyond parity, daycare attendance, breastfeeding, and household smoke "
        "exposure. Those are among the strongest determinants of infant RSV "
        "hospitalisation and are plausibly associated with maternal vaccine uptake. The "
        "authors say so themselves. Graded WN rather than SN because the residual "
        "directions do not align: unmeasured breastfeeding and smaller household size "
        "would exaggerate effectiveness, while the greater care-seeking of vaccinating "
        "families would raise their infants' probability of being admitted and attenuate "
        "it. With those pulling opposite ways, and the Tdap-uptake gap showing the "
        "care-seeking gradient is real and large, the net bias is not predictably "
        "substantial — but it is not negligible either."),
       quotes=[
        "language, ethnicity, or vaccine acceptance, could not be entirely excluded",
        "substantially more likely to have received other recommended vaccines during "
        "pregnancy such as the Tdap vaccine",
       ]),
  dict(question="1.3", response="PY", evidence_mode="manuscript_positive",
       rationale=(
        "Gestational age at birth and birth weight are realised after maternal "
        "vaccination, and both are matched or weighted on. Whether the vaccine affects "
        "gestational duration is precisely the open safety question that led the French "
        "campaign to confine administration to 32-36 weeks, so these are not safely "
        "pre-intervention covariates. Neonatal complications recorded during the birth "
        "stay sit at or after time zero as well. Answered PY rather than Y because an "
        "effect of RSVpreF on gestational duration is plausible and monitored rather "
        "than established."),
       quotes=[
        "immunised with RSVpreF was matched to one unimmunised infant on exact date of "
        "birth, gestational age (completed weeks), sex, and deprivation status",
        "Infant characteristics comprised sex, gestational age, birth weight, month of "
        "birth, congenital anomalies, neonatal complications",
        "recommended for administration between 32 and 36 weeks of gestation",
       ]),
  dict(question="1.4", response="N", evidence_mode="manuscript_absent",
       search_cue="negative_control",
       rationale=(
        "No negative outcome control, falsification endpoint, E-value or quantitative "
        "bias analysis appears anywhere in the article or appendix. The sensitivity "
        "analyses vary the analytic method — weight trimming, regression adjustment "
        "without weighting, one match per control — but none of them probes residual "
        "confounding, so nothing here suggests serious uncontrolled confounding and "
        "nothing rules it out either.")),
  dict(question="1.2", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Every controlled factor is an administrative field recorded prospectively for "
        "reimbursement: gestational age in completed weeks, sex, ATC-coded dispensings, "
        "ICD-10 diagnoses, and an area-level deprivation index computed from census "
        "data. These are not derived or self-reported."),
       quotes=[
        "1:1 exact matching on date of birth, gestational age, sex, and deprivation "
        "status, followed by inverse probability of treatment weighting based on "
        "baseline covariates",
        "The SNDS includes individual-level information on outpatient medical care, drug "
        "dispensations reimbursed in community pharmacies, hospital admissions",
       ]),
 ],
 2: [
  dict(question="2.1", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Maternal vaccination is complete before the infant exists as a unit of "
        "follow-up, so the two strategies are fully distinguishable at time zero. There "
        "is no period during which an infant's group membership is undetermined."),
       quotes=["aligning eligibility, exposure assignment, and initiation of follow-up at birth"]),
  dict(question="2.4", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "Exposure is read off pharmacy dispensing records written during pregnancy, "
        "before the infant was born and therefore before any outcome could occur. The "
        "outcome cannot have influenced the classification."),
       quotes=[
        "All community pharmacy dispensations of the RSVpreF vaccine were identified for "
        "mothers of infants born during the study period based on the specific ATC code "
        "J07BX05",
       ]),
  dict(question="2.5", response="PN", evidence_mode="manuscript_positive",
       rationale=(
        "Two routes to error remain and both are non-differential. A dispensed vaccine "
        "that was never administered would classify an unexposed infant as exposed, and "
        "any RSVpreF given outside the community pharmacy circuit would be missed "
        "entirely. The authors handle the first by taking the date of a recorded "
        "pharmacist administration where present, and RSVpreF was reimbursed through "
        "community pharmacies as the standard route, so both should be uncommon. Both "
        "would bias toward the null rather than create the observed effect."),
       quotes=[
        "The dispensing date was considered the date of vaccination when a "
        "pharmacist-administered vaccination was recorded",
       ]),
 ],
 3: [
  dict(question="3.1", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Time zero is birth for both groups and exposure is fixed before it, so "
        "eligibility, assignment and the start of follow-up coincide and no immortal "
        "time is created. Birth is also the earliest point at which the infant is at "
        "risk of the outcome, so no earlier start is available."),
       quotes=["Follow-up began at birth (time zero defined as the date of birth)"]),
  dict(question="3.2", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "No blanking or landmark window. Follow-up runs from day 0 to the outcome, "
        "death or 28 Feb 2025, and the 0-14 day interval is reported as its own "
        "stratum — the period in which effectiveness was highest."),
       quotes=[
        "continued until the occurrence of the study outcome, death from any cause, the "
        "end of the study fixed at February 28, 2025, whichever came first",
       ]),
  dict(question="3.3", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Two exclusions are made on information that only exists after time zero. "
        "Infants who received nirsevimab at any point in follow-up are excluded — "
        "nirsevimab is given after birth, mostly at maternity discharge but also in "
        "outpatient care weeks later. And infants born within 14 days of maternal "
        "vaccination are excluded, which is a criterion only the vaccinated arm can "
        "meet. Together these remove 147,127 of 195,340 live births."),
       quotes=[
        "Infants who received nirsevimab or both strategies were excluded to isolate the "
        "effectiveness of maternal RSVpreF vaccination compared with no RSV "
        "immunoprophylaxis",
        "Infants were excluded if their birth occurred within 14 days of maternal "
        "vaccination",
       ]),
  dict(question="3.4", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Strongly associated, and by construction. Nirsevimab and maternal RSVpreF were "
        "the two alternatives on offer in the same season and function as substitutes, "
        "so an unvaccinated mother's infant is far more likely to have received "
        "nirsevimab and so to be excluded. The 14-day rule applies to the vaccinated arm "
        "alone. The surviving comparator group is therefore families who declined every "
        "available form of RSV prophylaxis."),
       quotes=[
        "These strategies were complementary approaches targeting different time points, "
        "during pregnancy for maternal vaccination and after birth for nirsevimab",
        "After exclusion of 147,127 infants who were immunised with nirsevimab or "
        "palivizumab, born in private hospitals or within 14 days of maternal vaccination",
       ]),
  dict(question="3.5", response="PN", evidence_mode="manuscript_positive",
       rationale=(
        "Nirsevimab was given to infants in maternity wards before discharge or in "
        "outpatient care at the start of the season, in both cases as prophylaxis "
        "against an outcome that had not yet occurred. An RSV hospitalisation could not "
        "ordinarily cause the exclusion, since an infant already hospitalised for RSV "
        "has already had the outcome. Answered PN rather than N because late outpatient "
        "administration leaves a narrow window in which the two could interact."),
       quotes=[
        "Nirsevimab was recommended for all infants during their first RSV season in "
        "outpatient settings and in maternity hospitals before discharge starting "
        "September 2024",
       ]),
 ],
 4: [
  dict(question="4.1", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Intervention status is derived from a reimbursement database that captures "
        "essentially every community dispensing nationally; there is no missingness "
        "mechanism for it. Infants whose gestational age was missing or whose birth "
        "record was inconsistent were removed at eligibility rather than carried with "
        "gaps."),
       quotes=[
        "Infants were excluded if gestational age was missing or birth information was "
        "inconsistent",
       ]),
  dict(question="4.2", response="Y", evidence_mode="manuscript_positive",
       rationale=(
        "Outcome data come from the national hospital discharge database, which records "
        "every inpatient stay in France, and follow-up ends at a fixed calendar date "
        "rather than at loss to follow-up. Emigration is the only route out and is "
        "negligible over a median 86 days."),
       quotes=[
        "Hospitalisation data were extracted from the French National Hospital Discharge "
        "Database (PMSI), which records diagnoses and procedures coded using the "
        "International Classification of Diseases, 10th Revision (ICD-10)",
       ]),
  dict(question="4.3", response="Y", evidence_mode="reviewer_prior",
       prior_ref="P1 items 1-11 — the prespecified factors that the SNDS does measure",
       rationale=(
        "Among the prespecified factors the database actually records, missingness is "
        "trivial: deprivation index is missing for 24 of 31,356 infants in the matched "
        "cohort, 0.1%, and gestational age missingness was an exclusion criterion. The "
        "household and feeding factors in P1 are absent from the data source altogether, "
        "which is unmeasured confounding rather than missing data, and is scored in "
        "domain 1 at question 1.1 rather than here.")),
 ],
 5: [
  dict(question="5.1", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "One national database, one ICD-10 code set, applied identically to both groups. "
        "The method of ascertainment cannot differ between arms because it is the same "
        "extraction."),
       quotes=[
        "Hospitalisations were classified as RSV-related when one of these codes was "
        "recorded as the primary or related discharge diagnosis",
       ]),
  dict(question="5.2", response="Y", evidence_mode="manuscript_absent",
       search_cue="blinding",
       rationale=(
        "Nothing in the article or appendix describes blinding, masking or independent "
        "adjudication — the search returns nothing at all. The outcome is a discharge "
        "code assigned by treating clinicians who were not blinded to anything, so "
        "awareness has to be assumed rather than excluded.")),
  dict(question="5.3", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "The endpoint admits almost no assessor discretion: it requires an inpatient "
        "admission and one of three specific RSV codes. A clinician coding an infant's "
        "bronchiolitis admission would not ordinarily know whether the mother received "
        "RSVpreF in pregnancy, and the coding decision turns on the virological and "
        "clinical picture in front of them."),
       quotes=[
        "including acute RSV bronchiolitis (J210), RSV pneumonia (J121), and acute RSV "
        "bronchitis (J205)",
       ]),
 ],
 6: [
  dict(question="6.1", response="NI", evidence_mode="manuscript_positive",
       rationale=(
        "The study is registered, which is more than most, but the register entry was "
        "not retrieved and is not in the assessed bundle — so there is no plan to "
        "compare the reported result against. The authors describe the durability and "
        "subgroup analyses as predefined, but that is an assertion inside the report "
        "rather than a document that can be checked. NI rather than N: the information "
        "exists, we did not obtain it."),
       quotes=[
        "This study was approved by the scientific committee of EPI-PHARE and registered "
        "on the EPI-PHARE study register (reference T-2025-08-637)",
       ]),
  dict(question="6.2", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "One primary outcome, named as such, with the severity outcomes reported "
        "alongside it rather than in place of it. Every outcome measurement described in "
        "the methods appears in the results."),
       quotes=[
        "Other outcomes included hospitalisation for severe RSV-LRTI, defined as RSV-LRTI "
        "requiring admission to a paediatric intensive care unit",
       ]),
  dict(question="6.3", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "Three sensitivity analyses are prespecified in the methods and all three are "
        "reported, with results consistent with the primary analysis. Crude and weighted "
        "hazard ratios are both shown throughout, so the analytic choices are visible "
        "rather than selected between."),
       quotes=[
        "Sensitivity analyses included trimming of extreme propensity score weights, "
        "multivariable regression adjustment without weighting, and restricting each "
        "unimmunised infant to a single match",
        "Sensitivity analyses yielded similar results",
       ]),
  dict(question="6.4", response="N", evidence_mode="manuscript_positive",
       rationale=(
        "The subgroups are listed in the methods before any of them is reported, and the "
        "full set appears in the forest plot including the strata that show no benefit — "
        "beyond 75 days of life the estimate crosses one and is reported anyway. That is "
        "the opposite of selection from multiples."),
       quotes=[
        "Other predefined subgroup analyses were conducted according to infant sex, "
        "gestational age at birth",
       ]),
 ],
}

SUPPORT = {
 1: ("Confounding control here is unusually strong on the axis that matters most — exact "
     "matching on date of birth removes the confounding by RSV circulation and campaign "
     "roll-out that has dogged every other RSVpreF effectiveness study — and the "
     "propensity score is broad. The domain nonetheless lands at serious, and it does so "
     "on question 1.3 rather than 1.1: gestational age at birth and birth weight are "
     "matched and weighted on despite being realised after the vaccine was given, and "
     "whether RSVpreF affects gestational duration is the very question that confined the "
     "French campaign to 32-36 weeks. With no negative control or bias analysis run, "
     "nothing bounds what that adjustment did. A reviewer who judges gestational age at "
     "birth to be unaffected by maternal vaccination should answer 1.3 = N, which sends "
     "this domain to moderate, and should record that judgement rather than leave it "
     "implicit."),
 2: ("Exposure is a point intervention completed before follow-up begins and recorded in a "
     "reimbursement database at the moment it happened, so classification is close to "
     "ideal. The residual risk is under-capture of vaccinations given outside the "
     "community pharmacy circuit, which would dilute rather than manufacture the effect."),
 3: ("Follow-up starts cleanly at birth with no immortal time, and the paper is explicit "
     "and correct about that. The problem is elsewhere: the cohort is defined by excluding "
     "everyone who took the competing prophylaxis, and nirsevimab is administered after "
     "time zero. Because nirsevimab and maternal vaccination are substitutes, that "
     "exclusion falls disproportionately on the unvaccinated, and what remains as the "
     "comparator is the subset of families who declined every form of RSV protection on "
     "offer. Three quarters of the eligible birth cohort is removed this way. The "
     "algorithm does not escalate, because the selection variable is not influenced by the "
     "outcome, but the generalisability cost is real and the paper acknowledges only part "
     "of it."),
 4: ("A national reimbursement database with a fixed administrative end of follow-up "
     "leaves essentially nothing missing: intervention and outcome are captured by "
     "construction, and the one confounder with any missingness, area deprivation, is "
     "missing for 0.1% of the matched cohort. The factors that are absent are absent from "
     "the data source entirely, which is a confounding problem and is scored as one."),
 5: ("A hard endpoint — inpatient admission with a specific RSV code — ascertained "
     "identically in both arms through one national system. Nobody was blinded, but there "
     "is no assessor judgement for the lack of blinding to operate on. The acknowledged "
     "under-ascertainment from imperfect RSV testing sensitivity applies equally to both "
     "groups."),
 6: ("The study is registered and every analysis described in the methods is reported, "
     "including the strata that show no benefit. What is missing is the register record "
     "itself, which was not retrieved, so 6.1 is answered NI on information we chose not "
     "to obtain rather than on information that does not exist. Retrieving T-2025-08-637 "
     "would settle it and could move this domain to low on a firmer basis than the "
     "algorithm's current route."),
}

# --------------------------------------------------------------------------- #
def main():
    bundle = S.parse_document(
        document=f"{PUBS}/TTE example 1.pdf",
        manuscript_id="jabagi-2026-rsvpref",
        supplements=[f"{PUBS}/TTE example 1 SUPPLEMENT.docx"],
        citation=CITATION,
    )
    sha = bundle["text_sha256"]
    print(f"parsed: {bundle['n_pages']}pp + supplement, sha {sha[:12]}, "
          f"{sum(s['chars'] for s in bundle['sections'])} chars")

    S.set_prespecified_confounders(P1, review_id="rsvpref-maternal")

    spec = S.specify_result(
        result_id=RESULT_ID,
        text_sha256=sha,
        result_assessed=(
            "Weighted hazard ratio 0.50 (95% CI 0.45-0.55) for RSV-LRTI hospitalisation, "
            "RSVpreF-exposed vs unimmunised, over the full first RSV season; vaccine "
            "effectiveness 50% (95% CI 45-55)"),
        outcome=("Hospitalisation for RSV-associated lower respiratory tract infection "
                 "during the infant's first RSV season, ICD-10 J210/J121/J205 as primary "
                 "or related discharge diagnosis"),
        accounts_for_deviations="no_itt",
        result_location="Abstract Findings; Results paragraph 3; Fig. 2 (wHR row 1)",
        citation=CITATION,
        target_trial=TARGET_TRIAL,
        information_sources=["Journal article(s)", "Supplementary appendix"],
        review_id="rsvpref-maternal",
        model="claude-opus-5",
        b1="Y", b3="N",
    )
    print(f"C4 -> domain 1 variant {spec['domain1_variant']}")
    for w in spec["warnings"]:
        print(f"  warning: {w}")

    for domain in range(1, 7):
        scaffold = S.assess_result(RESULT_ID, domain)
        cues = ", ".join(f"{c['cue']}={c['n_hits']}" for c in scaffold["cues"])
        print(f"\n--- domain {domain}: {scaffold['domain_label']}")
        print(f"    in play: {[q['id'] for q in scaffold['questions']]}   cues: {cues}")
        out = S.submit_answers(RESULT_ID, domain, ANSWERS[domain],
                               support=SUPPORT[domain])
        if out["status"] != "domain_scored":
            print(f"    INCOMPLETE — needs {out['needs_answer']} at {out['needs_answer_at_node']}")
            sys.exit(1)
        trail = " -> ".join(f"{p['question']}={p['response']}" for p in out["path"])
        print(f"    {out['judgement_label']}")
        print(f"    path: {trail}")
        print(f"    not reached: {out['not_reached'] or '(none)'}")
        for note in out["notes"]:
            print(f"    note: {note}")

    final = S.submit_answers(RESULT_ID, 0)
    print("\n" + "=" * 72)
    print(f"OVERALL: {final['overall_label']}")
    for note in final["overall_algorithm"]["notes"]:
        print(f"  {note}")
    print(f"\nevidence: {json.dumps(final['evidence'])}")
    print(f"\nratification queue ({len(final['ratification_queue'])}):")
    for item in final["ratification_queue"]:
        print(f"  - {item}")
    print(f"\nprovenance: {final['provenance']['algorithm_fingerprint']} / "
          f"text {final['provenance']['text_sha256'][:12]} / "
          f"{final['provenance']['extractor_version']}")
    out_path = "/Users/jddmacbook/Desktop/Testing Folder for AI/Robins-I 2025/robins-mcp/jabagi_2026_robins.html"
    open(out_path, "w").write(final["report"]["html"])
    print(f"\nwrote {out_path} ({len(final['report']['html'])} bytes)")


if __name__ == "__main__":
    main()
