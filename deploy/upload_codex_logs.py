#!/usr/bin/env python3
"""Upload changed local Codex session transcripts to Gatehouse."""

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    url: str,
    *,
    data: bytes | None = None,
    token: str | None = None,
    content_type: str = "application/json",
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data is not None else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gatehouse returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach Gatehouse: {exc.reason}") from exc
    return json.loads(body) if body else {}


def save_token(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{token}\n")
    os.chmod(path, 0o600)


def load_state(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main() -> int:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("GATEHOUSE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--email", default=os.environ.get("GATEHOUSE_EMAIL"))
    parser.add_argument("--sessions-dir", type=Path, default=codex_home / "sessions")
    parser.add_argument("--state", type=Path, default=codex_home / "gatehouse-upload-state.json")
    parser.add_argument("--token-file", type=Path, default=codex_home / "gatehouse-upload-token")
    parser.add_argument("--file", type=Path, help="upload one transcript instead of scanning")
    parser.add_argument("--configure", action="store_true", help="create and save an upload token")
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--all", action="store_true", help="upload unchanged files too")
    parser.add_argument(
        "--since-days",
        type=int,
        help="only scan transcripts modified within the last N days",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    token = args.token_file.read_text().strip() if args.token_file.exists() else ""
    if args.configure or not token:
        email = args.email or input("Gatehouse email: ").strip()
        password = (
            sys.stdin.readline().rstrip("\n")
            if args.password_stdin
            else getpass.getpass("Gatehouse password: ")
        )
        login = request_json(
            f"{base_url}/api/auth/login",
            data=json.dumps({"email": email, "password": password}).encode(),
        )
        session_token = login.get("token")
        if not isinstance(session_token, str):
            raise RuntimeError("Gatehouse login did not return a session token")
        created = request_json(f"{base_url}/api/codex/upload-token", data=b"", token=session_token)
        token = created.get("token")
        if not isinstance(token, str):
            raise RuntimeError("Gatehouse did not return a Codex upload token")
        save_token(args.token_file, token)
        print(f"Saved Codex upload token to {args.token_file}")
        if args.configure:
            return 0

    state = load_state(args.state)
    files = (
        [args.file]
        if args.file
        else (sorted(args.sessions_dir.rglob("*.jsonl")) if args.sessions_dir.exists() else [])
    )
    if args.since_days is not None and not args.file:
        if args.since_days < 0:
            parser.error("--since-days must be zero or greater")
        cutoff = time.time() - args.since_days * 86400
        files = [path for path in files if path.stat().st_mtime >= cutoff]
    uploaded = skipped = failed = 0
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        state_key = str(path.resolve())
        if not args.all and state.get(state_key) == digest:
            skipped += 1
            continue
        query = urllib.parse.urlencode({"filename": path.name})
        try:
            result = request_json(
                f"{base_url}/api/codex/sessions/import?{query}",
                data=raw,
                token=token,
                content_type="application/x-ndjson",
            )
            state[state_key] = digest
            uploaded += 1
            print(f"{result.get('status', 'uploaded'):>9}  {path}")
        except (OSError, RuntimeError) as exc:
            failed += 1
            print(f"   failed  {path}: {exc}", file=sys.stderr)
    save_state(args.state, state)
    print(f"Done: {uploaded} uploaded, {skipped} unchanged, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
