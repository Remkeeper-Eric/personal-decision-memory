param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$taskSession = Join-Path $taskRoot 'runtime/review-session.json'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '项目 Python 环境不存在，请先完成安装。' }
$taskRuntime = Join-Path $taskRoot 'runtime'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
$taskUrl = $null
if (Test-Path -LiteralPath $taskSession) {
    $taskExisting = Get-Content -LiteralPath $taskSession -Raw -Encoding utf8 | ConvertFrom-Json
    try {
        if ($taskExisting.vault -ne (Join-Path $taskRoot 'vault') -or $taskExisting.url -notmatch '^http://127\.0\.0\.1:\d+/review/[A-Za-z0-9_-]+/$') { throw '审核会话不是本项目' }
        $taskResponse = Invoke-WebRequest -UseBasicParsing -Uri ($taskExisting.url + 'api/list') -TimeoutSec 2
        if ($taskResponse.StatusCode -eq 200) { $taskUrl = $taskExisting.url }
    } catch { }
}
if (-not $taskUrl) {
    $taskArguments = @('-m', 'decision_memory', 'review')
    Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'runtime/review-output.log') -RedirectStandardError (Join-Path $taskRoot 'runtime/review-error.log') | Out-Null
    for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
        Start-Sleep -Milliseconds 200
        if (Test-Path -LiteralPath $taskSession) {
            $taskNew = Get-Content -LiteralPath $taskSession -Raw -Encoding utf8 | ConvertFrom-Json
            try {
                $taskResponse = Invoke-WebRequest -UseBasicParsing -Uri ($taskNew.url + 'api/list') -TimeoutSec 1
                if ($taskResponse.StatusCode -eq 200) { $taskUrl = $taskNew.url; break }
            } catch { }
        }
    }
}
if (-not $taskUrl) { throw '审核页面启动失败，请查看 runtime/review-error.log。' }
Write-Output ('审核地址：' + $taskUrl)
if (-not $NoBrowser) { Start-Process $taskUrl }
