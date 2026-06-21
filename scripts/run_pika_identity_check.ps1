<#
.SYNOPSIS
    Pika MCP smoke test (Phase P) — verifies the headless Claude Code CLI can reach the Pika MCP server
    and that the required tools are NOT auto-denied.

.DESCRIPTION
    Implements the LLD §9 identity-check contract:
      - locates the Claude CLI (override with $env:CLAUDE_CLI; else `claude` on PATH);
      - runs it non-interactively (`-p`) with `--mcp-config .mcp.json` and an explicit `--allowedTools`
        list (identity_whoami + identity_balance) and `--output-format json`;
      - writes the raw CLI JSON to out/pika_identity_check.json;
      - FAILS (exit 1) if `permission_denials` is non-empty — that means a needed tool was missing from
        the allowlist (the original "pending approval" blocker), NOT an OAuth problem.

    Does NOT use --dangerously-skip-permissions: the explicit allowlist is the supported path.

.EXAMPLE
    pwsh scripts/run_pika_identity_check.ps1
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
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$ResultPath = Join-Path $OutDir 'pika_identity_check.json'

# Minimal allowlist — just identity surface. permission_denials must come back empty.
$AllowedTools = 'mcp__pika-mcp__identity_whoami,mcp__pika-mcp__identity_balance'
$Prompt = 'Call the Pika identity_whoami and identity_balance tools. Report the resolved agent ' +
          'identity and the remaining credit balance in one short sentence.'

Write-Host "Running Pika identity check via $ClaudeCli ..." -ForegroundColor Cyan
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
    Write-Error ("permission_denials is NON-EMPTY ($(@($denials).Count)) - a needed tool was not in " +
                 "the allowlist. Add it to --allowedTools and re-run. Denials: " +
                 ($denials | ConvertTo-Json -Compress))
    exit 1
}

Write-Host "permission_denials: [] (OK - required tools allowed)" -ForegroundColor Green
if ($json.result) { Write-Host "Result: $($json.result)" }
exit 0
