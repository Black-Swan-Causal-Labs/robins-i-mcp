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

## Where to pick up

The honest gap: **published and installable, never driven over stdio from a real
client.** Everything so far has been in-process or through `mcp.call_tool`,
which validates output schemas but is not a client session. That is the top item
in STATUS.md NEXT.

Then, per the user: announce it — a page on the BSCL website and a LinkedIn
post. Both need the framing this repo has been careful about everywhere else:
the instrument is a **draft**, the algorithms are hand-traced and externally
unverified, and no assessment is final until a human ratifies. An announcement
that drops those qualifications would undo the thing that makes the tool
defensible.
