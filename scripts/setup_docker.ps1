<# Generate a local Docker Compose .env without exposing secrets in shell history. #>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$modelPath = Join-Path $repoRoot "wishindiary-api\ml\menstrual_rf_model.skops"

if ((Test-Path -LiteralPath $envPath) -and -not $Force) {
    throw "$envPath 已存在。为避免覆盖现有数据库配置，请先备份；确认后使用 -Force。"
}
if (-not (Test-Path -LiteralPath $modelPath)) {
    throw "安全模型不存在：$modelPath"
}

function New-SecureToken([int]$byteCount = 32) {
    $bytes = New-Object byte[] $byteCount
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$modelHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
$lines = @(
    "ENVIRONMENT=production",
    "DB_HOST=db",
    "DB_PORT=3306",
    "DB_USER=wishin_app",
    "DB_PASSWORD=$(New-SecureToken 24)",
    "DB_ROOT_PASSWORD=$(New-SecureToken 32)",
    "DB_NAME=wishindiary_db",
    "SECRET_KEY=$(New-SecureToken 48)",
    "CORS_ORIGINS=http://localhost:5173,http://localhost:8080",
    "MODEL_SHA256=$modelHash",
    "API_PORT=8000",
    "WEB_PORT=8080"
)

Set-Content -LiteralPath $envPath -Value ($lines -join "`n") -Encoding utf8
Write-Host "Docker 配置已生成：$envPath" -ForegroundColor Green
Write-Host "已自动生成数据库密码、JWT 密钥并写入模型 SHA-256。请勿提交 .env。"
Write-Host "下一步：docker compose up -d --build"
