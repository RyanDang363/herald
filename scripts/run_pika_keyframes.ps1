<#
.SYNOPSIS
    Turn captured incident-replay keyframes into a Pika keyframe-interpolated clip (Phase 4, LLD §9.1).

.DESCRIPTION
    Data-driven sibling of run_pika_replay.ps1. Instead of a hallucinated animation from a text brief,
    this feeds the REAL captured ER-state keyframes to Pika `generate_keyframes_video`:
      - REQUIRES out/replay/{incident}.json (Phase 1) and out/frames/{incident}/frame_*.png (Phase 3,
        `python -m scripts.capture_replay_frames {incident}`);
      - generate_keyframes_video interpolates between exactly two images, so it passes the FIRST and
        LAST captured frame (start -> end) for one clip (decision: single start->end clip);
      - requests duration = clamp(real_elapsed / speed_factor -> {5,10}) (REPLAY-LIB-002), computed from
        the incident JSON via er_twin.replay.requested_clip_duration;
      - drives the headless Claude CLI with `--mcp-config .mcp.json` + an explicit `--allowedTools` list
        (upload + generate_keyframes_video + task_status), `--output-format json`;
      - writes the raw CLI JSON to out/pika_result.json, FAILS loudly on non-empty `permission_denials`;
      - writes the returned media URL back into out/replay/{incident}.json as `video_url` (REPLAY-LIB-003).

    Fallback (REPLAY-PIKA-002): if the frames are missing, it does NOT crash — it defers to the existing
    text-brief path (run_pika_replay.ps1).

    @spec REPLAY-PIKA-001 @spec REPLAY-PIKA-002 @spec REPLAY-LIB-002 @spec REPLAY-LIB-003

.EXAMPLE
    pwsh scripts/run_pika_keyframes.ps1 patient_intake-0001
.EXAMPLE
    pwsh scripts/run_pika_keyframes.ps1          # uses the most recent out/replay/*.json
#>
[CmdletBinding()]
param(
    [string]$IncidentId,
    [string]$ClaudeCli = $env:CLAUDE_CLI
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$OutDir = Join-Path $RepoRoot 'out'
$ReplayDir = Join-Path $OutDir 'replay'
$FramesRoot = Join-Path $OutDir 'frames'
$ResultPath = Join-Path $OutDir 'pika_result.json'

# Resolve the incident: explicit arg, else the most recently written out/replay/*.json.
if (-not $IncidentId) {
    $latest = Get-ChildItem -Path $ReplayDir -Filter '*.json' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Error "No incident given and no out/replay/*.json found. Run an ER event first (Phase 1)."
        exit 1
    }
    $IncidentId = [System.IO.Path]::GetFileNameWithoutExtension($latest.Name)
}
Write-Host "Incident: $IncidentId" -ForegroundColor Cyan

$ReplayJson = Join-Path $ReplayDir "$IncidentId.json"
if (-not (Test-Path $ReplayJson)) {
    Write-Error "Missing $ReplayJson. Run an ER event first (Phase 1 writes the snapshot timeline)."
    exit 1
}

# Gather captured keyframes (frame_00 = start ... frame_NN = end).
$FramesDir = Join-Path $FramesRoot $IncidentId
$frames = @()
if (Test-Path $FramesDir) {
    $frames = Get-ChildItem -Path $FramesDir -Filter 'frame_*.png' | Sort-Object Name
}

# Fallback (REPLAY-PIKA-002): no usable frames -> defer to the text-brief Pika path, do not crash.
# Pass the resolved $IncidentId through so the fallback renders THIS incident's brief (out/{id}.json),
# not whatever happens to be the most recent incident_replay_brief.json.
if ($frames.Count -lt 2) {
    Write-Warning "Need >=2 keyframes in $FramesDir (found $($frames.Count)). Capture them with:"
    Write-Warning "  uv run python -m scripts.capture_replay_frames $IncidentId"
    Write-Warning "Falling back to the text-brief Pika path (run_pika_replay.ps1) for $IncidentId..."
    & (Join-Path $PSScriptRoot 'run_pika_replay.ps1') -IncidentId $IncidentId
    exit $LASTEXITCODE
}

$firstFrame = $frames[0].FullName
$lastFrame = $frames[-1].FullName
Write-Host "First frame: $firstFrame" -ForegroundColor DarkGray
Write-Host "Last  frame: $lastFrame" -ForegroundColor DarkGray

# Requested clip duration = clamp(real_elapsed / speed_factor) to Pika's {5,10} (REPLAY-LIB-002).
# Routed through scripts.replay_meta (argv, not inline `python -c`) to dodge PS 5.1 quote-mangling and
# keep the path off the Python source line. The parse takes the last bare-integer line so any
# incidental stdout noise from `uv run` is ignored.
$Duration = 5
try {
    $durRaw = & uv run python -m scripts.replay_meta duration $ReplayJson
    $durLine = @($durRaw) | Where-Object { $_ -match '^\s*\d+\s*$' } | Select-Object -Last 1
    if ($durLine) { $Duration = [int]($durLine.Trim()) }
} catch {
    Write-Warning "Could not compute clip duration; defaulting to ${Duration}s."
}
Write-Host "Requested clip duration: ${Duration}s (time-compressed)" -ForegroundColor Cyan

