"""Vosk transcription engine — offline, CPU-friendly, with word-level timestamps."""
from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from typing import Callable

from . import model_manager

ProgressCb = Callable[[float, str], None] | None


@dataclass
class Word:
    word: str
    start: float
    end: float
    conf: float


class VoskEngine:
    name = "vosk"

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._model = None
        self._model_dir = None

    def ensure_model(self, progress=None):
        path = model_manager.model_path(self.lang)
        if path is None:
            path = model_manager.download_model(
                self.lang,
                progress=(lambda msg, pct: progress(pct / 100.0, msg)) if progress else None,
            )
        if self._model is None or self._model_dir != str(path):
            import vosk
            from vosk import Model

            vosk.SetLogLevel(-1)  # silence the verbose Kaldi/Vosk decoder logs
            self._model = Model(str(path))
            self._model_dir = str(path)
        return self._model

    def transcribe_wav(self, wav_path: str, progress: ProgressCb = None) -> dict:
        """Transcribe a 16 kHz mono PCM WAV. Returns {text, words:[...]}.

        Words carry start/end times and confidence so subtitles can be built.
        """
        from vosk import KaldiRecognizer

        model = self.ensure_model(progress=progress)

        wf = wave.open(wav_path, "rb")
        try:
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)

            total_frames = wf.getnframes() or 1
            read = 0
            words: list[Word] = []
            chunks: list[str] = []

            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                read += 4000
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    chunks.append(res.get("text", ""))
                    for w in res.get("result", []):
                        words.append(Word(w["word"], w["start"], w["end"], w.get("conf", 1.0)))
                if progress:
                    progress(min(0.99, read / total_frames), "Transcribing")

            final = json.loads(rec.FinalResult())
            chunks.append(final.get("text", ""))
            for w in final.get("result", []):
                words.append(Word(w["word"], w["start"], w["end"], w.get("conf", 1.0)))
        finally:
            wf.close()

        text = " ".join(c for c in chunks if c).strip()
        if progress:
            progress(1.0, "Done")
        return {"text": text, "words": [w.__dict__ for w in words]}
