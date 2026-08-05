# Session notes — 2026-08-04 (publication)

Continues `SESSION-NOTES-2026-08-03.md`, which covers building the server. This
half is naming, publication, and two credential mistakes worth not repeating.

## What shipped

| | |
|---|---|
| GitHub | https://github.com/Black-Swan-Causal-Labs/robins-i-mcp (public) |
| PyPI | `robins-i-mcp` 0.1.0 |
| MCP registry | `com.blackswancausallabs/robins-i-mcp`, status `active` |

Before pushing, three things were fixed that would have been permanent
afterwards: the examples hardcoded an absolute path under the author's home
directory (now `examples/_papers.py`, overridable with `ROBINS_MCP_PAPERS`);
`pyproject.toml` declared a `readme` that did not exist, so the wheel metadata
had no description at all; and `license = "Apache-2.0"` was declared with no
LICENSE file to back it.

## The naming argument, which took three passes

Started as `robins-mcp`, matching the sibling `target-mcp`.

**First challenge — should it say v2?** Argued no: the instrument version is
carried by the SPEC (`robins-i-v2-cohort-0.1.0.yaml`), and TRANSCRIPTION-NOTES
already says a variant for other designs gets its own spec file, not its own
package. So the package is deliberately a container for versioned specs, and
naming it after one spec would be wrong the day a second lands.

**Second challenge, and the one that landed — "there's so many other robins
tools".** Correct, and it exposed that the first argument was applied at the
wrong granularity. ROBINS-I (interventions) and ROBINS-E (exposures) are
different published tools. `robins-mcp` claimed the family for one member of it
and would have become actively confusing the day a ROBINS-E server existed —
plausible, since it is the same shape.

Landed on **specific about the instrument, generic across its versions**:
`robins-i-mcp`, with `robins-e-mcp` left free. Version discoverability is
handled where it bites — the registry title is "ROBINS-I V2 MCP" and the
description leads "ROBINS-I V2 (not V1)". The rename touched the distribution,
entry point, import package, registry name and the extractor string stamped
into every report's provenance. Free at that moment; an hour later it would not
have been.

## Two credential mistakes

**The one I made.** Told the user to pipe `target-mcp/.keyfile` into
`mcp-publisher --private-key`, having inferred from the filename and the
gitignore context that it was the DNS signing key. It was an **Anthropic API
key** for target-mcp's judge mode. The login failed on `invalid hex byte 's'`,
which is how it surfaced.

Verified afterwards that nothing leaked: never committed to any of nine local
repos, absent from both PyPI artifacts, and absent from shell history (zsh
stores the literal `"$(cat …)"`, not the expansion). It was passed as a process
argument, so briefly visible to local `ps` — low severity on a single-user
machine. Renamed to `.anthropic-api-key`; note `*.key` did **not** match a name
ending in `-key`, so the ignore patterns needed widening.

The check that would have prevented this, and which later confirmed the right
key: **derive the public half and compare it against the DNS TXT record.**

**The one that was just cost.** The real key was in
`~/.config/mcp-publisher/bscl-mcp-dns-key.pem` all along, alongside an expired
`token.json`. It is a PEM; `mcp-publisher` wants raw hex; and OpenSSL emits 49
bytes for a 48-byte P-384 key because it prepends `00`. Strip it. Command in
STATUS.md.

## Publication mechanics worth not rediscovering

- **PyPI must precede the registry publish.** The registry proves ownership by
  finding an `mcp-name:` comment in the PyPI long_description, so the package
  has to be up there first. The other order fails validation with no useful hint.
- **`description` is capped at 100 characters.** The first attempt was 290 and
  returned 422.
- The 401 that followed was just the expired token from the target-mcp publish,
  not an authorization problem.

## Copyright, after a good question

The user spotted `Copyright [yyyy] [name of copyright owner]` in LICENSE and
asked whether it should carry their details. It should not: that sits under the
appendix *"How to apply the Apache License to your work"* and is a template, not
a blank. Canonical licence text stays verbatim; editing it creates exactly the
ambiguity a standard licence removes.

The real assertion was already in NOTICE (`Copyright 2026 Black Swan Causal
Labs`) and ships in the wheel via `license-files`. Confirmed BSCL is the holder.

