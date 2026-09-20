Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$DirectorRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$DirectorRuntime = Join-Path $DirectorRoot '.runtime'

function Get-DirectorRecordPath([string]$Name) {
    if ($Name -notin @('backend', 'web')) { throw 'Unknown service.' }
    Join-Path $DirectorRuntime ($Name + '.json')
}

function Get-DirectorRecord([string]$Name) {
    $path = Get-DirectorRecordPath $Name
    if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
}

function Get-DirectorProcess([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-DirectorProcess($Record) {
    if (-not $Record -or $Record.root -ne $DirectorRoot) { return $false }
    $process = Get-DirectorProcess ([int]$Record.pid)
    if (-not $process) { return $false }
    # PowerShell 7 may deserialize ISO timestamps as DateTime; normalize before
    # comparing so a live owned service is not mistaken for a stale PID.
    $recordCreated = if ($Record.created -is [datetime]) { $Record.created.ToUniversalTime().ToString('o') } else { [string]$Record.created }
    return ($process.ExecutablePath -eq $Record.executable -and
        $process.CreationDate.ToUniversalTime().ToString('o') -eq $recordCreated -and
        $process.CommandLine -eq $Record.command -and
        $process.CommandLine.Contains($DirectorRoot))
}

function Save-DirectorProcess([string]$Name, [int]$ProcessId, [int]$Port) {
    $process = Get-DirectorProcess $ProcessId
    if (-not $process -or -not $process.CommandLine.Contains($DirectorRoot)) {
        throw "Cannot establish process identity for $Name."
    }
    $record = [ordered]@{
        root = $DirectorRoot; name = $Name; pid = $ProcessId; port = $Port
        created = $process.CreationDate.ToUniversalTime().ToString('o')
        executable = $process.ExecutablePath; command = $process.CommandLine
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Get-DirectorRecordPath $Name) -Encoding UTF8
    Get-DirectorRecord $Name
}

function Get-DirectorListeners([int]$Port) {
    # Query the complete table: a failure must not be mistaken for a free port.
    @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $Port)
}

function Assert-DirectorPort([string]$Name, [int]$Port) {
    $record = Get-DirectorRecord $Name
    $owned = Test-DirectorProcess $record
    foreach ($listener in @(Get-DirectorListeners $Port)) {
        if (-not $owned -or [int]$listener.OwningProcess -ne [int]$record.pid) {
            throw "Port $Port is occupied by PID $($listener.OwningProcess). No process was stopped. Close that program yourself or use its own stop command."
        }
    }
    return $owned
}

function Stop-DirectorProcess([string]$Name) {
    $record = Get-DirectorRecord $Name
    if (-not $record) { return }
    if (Test-DirectorProcess $record) {
        Stop-Process -Id ([int]$record.pid) -ErrorAction Stop
        Write-Host "Stopped $Name (PID $($record.pid))."
    } else {
        Write-Host "No matching $Name process; no process was stopped."
    }
    Remove-Item -LiteralPath (Get-DirectorRecordPath $Name) -ErrorAction Stop
}

function Enter-DirectorLock {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($DirectorRoot))).Replace('-', '') }
    finally { $sha.Dispose() }
    $mutex = [Threading.Mutex]::new($false, ('Local\ShortDramaDirector_' + $key))
    if (-not $mutex.WaitOne(0)) { $mutex.Dispose(); throw 'Another start/stop operation is already running.' }
    $mutex
}
