# Status & handoff

Snapshot for picking the project back up cold. Last updated 2026-08-03.

## What this is

An implementation of **ROBINS-I V2** (risk of bias in non-randomized studies of
interventions, follow-up/cohort variant, 20 November 2025) as a deterministic,
provenanced assessment engine. Sibling to `target-mcp`: that one scores how
*completely* a target-trial-emulation study reports what TARGET requires; this
one assesses *risk of bias* in one specific result from a cohort study. The two
are complementary on the same paper.

> **Two facts about the source, established 2026-08-03, that shape everything:**
>
> 1. **It is a draft.** riskofbias.info presents the 20 Nov 2025 release as still
>    a draft, subject to change. Every report now stamps
>    `source draft (20 Nov 2025 release, subject to change)` in its provenance
>    line. The algorithm fingerprint does NOT cover this — it hashes our
>    transcription, so an upstream revision is invisible to it.
> 2. **Scope is follow-up cohort studies** — the source's own phrasing, with
>    "follow-up" and "cohort" naming one structural property, not two criteria.
>    Read the property (a defined time zero, individuals followed forward under
>    the contrasted strategies) rather than a design label: target trial
>    emulations are the central use case and are cohort studies in exactly this
>    sense — both worked examples are TTEs. Out of scope: designs with no
>    follow-up structure (cross-sectional, conventional case-control,
>    before-after). No variant for other designs is *published*; separate tools
>    are reported to be in development. Beware "variant" in the source: it means
>    Domain 1's two forms, never a study design. Our own open scope question
>    (designs sampled from within a cohort) is NOT in the spec — it lives in
>    TRANSCRIPTION-NOTES.md under "Questions for the development group", because
>    the source never raises it.

Built by Black Swan Causal Labs. See `docs/DECISIONS.md` for why things are the
way they are, and `TRANSCRIPTION-NOTES.md` for how the algorithms were obtained
and what still needs external verification.

## State: **server built and running**; verified on two real papers

```
robins-i-mcp/
├── robins_i_mcp/
│   ├── specs/robins-i-v2-cohort-0.1.0.yaml   spec: 13 preliminaries, 40 SQs, 6 domains
│   ├── spec.py            spec loader + own-words question labels
│   ├── algorithms.py      7 domain algorithms + overall, as explicit edge graphs
│   ├── ingest.py          PDF/docx/text → SectionMap, quote→offset, cue search
│   ├── retrieve.py        Europe PMC JATS + supplement fetch (ported from target-mcp)
│   ├── report.py          Assessment assembly, evidence binding, provenance
│   ├── render_html.py     self-contained BSCL-branded HTML report
│   ├── scaffold.py        per-domain question/cue scaffolds for the model
│   ├── review.py          the portable assessment record + robvis export
│   └── server.py          the MCP tool surface — 9 tools
├── examples/
│   ├── dickerman_2022.py            library-level assessment (NEJM 2022)
│   ├── jabagi_2026_server_run.py    server-level assessment (Lancet Reg Health Eur 2026)
│   ├── review_from_records.py       cross-session: save records, aggregate from disk
│   └── demo_report.py               synthetic, exercises all three flag paths
├── tests/                 205 passing (137 library + 43 server + 25 record/export)
├── pyproject.toml         installable; entry point `robins-i-mcp`
└── docs/                  DECISIONS.md, STATUS.md
```

Setup and run:
```
python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q          # 202 passed
.venv/bin/python examples/jabagi_2026_server_run.py
.venv/bin/robins-i-mcp                          # stdio MCP server
```

> `mcp` is pinned `>=1.9,<2` — 2.0 replaced `FastMCP` with `MCPServer`. See
> DECISIONS.md.

## Published (2026-08-04)

| | |
|---|---|
| GitHub | https://github.com/Black-Swan-Causal-Labs/robins-i-mcp (public) |
| PyPI | `robins-i-mcp` 0.1.0 |
| MCP registry | `com.blackswancausallabs/robins-i-mcp`, status `active` |

Install and register in a client:

```jsonc
// claude_desktop_config.json (or equivalent)
{ "mcpServers": { "robins-i": { "command": "robins-i-mcp" } } }
```

after `pip install robins-i-mcp` (or `uvx robins-i-mcp` with no install).

Registry publication is DNS-verified against `blackswancausallabs.com`. The
signing key is `~/.config/mcp-publisher/bscl-mcp-dns-key.pem` — it is a PEM,
and `mcp-publisher` wants raw hex with OpenSSL's leading `00` stripped:

```bash
KEY=$(openssl ec -in ~/.config/mcp-publisher/bscl-mcp-dns-key.pem -text -noout 2>/dev/null \
      | awk '/priv:/{f=1;next}/pub:/{f=0}f' | tr -d ' :\n' | sed 's/^00//')
mcp-publisher login dns --domain blackswancausallabs.com --algorithm ecdsap384 --private-key "$KEY"
unset KEY
```

Two things that cost time the first time: the registry caps `description` at
100 characters, and it verifies PyPI ownership through the `mcp-name` comment
in the README — so **PyPI must be uploaded before the registry publish**, or
validation fails.

