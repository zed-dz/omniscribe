#!/usr/bin/env python
"""OmniScribe unified command-line interface.

    python cli.py caps
    python cli.py ocr book.pdf --lang ara --preset balanced --pages 1-5
    python cli.py transcribe voice.ogg --lang en
    python cli.py dissect notes.txt --assets guidebook,flashcards,mindmap
    python cli.py pipeline scan.pdf
    python cli.py models list
    python cli.py models download ar
    python cli.py serve --port 8000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from omniscribe import capabilities, config, services  # noqa: E402
from omniscribe.transcribe import model_manager  # noqa: E402


def _bar(frac, msg):
    width = 30
    filled = int(width * max(0.0, min(1.0, frac)))
    sys.stdout.write(f"\r  [{'█' * filled}{'·' * (width - filled)}] {int(frac*100):3d}%  {msg[:40]:<40}")
    sys.stdout.flush()
    if frac >= 1.0:
        sys.stdout.write("\n")


def _print_files(files: dict):
    print("\n  Output files:")
    for kind, name in files.items():
        print(f"    {kind:12s} {config.OUTPUT_DIR / name}")


def cmd_caps(_args):
    print("\n".join(capabilities.summary_lines()))


def cmd_ocr(args):
    pr = None
    if args.pages:
        if "-" in args.pages:
            a, b = args.pages.split("-", 1)
            pr = (int(a) - 1, int(b))
        else:
            n = int(args.pages)
            pr = (n - 1, n)
    res = services.run_ocr(
        args.file, lang=args.lang, preset=args.preset, page_range=pr,
        prefer_embedded=not args.no_embedded, deskew=args.deskew, denoise=args.denoise,
        remove_diacritics=args.diacritics,
        formats=set(args.formats.split(",")) if args.formats else None,
        progress=_bar,
    )
    print(f"\n  Pages: {res['page_count']} | words: {res['stats']['words']} | "
          f"chars: {res['stats']['characters']} | {res['seconds']}s | engine: {res['engine']}")
    print("\n  --- preview ---")
    print("  " + res["text"][:500].replace("\n", "\n  "))
    _print_files(res["files"])


def cmd_transcribe(args):
    if not model_manager.is_installed(args.lang):
        print(f"  Speech model '{args.lang}' not installed — downloading…")
    res = services.run_transcribe(args.file, lang=args.lang, progress=_bar)
    print(f"\n  Words: {res['word_count']} | duration: {res['duration']}s | {res['seconds']}s")
    print("\n  --- transcript ---")
    print("  " + res["text"][:800].replace("\n", "\n  "))
    _print_files(res["files"])


def cmd_dissect(args):
    if args.file == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.file).read_text(encoding="utf-8", errors="ignore")
    res = services.run_dissect(
        text, which=args.assets.split(",") if args.assets else None,
        use_llm=not args.no_llm, base_hint=Path(args.file).stem if args.file != "-" else "study",
        progress=_bar,
    )
    p = res["preview"]
    print(f"\n  Method: {res['method']} | {res['seconds']}s")
    print(f"  Title: {p['title']}")
    print(f"  Concepts {p['counts']['concepts']} · Flashcards {p['counts']['flashcards']} · "
          f"Quiz {p['counts']['quiz']} · Branches {p['counts']['mindmap_branches']}")
    if res.get("llm_error"):
        print(f"  (AI fallback: {res['llm_error']})")
    _print_files(res["files"])


def cmd_pipeline(args):
    res = services.run_pipeline(
        args.file, ocr_lang=args.lang, ocr_preset=args.preset, stt_lang=args.stt_lang,
        which=args.assets.split(",") if args.assets else None, use_llm=not args.no_llm,
        progress=_bar,
    )
    print(f"\n  Stage: {res['stage_kind']}")
    if res.get("warning"):
        print("  " + res["warning"])
    stage = res["stage"]
    print("  Extracted text preview:")
    print("  " + (stage.get("text", "")[:400]).replace("\n", "\n  "))
    if stage.get("files"):
        _print_files(stage["files"])
    if res.get("dissect"):
        print("\n  Study materials:")
        _print_files(res["dissect"]["files"])


def cmd_models(args):
    if args.action == "list":
        for lang, spec in config.VOSK_MODELS.items():
            mark = "✓ installed" if model_manager.is_installed(lang) else "  not installed"
            print(f"  {lang:4s} {mark}  {spec['label']}")
    elif args.action == "download":
        if not args.lang:
            print("  Specify a language code, e.g. 'models download en'")
            return
        model_manager.download_model(args.lang, progress=lambda msg, pct: _bar(pct / 100.0, msg))
        print(f"  Model '{args.lang}' ready.")


def cmd_serve(args):
    import uvicorn
    print("\n".join("  " + l for l in capabilities.summary_lines()))
    print(f"  Serving on http://{args.host}:{args.port}")
    uvicorn.run("omniscribe.web.app:app", host=args.host, port=args.port, log_level="info")


def build_parser():
    p = argparse.ArgumentParser(prog="omniscribe", description="OmniScribe — Reads. Listens. Teaches.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("caps", help="Show engine capabilities").set_defaults(func=cmd_caps)

    o = sub.add_parser("ocr", help="Extract text from a PDF/image")
    o.add_argument("file")
    o.add_argument("--lang", default=config.DEFAULT_OCR_LANG)
    o.add_argument("--preset", default=config.DEFAULT_OCR_PRESET, choices=list(config.OCR_PRESETS))
    o.add_argument("--pages", default="")
    o.add_argument("--formats", default="")
    o.add_argument("--no-embedded", action="store_true", help="Force OCR even if a text layer exists")
    o.add_argument("--deskew", action="store_true")
    o.add_argument("--denoise", action="store_true")
    o.add_argument("--diacritics", action="store_true", help="Remove Arabic diacritics")
    o.set_defaults(func=cmd_ocr)

    t = sub.add_parser("transcribe", help="Transcribe an audio file")
    t.add_argument("file")
    t.add_argument("--lang", default=config.DEFAULT_STT_LANG)
    t.set_defaults(func=cmd_transcribe)

    d = sub.add_parser("dissect", help="Turn text into study materials")
    d.add_argument("file", help="Text file, or '-' for stdin")
    d.add_argument("--assets", default="")
    d.add_argument("--no-llm", action="store_true")
    d.set_defaults(func=cmd_dissect)

    pl = sub.add_parser("pipeline", help="Document/audio -> text -> study materials")
    pl.add_argument("file")
    pl.add_argument("--lang", default=config.DEFAULT_OCR_LANG, help="OCR language")
    pl.add_argument("--preset", default=config.DEFAULT_OCR_PRESET, choices=list(config.OCR_PRESETS))
    pl.add_argument("--stt-lang", default=config.DEFAULT_STT_LANG)
    pl.add_argument("--assets", default="")
    pl.add_argument("--no-llm", action="store_true")
    pl.set_defaults(func=cmd_pipeline)

    m = sub.add_parser("models", help="Manage speech models")
    m.add_argument("action", choices=["list", "download"])
    m.add_argument("lang", nargs="?", default="")
    m.set_defaults(func=cmd_models)

    s = sub.add_parser("serve", help="Run the web UI")
    s.add_argument("--host", default=config.WEB_HOST)
    s.add_argument("--port", type=int, default=config.WEB_PORT)
    s.set_defaults(func=cmd_serve)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
