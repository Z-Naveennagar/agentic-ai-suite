"""
Grader *families* — reusable templates that let skill authors fill structured
inputs instead of writing core graders by hand.

A family is a **pure spec-expander**: given the author's structured params it
returns a list of CORE grader specs (each a dict carrying a ``type`` that is
registered in ``GRADER_REGISTRY``). Families contain NO grading logic — all
judging stays in the core graders.

Author-facing YAML (in a case's ``grading_spec.yaml``)::

    graders:
      - family: violation        # instead of `type:`
        id: verdict
        verdict: NO
      - family: tool-execution
        id: usage
        sequence: [Read]
        matching: any_order_match
      - id: no_tool_errors        # raw core graders are still allowed
        type: content_contains
        source: stderr
        substring: "ERROR:"
        must_not_contain: true

The case loader calls :func:`expand_graders` to splice family entries into the
flat list of core grader specs the runner already understands; the runner,
``GRADER_REGISTRY`` and the DB schema are untouched.
"""

from __future__ import annotations

import abc
from typing import Any


# -- base + registry --------------------------------------------------------


class Family(abc.ABC):
    family_type: str = ""
    # Author fields that must be present; checked by :meth:`validate`.
    required: tuple[str, ...] = ()

    def validate(self, params: dict) -> None:
        missing = [k for k in self.required if params.get(k) is None]
        if missing:
            raise ValueError(
                f"family {self.family_type!r}: missing required field(s): "
                + ", ".join(missing)
            )

    @abc.abstractmethod
    def expand(self, params: dict, meta: dict) -> list[dict]:
        """Return a list of CORE grader specs (dicts with a ``type`` key)."""


FAMILY_REGISTRY: dict[str, Family] = {}


def register_family(instance: Family) -> None:
    FAMILY_REGISTRY[instance.family_type] = instance


def get_family(name: str) -> Family:
    if name not in FAMILY_REGISTRY:
        raise KeyError(
            f"unknown grader family: {name!r} "
            f"(known: {', '.join(sorted(FAMILY_REGISTRY)) or 'none'})"
        )
    return FAMILY_REGISTRY[name]


# -- expansion --------------------------------------------------------------


# Keys the family layer manages on a spec; not passed as grader params but
# kept for grouping / provenance in the dashboard.
_PROVENANCE_KEYS = ("_family",)


def expand_graders(graders: list[Any], meta: dict | None = None) -> list[dict]:
    """Expand any ``family:`` entries into core grader specs.

    Raw ``type:`` graders pass through unchanged. Each child spec produced by a
    family gets a namespaced id (``<family-id>.<child-id>``) and a ``_family``
    tag. Raises ``ValueError``/``KeyError`` on a bad family entry so the loader
    can surface a clear schema error.
    """
    meta = meta or {}
    out: list[dict] = []
    for g in graders:
        if not isinstance(g, dict):
            out.append(g)
            continue
        fam_name = g.get("family")
        if not fam_name:
            out.append(g)
            continue

        fam = get_family(fam_name)
        fam.validate(g)
        fam_id = g.get("id", fam_name)
        children = fam.expand(g, meta)
        if not children:
            raise ValueError(
                f"family {fam_name!r} (id={fam_id!r}) expanded to zero graders"
            )
        for child in children:
            spec = dict(child)
            spec["id"] = f"{fam_id}.{spec.get('id', 'check')}"
            spec.setdefault("_family", fam_name)
            out.append(spec)
    return out


# -- side-effect: register the built-in families ----------------------------

from . import violation as _violation  # noqa: E402,F401
from . import tool_execution as _tool_execution  # noqa: E402,F401
