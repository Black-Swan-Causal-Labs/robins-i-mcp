"""How a review of many studies is actually assembled.

Each ROBINS-I assessment costs a session: the model reads one paper and answers
signalling questions against it. A review of 200 studies is 200 runs, and this
server keeps NO state between them. So the workflow is not "run everything in
one place" — it is:

    session 1..N   assess one result, save submit_answers(domain=0)['record']
    later          load the saved records, export once

This script does both halves, with two real papers assessed independently and
then combined *from files on disk* — never from server memory. That is the part
worth seeing: the aggregation step touches no bundles, no answers, no quotes,
and would work just as well run by a different agent on a different machine.

Run: python examples/review_from_records.py
"""

import json
import tempfile
from pathlib import Path

from robins_mcp import review, server as S

import dickerman_2022 as D
import jabagi_2026_server_run as J

from _papers import PAPERS as PUBS, require
require("Dickerman 2022.pdf", "Dickerman 2022 SUPPLEMENT.pdf",
        "TTE example 1.pdf", "TTE example 1 SUPPLEMENT.docx")

REVIEW = "rsv-and-covid-vaccine-effectiveness"
RECORDS = Path(tempfile.mkdtemp(prefix="robins-records-"))


def _answer_rows(answers, domain):
    """The example answer sets are Answer objects; over the wire they are dicts."""
    rows = []
    for question, a in answers.items():
        if int(question.split(".")[0]) != domain:
            continue
        row = {"question": question, "response": a.response,
               "evidence_mode": a.evidence_mode, "rationale": a.rationale,
               "quotes": list(a.quotes)}
        if a.prior_ref:
            row["prior_ref"] = a.prior_ref
        if a.evidence_mode == "manuscript_absent":
            row["search_terms"] = list(a.search_record.terms)
        rows.append(row)
    return rows


def assess_dickerman() -> dict:
    """One session's worth of work. Returns the record it would have saved."""
    bundle = S.parse_document(
        str(PUBS / "Dickerman 2022.pdf"), manuscript_id="NEJMoa2115463",
        supplements=[str(PUBS / "Dickerman 2022 SUPPLEMENT.pdf")],
        citation="Dickerman BA, et al. NEJM 2022;386:105-115.")
    rid = "Dickerman 2022 / documented infection / RD"
    S.specify_result(
        result_id=rid, text_sha256=bundle["text_sha256"],
        result_assessed="24-week risk difference 1.23 per 1000 (95% CI 0.72-1.81)",
        outcome="Documented SARS-CoV-2 infection, alpha period",
        accounts_for_deviations="no_itt", review_id=REVIEW, model="claude-opus-5",
        citation="Dickerman BA, et al. NEJM 2022;386:105-115.", b1="Y", b3="N")
    for domain in range(1, 7):
        S.submit_answers(rid, domain, _answer_rows(D.ANSWERS, domain),
                         support=f"domain {domain}")
    return S.submit_answers(rid, 0, render=False)["record"]


def assess_jabagi() -> dict:
    """A second, entirely independent session."""
    bundle = S.parse_document(
        str(PUBS / "TTE example 1.pdf"), manuscript_id="jabagi-2026-rsvpref",
        supplements=[str(PUBS / "TTE example 1 SUPPLEMENT.docx")], citation=J.CITATION)
    rid = "Jabagi 2026 / RSV-LRTI hospitalisation / wHR"
    S.specify_result(
        result_id=rid, text_sha256=bundle["text_sha256"],
        result_assessed="Weighted HR 0.50 (95% CI 0.45-0.55)",
        outcome="RSV-LRTI hospitalisation, first RSV season",
        accounts_for_deviations="no_itt", review_id=REVIEW, model="claude-opus-5",
        citation=J.CITATION, target_trial=J.TARGET_TRIAL, b1="Y", b3="N")
    for domain in range(1, 7):
        S.submit_answers(rid, domain, J.ANSWERS[domain], support=J.SUPPORT[domain])
    return S.submit_answers(rid, 0, render=False)["record"]


def main() -> None:
    # ---- the N sessions, each ending by saving one small file ---------------
    S.set_prespecified_confounders(J.P1, review_id=REVIEW)
    for record in (assess_dickerman(), assess_jabagi()):
        path = RECORDS / (record["result_id"].replace("/", "_").strip() + ".json")
        path.write_text(json.dumps(record, indent=1))
        print(f"saved {path.name}  ({path.stat().st_size} bytes)")

    # ---- much later, elsewhere: load the files and export -------------------
    saved = [json.loads(p.read_text()) for p in sorted(RECORDS.glob("*.json"))]
    print(f"\nloaded {len(saved)} record(s) from disk — no server state involved")

    export = review.robvis_csv(review.as_records(saved), labels={
        "Dickerman 2022 / documented infection / RD": "Dickerman 2022",
        "Jabagi 2026 / RSV-LRTI hospitalisation / wHR": "Jabagi 2026",
    })
    print(f"\n--- upload to robvis with tool = '{export['robvis_tool']}' ---")
    print(export["csv"])
    print("summary:", json.dumps(export["summary"], indent=1))
    print("\nlosses to read before publishing:")
    for loss in export["losses"]:
        print(f"  - {loss}")
    print(f"\nrecords kept in {RECORDS}")


if __name__ == "__main__":
    main()
