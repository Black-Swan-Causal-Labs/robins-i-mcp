# Decision log

Load-bearing decisions for the ROBINS-I MCP server, with rationale, so a future
session (or contributor) doesn't re-litigate them. Newest first.

Format: **what** — why — status.

---

## 2026-08-03 · The unit of interchange between runs is a record, not server state
`submit_answers(domain=0)` returns a small, flat, JSON-native `record`
(`review.assessment_record`, versioned by `RECORD_VERSION`). `export_robvis`
takes any number of those, from any number of sessions.

- **The problem this fixes, which the first version had:** a review of 200
  studies is 200 runs. Each assessment costs a session — the model must read a
  paper and answer signalling questions against it — and this server keeps no
  state between runs. The first `export_robvis` read `_assessments` from the
  running process, so it could only ever export what one session had done. It
  aggregated without anything to aggregate.
- **Why a record rather than passing `Assessment` objects around:** the
  interchange format should not be this server's internals. A record is ~4 KB,
  flat, and depends on nothing in this codebase, so a different agent — or a
  script, or a person — can consume it. It is also the natural deliverable of a
  run alongside the HTML: the HTML is for a human, the record is for whatever
  comes next.
- **What a record must carry, and why each part earns its place:** the
  judgements (what a figure plots); citation/outcome/result (what labels a row);
  the C4 variant (domain 1 means something different under each); override and
  ratification state (an unratified assessment is not final and a figure must
  not imply otherwise); and the full provenance stamp. Without the stamp a row
  in a summary figure is an anonymous coloured square — with it, the row traces
  back to a document hash and an algorithm fingerprint.
- **A consequence worth having:** because records carry fingerprints,
  `robvis_table` can notice when a set mixes algorithm transcriptions and say
  the judgements are not strictly comparable. Server-state aggregation could
  never have detected that.
- `RECORD_VERSION` is a compatibility surface; consumers check it rather than
  assuming shape, and a record from a future version is refused rather than
  half-read.
- **Known limit, not solved:** ~4 KB per record means ~800 KB for 200 studies,
  which is too much for a single context. Typical ROBINS-I reviews run 10-40, so
  this is not pressing; at real scale, aggregate in batches or strip the
  review-level fields (`prespecified_confounders`, `information_sources`) that
  repeat identically across every record.
- Status: built. 24 tests, of which `test_records_survive_a_round_trip_through_json`
  is the one the whole design rests on.

## 2026-08-03 · No parallel review figure; robvis is the figure
`render_review.py` was built and then removed the same day.

- **Why it was built:** to keep `low_except_confounding` as a sixth level, which
  robvis cannot represent.
- **Why it was removed:** it duplicated a mature, citable tool that reviewers
  already recognise, to preserve a distinction that a figure caption carries
  perfectly well. Its first demo — three results from one paper — also produced
  three identical rows, which is what finally exposed the shape as wrong: within
  one study, domains 2, 3 and 4 are properties of the cohort and cannot vary by
  outcome, and only D5 and sometimes D6 move at all. The figure needed a caveat
  box explaining why its own rows were not what its format implied, and needing
  to explain away your own output is a design smell.
- **What survives, and is the actually novel part:** the V1-slot mapping in
  `export_robvis`. robvis gets that silently wrong and cannot fix it for itself.
- The cross-STUDY case remains real — one row per study, shared P1, which is
  ROBINS-I's own planning-stage design — and is served by the export.
- Reversible: `git revert` restores the figure if a review ever needs the sixth
  level plotted rather than captioned.

## 2026-08-03 · robvis export must use tool="Generic", never tool="ROBINS-I"
Not yet built, but the finding is load-bearing enough to record before it is.

