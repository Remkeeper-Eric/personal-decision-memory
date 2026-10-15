$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskSession = Join-Path $taskRoot 'runtime/review-session.json'
if (Test-Path -LiteralPath $taskSession) {
    $taskInfo = Get-Content -LiteralPath $taskSession -Raw -Encoding utf8 | ConvertFrom-Json
    if ($taskInfo.url -notmatch '^http://127\.0\.0\.1:\d+/review/[A-Za-z0-9_-]+/$') { throw '审核地址不是允许的本机地址。' }
    try { $taskIdentity = Invoke-RestMethod -Uri ($taskInfo.url + 'api/identity') -TimeoutSec 2 }
    catch { Write-Output '本机审核服务未运行，无需停止。'; return }
    if ($taskIdentity.pid -ne $taskInfo.pid -or $taskIdentity.vault -ne (Join-Path $taskRoot 'vault')) { throw '审核进程与本项目不匹配，未停止。' }
    $taskProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$taskInfo.pid)
    $taskExpected = (Join-Path $taskRoot '.venv/Scripts/python.exe')
    $taskBaseLine = Get-Content -LiteralPath (Join-Path $taskRoot '.venv/pyvenv.cfg') | Where-Object { $_ -match '^home = ' } | Select-Object -First 1
    $taskBasePython = Join-Path ($taskBaseLine -replace '^home = ', '') 'python.exe'
    if ($taskProcess -and $taskProcess.ExecutablePath -in @($taskExpected,$taskBasePython) -and $taskProcess.CommandLine -match 'decision_memory.+review') {
        Stop-Process -Id ([int]$taskInfo.pid)
        Write-Output '本机审核服务已停止。'
    } else { Write-Output '未找到本项目的审核进程，未停止其他程序。' }
}