Added SPDX headers to the ten package modules for one specific reason rather
than convention: **`algorithms.py` is the file most likely to be lifted on its
own**, being the only machine-readable transcription of flowcharts that exist
elsewhere purely as raster images. Detached from the repo it would carry no
owner, no licence, and no signal that it was hand-traced from a draft and is
externally unverified.

## Announcement: website live, posts drafted

`robins-i-mcp.html` is live on blackswancausallabs.com, built on the TARGET
page's own stylesheet and wired into the AI Toolkit dropdown, mobile menu,
footer column and homepage grid across thirteen pages. Three commits in the
website repo (`a0e1d60`, `3fa4d41`, `4cfdcdb`).

Three judgement calls there worth knowing:

- **The hero and card use the SYNTHETIC example**, labelled as such. The Jabagi
  assessment is more compelling but publicly grades a named 2026 Lancet paper as
  serious. Defensible in a methods repository; not what belongs on a marketing
  page.
- **Two crops, not one.** The full report for the hero, a tight crop on the
  title block for the card, which otherwise reads as grey noise at thumbnail
  size.
- **The disclaimer sits in the meta strip**, not buried. More prominent than a
  typical product page, deliberately.

The user then asked for em dashes removed from that page (eleven, rewritten
per-sentence rather than swapped, since several clauses were already comma-heavy)
and reworded the hero and In Brief. "Model" became "agent" throughout, including
the meta description, after the user pointed out the page's own diagram already
said "LLM agent". The lede also had an orphan reference to "the flowchart"
without ever saying ROBINS-I publishes one.

LinkedIn posts are **drafted, not published**: a Black Swan announcement and a
personal reshare carrying the Jabagi use case. The user edited both. Two things
were pushed back on and accepted: "automates this tool" contradicted the post's
own closing line about the epi in the loop, and the personal post named a paper
without carrying the draft/unratified caveats the company post had.

## Three ecosystem facts, checked late and consequential

Prompted by the user asking whether "by hand" was a fair claim.

1. **No official ROBINS-I V2 implementation exists, and none is announced.** An
   earlier note in this project said the group had one in development with
   algorithm-derived judgements. That was wrong or stale. It matters because the
   verification plan was "check against the official implementation when it
   ships" — there is no such timetable, so contacting the development group is
   now the only external check available.
2. **robvis is no longer supported.** riskofbias.info: "we are no longer able to
   support robvis or any Excel tool implementations." `export_robvis` targets a
   renderer its authors' host has stepped back from. It still works and is still
   what reviewers recognise, but the argument that removed `render_review.py`
   ("robvis is the figure") is weaker than it was on 2026-08-03.
3. **Nothing automates ROBINS-I assessment.** Automation exists for randomized
   trial tools (RobotReviewer, ROBoto2), both RCT-only. What exists for ROBINS-I
   is review-management software that captures judgements in a form.

## A methodological exchange that found a real gap

The user asked why domain 1 came out serious, then whether it was immortal time
bias. It isn't: exposure is fixed before time zero, follow-up starts at birth,
and no exposed infant accrues time during which the outcome could not occur.
Domain 3's 3.1 answered `Y` on exactly that basis and it stands.

But the question was pointing at something real. Between vaccination and birth
the pregnancy can leave the cohort, and the cohort is restricted to live births,
which is a post-exposure event. That is **live-birth selection**, a collider
problem, not immortal time.

**Two defects in the Jabagi 3.3 rationale, found this way and NOT yet fixed:**

- Live-birth conditioning is never named. The phrase "live births" appears only
  as a denominator.
- The rationale says the exclusions rest on "information that only exists after
  time zero". True for nirsevimab, wrong for the 14-day rule, which turns on the
  vaccination-to-delivery interval — post-exposure but realised AT time zero.

Neither changes an answer (3.3 is already `Y`, 3.4 `Y`, 3.5 `PN`, domain 3 stays
moderate), but the rationale is what a reader checks, and it currently
under-describes and partly mislabels the problem. See NEXT.

## Where to pick up

The honest gap remains: **published and installable, never driven over stdio
from a real client.** Everything so far has been in-process or through
`mcp.call_tool`, which validates output schemas but is not a client session.

Then the two small corrections above, and the graphic for the announcement,
which was offered and never built.