## The tool surface (9 tools)

| Group | Tool | Notes |
|---|---|---|
| Spec | `get_spec` | optional introspection; `detail='compact'\|'full'` |
| Ingest | `parse_document` | PDF/docx/text + supplements; returns hash + cue survey |
| | `parse_pmcid` | Europe PMC; **untested against the live API** |
| Setup | `set_prespecified_confounders` | P1, review-scoped, **blocks domain 1** |
| | `specify_result` | A1/A2/A3, C1-C3, D1, section B, and **C4** |
| Assess | `assess_result` | `domain=0` overview, `domain=1..6` scaffold |
| | `submit_answers` | per domain; `domain=0` finalizes and renders |
| Render | `render_report` | re-render of the stamped artifact |
| Review | `export_robvis` | many runs' records -> one robvis CSV; read its `losses` |

Three things are enforced at `submit_answers` and are the point of the layer:
quotes resolve to offsets in the ingested bundle or are rejected with the nearest
actual text; absence claims are backed by a search the *server* runs from a named
cue; judgements are computed by the algorithm and cannot be asserted by the caller.
An unanswered question on the traversal path returns `status='incomplete'` naming
it rather than failing.

## The pipeline

```
1  parse_document / build_bundle    PDF + supplement → SectionMap      deterministic
2  detect_cues                      where to look, per domain          deterministic
3  answer signalling questions      quotes copied from full_text       MODEL
4  bind_evidence                    quotes → offsets, or REJECT        deterministic
5  algorithms                       answers → domain → overall         deterministic
6  report + render                  stamped artifact                   deterministic
7  human ratification               P1, reviewer-prior answers, overrides
```

The model's contribution is bounded at step 3. It cannot compute a judgement
(step 5 does) and cannot invent evidence (step 4 rejects it).

## Verified end to end on a real paper

`examples/dickerman_2022.py` — Dickerman et al., *Comparative Effectiveness of
BNT162b2 and mRNA-1273 Vaccines in U.S. Veterans*, NEJM 2022;386:105-15. Scored
from the article + Supplementary Appendix, one result (24-week risk difference
for documented infection, alpha period).

Outcome: **low, except for concerns about uncontrolled confounding**. All 26
quotes bind (24 exact, 1 hyphen_relaxed, 1 refs_stripped). 24 of 41 signalling
questions were never reached — the algorithm's branching decided that, not the
assessor.

Three things that run surfaced, worth knowing:
- The paper's Table S1 labels its estimand "observational analogue of the
  per-protocol effect", but no censoring or follow-up partitioning at deviation
  occurs, so **C4 = No and domain 1 variant A applies**. A reviewer taking the
  label at face value would have run variant B and answered five different
  questions.
- Domain 1 was unanswerable without P1. The proposed confounder list sits in the
  ratification queue, unratified. The substantive finding is that the matching
  set was deliberately coarsened from VA station to VISN, and brand availability
  is a station-level phenomenon.
- Domain 6 came out low despite no registered protocol: 6.1 = NI, but 6.2–6.4 all
  N, and the published bands only escalate on evidence of selection from
  multiples. Correct per the algorithm, and a likely override point.

## Second verified assessment (2026-08-03)

`examples/jabagi_2026_server_run.py` — Jabagi et al., *Maternal RSVpreF
Immunisation Against Infant RSV Hospitalisation*, Lancet Reg Health Eur
2026;67:101756. Scored from the article + appendix, one result (weighted HR 0.50
for RSV-LRTI hospitalisation over the first season), driven entirely through the
MCP tools.

Outcome: **serious**, on domain 1. All 26 quotes bound on the exact pass. 13 of
35 questions never reached. Three things it surfaced:
- Domain 1 reaches serious through **1.3, not 1.1**. Confounding *coverage* is
  good — exact matching on date of birth removes the calendar-time confounding
  that has dogged every other RSVpreF study. But gestational age at birth and
  birth weight are matched and weighted on despite being realised *after*
  maternal vaccination, and whether RSVpreF affects gestational duration is the
  open safety question that confined the French campaign to 32-36 weeks. With no
  negative control or bias analysis run, nothing bounds what that adjustment did.
  A reviewer who judges gestational age unaffected answers 1.3 = N and the domain
  drops to moderate; that is the override point and it is recorded as one.
- Domain 3 is **moderate on the nirsevimab exclusion**: infants who received the
  competing prophylaxis are excluded, nirsevimab is given after time zero, and it
  is a substitute for maternal vaccination — so the exclusion falls
  disproportionately on the unvaccinated. 147,127 of 195,340 live births removed.
- 6.1 = NI is an artefact of **what we chose to ingest**: the study is registered
  (EPI-PHARE T-2025-08-637) but the record was not retrieved. Retrieving it would
  settle 6.1 on evidence rather than on absence.

The run also found a real bug — an agent-proposed P1 was not entering the
ratification queue. Fixed; see DECISIONS.md 2026-08-03.

## Across runs: the record (added 2026-08-03)

