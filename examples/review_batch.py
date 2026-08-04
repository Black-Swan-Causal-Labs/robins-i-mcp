"""Batch: several results under one review_id, then the review figure + robvis.

Demonstrates the review-level path. A review is a SERIES of ROBINS-I
assessments — one per numerical result, sharing a review_id and therefore a
single agreed P1. Here three results (two real, one illustrative variant-B row)
come from one paper, which is the case the figure has to be honest about: three
rows, one document, not three studies' worth of evidence.

Run: python examples/review_batch.py
"""
import json

from robins_mcp import server as S
import jabagi_2026_server_run as J   # reuse its answers/P1/target trial

REVIEW = "rsv-prophylaxis-infants"
PUBS = "/Users/jddmacbook/Desktop/Testing Folder for AI/TARGET Checklist MCP/other pubs"

b = S.parse_document(
    document=f"{PUBS}/TTE example 1.pdf", manuscript_id="jabagi-2026-rsvpref",
    supplements=[f"{PUBS}/TTE example 1 SUPPLEMENT.docx"], citation=J.CITATION)
sha = b["text_sha256"]
S.set_prespecified_confounders(J.P1, review_id=REVIEW)

# Result 1 — the primary, as before (C4 = no_itt -> variant A)
R1 = "lanepe-101756 / RSV-LRTI hospitalisation / wHR"
S.specify_result(result_id=R1, text_sha256=sha,
    result_assessed="Weighted HR 0.50 (95% CI 0.45-0.55), full first RSV season",
    outcome="RSV-LRTI hospitalisation", accounts_for_deviations="no_itt",
    citation=J.CITATION, target_trial=J.TARGET_TRIAL, review_id=REVIEW,
    information_sources=["Journal article(s)", "Supplementary appendix"],
    model="claude-opus-5", b1="Y", b3="N")
for d in range(1, 7):
    S.submit_answers(R1, d, J.ANSWERS[d], support=J.SUPPORT[d])
S.submit_answers(R1, 0, render=False)

# Result 2 — a severity outcome from the SAME paper. Same answers except
# domain 5, where the endpoint is PICU admission within an RSV admission.
R2 = "lanepe-101756 / RSV-LRTI PICU admission / wHR"
S.specify_result(result_id=R2, text_sha256=sha,
    result_assessed="Effectiveness 51% (95% CI 43-57) for RSV-LRTI requiring PICU admission",
    outcome="RSV-LRTI hospitalisation requiring paediatric intensive care",
    accounts_for_deviations="no_itt", citation=J.CITATION,
    target_trial=J.TARGET_TRIAL, review_id=REVIEW,
    information_sources=["Journal article(s)", "Supplementary appendix"],
    model="claude-opus-5", b1="Y", b3="N")
for d in range(1, 7):
    S.submit_answers(R2, d, J.ANSWERS[d], support=J.SUPPORT[d])
S.submit_answers(R2, 0, render=False)

# Result 3 — a synthetic variant-B row so the figure has to cope with mixed C4.
R3 = "synthetic / per-protocol sensitivity / HR"
S.specify_result(result_id=R3, text_sha256=sha,
    result_assessed="Illustrative per-protocol analysis",
    outcome="RSV-LRTI hospitalisation, sustained-adherence contrast",
    accounts_for_deviations="yes_pp", citation=J.CITATION, review_id=REVIEW,
    model="claude-opus-5", b1="Y", b3="N")
q = lambda t: {"evidence_mode": "manuscript_positive", "quotes": [t]}
S.submit_answers(R3, 1, [
    {"question": "1.1", "response": "N", **q("Follow-up began at birth")},
    {"question": "1.4", "response": "N", **q("Follow-up began at birth")},
    {"question": "1.5", "response": "N", "evidence_mode": "manuscript_absent",
     "search_cue": "negative_control"}], support="illustrative")
for d in range(2, 7):
    S.submit_answers(R3, d, J.ANSWERS[d], support=J.SUPPORT[d])
S.submit_answers(R3, 0, render=False)

LABELS = {R1: "Jabagi 2026 — RSV-LRTI hospitalisation",
          R2: "Jabagi 2026 — PICU admission",
          R3: "Jabagi 2026 — per-protocol (illustrative)"}

fig = S.render_review(review_id=REVIEW, labels=LABELS)
print("=== REVIEW ===")
print(json.dumps(fig["summary"], indent=1))
for r in fig["rows"]:
    doms = " ".join(f"D{d}={r['domains'][d]['judgement'][:4]}" for d in sorted(r["domains"]))
    print(f"  [{r['variant']}] {r['label'][:44]:46s} {doms}  -> {r['overall']}")

out = "/Users/jddmacbook/Desktop/Testing Folder for AI/Robins-I 2025/robins-mcp/review_figure.html"
open(out, "w").write(fig["html"])
print(f"\nwrote {out} ({len(fig['html'])} bytes)")

for layout in ("robins_i", "generic"):
    ex = S.export_robvis(review_id=REVIEW, labels=LABELS, layout=layout)
    print(f"\n=== robvis layout={layout} (tool='{ex['robvis_tool']}') ===")
    print(ex["csv"])
    for L in ex["losses"]:
        print("  LOSS:", L[:150], "...")
    if ex.get("slot_mapping"):
        for k, v in ex["slot_mapping"].items():
            print(f"   {k} <- {v}")
