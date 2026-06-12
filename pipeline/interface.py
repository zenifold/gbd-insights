from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class PipelineResult:
    """The output contract every pipeline implementation must satisfy."""

    artifact_path: Path  # path to the produced report (e.g. report.pdf) inside workdir
    summary: dict = field(default_factory=dict)  # structured metrics for UI/db later
    warnings: list[str] = field(default_factory=list)  # caveats (LLM validation later)


class Pipeline(Protocol):
    def __call__(self, input_path: Path, workdir: Path) -> PipelineResult: ...