**A review of N studies is N runs.** Each assessment costs a session — the model
reads one paper and answers signalling questions against it — and this server
keeps NO state between runs. So the interchange unit is not server memory and
not an `Assessment` object; it is a **record**: the small, flat, JSON-native
summary `submit_answers(domain=0)` returns alongside the report.

```
session 1..N   assess one result -> save submit_answers(domain=0)['record']
later          export_robvis(records=[...]) -> one figure-ready CSV
```

~4 KB each, so a normal review's worth fits in one context (see DECISIONS.md for
the limit at 200+). Each record carries its own provenance — text hash,
algorithm fingerprint, spec version, source status, ratification state — so a
row in the resulting figure traces back to a document rather than being an
anonymous coloured square. That also lets the export notice when a set mixes
algorithm transcriptions and warn that the judgements are not comparable.

`export_robvis` is not a column dump. Its default `layout="robins_i"` places
each V2 judgement into its correct **V1 slot** — V1 has seven domains and orders
selection *before* classification, which V2 swaps — and marks the dropped
deviations domain NA. A positional dump would parse, plot, and lie. Always read
the returned `losses`: unratified records, mixed C4 variants, equal weighting,
mixed fingerprints, and the fact that `low_except_confounding` cannot survive
robvis's five-fill palette.

`examples/review_from_records.py` runs the whole loop: two papers assessed
independently, records written to disk, then aggregated *from files* with no
server state involved.

## NEXT

- **Drive it over stdio from a real client.** Published and installable, but
  every exercise so far has been in-process or through `mcp.call_tool` — that
  validates the output schemas, which is not the same as a real client session.
  This is the first thing to do next.
- **Exercise `parse_pmcid` against the live Europe PMC API.** The port is a
  straight lift and the code path is unchanged from target-mcp, but it has not
  been run here.
- **`render_report_docx`** — deliberately not built. The target-mcp docx renderer
  is shaped around a checklist table and does not transfer to a
  domain/judgement/support document; this needs its own renderer, not a port.
- **Corpus tools** (`aggregate_corpus`, `build_coding_sheet`,
  `validate_against_gold`) — also deliberately not built. They are written
  against TARGET's leaf/verdict data model, not a domain/judgement one, so these
  are rewrites rather than ports. Needed before any gold-standard validation.
- **Migrate to `mcp` 2.0** (`MCPServer` replaces `FastMCP`), for both servers together.
- **Fan-out skill** — serial preliminaries and confounding table, then six domain
  subagents in parallel, then deterministic evaluation. All MCP calls stay with
  the orchestrator; subagents are pure scorers with no server reachability (same
  rule as `target-checklist-fanout`). The tool itself requires preliminaries be
  agreed before assessors work individually, so the structure is not an
  imposition on it.
- **A confounding-factor table.** The spec defines a rich per-factor row schema
  (measured variables, controlled Y/N, measured validly, control demonstrably
  unnecessary, expected direction). The server currently carries P1 as a list of
  strings only. This is the largest remaining gap against the published tool.
- **Version control.** This directory is still not a git repo. Now that the
  server exists and two assessments depend on the algorithm fingerprint, that is
  overdue.
- **Diff the Nov 2024 release against Nov 2025.** riskofbias.info archives the
  earlier one. Cheapest unexploited check we have: it shows which parts of the
  tool are still moving, and gives a second rendering of the same raster
  flowcharts to trace against — the only independent check on the tracing that
  does not require anyone else's cooperation. Do this BEFORE contacting the
  development group; it sharpens the questions worth asking.
- **Watch for a source revision.** The stamp records that we built against a
  draft, but nothing detects a new release. Re-check riskofbias.info before
  relying on an assessment; bump `spec_version` if the content moves.
- **Contact the ROBINS-I development group** (Sterne, Higgins et al., via
  riskofbias.info). Three things at once now: a possible wording grant, an
  independent cross-check of the hand-traced algorithms, and whether a
  non-follow-up variant is planned (it would need its own spec and its own
  algorithms, not an extension of this one).
- **Gold-standard validation.** Cochrane reviews publish ROBINS-I tables, but
  almost all are **V1**, and V2 restructured the domains (dropped "deviations
  from intended interventions", added variant A/B). Validate on overlapping
  domains only, or dual-code a fresh sample.

## Licensing position (settled — do not re-open casually)

ROBINS-I V2 is **CC BY-NC-ND 4.0**, stricter than TARGET's BY-ND. Consequences,
all already reflected in the code:

- Spec carries **own-words intent only**. No signalling-question wording appears
  anywhere in this repo. Verified by n-gram check against the source PDF.
- There is deliberately **no `OFFICIAL_TEXT` mapping** and no projection onto a
  published form. The TARGET pattern does not transfer.
- **Algorithms are decision logic**, not prose, and are not restricted the way
  wording is.
- Because no licensed material ships, the NC clause never attaches to the
  software — a BSCL-branded, commercially-used tool is fine. Trademark, not
  copyright, is the live constraint: nominative use ("assessed using the
  ROBINS-I V2 framework") is fine; logos, "official", "certified", or a layout
  mimicking riskofbias.info's own output are not.

See `docs/DECISIONS.md` (2026-07-29 entry) for the full reasoning.
