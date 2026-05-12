"""Controlled raw evidence reads for review."""

from vanguard.research.agent import filesystem_backend
from vanguard.state import AgentState

from .defaults import MAX_EVIDENCE_READ_CHARACTERS
from .models import EvidenceReadRequest


def read_selected_evidence(
    state: AgentState,
    requests: list[EvidenceReadRequest],
    *,
    remaining_reads: int,
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]]]:
    if remaining_reads <= 0:
        return [], []

    paths_by_source_id = _raw_content_paths_by_source_id(state)
    backend = filesystem_backend()
    snippets = []
    records = []
    seen_source_ids: set[str] = set()
    for request in requests:
        source_id = request.source_id.strip()
        path = paths_by_source_id.get(source_id)
        if (
            source_id in seen_source_ids
            or path is None
            or not path.startswith("/evidence/")
        ):
            continue
        seen_source_ids.add(source_id)
        read_result = backend.read(path, limit=MAX_EVIDENCE_READ_CHARACTERS)
        if read_result.error is not None:
            continue
        content = str(read_result.file_data.get("content", ""))[
            :MAX_EVIDENCE_READ_CHARACTERS
        ]
        snippets.append(
            {
                "source_id": source_id,
                "path": path,
                "reason": request.reason,
                "content": content,
                "content_characters": len(content),
            }
        )
        records.append(
            {
                "source_id": source_id,
                "path": path,
                "reason": request.reason,
                "content_characters": len(content),
            }
        )
        if len(snippets) >= remaining_reads:
            break
    return snippets, records


def _raw_content_paths_by_source_id(state: AgentState) -> dict[str, str]:
    artifact_paths = {
        artifact.get("path")
        for artifact in state.get("evidence_artifacts", [])
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
    }
    paths: dict[str, str] = {}
    for source in state.get("research_sources", []):
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        raw_content_path = source.get("raw_content_path")
        if (
            isinstance(source_id, str)
            and isinstance(raw_content_path, str)
            and raw_content_path in artifact_paths
        ):
            paths[source_id] = raw_content_path
    return paths
