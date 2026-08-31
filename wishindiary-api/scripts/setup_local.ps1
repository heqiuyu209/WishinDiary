<#
    Configure the local API without putting the database password or JWT secret
    in the shell history. This script only reads the database and writes
    wishindiary-api/.env after a successful connection test.

    It never drops, truncates, migrates, or recreates tables.
#>
[CmdletBinding()]
param(
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 3306,
    [string]$DbName = "wishindiary_db",
    [string]$DbUser = "root",
    [string]$MysqlPath = ""
)

$ErrorActionPreference = "Stop"
$apiRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $apiRoot ".env"

$mysql = $MysqlPath
if (-not $mysql) {
    $mysql = (Get-Command mysql.exe -ErrorAction SilentlyContinue).Source
}
if (-not $mysql) {
    $mysql = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
}
if (-not (Test-Path -LiteralPath $mysql)) {
    throw "找不到 mysql.exe。请先安装 MySQL Client，或用 -MysqlPath 指定客户端路径。"
}

Write-Host "将测试 MySQL $DbHost`:$DbPort / 用户 $DbUser / 数据库 $DbName"
Write-Host "不会删除或重建任何表。"
$securePassword = Read-Host "请输入现有 MySQL 密码（输入不会显示）" -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}

# MYSQL_PWD avoids putting the password in the process command line.
$oldMysqlPwd = $env:MYSQL_PWD
$env:MYSQL_PWD = $plainPassword
try {
    $probe = & $mysql -h $DbHost -P $DbPort -u $DbUser -D $DbName --batch --skip-column-names -e "SELECT 1; SELECT COUNT(*) FROM users;" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL 登录失败。请确认用户名、密码、端口以及当前实例。原始错误：$($probe -join ' ')"
    }
    $probeLines = @($probe | Where-Object { $_ -notmatch '^mysql:' })
    if ($probeLines.Count -lt 2 -or $probeLines[0].Trim() -ne "1") {
        throw "已连接 MySQL，但数据库 '$DbName' 不存在或不可访问。未执行任何修改。"
    }
    Write-Host "users 表当前记录数：$($probeLines[1].Trim())（只读检查，未删除用户）"

    # Windows PowerShell 5/.NET Framework 没有 RandomNumberGenerator.Fill；
    # 使用 Create().GetBytes() 兼容 Windows PowerShell 与 PowerShell 7。
    $secretBytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($secretBytes)
    } finally {
        $rng.Dispose()
    }
    $secretKey = [Convert]::ToBase64String($secretBytes)
    $cors = "http://localhost:5173,http://127.0.0.1:5173"
    $modelPath = Join-Path $apiRoot "ml\menstrual_rf_model.skops"
    $modelSha256 = if (Test-Path -LiteralPath $modelPath) {
        (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    } else {
        ""
    }

    function ConvertTo-DotEnvValue([string]$value) {
        if ($value -match '^[A-Za-z0-9_./:@%+\-=,~]+$') {
            return $value
        }
        $escaped = $value.Replace('\', '\\').Replace("'", "\'")
        return "'$escaped'"
    }

    $lines = @(
        "ENVIRONMENT=$(ConvertTo-DotEnvValue 'development')",
        "DB_HOST=$(ConvertTo-DotEnvValue $DbHost)",
        "DB_PORT=$(ConvertTo-DotEnvValue $DbPort)",
        "DB_USER=$(ConvertTo-DotEnvValue $DbUser)",
        "DB_PASSWORD=$(ConvertTo-DotEnvValue $plainPassword)",
        "DB_NAME=$(ConvertTo-DotEnvValue $DbName)",
        "SECRET_KEY=$(ConvertTo-DotEnvValue $secretKey)",
        "CORS_ORIGINS=$(ConvertTo-DotEnvValue $cors)",
        "MODEL_SHA256=$(ConvertTo-DotEnvValue $modelSha256)"
    )
    Set-Content -LiteralPath $envPath -Value ($lines -join "`n") -Encoding utf8
    Write-Host "配置已写入：$envPath"
    Write-Host "数据库连接测试成功；现有用户数据未被修改。"
    Write-Host "下一步：在 API 目录运行 python -m uvicorn app.main:app --reload"
} finally {
    if ($null -eq $oldMysqlPwd) { Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue }
    else { $env:MYSQL_PWD = $oldMysqlPwd }
    $plainPassword = $null
}
