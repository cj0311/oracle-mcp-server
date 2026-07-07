param(
    [string]$Python = "python",
    [string]$PythonVersion = "3.12",
    [string]$Abi = "cp312",
    [string]$Platform = "manylinux2014_x86_64",
    [string]$OutputDir = "dist\oracle-mcp-offline-bundle-py312-linux-x86_64"
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
    "opencode.remote-http.example.jsonc",
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

& $Python -c "import sys; print(f'Using builder Python {sys.version.split()[0]}')"
Write-Host "Downloading wheels for $Platform / Python $PythonVersion / ABI $Abi"

function Invoke-Native {
    $command = $args[0]
    $commandArgs = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }
    & $command @commandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($args -join ' ')"
    }
}

# pip evaluates environment markers like sys_platform against the current OS
# when cross-downloading from Windows. Download every needed Linux-compatible
# wheel without dependency resolution so Windows-only dependencies such as
# pywin32 are not pulled into the Linux bundle.
$packages = @(
    "setuptools",
    "wheel",
    "packaging",
    "mcp>=1.27,<2",
    "oracledb>=2.4,<4",
    "pydantic>=2.7,<3",
    "python-dotenv>=1.0,<2",
    "PyYAML>=6.0,<7",
    "annotated-types",
    "anyio",
    "attrs",
    "certifi",
    "cffi",
    "click",
    "colorama",
    "cryptography",
    "h11",
    "httpcore",
    "httpx",
    "httpx-sse",
    "idna",
    "jsonschema",
    "jsonschema-specifications",
    "pydantic-core==2.46.4",
    "pydantic-settings",
    "PyJWT",
    "pycparser",
    "python-multipart",
    "referencing",
    "rpds-py",
    "sse-starlette",
    "starlette",
    "typing-extensions",
    "typing-inspection",
    "uvicorn"
)

Invoke-Native $Python -m pip download `
    --dest $WheelhousePath `
    --no-deps `
    --only-binary=:all: `
    --platform $Platform `
    --implementation cp `
    --python-version $PythonVersion `
    --abi $Abi `
    $packages

Invoke-Native $Python -m pip wheel --no-deps --wheel-dir $WheelhousePath $RepoRoot

$badWheels = Get-ChildItem -LiteralPath $WheelhousePath -Filter *.whl |
    Where-Object { $_.Name -match 'win_amd64|pywin32' }
if ($badWheels) {
    throw "Linux bundle contains Windows-only wheels: $($badWheels.Name -join ', ')"
}

$ZipPath = "$OutputPath.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Compress-Archive -Path (Join-Path $OutputPath "*") -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Linux offline bundle created:"
Get-Item -LiteralPath $ZipPath | Select-Object FullName, Length, LastWriteTime | Format-List
Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256 | Format-List
Write-Host "Use this bundle on Linux x86_64 with Python $PythonVersion."
