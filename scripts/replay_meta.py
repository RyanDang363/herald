"""Tiny argv CLI helpers for the Pika keyframes script (Phase 4, LLD §9.1).

Why a module instead of inline `python -c` in the PowerShell script: Windows PowerShell 5.1 mangles
embedded double quotes when a multi-line script is passed to `python -c $var` (`encoding="utf-8"` ->
`NameError: name 'utf'`). Routing through a real module avoids that entirely AND keeps the
security-critical value handling on **argv** — the incident path and the model-extracted media URL are
never interpolated into Python source, so a single quote / backslash / shell metachar in the URL can
neither break the parse nor inject code (REPLAY-LIB-002/003). Pure file IO over `er_twin.replay`; never
calls Pika.

Usage:
    uv run python -m scripts.replay_meta duration out/replay/{incident}.json
    uv run python -m scripts.replay_meta set-video-url out/replay/{incident}.json <url>
"""

import json
import sys
from pathlib import Path

from er_twin import replay


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "duration":
        if len(argv) < 3:
            print("usage: replay_meta duration <incident.json>", file=sys.stderr)
            return 2
        record = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        print(
            replay.requested_clip_duration(
                record.get("start_ts"), record.get("end_ts"),
                record.get("speed_factor", replay.DEFAULT_SPEED_FACTOR),
            )
        )
        return 0

    if cmd == "set-video-url":
        if len(argv) < 4:
            print("usage: replay_meta set-video-url <incident.json> <url>", file=sys.stderr)
            return 2
        path, url = Path(argv[2]), argv[3]
        record = json.loads(path.read_text(encoding="utf-8"))
        record["video_url"] = url
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"video_url written into {path}")
        return 0

    print(f"unknown command: {cmd!r} (expected 'duration' or 'set-video-url')", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
