"""Capture incident-replay keyframe PNGs from the replay page (Phase 3, LLD §9.1).

Loads `out/replay/{incident}.json`, selects the keyframe snapshots with the pure
`er_twin.replay.select_keyframes` (cap = `KEYFRAME_CAP` = 2 → start + end), then drives a headless
Chromium (Playwright) over the `/replay/{incident}` page — seeking to each keyframe via the page's
`window.replayApi` and screenshotting the floor map to `out/frames/{incident}/frame_NN.png`.

    uv run python -m scripts.capture_replay_frames patient_intake-0001

@spec REPLAY-KEY-001 (selection) @spec REPLAY-KEY-002 (one PNG per selected keyframe)

Keyframe selection is a pure function so it is unit-tested without a browser (tests/test_replay.py).
Only the rasterization needs Chromium; if Playwright install is problematic on the day, the same
selection + replay SVG markup can be rasterized with resvg/cairosvg instead (LLD §9.1, fallback).
"""

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from er_twin import replay

REPO_ROOT = Path(__file__).resolve().parent.parent


def _incident_path(incident_id: str, out_dir: Path) -> Path:
    path = out_dir / replay.REPLAY_SUBDIR / f"{incident_id}.json"
    if not path.is_file():
        raise SystemExit(f"No replay timeline at {path}. Run an ER event first (Phase 1 writes it).")
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 — localhost only
                if resp.status < 500:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    raise SystemExit(f"Dashboard server did not come up at {url} within {timeout}s.")


def _start_server(port: int) -> subprocess.Popen:
    """Start the dashboard so the replay page can fetch /api/replay/{incident}."""
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.server:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=str(REPO_ROOT),
    )


def capture(incident_id: str, out_dir: Path, cap: int, port: int | None) -> list[Path]:
    record = json.loads(_incident_path(incident_id, out_dir).read_text(encoding="utf-8"))
    keyframes = replay.select_keyframes(record.get("snapshots", []), cap=cap)
    if not keyframes:
        raise SystemExit(f"No snapshots in {incident_id}; nothing to capture.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "Playwright is not installed. Run `uv sync` then `uv run playwright install chromium`."
        ) from exc

    frames_dir = out_dir / replay.FRAMES_SUBDIR / incident_id
    frames_dir.mkdir(parents=True, exist_ok=True)

    port = port or _free_port()
    base = f"http://127.0.0.1:{port}"
    server = _start_server(port)
    written: list[Path] = []
    try:
        _wait_until_up(f"{base}/api/replay/{incident_id}")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.goto(f"{base}/replay/{incident_id}", wait_until="networkidle")
            page.wait_for_function("window.replayApi && window.replayApi.ready === true", timeout=15000)
            shell = page.wait_for_selector(".floor-shell", timeout=15000)
            for i, frame in enumerate(keyframes):
                ok = page.evaluate("(seq) => window.replayApi.seekToSeq(seq)", frame["seq"])
                if not ok:
                    print(f"  ! could not seek to seq {frame['seq']}", file=sys.stderr)
                page.wait_for_timeout(250)  # let the tween settle on the keyframe
                dest = frames_dir / f"frame_{i:02d}.png"
                shell.screenshot(path=str(dest))
                written.append(dest)
                print(f"  captured seq {frame['seq']:>2} ({frame.get('action', '')}) -> {dest.name}")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture replay keyframe PNGs (Playwright).")
    parser.add_argument("incident_id", help="e.g. patient_intake-0001")
    parser.add_argument("--out", default=str(REPO_ROOT / "out"), help="out/ dir (default: repo out/)")
    parser.add_argument("--cap", type=int, default=replay.KEYFRAME_CAP,
                        help=f"max keyframes (default {replay.KEYFRAME_CAP} — Pika's first+last limit)")
    parser.add_argument("--port", type=int, default=None, help="dashboard port (default: a free port)")
    args = parser.parse_args()

    frames = capture(args.incident_id, Path(args.out), args.cap, args.port)
    print(f"Wrote {len(frames)} frame(s) to {Path(args.out) / replay.FRAMES_SUBDIR / args.incident_id}")


if __name__ == "__main__":
    main()