[robvis](https://mcguinlu.shinyapps.io/robvis/) (McGuinness & Higgins) is how
risk-of-bias assessments become Cochrane-style traffic-light and summary figures,
so it is the natural downstream target for this server's output. Its ROBINS-I
template is **V1** and V2 is NOT drop-in compatible. Read from robvis source
(`R/rob_summary.R`, `R/rob_traffic_light.R`):

| robvis `tool="ROBINS-I"` (V1) | ROBINS-I V2 |
|---|---|
| D1 confounding | D1 confounding |
| D2 **selection of participants** | D2 **classification of interventions** |
| D3 **classification of interventions** | D3 **selection of participants** |
| D4 deviations from intended interventions | — dropped, folded into D1 variant B |
| D5 missing data | D4 missing data |
| D6 measurement of outcomes | D5 measurement of the outcome |
| D7 selection of the reported result | D6 selection of the reported result |

- **The dangerous part is not the dropped domain, it is the transposition.** V2
  swapped D2 and D3 relative to V1. A positional dump into the ROBINS-I template
  loses no data and raises no error — it just prints the classification
  judgement under the heading "Bias due to selection of participants". On the
  Jabagi assessment that silently swaps Low and Moderate. A figure that is wrong
  and confident is worse than no figure.
- **Judgement vocabulary does not fit either.** robvis takes l/m/s/c/n/x. There
  is no slot for `low_except_confounding`, and mapping it to `l` erases the one
  thing V2 insists on about domain 1 — that it can never reach plain low. And
  robvis's `n` ("No information") is a V1 domain-level verdict; in V2, NI is a
  signalling-question answer and no domain judgement can be NI.
- **First conclusion, WRONG, corrected below:** "therefore target
  `tool = 'Generic'`". Reading robvis's `rob_summary_generic` shows Generic is
  really its ROB1 path (`check_rob1(tool)`), and its preprocessing is
  `substr(x,0,2); gsub("se","h"); substr(x,0,1); gsub("m","s")` — which renames
  Moderate to "Some concerns" and Serious to "High". Correct columns, wrong
  vocabulary.
- **What we built instead** (`review.py`, `layout="robins_i"`, the default):
  emit V1's SEVEN-column template with each V2 judgement placed in its correct
  V1 slot and the deviations slot written `NA`, which robvis's `clean_data`
  maps to "x" and draws as N/A. Upload with `tool = "ROBINS-I"`. This keeps
  ROBINS-I's own judgement vocabulary AND fixes the transposition, because we
  do the slotting rather than trusting column order. `layout="generic"` remains
  available for when V2's own headings matter more than the vocabulary.
- **A hard limit neither layout escapes.** robvis's `clean_data` reduces every
  cell to its first initial and the fill scale defines only l/m/s/c/n/x. "Low"
  and "Low except for concerns about uncontrolled confounding" both collapse to
  "l", so the qualified level cannot be carried into robvis by ANY cell string.
  `robvis_table` therefore returns a `losses` list — the qualified level, mixed
  C4 variants, and equal weighting — rather than quietly degrading. Note the
  overall judgement is qualified whenever every domain is at its lowest level,
  so this loss fires more often than the domain cells suggest.
- **Where the sixth level lives instead:** `render_review.py`, our own
  review-level figure, draws it as a distinct level. That was the user's call
  when asked; it is the right one, because the whole point of that level is
  that it is not plain low.
- Status: built. `review.py`, `render_review.py`, tools `export_robvis` and
  `render_review`, 22 tests. The load-bearing one is
  `test_robins_i_layout_transposes_d2_and_d3` — every other export bug is loud.

## 2026-08-03 · Scope is follow-up cohort studies; read the property, not the label
`guideline_scope` states the structural property and names the one case where
the wording genuinely bites. Settled after two wrong turns in one conversation,
both recorded here because the wrong turns are instructive.

- **Wrong turn 1 (too narrow):** answered that the tool is for cohort studies,
  reading the outline's parenthetical as the scope.
- **Wrong turn 2 (too broad, overcorrecting):** answered that "follow-up" is the
  operative term and the scope is *wider* than "cohort study". It isn't. The two
  words name one structural property, which is why the source writes them
  together rather than as alternatives — a cohort study IS a follow-up study.
  TTEs and new-user active-comparator designs are not outside "cohort study";
  they are cohort studies run with particular design discipline.
- **Where it lands:** follow-up cohort studies, the source's own phrasing. The
  criterion is the property — a defined time zero, individuals followed forward
  under the contrasted strategies — not a design name, because the document
  never enumerates eligible designs. Out: cross-sectional, conventional
  case-control, before-and-after.
- **The one place the wording genuinely bites**, and the part of the correction
  worth keeping: designs SAMPLED FROM a cohort — nested case-control,
  case-cohort. Cohort estimand, follow-up structure underneath, but not a cohort
  analysis. The source is silent. Recorded as a judgement call to document, not
  resolved by fiat, and worth raising with the development group.
- **A separate, real error, independent of the above:** the claim that no other
  design variant "exists" was asserted from a single page fetch summarised by a
  small model — thin evidence for a negative. The supportable statement is that
  none is *published*, with separate tools reported to be in development.
- **Method note worth keeping:** the primary source settled the factual questions
  and the secondary summary did not. Grepping the PDF for design vocabulary — one
  hit for "cohort study", zero for "case-control" — beat any description of the
  tool. But note that grep established what the document *says*, not what the
  terms *mean*; the second wrong turn came from over-reading a word-frequency
  result as a semantic distinction.
- Status: settled across spec, STATUS, TRANSCRIPTION-NOTES and README.

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
