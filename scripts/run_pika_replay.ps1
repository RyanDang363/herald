<#
.SYNOPSIS
    Drive Pika MCP from an incident replay brief via the headless Claude Code CLI (Phase P).

.DESCRIPTION
    Implements the LLD §9 automated invocation contract:
      - REQUIRES out/incident_replay_brief.json (run an event first; Phase R writes it);
      - ensures out/pika_prompt.md exists (regenerates it with scripts.build_pika_prompt if missing);
      - calls the Claude CLI non-interactively (`-p`) with `--mcp-config .mcp.json` and an explicit
        `--allowedTools` list (the Pika generation/edit tools + task_status for long renders) and
        `--output-format json`;
      - writes the raw CLI JSON to out/pika_result.json;
      - FAILS loudly if `permission_denials` is non-empty (a needed tool was missing from the allowlist);
      - prints the media URL / asset ID / task_id from the result, or a clear "no media found" message.

    Long renders return {task_id, status}; the CLI session (with task_status allowed) polls to completion.
    Does NOT use --dangerously-skip-permissions — the explicit allowlist is the supported path.

.EXAMPLE
    pwsh scripts/run_pika_replay.ps1
#>
[CmdletBinding()]
param(
    [string]$ClaudeCli = $env:CLAUDE_CLI
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $ClaudeCli) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $ClaudeCli = $cmd.Source }
}
if (-not $ClaudeCli -or -not (Test-Path $ClaudeCli)) {
    Write-Error "Claude CLI not found. Set `$env:CLAUDE_CLI to its path, or put 'claude' on PATH."
    exit 1
}

$OutDir = Join-Path $RepoRoot 'out'
$BriefPath = Join-Path $OutDir 'incident_replay_brief.json'
$PromptPath = Join-Path $OutDir 'pika_prompt.md'
$ResultPath = Join-Path $OutDir 'pika_result.json'

if (-not (Test-Path $BriefPath)) {
    Write-Error "Missing $BriefPath. Run an ER event first (Phase R writes the brief), then re-run."
    exit 1
}

if (-not (Test-Path $PromptPath)) {
    Write-Host "pika_prompt.md missing; regenerating from the brief ..." -ForegroundColor Yellow
    & uv run python -m scripts.build_pika_prompt $BriefPath
    if (-not (Test-Path $PromptPath)) {
        Write-Error "Failed to generate $PromptPath."
        exit 1
    }
}

# Full generation surface + task_status for async polling (LLD §9 recommended first allowlist).
$AllowedTools = @(
    'mcp__pika-mcp__identity_whoami',
    'mcp__pika-mcp__identity_balance',
    'mcp__pika-mcp__estimate_cost',
    'mcp__pika-mcp__generate_image',
    'mcp__pika-mcp__generate_video',
    'mcp__pika-mcp__generate_keyframes_video',
    'mcp__pika-mcp__add_captions',
    'mcp__pika-mcp__edit_text_overlay',
    'mcp__pika-mcp__task_status'
) -join ','

$brief = Get-Content $PromptPath -Raw
$Prompt = @"
You are producing incident-replay media for a hackathon demo using the Pika MCP tools.

Follow this creative brief exactly:

$brief

Generate ONE short (15-25s) incident-replay video from the brief. If video generation is unavailable,
produce a single cinematic still image instead. Keep to one simple generation path — do not build a
multi-tool pipeline. If the render is asynchronous, poll task_status until it completes.

When done, return: the asset URL/ID, the task_id (if async), the Pika tool used, and a one-sentence
summary of what was produced.
"@

Write-Host "Driving Pika MCP replay via $ClaudeCli ..." -ForegroundColor Cyan
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

$result = [string]$json.result
Write-Host "permission_denials: [] (OK)" -ForegroundColor Green
Write-Host "--- CLI result ---"
Write-Host $result

# Surface a media URL / asset id / task id if present in the result text.
$urlMatch = [regex]::Match($result, 'https?://\S+')
$taskMatch = [regex]::Match($result, '(?i)task[_ ]?id\W+([A-Za-z0-9._-]+)')
if ($urlMatch.Success) {
    Write-Host "Media URL: $($urlMatch.Value)" -ForegroundColor Green
} elseif ($taskMatch.Success) {
    Write-Host "Async task id: $($taskMatch.Groups[1].Value) (poll mcp__pika-mcp__task_status)" -ForegroundColor Yellow
} else {
    Write-Warning "No media URL or task_id found in the result. Inspect $ResultPath."
}
exit 0
