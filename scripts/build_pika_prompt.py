"""Render `out/pika_prompt.md` from an incident replay brief (REPLAY-BRIEF-002).

`replay.export_incident` already writes `pika_prompt.md` alongside the brief during a live run, so this
script is a standalone re-render utility — useful to regenerate the prompt from an existing brief
(e.g. after editing it by hand, or to target a specific per-incident history file) without re-running
the Bureau. It is pure file IO over `replay.render_pika_prompt`; it never calls Pika.

Usage:
    uv run python -m scripts.build_pika_prompt                      # uses out/incident_replay_brief.json
    uv run python -m scripts.build_pika_prompt out/low_oxygen_alert-0001.json
"""

import json
import sys
from pathlib import Path

from er_twin import replay

DEFAULT_BRIEF = Path("out") / replay.LATEST_BRIEF_FILENAME


def main(argv: list[str]) -> int:
    brief_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_BRIEF
    if not brief_path.exists():
        print(f"error: brief not found: {brief_path} (run an event first to generate it)", file=sys.stderr)
        return 1

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    prompt_path = brief_path.parent / replay.PROMPT_FILENAME
    prompt_path.write_text(replay.render_pika_prompt(brief), encoding="utf-8")
    print(f"wrote {prompt_path} from {brief_path} (incident {brief.get('incident_id')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
