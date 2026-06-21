"""On-demand Pika replay-generation jobs for the dashboard (the "Generate clip" action).

@spec REPLAY-PIKA-003 — dashboard-orchestrated, gated, on-demand Pika render

The dashboard is an ops/replay surface, NOT the er_twin agent runtime, so CLAUDE.md's hard rule
("Pika MCP is never called from er_twin/") still holds: this module shells out to the verified
OFFLINE path and never touches Pika MCP itself. One click turns a logged incident into a clip by
running, in sequence:

    1. scripts/capture_replay_frames.py  — rasterize the start/end keyframes (Playwright)
    2. scripts/run_pika_keyframes.ps1     — Claude Code CLI -> Pika MCP, which back-writes
                                            `video_url` into out/replay/{incident}.json

The incident file is the source of truth for success: a job is COMPLETED only once a `video_url`
appears there. Jobs are tracked in-process (the dashboard is a single uvicorn worker), keyed by
incident id, at most one active job per incident. The runner and the thread-spawn are injectable so
tests drive the whole lifecycle without Chromium, PowerShell, or spending Pika credits.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
IDLE = "idle"


@dataclass
class JobState:
    incident_id: str
    status: str
    video_url: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "video_url": self.video_url,
            "error": self.error,
        }


_jobs: dict[str, JobState] = {}
_lock = threading.Lock()


def get_job(incident_id: str) -> JobState | None:
    with _lock:
        return _jobs.get(incident_id)


def reset() -> None:
    """Clear all tracked jobs (test hook)."""
    with _lock:
        _jobs.clear()


def read_video_url(replay_dir: Path, incident_id: str) -> str | None:
    """The `video_url` recorded in out/replay/{incident}.json, or None if absent/unreadable."""
    path = replay_dir / f"{incident_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record.get("video_url") if isinstance(record, dict) else None


def default_runner(incident_id: str) -> None:
    """Capture keyframes then drive run_pika_keyframes.ps1 (CLI -> Pika MCP). Raises on failure.

    Both steps are subprocesses with timeouts; the keyframes script back-writes the media URL into the
    incident file itself, so this function only needs to run them and let failures propagate.
    """
    # 1. Rasterize start/end keyframes — capture_replay_frames spins up its OWN ephemeral dashboard +
    #    Chromium on a free port, so it does not collide with the live dashboard serving this request.
    subprocess.run(
        [sys.executable, "-m", "scripts.capture_replay_frames", incident_id],
        cwd=_REPO_ROOT, check=True, capture_output=True, text=True, timeout=300,
    )
    # 2. Drive the verified Pika keyframes path. CurrentUser policy is RemoteSigned, which runs a local
    #    unsigned script via -File without any execution-policy bypass.
    script = _REPO_ROOT / "scripts" / "run_pika_keyframes.ps1"
    subprocess.run(
        ["powershell", "-NoProfile", "-File", str(script), incident_id],
        cwd=_REPO_ROOT, check=True, capture_output=True, text=True, timeout=900,
    )


def _spawn(target: Callable[[], None]) -> None:
    """Run a job body off-request. Indirection so tests can monkeypatch to run synchronously."""
    threading.Thread(target=target, daemon=True).start()


def start_job(
    incident_id: str,
    replay_dir: Path,
    runner: Callable[[str], None] | None = None,
) -> JobState:
    """Start a generation job for `incident_id`, or return the one already in flight for it."""
    run = runner or default_runner
    with _lock:
        existing = _jobs.get(incident_id)
        if existing is not None and existing.status == RUNNING:
            return existing
        job = JobState(incident_id, RUNNING)
        _jobs[incident_id] = job

    def _work() -> None:
        try:
            run(incident_id)
        except subprocess.CalledProcessError as exc:
            _finish(job, FAILED, error=_tail(exc.stderr) or _tail(exc.stdout) or "render command failed")
            return
        except Exception as exc:  # noqa: BLE001 — a failure must mark the job, never kill the worker
            _finish(job, FAILED, error=str(exc))
            return
        url = read_video_url(replay_dir, incident_id)
        if url:
            _finish(job, COMPLETED, video_url=url)
        else:
            _finish(job, FAILED, error="render finished but no video_url was written to the incident")

    _spawn(_work)
    return job


def _finish(job: JobState, status: str, video_url: str | None = None, error: str | None = None) -> None:
    with _lock:
        job.status = status
        job.video_url = video_url
        job.error = error


def _tail(text: str | None, limit: int = 600) -> str:
    return text[-limit:].strip() if text else ""
