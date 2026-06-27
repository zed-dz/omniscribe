"""High-level dissection: text -> structured schema -> educational asset files."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from . import assets, extract

DEFAULT_ASSETS = ["guidebook", "infographic", "flashcards", "quiz", "mindmap"]


@dataclass
class DissectResult:
    schema: dict
    method: str
    files: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "method": self.method,
            "files": {k: Path(v).name for k, v in self.files.items()},
            "file_paths": self.files,
            "seconds": self.seconds,
        }


class DissectPipeline:
    def process(
        self,
        text: str,
        *,
        out_dir: str | Path | None = None,
        base_name: str = "study_materials",
        which: list[str] | None = None,
        use_llm: bool = True,
        model: str | None = None,
    ) -> DissectResult:
        if not text or not text.strip():
            raise ValueError("No text provided to dissect")

        started = time.time()
        config.ensure_dirs()
        out_dir = Path(out_dir) if out_dir else config.OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        which = which or DEFAULT_ASSETS

        schema, method = extract.extract(text, use_llm=use_llm, model=model)

        files: dict[str, str] = {}
        for name in which:
            gen = assets.GENERATORS.get(name)
            if not gen:
                continue
            func, ext = gen
            path = out_dir / f"{base_name}_{name}.{ext}"
            files[name] = func(schema, path)

        return DissectResult(
            schema=schema, method=method, files=files,
            seconds=round(time.time() - started, 2),
        )

    def extract_only(self, text: str, use_llm: bool = True, model: str | None = None) -> tuple[dict, str]:
        return extract.extract(text, use_llm=use_llm, model=model)
