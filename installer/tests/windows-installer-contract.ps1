Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Contract([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw $Message }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
$installerPath = Join-Path $repositoryRoot 'install.ps1'
$installerText = Get-Content -LiteralPath $installerPath -Raw
$tokens = $null
$parseErrors = $null
$installerAst = [System.Management.Automation.Language.Parser]::ParseFile(
  $installerPath,
  [ref]$tokens,
  [ref]$parseErrors
)
Assert-Contract ($parseErrors.Count -eq 0) 'install.ps1 did not parse successfully.'

foreach ($Name in @('Assert-ExitCode', 'Assert-Command', 'Assert-Docker', 'Get-ComposePullServices')) {
  $functionAst = $installerAst.Find({
      param($Node)
      $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $Node.Name -eq $Name
    }, $true)
  Assert-Contract ($null -ne $functionAst) "install.ps1 is missing function '$Name'."
  Invoke-Expression $functionAst.Extent.Text
}

# Exercise the production preflight and Compose service derivation with a
# deterministic in-process Docker command.  No Docker daemon is needed.
$global:ComposeVersion = '2.24.4'
$global:DockerCalls = [System.Collections.Generic.List[string]]::new()
function global:docker {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ArgumentList)
  $joined = $ArgumentList -join ' '
  [void]$global:DockerCalls.Add($joined)
  $global:LASTEXITCODE = 0
  if ($joined -match 'compose version --short') { return $global:ComposeVersion }
  if ($joined -match 'compose version') { return "Docker Compose version v$($global:ComposeVersion)" }
  if ($joined -match 'version --format') { return '27.0.0' }
  if ($joined -match 'config --format json') {
    return '{"services":{"registry":{"image":"registry.example/service:latest"},"dashboard":{"build":{"context":"dashboard-app"}}}}'
  }
  throw "Unexpected Docker invocation: $joined"
}

Assert-Docker
Assert-Contract (
  $global:DockerCalls -contains 'version --format {{.Server.Version}}' -and
    ($global:DockerCalls -contains 'compose version') -and
    ($global:DockerCalls -contains 'compose version --short')
) 'Assert-Docker did not perform both Docker and Compose preflight checks.'

$envFile = Join-Path $repositoryRoot '.env.example'
$composeFile = Join-Path $repositoryRoot 'docker-compose.yml'
$pullServices = @(Get-ComposePullServices)
Assert-Contract ($pullServices.Count -eq 1 -and $pullServices[0] -eq 'registry') `
  'Compose pull derivation must select image-only services and exclude build services.'

$global:ComposeVersion = '2.24.3'
$oldVersionRejected = $false
try {
  Assert-Docker
} catch {
  $oldVersionRejected = $_.Exception.Message -match 'too old'
}
Assert-Contract $oldVersionRejected 'Assert-Docker must reject Compose versions older than 2.24.4.'

# The hook is an executable path contract: it must resolve the repository root,
# enter dashboard-app, and run the quality command there.  Keep this check on
# Windows so the Windows developer workflow is covered without invoking npm.
$hookText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'dashboard-app/githooks/pre-commit') -Raw
Assert-Contract ($hookText -match 'git rev-parse --show-toplevel') `
  'pre-commit must resolve the repository root before running quality.'
Assert-Contract ($hookText -match 'dashboard-app') `
  'pre-commit must run from dashboard-app.'
Assert-Contract ($hookText -match 'npm run quality') `
  'pre-commit must run npm run quality.'

# Compose config is intentionally rendered in the Linux matrix; this source
# assertion keeps the Windows contract explicit without requiring Docker on a
# Windows-hosted runner.
Assert-Contract ($installerText -match "QBT_PASSWORD") `
  'Windows installer must retain the qBittorrent password contract.'
$composeText = Get-Content -LiteralPath (Join-Path $repositoryRoot 'docker-compose.yml') -Raw
Assert-Contract ($composeText -match 'QBT_PASSWORD=\$\{QBT_PASSWORD') `
  'homepage-actions must receive QBT_PASSWORD from Compose environment.'

Write-Host 'Windows installer contracts passed.'
