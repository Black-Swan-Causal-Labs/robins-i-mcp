# Decision log

Load-bearing decisions for the ROBINS-I MCP server, with rationale, so a future
session (or contributor) doesn't re-litigate them. Newest first.

Format: **what** — why — status.

---

## 2026-08-03 · Scope is "follow-up", not "cohort" — correcting an error made earlier the same day
`guideline_scope` now states a structural criterion rather than a design label,
and `variant_scope_note` warns against the narrow reading explicitly.
- **The error:** the source's outline glosses its scope as "follow-up (cohort)
  studies", and earlier entries in this repo let the parenthetical become the
  scope, describing the tool as being for cohort studies. That is narrower than
  the source. The title says follow-up studies; the phrase "cohort study" occurs
  exactly once in 49 pages, in a time-varying-confounding example; and no list of
  eligible designs appears anywhere in the document.
- **Why it mattered practically, not just terminologically:** the narrow reading
  would exclude target trial emulations, which are the central use case and are
  what BOTH worked examples in `examples/` actually are. Neither Dickerman nor
  Jabagi is a textbook cohort study.
- **The criterion that does apply** is structural: individuals observed forward
  from a defined start of follow-up under the contrasted strategies. Satisfied by
  TTEs, new-user active-comparator designs, registry and pragmatic comparisons;
  not satisfied by cross-sectional, conventional case-control, or before-after.
- **Left open deliberately:** nested case-control and case-cohort, where sampling
  is an efficiency device inside a follow-up study. The source is silent. Recorded
  as a judgement call to make and document, not resolved by fiat.
- **Second correction, same entry:** the claim that no other design variant
  "exists" was asserted from a single page fetch summarised by a small model —
  thin evidence for a negative. The supportable statement is that none is
  *published*, with separate tools reported to be in development.
- **Method note worth keeping:** the primary source settled this and the
  secondary summary did not. Grepping the PDF for design vocabulary — one hit for
  "cohort study", zero for "case-control" — was more informative than any
  description of the tool.
- Status: corrected across spec, STATUS, TRANSCRIPTION-NOTES and README.

## 2026-08-03 · The source is a draft, and every report says so
`report.SOURCE_STATUS` is stamped into `provenance()` and the rendered
provenance line; `spec.source_status: draft` carries the same fact into
`get_spec`.
- **What prompted it:** checking riskofbias.info to answer whether ROBINS-I V2
  covers designs other than cohort. It does not — and the same page describes
  the 20 November 2025 release as still a draft, subject to change, with a
  November 2024 release archived beside it. Nothing in the repo recorded that.
- **Why it needed its own stamp field rather than a note in the docs:** the
  `algorithm_fingerprint` was doing work it cannot actually do. It hashes *our*
  edge tables, so it detects a correction we make. An upstream revision we have
  not ingested changes nothing on our side and is therefore invisible to it.
  Those are different failure modes and only one of them was covered.
- **Why on the artifact and not just in the code:** a ROBINS-I judgement feeds
  evidence synthesis. A reader deciding how much weight to give one should not
  have to know the tool's release history to learn it was drafted against a
  moving target.
- `spec_version` was deliberately NOT bumped. Nothing encoded changed — no
  question, no option set, no algorithm — so two reports carrying
  `robins-i-v2-cohort-0.1.0` remain comparable. Bump it when the *content*
  moves, which is what a source revision would do.
- **Cheapest next check, not yet done:** diff the archived Nov 2024 release
  against Nov 2025. It shows where the tool is still moving, and gives a second
  rendering of the same raster flowcharts to trace against — the only
  independent check on the tracing that does not need the development group.
- Status: done. Diff and contact remain open; see TRANSCRIPTION-NOTES.md.

## 2026-08-03 · The server is stateful in two places, and both are gates
`set_prespecified_confounders` (review-scoped) and `specify_result` (result-scoped)
hold state that later calls read; neither has a safe default.
- **Why P1 is review-scoped:** it belongs to the review, not to a study. The same
  list applies to every result assessed under one `review_id`, which is also what
  makes it prespecified rather than reactive.
- **Why C4 has no default:** it selects domain 1's variant, so a default would
  silently pick a question set. `accounts_for_deviations` is a required argument
  with two legal values and the docstring says to judge it on what the analysis
  does, not on the authors' label for their estimand.
- **Why `assess_result` is per domain:** most questions are unreachable on any
  path (on the Jabagi run, 13 of 35 were never reached). A flat rubric would ask
  for answers the algorithm discards and would misstate domain 1 half the time.
- Status: done; 44 server tests.

## 2026-08-03 · Answers cannot be self-ratified, and an unratified P1 says so
`set_prespecified_confounders(ratified_by=...)` is documented as human-only, and
`Assessment.prespecified_confounders_ratified` puts an unratified list in the
ratification queue.
- **Why:** the previous behaviour queued P1 only when it was *absent*. An
  agent-proposed list therefore read as settled the moment it was supplied, which
  is exactly the substitution the P1 gate exists to prevent. Found by running the
  Jabagi paper end to end: the queue came back with two items and should have had
  three.
