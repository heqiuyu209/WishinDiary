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
    Write-Host "未检测到模型文件 ${modelPath}，将先调用训练脚本生成（与本项目'不附带模型'的发布政策一致）..." -ForegroundColor Yellow
    Push-Location $repoRoot
    try {
        if (Test-Path ".\.venv\Scripts\python.exe") {
            & ".\.venv\Scripts\python.exe" "wishindiary-api\scripts\train.py" --synthetic-only
            $trainExit = $LASTEXITCODE
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python "wishindiary-api\scripts\train.py" --synthetic-only
            $trainExit = $LASTEXITCODE
        } else {
            $trainExit = -1
            Write-Host "未找到 Python 环境（.venv 或系统 python），无法自动训练。" -ForegroundColor Red
        }
    } catch {
        Write-Host "训练脚本执行失败：$($_.Exception.Message)" -ForegroundColor Red
        $trainExit = -1
    }
    Pop-Location

    if (-not (Test-Path -LiteralPath $modelPath)) {
        Write-Host "模型 ${modelPath} 不存在，且本地未生成成功。" -ForegroundColor Red
        Write-Host "请手动训练后重试本脚本：" -ForegroundColor Yellow
        Write-Host "  cd $repoRoot"
        Write-Host "  .\.venv\Scripts\python.exe wishindiary-api\scripts\train.py --synthetic-only"
        Write-Host "（仓库不附带预训练模型，模型一律由 wishindiary-api/scripts/train.py 用合成数据本地生成。）"
        Write-Host "已跳过生成 Docker 配置，未修改 .env。"
        exit 0
    }
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
