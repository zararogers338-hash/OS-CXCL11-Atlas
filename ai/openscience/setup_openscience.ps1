<# Configure an explicitly selected project from a verified kit. Existing settings are preserved by default. #>
param(
  [string]$AppPath = "$env:LOCALAPPDATA\Programs\open-science\open-science.exe",
  [string]$RepoRoot,
  [string]$ProjectName = 'OS-CXCL11 Atlas',
  [string[]]$EnableConnector = @(),
  [switch]$UpdateProjectContext,
  [switch]$ApplySessionDefaults
)
$ErrorActionPreference = 'Stop'
# Authenticate the helper against the manifest before dot-sourcing it. The manifest itself is unsigned.
$bootstrapManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$helperPath = Join-Path $PSScriptRoot 'verify_kit.ps1'
$helperRecords = @($bootstrapManifest.files | Where-Object { $_.path -ceq 'verify_kit.ps1' })
if ($helperRecords.Count -ne 1 -or
    ((Get-Item -LiteralPath $helperPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid verification helper record/path.' }
$bootstrapStream = [IO.File]::OpenRead($helperPath)
$bootstrapHasher = [Security.Cryptography.SHA256]::Create()
try { $helperHash = ([BitConverter]::ToString($bootstrapHasher.ComputeHash($bootstrapStream))).Replace('-', '').ToLowerInvariant() }
finally { $bootstrapHasher.Dispose(); $bootstrapStream.Dispose() }
if ($helperHash -cne $helperRecords[0].sha256 -or (Get-Item -LiteralPath $helperPath).Length -ne $helperRecords[0].size) {
  throw 'Verification helper hash/size mismatch; refusing to execute it.'
}
. (Join-Path $PSScriptRoot 'verify_kit.ps1')
$manifest = Test-Kit $PSScriptRoot
if (-not $RepoRoot) { throw 'Pass -RepoRoot pointing to a separate workspace copied from the kit project/ source snapshot.' }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
$kitPrefix = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($RepoRoot.StartsWith($kitPrefix, [StringComparison]::OrdinalIgnoreCase) -or $RepoRoot.TrimEnd('\', '/') -ieq $kitPrefix.TrimEnd('\', '/')) {
  throw 'The kit is an immutable verified source snapshot; copy project/ outside the kit before using it as a workspace.'
}
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'config\config.yaml')) -or
    -not (Test-Path -LiteralPath (Join-Path $RepoRoot 'py\governance.py'))) { throw "Not a v0.4.0 project source tree: $RepoRoot" }
if (-not (Test-Path -LiteralPath $AppPath)) { throw "Open-Science not found: $AppPath" }
$Cli = Join-Path (Split-Path $AppPath) 'resources\cli\index.mjs'
function Invoke-OS {
  $previousNode = $env:ELECTRON_RUN_AS_NODE
  $previousApp = $env:OPEN_SCIENCE_APP_PATH
  $env:ELECTRON_RUN_AS_NODE = '1'; $env:OPEN_SCIENCE_APP_PATH = $AppPath
  try { $out = @(& $AppPath $Cli @args | ForEach-Object { "$_" }); $code = $LASTEXITCODE }
  finally { $env:ELECTRON_RUN_AS_NODE = $previousNode; $env:OPEN_SCIENCE_APP_PATH = $previousApp }
  if ($code -ne 0) { throw "open-science command failed (exit $code): $($out -join ' ')" }
  $out
}
function Invoke-OSJson { (Invoke-OS @args) -join [Environment]::NewLine | ConvertFrom-Json }
$status = Invoke-OSJson status --json
if (-not $status.running) { Invoke-OS start --no-open | Out-Null }
if ($EnableConnector.Count -gt 0) {
  $connectors = @((Invoke-OSJson connector list --json).connectors | ForEach-Object { $_ })
  foreach ($id in $EnableConnector) {
    if ($id -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') { throw "Invalid connector id: $id" }
    $matching = @($connectors | Where-Object { $_.id -eq $id -or $_.name -eq $id })
    if ($matching.Count -ne 1) { throw "Unknown/ambiguous connector id: $id" }
  }
  foreach ($id in $EnableConnector) {
    $connector = @($connectors | Where-Object { $_.id -eq $id -or $_.name -eq $id })[0]
    if (-not $connector.enabled) { Invoke-OS connector enable $id | Out-Null }
  }
}
Write-Host "Connector allowlist: $($EnableConnector.Count) requested; all other settings preserved."
$existing = @((Invoke-OSJson project list --json) | ForEach-Object { $_ } | Where-Object { $_.name -eq $ProjectName })
if ($existing.Count -gt 1) { throw "Multiple projects named $ProjectName; resolve ambiguity in the app." }
if ($existing.Count -eq 0 -or $UpdateProjectContext) {
  $template = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'project_agent_context.md') -Raw -Encoding UTF8
  $context = Join-Path ([IO.Path]::GetTempPath()) "os-cxcl11-context-$([guid]::NewGuid().ToString('N')).md"
  try {
    [IO.File]::WriteAllText($context, $template.Replace('{{REPO_ROOT}}', $RepoRoot), (New-Object Text.UTF8Encoding $false))
    if ($existing.Count -eq 1) { Invoke-OS project update $ProjectName --agent-context-file $context --json | Out-Null }
    else { Invoke-OS project create $ProjectName --description 'Evidence-governed OS-CXCL11 research workspace' --agent-context-file $context --json | Out-Null }
  } finally { if (Test-Path -LiteralPath $context) { Remove-Item -LiteralPath $context } }
}
if ($ApplySessionDefaults) { Invoke-OS project session-defaults update $ProjectName --auto-review --memory --delegation allow --json | Out-Null }
if ($existing.Count -eq 1 -and -not $UpdateProjectContext) { Write-Host "Existing project context preserved: $ProjectName. Use -UpdateProjectContext to bind it to $RepoRoot." }
else { Write-Host "Project context configured: $ProjectName; source: $RepoRoot" }
Write-Host 'Enter model credentials in the app and import six specialist packages. Scientific data and pipeline dependencies are separate.'
