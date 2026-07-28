#Requires -Version 7.0
<#
.SYNOPSIS
  First-time installer for the Media Manager monorepo.
.EXAMPLE
  .\install.ps1 -Mode both
  .\install.ps1 -Mode stack -Gpu -Force
#>
[CmdletBinding()]
param(
  [ValidateSet('stack', 'frontend-dev', 'both')]
  [string]$Mode = 'both',
  [switch]$Force,
  [switch]$Gpu,
  [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$DashboardApp = Join-Path $RepoRoot 'dashboard-app'
$EnvFile = Join-Path $RepoRoot '.env'
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'
$ComposeGpuFile = Join-Path $RepoRoot 'docker-compose.gpu.yml'
$Interactive = -not [Console]::IsInputRedirected
$script:NpmCiComplete = $false

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }

function Assert-ExitCode([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." }
}

function Assert-Command([string]$Name, [string]$InstallHint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "'$Name' not found. $InstallHint"
  }
}

function Assert-Node {
  Assert-Command 'node' 'Install Node.js 20+ from https://nodejs.org/'
  Assert-Command 'npm' 'Install Node.js 20+ from https://nodejs.org/'
  $major = [int]((node --version).TrimStart('v').Split('.')[0])
  if ($major -lt 20) { throw "Node.js 20+ required, found $(node --version)." }
  Write-Host "node $(node --version), npm $(npm --version)"
}

function Assert-Docker {
  Assert-Command 'docker' 'Install Docker Desktop: https://www.docker.com/products/docker-desktop/'
  docker compose version | Out-Null
  Assert-ExitCode 'docker compose version'
  Write-Host (docker --version)
}

function Format-DotEnvValue([string]$Value) {
  $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
  return "`"$escaped`""
}

function Read-Value([string]$Prompt, [string]$Default, [string]$EnvVar) {
  $fromEnv = (Get-Item -Path "Env:$EnvVar" -ErrorAction SilentlyContinue).Value
  if ($fromEnv) { return $fromEnv }
  if ($Interactive) {
    $answer = Read-Host "$Prompt [$Default]"
    if ($answer) { return $answer }
  }
  return $Default
}

function Invoke-NpmCi {
  if ($script:NpmCiComplete) { return }
  Push-Location $DashboardApp
  try {
    npm ci
    Assert-ExitCode 'npm ci'
    $script:NpmCiComplete = $true
  } finally { Pop-Location }
}

function Initialize-EnvFile {
  if ((Test-Path $EnvFile) -and -not $Force) {
    Write-Host ".env already exists (use -Force to recreate). Keeping it."
    return
  }
  $rootPath = (Read-Value 'Media root path' $RepoRoot 'ROOT_PATH') -replace '\\', '/'
  $downloadsPath = (Read-Value 'Downloads path' "$rootPath/downloads" 'DOWNLOADS_PATH') -replace '\\', '/'
  $password = Read-Value 'Stack password (qBittorrent WebUI)' 'changeme' 'STACK_PASSWORD'
  if ($password -eq 'changeme') {
    Write-Warning "Using default password 'changeme'. Change it in .env and the qBittorrent WebUI."
  }
  $values = @{
    'ROOT_PATH'       = $rootPath
    'DOWNLOADS_PATH'  = $downloadsPath
    'ACTIONS_TOKEN'   = [guid]::NewGuid().ToString('N')
    'STACK_PASSWORD'  = $password
  }
  $lines = Get-Content (Join-Path $RepoRoot '.env.example') | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=' -and $values.ContainsKey($Matches[1])) {
      "$($Matches[1])=$(Format-DotEnvValue $values[$Matches[1]])"
    } else { $_ }
  }
  Set-Content -Path $EnvFile -Value $lines -Encoding utf8
  Write-Host "Wrote $EnvFile (gitignored; never commit it)."
}

function Build-DashboardImage {
  Invoke-NpmCi
  Push-Location $DashboardApp
  try {
    npm run build:live
    Assert-ExitCode 'npm run build:live'
  } finally { Pop-Location }
  docker build -t media-dashboard-angular:local $DashboardApp
  Assert-ExitCode 'docker build'
  $pinMatch = Select-String -Path $ComposeFile -Pattern 'image: media-dashboard-angular:(\S+)'
  if (-not $pinMatch) {
    throw 'Could not find media-dashboard-angular image pin in docker-compose.yml.'
  }
  $pin = $pinMatch.Matches[0].Groups[1].Value
  docker tag media-dashboard-angular:local "media-dashboard-angular:$pin"
  Assert-ExitCode 'docker tag'
  Write-Host "Tagged media-dashboard-angular:local as media-dashboard-angular:$pin (compose pin)."
}

function Invoke-Stack {
  Assert-Docker
  Assert-Node   # dashboard image is built from source
  Initialize-EnvFile

  $envContent = Get-Content $EnvFile -Raw
  if ($envContent -match '(?m)^DOWNLOADS_PATH=(?:"([^"]*)"|([^\r\n]+))') {
    $downloadsDir = if ($Matches[1]) { $Matches[1] } else { $Matches[2].Trim() }
    New-Item -ItemType Directory -Force $downloadsDir | Out-Null
  }

  if (-not $SkipBuild) { Build-DashboardImage }

  Write-Step 'Pulling service images'
  docker compose --env-file $EnvFile -f $ComposeFile pull --ignore-pull-failures

  Write-Step 'Starting the stack'
  if ($Gpu) {
    docker compose --env-file $EnvFile -f $ComposeFile -f $ComposeGpuFile up -d
  } else {
    docker compose --env-file $EnvFile -f $ComposeFile up -d
  }
  Assert-ExitCode 'docker compose up'

  Write-Step 'Waiting for homepage-actions health'
  $healthy = $false
  foreach ($attempt in 1..12) {
    try {
      $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8085/health' -TimeoutSec 5
      if ($response) { $healthy = $true; break }
    } catch { Start-Sleep -Seconds 5 }
  }
  if ($healthy) { Write-Host 'homepage-actions healthy on http://127.0.0.1:8085' }
  else { Write-Warning 'homepage-actions did not answer /health yet — check: docker compose logs homepage-actions' }

  Write-Host @"

Stack is up. Remaining manual steps (one-time):
  1. Open each service and copy its API key into .env:
       Jellyfin    http://localhost:8096   (Dashboard > API Keys)
       Radarr      http://127.0.0.1:7878   (Settings > General)
       Sonarr      http://127.0.0.1:8989   (Settings > General)
       Prowlarr    http://127.0.0.1:9696   (Settings > General)
       Bazarr      http://127.0.0.1:6767   (Settings > General)
       Jellyseerr  http://127.0.0.1:5055
  2. Apply the keys:  docker compose up -d
  3. Dashboard:       http://127.0.0.1:3000
  qBittorrent WebUI:  http://127.0.0.1:8081 (admin / password you set)
"@
}

function Invoke-FrontendDev {
  Assert-Node
  Invoke-NpmCi
  Write-Host @"

Frontend dev ready. From dashboard-app/:
  npm start            Demo mode (mock data)   -> http://localhost:4200/
  npm run start:live   Live mode (needs stack running + ACTIONS_TOKEN in shell env)
"@
}

Push-Location $RepoRoot
try {
  switch ($Mode) {
    'frontend-dev' { Invoke-FrontendDev }
    'stack'        { Invoke-Stack }
    'both'         { Invoke-FrontendDev; Invoke-Stack }
  }
} finally {
  Pop-Location
}
