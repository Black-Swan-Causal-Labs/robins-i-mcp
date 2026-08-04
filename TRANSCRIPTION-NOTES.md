# ROBINS-I V2 transcription notes

Source: `ROBINS-I_cribsheet_20November2025 (1).pdf` — ROBINS-I V2 assessment tool
for follow-up (cohort) studies, 20 November 2025, 49 pp.

> **The source is a draft.** Confirmed against riskofbias.info on 2026-08-03:
> the 20 November 2025 release is presented as still a draft and subject to
> change, with a November 2024 release archived beside it. Everything below
> traces a moving target. The two internal defences catch *our* errors; neither
> catches a revision *they* make, and the algorithm fingerprint hashes our edge
> tables, not their PDF. Re-check riskofbias.info before relying on an
> assessment, and see "Diffing the two releases" below.
>
> **Scope is follow-up cohort studies** — the source's own phrasing, where
> "follow-up" and "cohort" name one structural property rather than two
> criteria. No list of eligible designs appears anywhere in the document, so
> read the property: a defined time zero, individuals followed forward under the
> contrasted strategies. Target trial emulations are the central use case and
> are cohort studies in exactly this sense. The wording only genuinely bites for
> designs *sampled from* a cohort — see Scope below. No variant for other designs
> is *published*; separate tools are reported to be in development. Beware
> "variant": inside the tool it means Domain 1's two forms, never a study design.

Two artefacts were produced from it:

- `robins_mcp/specs/robins-i-v2-cohort-0.1.0.yaml` — preliminaries, the
  confounding-factor table schema, and all signalling questions with their
  response-option sets, gating conditions and evidence modes. Question *intent*
  is in original words; no published wording is reproduced.
- `robins_mcp/algorithms.py` — the seven domain algorithms plus the overall
  algorithm. 111 tests pass (`pytest tests/`).

## How the algorithms were obtained

The domain-level algorithms are **raster flowchart images** embedded on pp. 20,
24, 28, 32, 38, 41 and 47. They extract to zero text. Each was pulled out with
`pypdf`, upscaled, and traced arrow by arrow. Only the overall algorithm (p. 49)
is a text table and transcribed mechanically.

This is the highest-risk part of the encoding. Two defences are in place:

1. **Structural tests.** For every node, the outgoing edges must exactly
   partition that question's response-option set — no option unrouted, none
   routed twice. A missed arrow fails this immediately.
2. **Property tests.** Domains 2 and 4 turn out to be additive severity ladders
   (entry level, then each subsequent answer bumps the level by 0/1/2,
   saturating at critical). The tests assert that equivalence across all answer
   combinations. Domain 1 can never reach plain `low`; domain 5 can never reach
   `critical`. A mis-traced arrow would almost certainly break one of these.

Both defences are internal-consistency checks, not external validation. **Verify
against the official implementation before any real use** — the tool states that
an online ROBINS-I V2 implementation with automatic question selection and
algorithm-derived judgements is in development at www.riskofbias.info.

## Errors in the source document

Encoded as intended, not as printed. Worth reporting upstream.

| Location | Printed | Should be | How we know |
|---|---|---|---|
| p. 30, guidance for 3.1 | "Answer 'SY' if either: (i) the effect… (ii) a substantial proportion…" | `SN` | 3.1's options are Y/PY/WN/SN/NI — there is no SY. 3.6's gate reads "If SN to 3.1". |
| p. 34, gate for 4.4 | "If N/PN/NI to 4.1, 4.4 or 4.4" | "4.1, 4.2 or 4.3" | 4.11's gate names 4.1, 4.2, 4.3 correctly. |
| p. 35, options for 4.7 | "NA / Y / PY / PN / NI" | includes `N` | The p. 38 flowchart branches 4.7 on N/PN/NI. |

## Judgement calls made during tracing

Each of these is a place a second reader should look first.

