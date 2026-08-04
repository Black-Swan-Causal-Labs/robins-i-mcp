import os
from pathlib import Path

#: Where the assessed PDFs live. These are published articles, not ours to
#: redistribute, so they are not in this repository — point this at your own
#: copies. Defaults to a `papers/` directory beside the repo.
PAPERS = Path(os.environ.get(
    "ROBINS_MCP_PAPERS", Path(__file__).resolve().parents[1] / "papers"))


def require(*filenames: str) -> None:
    """Fail with something actionable rather than a bare FileNotFoundError."""
    missing = [f for f in filenames if not (PAPERS / f).exists()]
    if missing:
        raise SystemExit(
            f"Missing from {PAPERS}: {missing}\n"
            "These are published articles and are not distributed with this "
            "repository. Put your own copies there, or set ROBINS_MCP_PAPERS to "
            "the directory holding them."
        )
