<# Read-only login smoke test. It never registers, updates, or deletes users. #>
[CmdletBinding()]
param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$username = Read-Host "WishinDiary 用户名"
$securePassword = Read-Host "WishinDiary 登录密码（输入不会显示）" -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}

try {
    $payload = @{ username = $username; password = $password } | ConvertTo-Json
    $result = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/auth/login" `
        -ContentType "application/json" -Body $payload -SessionVariable LoginSession
    Write-Host "登录成功：$($result.username) (user_id=$($result.user_id))" -ForegroundColor Green
} catch {
    $detail = $_.ErrorDetails.Message
    if ($detail) {
        Write-Host "登录失败，API 返回：$detail" -ForegroundColor Yellow
    } else {
        Write-Host "登录失败：$($_.Exception.Message)" -ForegroundColor Yellow
    }
} finally {
    $password = $null
}
