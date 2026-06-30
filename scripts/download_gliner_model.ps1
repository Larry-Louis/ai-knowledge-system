Param(
    [string]$PythonExe = "C:/Users/xchen3/AppData/Local/Programs/Python/Python313/python.exe",
    [string]$ModelId = "urchade/gliner_base",
    [string]$CacheRoot = "C:/Code/hf-cache",
    [string]$OutputDir = "",
    [string]$HfEndpoint = "",
    [switch]$UseMirror,
    [switch]$Insecure
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $safeModelName = $ModelId.Replace("/", "_")
    $OutputDir = Join-Path $CacheRoot "models/$safeModelName"
}

if ($UseMirror -and [string]::IsNullOrWhiteSpace($HfEndpoint)) {
    $HfEndpoint = "https://hf-mirror.com"
}

$env:HF_HOME = $CacheRoot
if (-not [string]::IsNullOrWhiteSpace($HfEndpoint)) {
    $env:HF_ENDPOINT = $HfEndpoint
}
if ($Insecure) {
    $env:HF_HUB_DISABLE_SSL_VERIFY = "1"
    Write-Warning "SSL verification is disabled for this run. Use only in trusted network environments."
}

Write-Host "[1/3] Installing huggingface_hub CLI..."
& $PythonExe -m pip install -U huggingface_hub
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install huggingface_hub"
}

Write-Host "[2/3] Downloading model: $ModelId"
Write-Host "      HF_HOME: $($env:HF_HOME)"
if (-not [string]::IsNullOrWhiteSpace($env:HF_ENDPOINT)) {
    Write-Host "      HF_ENDPOINT: $($env:HF_ENDPOINT)"
}
Write-Host "      OutputDir: $OutputDir"

$hfCmd = Get-Command hf -ErrorAction SilentlyContinue
$legacyCmd = Get-Command huggingface-cli -ErrorAction SilentlyContinue

if ($hfCmd) {
    & hf download $ModelId --local-dir "$OutputDir"
} elseif ($legacyCmd) {
    & huggingface-cli download $ModelId --local-dir "$OutputDir"
} else {
    throw "Neither 'hf' nor 'huggingface-cli' command is available"
}

if ($LASTEXITCODE -ne 0) {
    throw "Model download failed (ModelId=$ModelId)"
}

Write-Host "[3/3] Done. Model files are ready at: $OutputDir"
Write-Host "Run test with:"
Write-Host "  $PythonExe rag-api/gliner_smoke_test.py --model `"$OutputDir`" --text `"我在使用 Python 和 Qdrant 开发 RAG 系统`""
