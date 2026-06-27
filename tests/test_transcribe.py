import pytest

from omniscribe import capabilities
from omniscribe.transcribe import TranscribePipeline, model_manager
from omniscribe.transcribe import pipeline as tp

pytestmark = pytest.mark.skipif(
    not capabilities.snapshot()["transcribe"]["available"], reason="transcription unavailable"
)


def test_audio_conversion(speech_wav):
    from omniscribe.transcribe import audio

    wav = audio.to_wav16k_mono(speech_wav)
    assert wav.endswith(".wav")
    dur = audio.wav_duration_seconds(wav)
    assert dur > 0.5


def test_transcribe_speech(speech_wav):
    if not model_manager.is_installed("en"):
        model_manager.download_model("en")
    tr = TranscribePipeline(lang="en").process(speech_wav)
    text = tr.text.lower()
    assert "hello" in text
    assert "world" in text
    assert tr.duration > 0
    assert len(tr.words) >= 3


def test_subtitle_generation(speech_wav):
    if not model_manager.is_installed("en"):
        model_manager.download_model("en")
    tr = TranscribePipeline(lang="en").process(speech_wav)
    srt = tp.to_srt(tr.segments)
    vtt = tp.to_vtt(tr.segments)
    assert "-->" in srt
    assert vtt.startswith("WEBVTT")


def test_timestamp_format():
    assert tp._fmt_ts(3661.5) == "01:01:01,500"
    assert tp._fmt_ts(0) == "00:00:00,000"
