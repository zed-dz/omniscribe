"""High-level transcription orchestration: audio file -> text + timed segments + subtitles."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

from .. import config
from . import audio, model_manager
from .engine import VoskEngine

ProgressCb = Callable[[float, str], None] | None


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    source_file: str
    text: str
    lang: str
    segments: list[Segment] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    duration: float = 0.0
    seconds: float = 0.0
    engine: str = "vosk"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["word_count"] = len(self.text.split())
        return d


def _group_words(words: list[dict], max_gap: float = 0.8, max_chars: int = 84,
                 max_dur: float = 6.0) -> list[Segment]:
    """Group recognised words into readable, subtitle-sized segments."""
    segments: list[Segment] = []
    cur: list[dict] = []
    idx = 1

    def flush():
        nonlocal idx, cur
        if not cur:
            return
        seg = Segment(
            index=idx,
            start=round(cur[0]["start"], 2),
            end=round(cur[-1]["end"], 2),
            text=" ".join(w["word"] for w in cur),
        )
        segments.append(seg)
        idx += 1
        cur = []

    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            cur_text = " ".join(x["word"] for x in cur)
            if gap > max_gap or len(cur_text) >= max_chars or (w["end"] - cur[0]["start"]) > max_dur:
                flush()
        cur.append(w)
    flush()
    return segments


def _fmt_ts(seconds: float, sep: str = ",") -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(segments: list[Segment]) -> str:
    out = []
    for seg in segments:
        out.append(str(seg.index))
        out.append(f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}")
        out.append(seg.text)
        out.append("")
    return "\n".join(out)


def to_vtt(segments: list[Segment]) -> str:
    out = ["WEBVTT", ""]
    for seg in segments:
        out.append(f"{_fmt_ts(seg.start, '.')} --> {_fmt_ts(seg.end, '.')}")
        out.append(seg.text)
        out.append("")
    return "\n".join(out)


class TranscribePipeline:
    def __init__(self, lang: str = config.DEFAULT_STT_LANG):
        self.lang = lang
        self.engine = VoskEngine(lang)

    def model_installed(self) -> bool:
        return model_manager.is_installed(self.lang)

    def ensure_model(self, progress: ProgressCb = None):
        self.engine.ensure_model(progress=progress)

    def process(self, path: str, progress: ProgressCb = None) -> Transcript:
        path = str(path)
        ext = Path(path).suffix.lower()
        if ext not in config.AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio type: {ext}")

        started = time.time()
        if progress:
            progress(0.02, "Preparing audio")
        wav = audio.to_wav16k_mono(path)
        duration = audio.wav_duration_seconds(wav)

        result = self.engine.transcribe_wav(wav, progress=progress)
        segments = _group_words(result["words"])

        return Transcript(
            source_file=path,
            text=result["text"],
            lang=self.lang,
            segments=segments,
            words=result["words"],
            duration=round(duration, 2),
            seconds=round(time.time() - started, 2),
        )