- The server never sets `ratified_by` on its own behalf and says so in the tool
  description. The report shows the queue, so an unratified assessment cannot be
  presented as final without the reader seeing it.
- Status: done; fixed 2026-08-03.

## 2026-08-03 · Absence claims are searched by the server, at submission time
`submit_answers` takes `search_cue` (or `search_terms`) on a `manuscript_absent`
answer and runs the search itself; a prose assertion is rejected outright.
- **Why here rather than trusting the caller:** this is the enforcement point for
  the 2026-08-01 decision below. The model names *where* to look; the server
  decides what was found. A `SearchRecord` built by the server is reproducible
  against the same bundle; one described by the model is not.
- Quotes are resolved at submission too, not deferred to finalization, so a
  fabricated or paraphrased quote is rejected with the nearest actual text while
  the caller still has the domain in hand.
- Status: done.

## 2026-08-03 · Pinned to mcp < 2
`mcp` 2.0 replaced `FastMCP` with `MCPServer` at a new import path.
- **Why pin:** target-mcp runs 1.28.x in production and the two servers should
  not drift apart on the SDK. Migrating both is its own task with its own
  testing, not something to smuggle into building this one.
- Status: pinned in `pyproject.toml`; migration is an open item in STATUS.md.

## 2026-08-01 · Quote matching is a three-pass ladder that records which pass hit
`SectionMap.locate()` tries `exact` → `hyphen_relaxed` → `refs_stripped` and
stops at the first hit; the winning pass is stamped on the `EvidenceSpan`.
- **Why a ladder:** publisher PDFs mangle text in three separate ways, and each
  needs a different relaxation. `exact` collapses whitespace and ignores case.
  `hyphen_relaxed` additionally drops hyphens *and* all whitespace, so
  `SARS-CoV-2`, `SARSCoV-2` and `SARS CoV 2` unify. `refs_stripped` additionally
  drops inline superscript reference numerals (`controls 13 suggested`).
- **Why record the pass:** a loose match must never be silently equated with an
  exact one. The renderer shows the locator; the span carries `match=` so a
  future reviewer can tell how hard the matcher had to work.
- **Why strict by default:** `bind_evidence()` raises on an unresolvable quote.
  A quote that cannot be found is either not verbatim or not from this document,
  and both are reasons to stop. `strict=False` exists for triage only.
- Status: done; 137 tests.

## 2026-08-01 · Absence is generated by the server, not asserted by the model
The `CUES` table maps 15 evidence patterns to the signalling questions they
inform; `search_cue()` returns a `SearchRecord` (terms, sections, hit count) that
a `manuscript_absent` answer carries in place of prose.
- **Why:** ROBINS-I answers frequently rest on absence — `NI` for 6.1 when there
  is no protocol, `N` for 1.4 when no negative control was run. An unverified
  "I looked and found nothing" is not evidence. A search record distinguishes an
  exhaustive search from a cursory one and is reproducible against the same
  bundle. `Answer.search_is_auditable` flags free-text records as second-class.
- **Gotcha found immediately:** naive substring search reported 44 imputation
  hits in a paper that imputes nothing — `MAR` matching inside "marked". Terms
  that are ALL-CAPS or ≤4 chars are now word-anchored; longer terms stay
  substrings so deliberate stems (`imput`, `classif`, `adjudicat`) still catch
  their family.
- Status: done.

## 2026-08-01 · Structured-abstract labels are detected typographically, not by distance
Capitalized `BACKGROUND / METHODS / RESULTS` headings are dropped from body
sectioning when the same section kind reappears later in mixed case.
- **Why not distance:** the first implementation assumed abstract labels are
  tightly packed and body headings far apart. False — a short paper packs its
  body headings just as tightly, and the heuristic silently did nothing. The
  reliable signal is that clinical journals set abstract labels in capitals and
  body headings in title case.
