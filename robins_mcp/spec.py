"""Loader for the encoded ROBINS-I specification.

Exposes the own-words question labels used by the renderers. These labels are
this implementation's own wording — they are deliberately NOT the published
signalling-question text, which is not redistributable (CC BY-NC-ND). The
published question IDs are what make the output interoperable.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Mapping

import yaml

SPEC_DIR = Path(__file__).parent / "specs"
DEFAULT_SPEC = "robins-i-v2-cohort-0.1.0"


@functools.lru_cache(maxsize=4)
def load(spec_version: str = DEFAULT_SPEC) -> dict[str, Any]:
    path = SPEC_DIR / f"{spec_version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no such spec: {path}")
    spec = yaml.safe_load(path.read_text())
    _validate(spec)
    return spec


def _validate(spec: Mapping[str, Any]) -> None:
    for key in ("spec_version", "domains", "preliminaries", "response_vocabularies"):
        if key not in spec:
            raise ValueError(f"spec is missing required key {key!r}")
    vocab = spec["response_vocabularies"]
    for domain in spec["domains"]:
        for block in domain.get("variants", [domain]):
            for question in block["questions"]:
                options = question.get("response_options")
                if isinstance(options, str) and options not in vocab:
                    raise ValueError(
                        f"{question['id']}: unknown response vocabulary {options!r}"
                    )


@functools.lru_cache(maxsize=4)
def question_labels(spec_version: str = DEFAULT_SPEC) -> Mapping[str, str]:
    """Own-words labels keyed by question id.

    Domain 1's two variants reuse ids 1.1-1.3, so those are keyed with a variant
    suffix (``1.1A``, ``1.1B``) as well as plain, with variant A taking the
    unsuffixed slot only where the two agree.
    """
    spec = load(spec_version)
    labels: dict[str, str] = {}
    for domain in spec["domains"]:
        if "variants" in domain:
            for block in domain["variants"]:
                suffix = block["variant"]
                for question in block["questions"]:
                    labels[f"{question['id']}{suffix}"] = question["label"]
        else:
            for question in domain["questions"]:
                labels[question["id"]] = question["label"]
    return labels


def label_for(question: str, *, per_protocol: bool, spec_version: str = DEFAULT_SPEC) -> str:
    """Resolve a question id to its own-words label, honouring the domain 1 variant."""
    labels = question_labels(spec_version)
    if question.startswith("1."):
        return labels.get(f"{question}{'B' if per_protocol else 'A'}", question)
    return labels.get(question, question)
