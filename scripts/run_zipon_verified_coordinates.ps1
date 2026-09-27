param([switch]$Apply, [switch]$ReconcileFirst, [switch]$CanaryFirst, [switch]$ReconcileResume, [switch]$ResumeApply, [switch]$ReconcilePartial, [switch]$ResumeRemaining80, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
if ($ResumeRemaining80 -and ($Apply -or $ReconcileFirst -or $CanaryFirst -or $ReconcileResume -or $ResumeApply -or $ReconcilePartial)) { throw 'REMAINING80_MUST_BE_EXCLUSIVE' }
if ($ReconcilePartial -and ($Apply -or $ReconcileFirst -or $CanaryFirst -or $ReconcileResume -or $ResumeApply)) { throw 'PARTIAL_RECONCILIATION_IS_READ_ONLY' }
if ($Apply -and $ReconcileFirst) { throw 'RECONCILIATION_CANNOT_APPLY' }
if ($CanaryFirst -and ($Apply -or $ReconcileFirst)) { throw 'CANARY_MODE_MUST_BE_EXCLUSIVE' }
if ($ReconcileResume -and ($Apply -or $ReconcileFirst -or $CanaryFirst)) { throw 'RESUME_RECONCILIATION_IS_READ_ONLY' }
if ($ResumeApply -and ($Apply -or $ReconcileFirst -or $CanaryFirst -or $ReconcileResume)) { throw 'RESUME_APPLY_MUST_BE_EXCLUSIVE' }
$target = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'
$oldUrl = [Environment]::GetEnvironmentVariable('ZIPON_IMPORT_SUPABASE_URL', 'Process')
$oldKey = [Environment]::GetEnvironmentVariable('ZIPON_IMPORT_SUPABASE_KEY', 'Process')
if ($oldUrl -and $oldUrl.TrimEnd('/') -ne $target) { throw 'NEW_PROJECT_TARGET_MISMATCH' }
# A prior attempted run is never replayed. Route the explicit resume request to
# the separate remaining-80 run, behind fresh read-only and Python hash/count gates.
$resumeAfterPartial = $false
$previousResumePath = Join-Path (Split-Path -Parent $PSScriptRoot) 'data\development\coordinate_resume_apply_result.json'
if ($ResumeApply -and (Test-Path -LiteralPath $previousResumePath)) {
    # Python journals are UTF-8 without BOM. Windows PowerShell 5.1 otherwise
    # decodes them with the system ANSI code page and can corrupt Korean JSON.
    try {
        $previousResume = Get-Content -LiteralPath $previousResumePath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw 'STOP: LOCAL_JOURNAL_PARSE_ERROR; preserve journal; no DB/RPC request made'
    }
    $resumeAfterPartial = [bool]$previousResume.write_attempted
}
# Only the explicitly named new-DB variables are used. No dotenv/production secret access.
try {
    $env:ZIPON_IMPORT_SUPABASE_URL = $target
    if ($CanaryFirst -or -not $oldKey) {
        $secure = Read-Host 'NEW zipon-realestate server Secret key (hidden; never paste into chat)' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $env:ZIPON_IMPORT_SUPABASE_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $secure.Dispose() }
    }
    $entry = Join-Path $PSScriptRoot 'apply_zipon_verified_coordinates.py'
    if ($ResumeRemaining80 -or $resumeAfterPartial) {
        & $Python -B (Join-Path $PSScriptRoot 'reconcile_zipon_partial.py')
        if ($LASTEXITCODE -ne 0) { throw 'LIVE_READ_ONLY_GATE_BLOCKED; no writes attempted' }
        & $Python -B (Join-Path $PSScriptRoot 'resume_zipon_coordinates.py') --remaining80
        if ($LASTEXITCODE -ne 0) { throw 'REMAINING80_STOPPED; preserve all journals' }
        return
    }
    if ($ReconcilePartial) {
        & $Python -B (Join-Path $PSScriptRoot 'reconcile_zipon_partial.py')
        if ($LASTEXITCODE -ne 0) { Write-Warning 'PARTIAL_RECONCILIATION_BLOCKED; no writes attempted' }
        return
    }
    if ($ResumeApply) {
        & $Python -B (Join-Path $PSScriptRoot 'resume_zipon_coordinates.py')
        if ($LASTEXITCODE -ne 0) { throw 'RESUME_STOPPED; preserve journals and reconcile before any retry' }
        return
    }
    if ($ReconcileResume) {
        & $Python -B (Join-Path $PSScriptRoot 'reconcile_zipon_resume.py')
        if ($LASTEXITCODE -ne 0) { Write-Warning 'RESUME_RECONCILIATION_BLOCKED; no writes attempted' }
        return
    }
    if ($CanaryFirst) {
        & $Python -B (Join-Path $PSScriptRoot 'canary_zipon_coordinate.py')
        if ($LASTEXITCODE -ne 0) { throw 'CANARY_STOPPED; read the separate canary journal; do not retry' }
        return
    }
    if ($ReconcileFirst) {
        $entry = Join-Path $PSScriptRoot 'reconcile_zipon_coordinate.py'
        & $Python -B $entry
        if ($LASTEXITCODE -ne 0) { Write-Warning 'READ_ONLY_DIAGNOSIS_INCOMPLETE_OR_BLOCKED; no writes attempted' }
        return
    }
    & $Python -B $entry
    if ($LASTEXITCODE -ne 0) { throw 'READ_ONLY_PREFLIGHT_BLOCKED; no apply performed' }
    if ($Apply) {
        & $Python -B $entry --apply
        if ($LASTEXITCODE -ne 0) { throw 'APPLY_STOPPED; inspect non-secret journal before retrying' }
    }
} finally {
    [Environment]::SetEnvironmentVariable('ZIPON_IMPORT_SUPABASE_URL', $oldUrl, 'Process')
    [Environment]::SetEnvironmentVariable('ZIPON_IMPORT_SUPABASE_KEY', $oldKey, 'Process')
}