# Resolve the Claude CLI.
if (-not $ClaudeCli) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $ClaudeCli = $cmd.Source }
}
if (-not $ClaudeCli -or -not (Test-Path $ClaudeCli)) {
    Write-Error "Claude CLI not found. Set `$env:CLAUDE_CLI to its path, or put 'claude' on PATH."
    exit 1
}

# Upload + keyframes-video generation + async polling. Local PNGs are uploaded first so Pika gets a
# reachable reference; task_status covers long renders. Bash + Read are required because the upload
# flow has the agent hash/size the local frame PNGs (stat/sha256sum) and PUT them to the presigned
# URL — without them the run dies on non-empty permission_denials before any clip is produced.
$AllowedTools = @(
    'mcp__pika-mcp__identity_whoami',
    'mcp__pika-mcp__identity_balance',
    'mcp__pika-mcp__estimate_cost',
    'mcp__pika-mcp__upload_asset',
    'mcp__pika-mcp__create_upload_return',
    'mcp__pika-mcp__complete_upload_asset',
    'mcp__pika-mcp__generate_keyframes_video',
    'mcp__pika-mcp__task_status',
    'Bash',
    'Read'
) -join ','

$Prompt = @"
You are producing an ER incident-replay clip for a hackathon demo using Pika MCP. FIDELITY OVER FLASH:
the result must look like the two input images BARELY animated — never a reimagined, 3D, or photoreal scene.

The two PNGs are frames of a flat, 2D, TOP-DOWN SCHEMATIC FLOOR-PLAN ILLUSTRATION of an emergency
department (clean infographic / architectural-blueprint style; rooms are labeled rectangles — WAITING,
TRIAGE, MAIN CORRIDOR, NURSE STATION, SUPPLY, TRAUMA and bed bays — and people/equipment are simple
labeled colored circle markers). Synthetic data, no real PHI.
  - FIRST frame (start state): $firstFrame
  - LAST frame (end state):    $lastFrame

Steps:
1. If generate_keyframes_video cannot read a local path directly, upload each PNG first (upload_asset)
   and use the returned HTTPS URLs.
2. Call generate_keyframes_video with first_frame = the start image, last_frame = the end image,
   duration = $Duration, resolution 720p, ONE clip. The transition prompt MUST instruct the model to:
     - interpolate ONLY the positions of the colored circular markers, gliding smoothly from their
       first-frame positions to their last-frame positions;
     - PRESERVE EXACTLY the flat 2D top-down illustrated style, the room rectangles and layout, the
       walls, the colors, and EVERY text/room label from the inputs — do not redraw, restyle, distort,
       re-spell, blur, or add/remove any text, rooms, beds, or objects;
     - hold a LOCKED, perfectly static top-down camera: no pan, no zoom, no tilt, no perspective, no
       parallax, no 3D, and no lighting or shadow changes;
     - add NO photorealism and NO realistic human figures — the people stay simple flat circle markers;
       calm, minimal, schematic motion only.
   If generate_keyframes_video exposes parameters for motion strength / fidelity / adherence to the
   input frames, choose values that MINIMIZE invented motion and MAXIMIZE faithfulness to the inputs.
3. If the render is asynchronous, poll task_status until it completes.

When done, return on its own line: the final media URL, the task_id (if async), the tool used, and a
one-sentence summary.
"@

Write-Host "Driving Pika generate_keyframes_video via $ClaudeCli ..." -ForegroundColor Cyan
$cliArgs = @(
    '-p', $Prompt,
    '--mcp-config', '.mcp.json',
    '--allowedTools', $AllowedTools,
    '--output-format', 'json'
)
$raw = & $ClaudeCli @cliArgs | Out-String
$raw | Set-Content -Path $ResultPath -Encoding utf8
Write-Host "Raw CLI output -> $ResultPath"

try {
    $json = $raw | ConvertFrom-Json
} catch {
    Write-Error "Could not parse CLI output as JSON. See $ResultPath for the raw text."
    exit 1
}

$denials = $json.permission_denials
if ($denials -and @($denials).Count -gt 0) {
    Write-Error ("permission_denials is NON-EMPTY ($(@($denials).Count)) - add the missing tool(s) to " +
                 "`$AllowedTools and re-run. Denials: " + ($denials | ConvertTo-Json -Compress))
    exit 1
}
Write-Host "permission_denials: [] (OK)" -ForegroundColor Green

$result = [string]$json.result
Write-Host "--- CLI result ---"
Write-Host $result

# Write the returned media URL back into out/replay/{incident}.json as video_url (REPLAY-LIB-003).
# Via scripts.replay_meta set-video-url: the path and the URL are passed as argv — never interpolated
# into Python source — so a single quote, backslash, or shell metachar in the model-extracted URL can
# neither break the parse nor inject code.
$urlMatch = [regex]::Match($result, 'https?://\S+')
if ($urlMatch.Success) {
    $mediaUrl = $urlMatch.Value.TrimEnd('.,)`"''')
    Write-Host "Media URL: $mediaUrl" -ForegroundColor Green
    & uv run python -m scripts.replay_meta set-video-url $ReplayJson $mediaUrl
} else {
    $taskMatch = [regex]::Match($result, '(?i)task[_ ]?id\W+([A-Za-z0-9._-]+)')
    if ($taskMatch.Success) {
        Write-Host "Async task id: $($taskMatch.Groups[1].Value) (poll mcp__pika-mcp__task_status)" -ForegroundColor Yellow
    } else {
        Write-Warning "No media URL or task_id found in the result. Inspect $ResultPath."
    }
}
exit 0
