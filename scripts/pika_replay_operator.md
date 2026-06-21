# Pika Replay — Operator Runbook (Phase P)

How to turn a finished ER incident into replay media with Pika MCP. The Fetch runtime only writes
`out/*` files (Phase R); **this step is external post-processing** — the Claude Code CLI (or a human in
VSCode) drives Pika MCP. No Pika code runs inside `er_twin/`.

Contract reference: [LLD §9](../docs/llds/er-twin-core.lld.md) · file schema: `out/incident_replay_brief.json`.

## Prerequisites

- **Claude Code CLI** available. The scripts use `claude` on `PATH`, or set `CLAUDE_CLI` to an explicit
  path: `$env:CLAUDE_CLI = "C:\path\to\claude.exe"`.
- **Pika MCP authenticated.** Configured at project scope in [`.mcp.json`](../.mcp.json)
  (`https://mcp.pika.me/api/mcp`). If the CLI reports an auth/connection error (not a permission denial),
  authenticate once interactively in VSCode via `/mcp` (see Alternative B), then retry the script.
- **A brief to render.** Run an ER event first so Phase R writes `out/incident_replay_brief.json` +
  `out/pika_prompt.md`. (No event run → no brief, by design — REPLAY-BRIEF-003.)

> **Key gotcha (not OAuth):** in headless `-p` mode every MCP tool call is auto-denied unless the tool
> is in `--allowedTools`. A non-empty `permission_denials` array in the JSON output means a needed tool
> was missing from the allowlist — **add it and re-run**, don't reach for `--dangerously-skip-permissions`.

## Alternative A — Automated (primary path)

1. **Smoke test** the CLI → Pika path and credit balance:

   ```pwsh
   pwsh scripts/run_pika_identity_check.ps1
   ```

   - Writes `out/pika_identity_check.json`.
   - **Passes** when `permission_denials` is `[]` and it prints the identity + balance.
   - **Fails (exit 1)** if any tool was denied — the message names the denials; widen the allowlist.

2. **Generate the replay** from the latest brief:

   ```pwsh
   pwsh scripts/run_pika_replay.ps1
   ```

   - Requires `out/incident_replay_brief.json`; regenerates `out/pika_prompt.md` if missing
     (`uv run python -m scripts.build_pika_prompt`).
   - Calls the CLI with `--mcp-config .mcp.json` and the explicit Pika allowlist
     (`identity_whoami, identity_balance, estimate_cost, generate_image, generate_video,
     generate_keyframes_video, add_captions, edit_text_overlay, task_status`).
   - Writes raw CLI JSON to `out/pika_result.json`, fails loudly on non-empty `permission_denials`,
     and prints the media **URL / asset ID / task_id**.
   - Long renders return `{task_id, status}`; the CLI session polls `task_status` to completion.

3. **Pre-generate before judging.** Run step 2 ahead of time and keep `out/pika_result.json` +
   the media URL. Re-run live during the demo as proof-of-work; if the live render is slow or fails,
   show the pre-generated asset.

## Alternative B — Manual VSCode operator (fallback)

Use when the headless CLI is unavailable or first-time MCP auth is needed.

1. Open the project in VSCode with the Claude Code extension.
2. Run `/mcp` and authenticate the `pika-mcp` server if prompted (one-time).
3. Open `out/pika_prompt.md` and paste its contents into the chat.
4. Approve the Pika tool calls interactively when prompted (the interactive UI replaces `--allowedTools`).
5. Copy the returned asset URL/ID, `task_id`, tool used, and summary into `out/pika_result.json` by hand
   (or just keep the URL for the demo).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission_denials` non-empty | tool missing from `--allowedTools` | add the named `mcp__pika-mcp__*` tool to the script's allowlist, re-run |
| Auth/connection error (not a denial) | Pika MCP not authenticated in this environment | authenticate once via VSCode `/mcp` (Alternative B), retry |
| `Claude CLI not found` | `claude` not on PATH | set `$env:CLAUDE_CLI` to the binary path |
| `Missing out/incident_replay_brief.json` | no event has run this session | trigger an ER event first (Phase R writes the brief) |
| Output isn't valid JSON | CLI printed non-JSON (e.g. an error) | inspect the raw text in `out/pika_result.json` |
