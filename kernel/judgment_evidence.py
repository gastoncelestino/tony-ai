"""Prepare judgment records without weakening Task Graph evidence authority."""
from __future__ import annotations

from collections.abc import Mapping

from .evidence_lineage import validate_evidence_refs
from .task_graph import TaskStateGraph


def prepare_judgment_record(
    graph: TaskStateGraph,
    task_id: str,
    record: Mapping[str, object],
) -> dict[str, object]:
    """Return a judgment record whose evidence refs are graph-validated.

    Judgment Memory remains a persistence layer: it receives a copy of the
    record only after the Task State Graph validates its evidence lineage.
    """
    raw_refs = record.get("evidence_refs", ())
    if isinstance(raw_refs, str):
        raise ValueError("judgment evidence_refs must be a sequence, not a string")
    refs = tuple(raw_refs) if raw_refs else ()
    if not all(isinstance(ref, str) and ref for ref in refs):
        raise ValueError("judgment evidence_refs must contain non-empty strings")

    validated = validate_evidence_refs(graph, task_id, refs)
    prepared = dict(record)
    prepared["evidence_refs"] = list(validated)
    return prepared


__all__ = ["prepare_judgment_record"]
