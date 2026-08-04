# robins-mcp

An MCP server implementing **ROBINS-I V2** (Risk Of Bias In Non-randomized
Studies – of Interventions, follow-up/cohort variant) as a deterministic,
provenanced assessment engine.

Sibling to [`target-mcp`](../../TARGET%20Checklist%20MCP), which scores how
*completely* a target-trial-emulation study reports what the TARGET guideline
requires. This one assesses *risk of bias* in one specific result. The two are
complementary on the same paper.

> **The source is a draft.** riskofbias.info presents the 20 November 2025
> release of ROBINS-I V2 as still a draft, subject to change. Every report
> stamps that in its provenance line. See `NOTICE` and `TRANSCRIPTION-NOTES.md`.
>
> **Follow-up studies — which is broader than "cohort studies".** The criterion
> is structural: individuals observed forward from a defined time zero under the
> contrasted strategies. Target trial emulations, new-user active-comparator
> designs and registry comparisons all qualify; both worked examples below are
> TTEs. Designs with no follow-up structure do not. No variant for other designs
> is published yet. Note that "Variant A / Variant B" inside the tool means the
> two forms of Domain 1 selected by C4 — not a study design.

## What makes it different from asking a model

The model's contribution is bounded at answering signalling questions from the
text. It cannot compute a judgement and it cannot invent evidence.

```
1  parse_document              PDF + supplement → SectionMap        deterministic
2  cue detection               where to look, per domain            deterministic
3  answer signalling questions quotes copied from the bundle        MODEL
4  evidence binding            quotes → offsets, or REJECT          deterministic
5  algorithms                  answers → domain → overall           deterministic
6  report + render             stamped artifact                     deterministic
7  human ratification          P1, reviewer-prior answers, overrides
```

Three rules are enforced at submission, and they are the point of the server:

- **Quotes resolve or die.** Every quote is matched to character offsets in the
  ingested bundle through a three-pass ladder (exact → hyphen-relaxed →
  references-stripped), and the winning pass is recorded so a loose match is
  never silently equated with an exact one. An unresolvable quote is rejected
  with the nearest actual text.
- **Absence is searched, not asserted.** A `manuscript_absent` answer names a
  cue; the *server* runs the search and attaches the record — terms, sections,
  hit count. A prose claim that you looked is refused.
- **Judgements are computed.** No tool accepts a domain judgement as input. The
  six domain algorithms and the overall algorithm are explicit edge graphs
  traced from the published flowcharts. A human may override, with a recorded
  justification, and the report shows both values.

## Two gates

**P1 blocks domain 1.** Question 1.1 asks whether all *important* confounding
factors were controlled, and "important" is defined by the reviewer's
prespecified list — not by the paper's covariate table. The server refuses to
score domain 1 without `set_prespecified_confounders` rather than silently
substituting one for the other. A list you propose is a candidate: it enters the
ratification queue until a human accepts it.

**C4 selects domain 1's question set.** Whether the analysis accounts for
protocol deviations picks variant A (intention-to-treat, baseline confounding
only) or variant B (per-protocol, baseline *and* time-varying confounding), so
`specify_result` requires it up front with no default. Judge it on what the
analysis *does*, not on the label the authors give their estimand — on the
reference paper, the protocol table says "per-protocol effect" and the analysis
is intention-to-treat.

## Install and run

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q      # 181 passed
.venv/bin/robins-mcp                      # stdio MCP server
```

## Tools

| Group | Tool | |
|---|---|---|
| Spec | `get_spec` | optional introspection; `detail='compact'\|'full'` |
| Ingest | `parse_document` | PDF/docx/text + supplements → hash + cue survey |
| | `parse_pmcid` | Europe PMC retrieval |
| Setup | `set_prespecified_confounders` | P1, review-scoped, **blocks domain 1** |
| | `specify_result` | A1–A3, B1–B3, C1–C3, D1, and **C4** |
| Assess | `assess_result` | `domain=0` overview, `domain=1..6` scaffold |
| | `submit_answers` | per domain; `domain=0` finalizes and renders |
| Render | `render_report` | re-render of the stamped artifact |

Scaffolds are **per domain**, never one flat rubric: most signalling questions
are unreachable on any given path, and which of domain 1's two sets exists at
all depends on C4.

**Pass the supplement.** The target-trial specification that settles C1–C4, and
the analysis detail domains 1 and 4 turn on, routinely live only in the
appendix. Without it, those questions read `NI` when the answer was merely in a
file nobody ingested.

## Worked examples

```bash
.venv/bin/python examples/dickerman_2022.py out.html          # library level
.venv/bin/python examples/jabagi_2026_server_run.py           # server level
```

- **Dickerman et al., NEJM 2022** — BNT162b2 vs mRNA-1273 in US veterans. Comes
  out *low, except for concerns about uncontrolled confounding*. 24 of 41
  questions never reached.
- **Jabagi et al., Lancet Reg Health Eur 2026** — maternal RSVpreF vs infant RSV
  hospitalisation. Comes out *serious*, and the route is worth reading: domain 1
  fails at 1.3 rather than 1.1, because gestational age at birth and birth
  weight are matched on despite being realised after the intervention.

Both require their PDFs; paths are at the top of each file.

## Documentation

- `docs/STATUS.md` — current state and handoff. **Read this first.**
- `docs/DECISIONS.md` — why things are the way they are, newest first.
- `docs/SESSION-NOTES-*.md` — per-session narrative.
- `TRANSCRIPTION-NOTES.md` — how the algorithms were obtained from raster
  flowcharts, the errata found in the published document, and what still needs
  external verification.

## Licence

Apache-2.0 (`LICENSE`). The ROBINS-I V2 tool it implements is CC BY-NC-ND 4.0
and **no part of it is reproduced here** — see `NOTICE` for why that matters and
what the actual constraint is.
