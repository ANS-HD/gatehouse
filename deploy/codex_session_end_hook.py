#!/usr/bin/env python3
"""Start a detached Gatehouse upload for the current Codex session transcript."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    transcript = event.get("transcript_path")
    if not isinstance(transcript, str) or not Path(transcript).is_file():
        return 0

    codex_home = Path.home() / ".codex"
    log_path = codex_home / "gatehouse-upload.log"
    uploader = Path(__file__).with_name("upload_codex_logs.py")
    with log_path.open("ab") as log:
        subprocess.Popen(
            [
                sys.executable,
                str(uploader),
                "--url",
                args.url,
                "--file",
                transcript,
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
