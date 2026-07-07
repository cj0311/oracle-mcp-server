param(
    [string]$Python = "python",
    [string]$Venv = ".venv",
    [string]$Wheelhouse = "",
    [switch]$Editable
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Wheelhouse) {
    $Wheelhouse = Join-Path (Split-Path $RepoRoot -Parent) "wheelhouse"
}
$WheelhousePath = (Resolve-Path $Wheelhouse).Path
$VenvPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Venv))

if (-not $VenvPath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Venv must be inside the source directory: $VenvPath"
}

& $Python -m venv $VenvPath
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

if ($Editable) {
    & $VenvPython -m pip install --no-index --find-links $WheelhousePath setuptools wheel
    & $VenvPython -m pip install --no-index --find-links $WheelhousePath --no-build-isolation -e $RepoRoot
}
else {
    & $VenvPython -m pip install --no-index --find-links $WheelhousePath oracle-mcp-server
}

& $VenvPython -c "import mcp, oracledb, pydantic, dotenv, yaml; print('imports ok')"
& (Join-Path $VenvPath "Scripts\oracle-mcp-check.exe") --help

Write-Host ""
Write-Host "Offline install complete."
Write-Host "Python: $VenvPython"
Write-Host "Next: copy profiles.example.yaml to profiles.yaml and .env.example to .env."
