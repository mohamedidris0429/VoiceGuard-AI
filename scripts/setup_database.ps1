<#
    VoiceGuard AI - local PostgreSQL setup (Windows)

    Creates a dedicated PostgreSQL 18 cluster inside this project on port 5433,
    starts it, creates the `voiceguard` database and applies Alembic migrations.
    It never touches an existing PostgreSQL service on port 5432.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File scripts\setup_database.ps1
#>

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $projectRoot 'storage\.pgdata'
$logFile = Join-Path $projectRoot 'storage\pg.log'
$port = 5433
$dbUser = 'voiceguard'
$dbName = 'voiceguard'

function Find-PgBin {
    $candidates = @(
        'C:\Program Files\PostgreSQL\18\bin',
        'C:\Program Files\PostgreSQL\17\bin',
        'C:\Program Files\PostgreSQL\16\bin'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate 'initdb.exe')) { return $candidate }
    }
    $psql = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($psql) { return (Split-Path -Parent $psql.Source) }
    throw 'PostgreSQL binaries were not found. Install PostgreSQL 18 from https://www.postgresql.org/download/windows/'
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.ConnectAsync('127.0.0.1', $Port)
        return $async.Wait(800) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

$pgBin = Find-PgBin
Write-Host "Using PostgreSQL binaries: $pgBin"

if (-not (Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    Write-Host 'Initialising project-local PostgreSQL cluster...'
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    & (Join-Path $pgBin 'initdb.exe') -D $dataDir -U $dbUser -A trust -E UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'initdb failed.' }
    Add-Content -Path (Join-Path $dataDir 'postgresql.auto.conf') -Value @(
        "port = $port",
        "listen_addresses = '127.0.0.1'",
        'shared_buffers = 64MB',
        'max_connections = 20',
        'work_mem = 4MB'
    )
    Write-Host 'Cluster created (trust authentication, loopback only).'
}

if (-not (Test-Port $port)) {
    Write-Host "Starting PostgreSQL on port $port..."
    if (-not (Test-Path $logFile)) { New-Item -ItemType File -Path $logFile | Out-Null }
    Start-Process -FilePath (Join-Path $pgBin 'postgres.exe') `
        -ArgumentList @('-D', "`"$dataDir`"", '-p', $port) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError ($logFile + '.err')
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Port $port) { break }
    }
    if (-not (Test-Port $port)) {
        throw "PostgreSQL did not start. Inspect $logFile for details."
    }
    Write-Host 'PostgreSQL is running.'
} else {
    Write-Host "PostgreSQL already listening on port $port."
}

$databaseExists = & (Join-Path $pgBin 'psql.exe') -h 127.0.0.1 -p $port -U $dbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$dbName'"
if ($databaseExists -notmatch '1') {
    Write-Host "Creating database $dbName..."
    & (Join-Path $pgBin 'createdb.exe') -h 127.0.0.1 -p $port -U $dbUser $dbName
}

$python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw 'Backend virtual environment missing. Run: python -m venv backend/.venv && backend\.venv\Scripts\pip install -r backend\requirements.txt'
}

Write-Host 'Applying database migrations...'
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed.' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host "Database ready: postgresql+psycopg://$dbUser`:$dbUser@127.0.0.1:$port/$dbName"
Write-Host 'Ensure backend\.env contains the matching DATABASE_URL.'