**Domain 1 variant B — the unreachable box (p. 24).** The figure draws a green
`LOW RISK OF BIAS` box with no inbound arrow. Treated as a legend artefact: the
tool's own footnote (p. 4) says domain 1's best judgement is always "low risk of
bias except for concerns about uncontrolled confounding", because residual
confounding cannot be excluded in an observational study. Encoded so that
neither variant can reach plain `low`.

**Domain 1 variant A — the merging over-adjustment branch (p. 20).** `1.3 = Y/PY`
on the `1.1 = Y/PY` track and on the `1.1 = WN` track lead to the *same* 1.4
node. The upper line passes behind the lower 1.3 box (visible as a faded
segment) rather than terminating there. Confident, but it is the one place in
that figure where a line is occluded.

**Domain 2 — the two long SY arrows (p. 28).** `2.4(top) SY` skips a level to
`2.5(bottom)`, and `2.4(middle) SY` goes straight to `critical`, its line
passing *through* the 2.5(bottom) box. Resolved by zooming on the crossing and
confirmed by the additive-ladder property: entry level + 2.4 bump + 2.5 bump
reproduces every drawn edge with no exceptions.

**Domain 3 — panel B asymmetry (p. 32).** `3.3 = N/PN` and `3.4 = N/PN` both
terminate at `LOW`, but `3.5 = N/PN/NI` terminates at `MODERATE`. Counter-
intuitive but clearly drawn: having reached 3.5 at all means selection was based
on post-baseline characteristics *and* those were associated with intervention,
so residual concern remains even when they were not influenced by the outcome.

**Domain 3 — the ladder gate.** The tool gates 3.6 on "SN to 3.1 or Y/PY to
3.5". That is exactly the condition "panel A or panel B came out serious", which
is how it is implemented; a test asserts the two formulations agree across all
combinations of 3.1 and 3.5.

**Domain 6 — overlapping bands (p. 47).** The four bands are: all N/PN → low; at
least one NI but none Y/PY → moderate; one Y/PY, or all NI → serious; two or
more Y/PY → critical. "All NI" satisfies both the moderate and the serious band.
Implemented serious-first on the principle that the more specific band wins.
**This one is a genuine ambiguity in the source and should be confirmed.**

**Overall — additive escalation (p. 49).** "Several domains at moderate →
serious" and "several at serious → critical" are explicitly discretionary. The
default is pure worst-of; escalation is opt-in and raises `ValueError` without a
recorded justification.

## Licensing

The tool is **CC BY-NC-ND 4.0** — stricter than TARGET's CC BY-ND, which is what
let the TARGET server ship an `OFFICIAL_TEXT` verbatim projection of the
published item wording.

- **ND**: verbatim signalling-question wording may not be modified.
- **NC**: it may not be redistributed as part of anything with a commercial
  purpose.

Consequences, already reflected in the spec:

- The YAML carries **own-words intent only**. No verbatim signalling-question
  text appears anywhere in this repo.
- There is deliberately **no `OFFICIAL_TEXT` mapping** and no "project onto the
  published form" renderer of the kind `target_mcp/render.py` provides.
- The **algorithms are decision logic, not prose**, and are not restricted by
  copyright in the way the wording is.

Before publishing anything, contact the ROBINS-I development group (Sterne,
Higgins et al., via riskofbias.info). The Cochrane methods ecosystem is more
likely to want collaboration than a licence argument, and an official blessing
would also settle the algorithm-transcription risk above.

## Diffing the two releases

Not yet done, and it is the cheapest unexploited check available. riskofbias.info
hosts an archived **November 2024** release alongside the November 2025 draft we
transcribed. Diffing them would show which parts of the tool the development
group is still moving — and anything that changed between releases is, by
definition, where transcription against a draft is most likely to go stale. It
would also give a second rendering of the same flowcharts to trace against,
which is the only independent check on the raster tracing that does not require
the development group's cooperation.

Do this before, not after, contacting them: it is free, and it sharpens the
questions worth asking.

## Scope

