#Requires -Version 7.0
<#
.SYNOPSIS
  First-time installer for the Media Manager monorepo.
.EXAMPLE
  .\install.ps1 -Mode both
  .\install.ps1 -Mode stack -Gpu -Force
  .\install.ps1 -Mode redeploy-dashboard
#>
[CmdletBinding()]
param(
  [ValidateSet('stack', 'frontend-dev', 'both', 'redeploy-dashboard')]
  [string]$Mode = 'both',
  [switch]$Force,
  [switch]$Gpu
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

function Get-ComposePullServices {
  $configJson = docker compose --env-file $EnvFile -f $ComposeFile config --format json
  Assert-ExitCode 'docker compose config'
  $config = $configJson | ConvertFrom-Json
  $services = @(
    $config.services.PSObject.Properties |
      Where-Object { $_.Value.PSObject.Properties.Name -notcontains 'build' } |
      Select-Object -ExpandProperty Name
  )
  if (-not $services) { throw 'Compose config contains no enabled non-build services to pull.' }
  return $services
}

function Assert-Node {
  Assert-Command 'node' 'Install Node.js from https://nodejs.org/'
  Assert-Command 'npm' 'Install Node.js from https://nodejs.org/'
  Write-Host "node $(node --version), npm $(npm --version)"
}

function Assert-Docker {
  Assert-Command 'docker' 'Install and start Docker Desktop from https://www.docker.com/products/docker-desktop/'
  docker version --format '{{.Server.Version}}' | Out-Null
  Assert-ExitCode 'Docker daemon check'
  docker compose version | Out-Null
  Assert-ExitCode 'Docker Compose check'
  $composeVer = (docker compose version --short).Trim()
  if (-not $composeVer) { throw 'Could not read Docker Compose version.' }
  $parts = $composeVer.Split('.')
  $major = [int]$parts[0]
  $minor = if ($parts.Length -gt 1) { [int]$parts[1] } else { 0 }
  $patch = if ($parts.Length -gt 2) { [int]($parts[2] -replace '\D.*$', '') } else { 0 }
  # docker-compose.dev.yml uses Compose reset/override tags (Compose 2.24.4+)
  if ($major -lt 2 -or ($major -eq 2 -and ($minor -lt 24 -or ($minor -eq 24 -and $patch -lt 4)))) {
    throw "Docker Compose $composeVer is too old; need 2.24.4+ for docker-compose.dev.yml (Compose reset/override tags)."
  }
}

function Assert-AngularNodeEngine {
  Push-Location $DashboardApp
  try {
    node -e @"
const semver = require('semver');
const pkg = require('@angular/cli/package.json');
const version = process.version.replace(/^v/, '');
if (!semver.satisfies(version, pkg.engines.node)) {
  console.error('Node ' + process.version + ' does not satisfy Angular CLI requirement: ' + pkg.engines.node);
  process.exit(1);
}
"@
    Assert-ExitCode 'Angular CLI Node engine check'
  } finally { Pop-Location }
}

function Format-DotEnvValue([string]$Value) {
  $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
  return "`"$escaped`""
}

function Read-Value([string]$Prompt, [string]$Default, [string]$EnvVar) {
  $fromEnv = [Environment]::GetEnvironmentVariable($EnvVar)
  if ($fromEnv) { return $fromEnv }
  if ($Interactive) {
    $answer = Read-Host "$Prompt [$Default]"
    if ($answer) { return $answer }
  }
  return $Default
}

function Get-EnvMap([string[]]$Lines) {
  $map = @{}
  foreach ($line in $Lines) {
    if ($line -match '^([A-Z_]+)=(.*)$') {
      $map[$Matches[1]] = $Matches[2]
    }
  }
  return $map
}

function Unquote-DotEnvValue([string]$Value) {
  if ($Value -match '^"(.*)"$') { return $Matches[1].Replace('\"', '"').Replace('\\', '\') }
  return $Value
}

function Merge-MissingEnvKeys {
  $lines = [System.Collections.Generic.List[string]]::new()
  $lines.AddRange([string[]](Get-Content $EnvFile))
  $map = Get-EnvMap $lines
  $changed = $false

  if (-not $map.ContainsKey('DOWNLOADS_PATH')) {
    $root = if ($map['ROOT_PATH']) { (Unquote-DotEnvValue $map['ROOT_PATH']) -replace '\\', '/' } else { $RepoRoot -replace '\\', '/' }
    $lines.Add("DOWNLOADS_PATH=$(Format-DotEnvValue "$root/downloads")")
    $changed = $true
  }
  if (-not $map.ContainsKey('QBT_PASSWORD') -and $map.ContainsKey('STACK_PASSWORD')) {
    $lines.Add("QBT_PASSWORD=$($map['STACK_PASSWORD'])")
    $changed = $true
  }

  if ($changed) {
    Set-Content -Path $EnvFile -Value $lines -Encoding utf8
    Write-Host 'Added missing keys to .env (DOWNLOADS_PATH and/or QBT_PASSWORD).'
  }
}

function Initialize-EnvFile {
  if ((Test-Path $EnvFile) -and -not $Force) {
    Merge-MissingEnvKeys
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
    'QBT_PASSWORD'    = $password
  }
  $lines = Get-Content (Join-Path $RepoRoot '.env.example') | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=' -and $values.ContainsKey($Matches[1])) {
      "$($Matches[1])=$(Format-DotEnvValue $values[$Matches[1]])"
    } else { $_ }
  }
  Set-Content -Path $EnvFile -Value $lines -Encoding utf8
  Write-Host "Wrote $EnvFile (gitignored; never commit it)."
}

function Invoke-NpmCi {
  if ($script:NpmCiComplete) { return }
  Push-Location $DashboardApp
  try {
    npm ci
    Assert-ExitCode 'npm ci'
    $script:NpmCiComplete = $true
    Assert-AngularNodeEngine
  } finally { Pop-Location }
}

function Invoke-RedeployDashboard {
  Assert-Docker
  Initialize-EnvFile
  Write-Step 'Building dashboard with Compose and recreating container (http://127.0.0.1:3000)'
  if ($Gpu) {
    docker compose --env-file $EnvFile -f $ComposeFile -f $ComposeGpuFile up -d --build --force-recreate dashboard
  } else {
    docker compose --env-file $EnvFile -f $ComposeFile up -d --build --force-recreate dashboard
  }
  Assert-ExitCode 'docker compose up --build dashboard'
  Write-Host 'Dashboard redeployed. Hard-refresh the browser (Ctrl+Shift+R) if assets look cached.'
}

function Invoke-Stack {
  Assert-Docker
  Initialize-EnvFile

  $envContent = Get-Content $EnvFile -Raw
  if ($envContent -match '(?m)^DOWNLOADS_PATH=(?:"([^"]*)"|([^\r\n]+))') {
    $downloadsDir = if ($Matches[1]) { $Matches[1] } else { (Unquote-DotEnvValue $Matches[2].Trim()) }
    New-Item -ItemType Directory -Force $downloadsDir | Out-Null
  }

  Write-Step 'Pulling service images'
  $composePullServices = Get-ComposePullServices
  docker compose --env-file $EnvFile -f $ComposeFile pull $composePullServices
  Assert-ExitCode 'docker compose pull service images'

  Write-Step 'Building the dashboard and starting the stack'
  if ($Gpu) {
    docker compose --env-file $EnvFile -f $ComposeFile -f $ComposeGpuFile up -d --build
  } else {
    docker compose --env-file $EnvFile -f $ComposeFile up -d --build
  }
  Assert-ExitCode 'docker compose up --build'

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
  1. Optional profiles: subtitles enables Bazarr; requests enables Jellyseerr.
     Enable them before opening those services, for example:
       docker compose --profile subtitles --profile requests up -d
     Set BAZARR_ENABLED=true / JELLYSEERR_ENABLED=true only after their API keys are configured.
  2. Open each enabled service and copy its API key into .env:
       Jellyfin    http://localhost:8096   (Dashboard > API Keys)
       Radarr      http://127.0.0.1:7878   (Settings > General)
       Sonarr      http://127.0.0.1:8989   (Settings > General)
       Prowlarr    http://127.0.0.1:9696   (Settings > General)
       Bazarr      http://127.0.0.1:6767   (Settings > General)
       Jellyseerr  http://127.0.0.1:5055
  3. Set the selected BAZARR_ENABLED/JELLYSEERR_ENABLED flags to true in .env, then apply the keys and keep those profiles enabled:
       docker compose --profile subtitles --profile requests up -d
     (omit profiles you did not enable)
  4. Dashboard:       http://127.0.0.1:3000
  qBittorrent WebUI:  http://127.0.0.1:8081 (admin; set WebUI password to match QBT_PASSWORD in .env on first login)
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
    'frontend-dev'       { Invoke-FrontendDev }
    'stack'              { Invoke-Stack }
    'both'               { Invoke-FrontendDev; Invoke-Stack }
    'redeploy-dashboard' { Invoke-RedeployDashboard }
  }
} finally {
  Pop-Location
}
