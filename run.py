#!/usr/bin/env python
"""Launch the OmniScribe web app and open it in the browser.

    python run.py                # start server + open browser
    python run.py --no-browser   # start server only
    python run.py --port 9000
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from omniscribe import capabilities, config  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="OmniScribe — Reads. Listens. Teaches.")
    ap.add_argument("--host", default=config.WEB_HOST)
    ap.add_argument("--port", type=int, default=config.WEB_PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    config.ensure_dirs()
    print("=" * 58)
    print("  OmniScribe — Reads. Listens. Teaches.")
    print("=" * 58)
    for line in capabilities.summary_lines():
        print("  " + line)
    url = f"http://{args.host}:{args.port}"
    print("-" * 58)
    print(f"  Open: {url}")
    print("=" * 58)

    if not args.no_browser:
        def _open():
            time.sleep(1.4)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    import uvicorn

    uvicorn.run("omniscribe.web.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