This covers the **follow-up cohort studies** variant, which as of 2026-08-03 is
the only one published. If a variant for other designs appears it gets its own
spec file and its own `spec_version`; do not stretch this one.

"Follow-up" and "cohort" are one criterion, not two — the source writes them
together because they name the same structural property: individuals observed
forward from a defined start of follow-up under one of the contrasted
strategies. Read the property rather than hunting for a design name. Target
trial emulations on routinely collected data, new-user active-comparator
designs, registry-based and pragmatic non-randomized comparisons are all cohort
studies in this sense; both worked examples in `examples/` are TTEs.

The architecture is specific to follow-up designs rather than incidentally aimed
at them: it presumes a time zero, follow-up time, and the possibility of
time-varying confounding, having dropped V1's "deviations from intended
intervention" domain and folded protocol deviations into Domain 1 Variant B via
g-methods. None of that survives the move to a design with no follow-up
structure — cross-sectional, conventional case-control, before-and-after.

**That last sentence is inference, not encoding.** The source names no eligible
or ineligible design anywhere: "case-control", "cross-sectional" and
"before-after" each occur zero times in 49 pages. It states a criterion and
leaves the application to the assessor. The inference is easy in those three
cases and hard in one — see "Questions for the development group" below. Keep
the distinction: the criterion is theirs, the design labels are ours, and only
the criterion is in the encoded spec.

## Questions for the development group

**These are OURS. None of them is raised by the source document, and none of
them appears in the encoded spec** — the spec records what the tool states, not
what we wonder about it. Kept here so the distinction survives.

1. **Designs sampled from within a follow-up study** — nested case-control,
   case-cohort. Verified absent from the source: across 49 pages, "nested",
   "case-cohort", "case-control", "subcohort", "risk set", "density sampling"
   and "two-phase" occur **zero** times, and the only two hits for `sampl*` are
   both "sampling variation" in the target-trial definition. So the tool neither
   includes nor excludes these designs; it never contemplates them.
   The question is live because the sampling is an efficiency device over a
   follow-up study and the estimand is the underlying cohort's, so most domains
   appear to map — but domain 3 (selection into the study *or into the
   analysis*) and domain 4 would need care, and the algorithms assume the
   follow-up questions are answerable as written. Until answered: out of scope
   for this implementation, and an assessor who applies it anyway should record
   that as a deviation.
2. **The three errata** in "Errors in the source document" above.
3. **Domain 6's overlapping bands on all-NI** — see "Judgement calls made during
   tracing". The one genuine ambiguity in the transcription.
4. **An algorithm cross-check** against their own implementation when it ships.
5. **Whether a non-follow-up variant is planned**, and on what timeline — it
   would need its own spec and its own algorithms, not an extension of this one.

## What is not yet built

The spec and algorithms are the checklist layer. Items 1-4 below **landed with
`server.py` on 2026-08-03**; see `docs/STATUS.md` for current state. Kept here
because the ordering is the argument, and item 2 is only half done.

1. ~~**Result-scoped object model**~~ — done; `result_id` keys every assessment.
2. **`prespecified_confounders` input** — HALF DONE. P1 is in and blocking, and
   an unratified list now enters the ratification queue. The **confounding-factor
   table is not built**: the spec defines a per-factor row schema (measured
   variables, controlled Y/N, measured validly, control demonstrably unnecessary,
   expected direction) and the server carries only a list of strings. This is the
   largest remaining gap against the published tool. Natural integration point
   for `dag-studio`.
3. ~~**Ingestion / retrieval / render**~~ — done. `validate.py` is not ported and
   is a rewrite rather than a port; it is written against TARGET's leaf/verdict
   model.
4. ~~**Evidence-mode enforcement**~~ — done, at `submit_answers`.
5. **Orchestration skill** — serial preliminaries and confounding table, then
   six domain subagents in parallel, then deterministic algorithm evaluation,
   then merge and render. Note the tool itself requires that preliminaries be
   agreed before assessors work independently, which is the same constraint.
