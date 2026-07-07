param(
    [string]$Python = "python",
    [string]$OutputDir = "dist\oracle-mcp-offline-bundle"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))

if (-not $OutputPath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDir must be inside the repository: $OutputPath"
}

if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Recurse -Force
}

$SourcePath = Join-Path $OutputPath "source"
$WheelhousePath = Join-Path $OutputPath "wheelhouse"
New-Item -ItemType Directory -Force -Path $SourcePath, $WheelhousePath | Out-Null

$items = @(
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "README.md",
    "mcp-client.example.json",
    "opencode.example.jsonc",
    "profiles.example.yaml",
    "pyproject.toml",
    "requirements.txt",
    "scripts",
    "src",
    "tests"
)

foreach ($item in $items) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $item) -Destination $SourcePath -Recurse -Force
}

& $Python -c "import sys, platform; print(f'Building wheelhouse for Python {sys.version.split()[0]} on {platform.platform()} / {platform.machine()}')"
& $Python -m pip wheel --wheel-dir $WheelhousePath setuptools wheel
& $Python -m pip wheel --wheel-dir $WheelhousePath -r (Join-Path $RepoRoot "requirements.txt")
& $Python -m pip wheel --wheel-dir $WheelhousePath $RepoRoot

$ZipPath = "$OutputPath.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path (Join-Path $OutputPath "*") -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Offline bundle created:"
Get-Item -LiteralPath $ZipPath | Select-Object FullName, Length, LastWriteTime | Format-List
Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256 | Format-List
Write-Host "Use this bundle only on the same OS/CPU and compatible Python minor version."
