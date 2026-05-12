"""Python-owned recorder for deterministic research tool outputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


SourceRecord = dict[str, str | None]
EvidenceArtifactRecord = dict[str, str | int | None]


@dataclass
class ResearchRunRecorder:
    """Collect deterministic search metadata across one research agent run."""

    sources_by_url: dict[str, SourceRecord] = field(default_factory=dict)
    evidence_artifacts_by_url: dict[str, EvidenceArtifactRecord] = field(default_factory=dict)
    search_attempts: int = 0

    def record_search_results(
        self,
        sources: list[SourceRecord],
        evidence_artifacts: list[EvidenceArtifactRecord],
    ) -> None:
        self.search_attempts += 1
        artifacts_by_path = {
            artifact["path"]: artifact
            for artifact in evidence_artifacts
            if isinstance(artifact.get("path"), str)
        }
        for source in sources:
            merged_source = self.record_source(source)
            raw_content_path = merged_source.get("raw_content_path")
            normalized_url = merged_source.get("normalized_url")
            artifact = artifacts_by_path.get(raw_content_path)
            if isinstance(normalized_url, str) and artifact:
                self.evidence_artifacts_by_url[normalized_url] = dict(artifact)

    def record_source(self, source: SourceRecord) -> SourceRecord:
        normalized_url = source["normalized_url"]
        if normalized_url is None:
            return source

        existing = self.sources_by_url.get(normalized_url)
        if existing is None:
            self.sources_by_url[normalized_url] = dict(source)
            return self.sources_by_url[normalized_url]

        self.sources_by_url[normalized_url] = _merge_source(existing, source)
        return self.sources_by_url[normalized_url]

    def sources(self) -> list[SourceRecord]:
        return list(self.sources_by_url.values())

    def evidence_artifacts(self) -> list[EvidenceArtifactRecord]:
        return [
            artifact
            for normalized_url in self.sources_by_url
            if (artifact := self.evidence_artifacts_by_url.get(normalized_url)) is not None
        ]

    def provider_counts(self) -> dict[str, int]:
        return dict(
            Counter(
                provider
                for source in self.sources()
                if (provider := _string_field(source, "provider"))
            )
        )

    def domain_counts(self) -> dict[str, int]:
        return dict(
            Counter(
                domain
                for source in self.sources()
                if (domain := _string_field(source, "canonical_domain"))
            )
        )


def _merge_source(existing: SourceRecord, incoming: SourceRecord) -> SourceRecord:
    merged = dict(existing)
    for key, value in incoming.items():
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def _string_field(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    return value if isinstance(value, str) else ""