- **What it fixes:** on the NEJM test paper, Methods was being detected as 813
  characters (it was the abstract's METHODS label) and the real methods text was
  filed under Results. Now methods 7,897 / results 6,632 / discussion 18,932.
- Status: done; both the fire and no-fire cases are tested.

## 2026-07-29 · Summary strip spans the full content width; no traffic-light circles
The per-domain summary is a bordered 7-cell grid aligned to the same margins as
the meta panel and the domain table, each cell carrying the judgement as a word.
- **Why:** circles floating at the left margin broke the page's column and were
  too small to hold "Moderate". Words in wide bands removed the need for a colour
  legend entirely — the strip is self-documenting and assumes no convention.
- Overridden cells carry a dagger, and the footnote explaining it appears only
  when an override exists. The whole design premise is that overrides cannot
  hide, so the strip must not show a final value that silently differs from the
  algorithm's.
- Status: done.

## 2026-07-29 · Three evidence modes, and reviewer-prior answers block finalization
Every `Answer` declares `manuscript_positive` (needs a resolvable quote),
`manuscript_absent` (needs a search record) or `reviewer_prior` (needs a
reference to the prespecified item, and human ratification).
- **Why:** TARGET is a closed-book reporting audit — everything needed is in the
  manuscript. ROBINS-I is not. Question 1.1 asks whether *all important*
  confounders were controlled, and "important" is defined by the reviewer's
  prespecified list, not by the paper. Collapsing that distinction would let the
  instrument silently substitute the paper's own covariate list for the
  reviewer's judgement.
- `Answer.__post_init__` enforces the evidence requirement at construction, so an
  unevidenced assessment cannot be built. `ratification_queue` collects every
  reviewer-prior answer, every override, and a missing P1;
  `require_ratified()` blocks finalization while it is non-empty.
- Status: done.

## 2026-07-29 · P1 is blocking, and the assessment unit is one result
`prespecified_confounders` is a required input; the unit of assessment is a
single effect estimate, not a manuscript.
- **Why P1 blocks:** domain 1 is unanswerable without it. The server must refuse
  rather than guess. A candidate list may be proposed (a DAG from `dag-studio` is
  the obvious source) but must be ratified before it counts.
- **Why per-result:** ROBINS-I is explicitly scoped to one numerical result. A
  paper with three outcomes across two analyses is six assessments. This is also
  a second parallelism axis for a future fan-out.
- Status: spec + report layer done; per-result plumbing lands with the server.

## 2026-07-29 · Own-words only; no OFFICIAL_TEXT projection, and that is not a limitation
The spec carries own-words intent; no ROBINS-I wording is reproduced anywhere.
- **Why it differs from TARGET:** TARGET is CC BY-ND, which let that server ship
  an `OFFICIAL_TEXT` verbatim projection under attribution. ROBINS-I V2 is
  CC BY-**NC**-ND. NC forbids the commercial-use permission an open source
  licence grants downstream, so the same pattern does not transfer. ND
  independently forbids *sharing* adaptations, which a close reword would be.
- **What is free:** decision logic (methods and procedures are not copyrightable),
  question IDs, response-option letters, domain names, and our own expression.
  That covers everything the tool needs to do.
- **Consequence, deliberate:** ROBINS-I has no published blank form to project
  onto — the deliverable is a domain/judgement/support table, which is a genre
  convention nobody owns. So nothing of value is lost. If literal wording is ever
  wanted on screen, the route is bring-your-own-document at runtime, never
  redistribution.
- **Verified, not assumed:** an n-gram check against the source PDF confirms the
  only long overlaps are the tool's title (required attribution) and the domain
  names (functional headings). Two scope sentences that sat too close were
  rewritten.
- Status: done. Contacting the development group remains open and is the cleanest
  path to both a wording grant and an algorithm cross-check.

## 2026-07-28 · Algorithms are explicit edge graphs, not condensed logic
Each domain is written as a node/edge list mirroring the published flowchart one
arrow at a time, even where a compact rule would reproduce it.
- **Why:** the seven domain algorithms are raster images in the cribsheet with no
  text layer. Every edge was traced by hand from the drawing. An explicit edge
  list can be held next to the figure and checked arrow by arrow; condensed logic
  cannot.
- **Two defences, both internal:** structural tests assert each node's edges
  exactly partition its response-option set (a missed arrow fails immediately);
  property tests assert the invariants the figures imply — domains 2 and 4 are
  additive severity ladders, domain 1 never reaches plain low, domain 5 never
  reaches critical. Neither is external validation.
- **Still open:** verify against the official riskofbias.info implementation when
  it ships. See TRANSCRIPTION-NOTES.md for the specific judgement calls and the
  one genuine ambiguity (domain 6's overlapping bands on all-NI).
- Status: done; 111 algorithm tests.

## 2026-07-28 · Judgements are computed, never asserted
The model answers signalling questions; Python computes domain and overall
judgements; a human may override with a recorded justification.
- **Why this is the whole point:** it bounds the model's contribution to evidence
  retrieval and question answering, which is what it is good at, and keeps the
  contestable step — the judgement — deterministic and auditable. TARGET could
  not do this; the model's verdict *is* TARGET's output. ROBINS-I publishes an
  algorithm, so we get the separation for free.
- The provenance stamp carries an `algorithm_fingerprint` (hash of the traced
  edge tables) so a later transcription correction is detectable in reports
  produced under the earlier version.
- Status: done.

## 2026-07-28 · A separate server; copy from target-mcp first, factor later
`robins-mcp` is its own package. `ingest.py` was copied from the TARGET server
and adapted rather than extracted into a shared core.
- **Why separate:** different object model (result-scoped), different verdict
  vocabulary, different licence constraints on wording.
- **Why copy, not factor:** the right seams only become visible once the second
  implementation exists. That has now been borne out — the ported ingest needed
  per-domain cues, three-pass matching and typographic abstract detection, none
  of which the TARGET version has. Extract a shared core when a third consumer
  appears, not before.
- Status: done for ingest; `retrieve.py`, the docx renderer and `validate.py`
  remain to port.
