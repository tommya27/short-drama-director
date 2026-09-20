[CmdletBinding()]
param([switch]$SkipInstall)

. (Join-Path $PSScriptRoot 'scripts/runtime-common.ps1')
$directorMutex = Enter-DirectorLock
$startedServices = [Collections.Generic.List[string]]::new()
$previousPythonPath = $env:PYTHONPATH
try {
    $backendRunning = Assert-DirectorPort 'backend' 8200
    $webRunning = Assert-DirectorPort 'web' 5274
    New-Item -ItemType Directory -Path $DirectorRuntime -Force | Out-Null

    if (-not $backendRunning) {
        $pythonCommand = Get-Command py -ErrorAction Stop
        $pythonExe = ((& $pythonCommand.Source -3.13 -c 'import sys; print(sys.executable)' | Select-Object -Last 1).ToString()).Trim()
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExe)) { throw 'Install Python 3.13 with the Windows py launcher first.' }
        $deps = Join-Path $DirectorRoot 'backend/.depsclean'
        $env:PYTHONPATH = $deps
        # Keep this check free of embedded quote characters: Windows PowerShell's
        # native argument marshaller can strip them from a `-c` payload.
        & $pythonExe -c 'import fastapi,uvicorn,pydantic'
        if ($LASTEXITCODE -ne 0) {
            if ($SkipInstall) { throw 'Python dependencies are missing. Run start.ps1 without -SkipInstall.' }
            & $pythonExe -m pip install --disable-pip-version-check --target $deps --upgrade -r (Join-Path $DirectorRoot 'requirements.txt')
            if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
        }
        $arguments = '-m uvicorn api.app:app --app-dir "' + $DirectorRoot + '" --host 127.0.0.1 --port 8200'
        $backend = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $DirectorRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $DirectorRuntime 'backend.stdout.log') -RedirectStandardError (Join-Path $DirectorRuntime 'backend.stderr.log')
        Save-DirectorProcess 'backend' $backend.Id 8200 | Out-Null
        $startedServices.Add('backend')
    }

    if (-not $webRunning) {
        $nodeExe = (Get-Command node -ErrorAction Stop).Source
        $webRoot = Join-Path $DirectorRoot 'web'
        $vite = Join-Path $webRoot 'node_modules/vite/bin/vite.js'
        if (-not (Test-Path -LiteralPath $vite)) {
            if ($SkipInstall) { throw 'Web dependencies are missing. Run start.ps1 without -SkipInstall.' }
            Push-Location $webRoot
            try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed.' } }
            finally { Pop-Location }
        }
        $arguments = '"' + $vite + '" --host 127.0.0.1 --port 5274 --strictPort'
        $web = Start-Process -FilePath $nodeExe -ArgumentList $arguments -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $DirectorRuntime 'web.stdout.log') -RedirectStandardError (Join-Path $DirectorRuntime 'web.stderr.log')
        Save-DirectorProcess 'web' $web.Id 5274 | Out-Null
        $startedServices.Add('web')
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        foreach ($name in @('backend', 'web')) {
            if (-not (Test-DirectorProcess (Get-DirectorRecord $name))) { throw "$name exited. Read .runtime/$name.stderr.log." }
        }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8200/health' -TimeoutSec 1
            $page = Invoke-WebRequest -Uri 'http://127.0.0.1:5274/' -UseBasicParsing -TimeoutSec 1
            if ($health.service -eq 'short-drama-director' -and $page.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Services did not become ready. Read .runtime/*.log.' }
    Write-Host 'Director: http://127.0.0.1:5274/'
    Write-Host 'API docs: http://127.0.0.1:8200/docs'
    # 从后端读取真实运行模式，避免控制台提示与界面徽标互相矛盾
    $runtimeLabel = 'mode unknown'
    try {
        $runtime = Invoke-RestMethod -Uri 'http://127.0.0.1:8200/api/v1/runtime' -TimeoutSec 2
        $runtimeLabel = "$($runtime.label) / generator=$($runtime.generator)"
        if ($runtime.mode -ne 'live') { $runtimeLabel += '（离线规则：未配置模型密钥）' }
    } catch { }
    Write-Host "Model mode: $runtimeLabel"
    Write-Host 'To stop only these services, run ./stop.ps1.'
} catch {
    foreach ($name in $startedServices) { Stop-DirectorProcess $name }
    throw
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $directorMutex.ReleaseMutex()
    $directorMutex.Dispose()
}
