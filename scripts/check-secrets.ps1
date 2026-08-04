# File: scripts/check-secrets.ps1
# Version: 0.1.0
# Date: 2026-08-03
# Purpose: Fails CI when common credential patterns are accidentally committed.

$ErrorActionPreference = "Stop"
$patterns = @(
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "AKIA[0-9A-Z]{16}",
    "ghp_[A-Za-z0-9]{30,}",
    "(?i)(password|secret|token)\s*[:=]\s*['""][^'""]{8,}['""]"
)

$matches = @()
$files = git ls-files --cached --others --exclude-standard
foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        continue
    }
    foreach ($pattern in $patterns) {
        $matches += Select-String -LiteralPath $file -Pattern $pattern -ErrorAction SilentlyContinue
    }
}
if ($matches.Count -gt 0) {
    $matches | Write-Error
    exit 1
}
Write-Host "Keine typischen Secrets in versionierten Dateien gefunden."
