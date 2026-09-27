param(
    [switch]$Execute,
    [string]$CleanupRun,
    [switch]$RefreshDatabaseUri
)
$ErrorActionPreference = 'Stop'
if (($Execute -and $CleanupRun) -or (-not $Execute -and -not $CleanupRun)) {
    throw 'Specify exactly one: -Execute or -CleanupRun UUID. No test has run.'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot 'reports\zipon-rest-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the isolated test venv first; see docs/zipon_rest_compatibility.md.'
}
$names = @('ZIPON_TEST_PROJECT_REF', 'ZIPON_TEST_SUPABASE_URL',
    'ZIPON_TEST_SUPABASE_SERVICE_ROLE_KEY', 'ZIPON_TEST_DATABASE_URL')
# SecureString cache exists only in this PowerShell process, never on disk.
if (-not (Get-Variable -Name ZiponRestTestInputCache -Scope Global -ErrorAction SilentlyContinue)) {
    $global:ZiponRestTestInputCache = @{}
}
if ($RefreshDatabaseUri -and $global:ZiponRestTestInputCache.ContainsKey('ZIPON_TEST_DATABASE_URL')) {
    $global:ZiponRestTestInputCache['ZIPON_TEST_DATABASE_URL'].Dispose()
    $global:ZiponRestTestInputCache.Remove('ZIPON_TEST_DATABASE_URL')
}
$saved = @{}
try {
    foreach ($name in $names) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($saved[$name]) -and -not ($RefreshDatabaseUri -and $name -eq 'ZIPON_TEST_DATABASE_URL')) { continue }
        $inputLabel = $name
        if ($name -eq 'ZIPON_TEST_SUPABASE_SERVICE_ROLE_KEY') {
            $inputLabel = 'server Secret key (sb_secret_... supported; legacy service_role also accepted)'
        } elseif ($name -eq 'ZIPON_TEST_DATABASE_URL') {
            $inputLabel = 'Session pooler URI (postgres.<ref>, port 5432; URL-encoded password; no query string)'
        }
        if ($global:ZiponRestTestInputCache.ContainsKey($name)) {
            $secureValue = $global:ZiponRestTestInputCache[$name].Copy()
        } else {
            $secureValue = Read-Host "Enter NEW zipon-realestate $inputLabel (hidden)" -AsSecureString
            $global:ZiponRestTestInputCache[$name] = $secureValue.Copy()
        }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        try {
            [Environment]::SetEnvironmentVariable($name,
                [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr), 'Process')
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
            $secureValue.Dispose()
        }
    }
    $scriptPath = Join-Path $PSScriptRoot 'zipon_rest_compatibility.py'
    if ($Execute) {
        & $pythonPath -B $scriptPath --execute
    } else {
        & $pythonPath -B $scriptPath --cleanup-run $CleanupRun
    }
    $resultCode = $LASTEXITCODE
} finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
exit $resultCode
