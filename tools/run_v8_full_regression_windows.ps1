# Run VeloPOS V8 + legacy regressions on a Windows developer checkout.
# Does not launch the POS UI or enable commercial checkout.
param(
    [int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
if ($TimeoutSeconds -le 0) { throw 'TimeoutSeconds must be positive' }
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $repoRoot 'run_v8_full_regression.py'
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Missing full regression runner: $runner"
}
Push-Location $repoRoot
try {
    $branch = (& git branch --show-current 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch) -or $branch.Trim() -ne 'develop-v8') {
        throw "Refusing to test: checkout must be develop-v8 (found '$branch')"
    }
    $sha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Unable to determine checkout SHA' }
    Write-Host "VeloPOS V8 full regression | develop-v8 | $sha"
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        & py -3 $runner --timeout $TimeoutSeconds
    } else {
        $python = Get-Command python -ErrorAction Stop
        & python $runner --timeout $TimeoutSeconds
    }
    $result = $LASTEXITCODE
    if ($result -ne 0) { throw "Full regression failed (exit $result)" }
    Write-Host "Full regression passed for commit $sha"
} finally {
    Pop-Location
}
