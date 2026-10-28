<# Verified local installation; -VerifyOnly and -OfflineProfileRoot never launch the app. #>
param(
  [ValidateSet('zh', 'en')] [string]$Lang = 'zh',
  [string]$RepoRoot,
  [string]$AppPath = "$env:LOCALAPPDATA\Programs\open-science\open-science.exe",
  [switch]$VerifyOnly,
  [string]$OfflineProfileRoot,
  [string[]]$EnableConnector = @(),
  [switch]$UpdateProjectContext,
  [switch]$ApplySessionDefaults
)
$ErrorActionPreference = 'Stop'
$Kit = $PSScriptRoot
$SkillId = 'cxcl11-osteosarcoma-tme'
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
. (Join-Path $Kit 'verify_kit.ps1')
$manifest = Test-Kit $Kit
Write-Host "Verified kit $($manifest.version): SHA256 payloads and nested ZIP safety."
if ($VerifyOnly) { return }
$zip = Join-Path $Kit "packages\$Lang\$SkillId-$($manifest.version)-$Lang.zip"
if (-not (Test-Path -LiteralPath $zip)) { throw "Language not included in this kit: $Lang" }

function Invoke-OS {
  $previousNode = $env:ELECTRON_RUN_AS_NODE
  $previousApp = $env:OPEN_SCIENCE_APP_PATH
  $env:ELECTRON_RUN_AS_NODE = '1'
  $env:OPEN_SCIENCE_APP_PATH = $AppPath
  try { $out = @(& $AppPath $Cli @args | ForEach-Object { "$_" }); $code = $LASTEXITCODE }
  finally { $env:ELECTRON_RUN_AS_NODE = $previousNode; $env:OPEN_SCIENCE_APP_PATH = $previousApp }
  if ($code -ne 0) { throw "open-science command failed (exit $code): $($out -join ' ')" }
  $out
}
function Invoke-OSJson { (Invoke-OS @args) -join [Environment]::NewLine | ConvertFrom-Json }

if ($OfflineProfileRoot) {
  $profile = [IO.Path]::GetFullPath($OfflineProfileRoot)
  $realProfile = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('UserProfile')) '.open-science'))
  if ($profile.TrimEnd('\') -ieq $realProfile.TrimEnd('\') -or
      $profile.StartsWith($realProfile.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OfflineProfileRoot must not target the real Open-Science profile.'
  }
  if ($EnableConnector.Count -or $UpdateProjectContext -or $ApplySessionDefaults -or $RepoRoot) {
    throw 'OfflineProfileRoot supports skill-only installation; omit project/connector options.'
  }
} else {
  if (-not (Test-Path -LiteralPath $AppPath)) {
    $setups = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'installer') -Filter 'aipoch-open-science-*-setup.exe' -ErrorAction SilentlyContinue)
    if ($setups.Count -ne 1) { throw 'Exactly one bundled official installer is required when the app is absent.' }
    $setup = $setups[0]
    $signature = Get-AuthenticodeSignature -LiteralPath $setup.FullName
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=AIPOCH PTE\. LTD\.(,|$)') {
      throw "Vendor Authenticode verification failed: $($signature.Status)"
    }
    $process = Start-Process -FilePath $setup.FullName -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $AppPath)) { throw "Vendor installation failed: $($process.ExitCode)" }
  }
  $Cli = Join-Path (Split-Path $AppPath) 'resources\cli\index.mjs'
  if (-not (Test-Path -LiteralPath $Cli)) { throw "App CLI not found: $Cli" }
  $status = Invoke-OSJson status --json
  if (-not $status.running) { Invoke-OS start --no-open | Out-Null; $status = Invoke-OSJson status --json }
  if (-not $status.configRoot) { throw 'App did not report a profile path.' }
  $profile = [IO.Path]::GetFullPath($status.configRoot)
}

# Extract fully before renaming the existing skill. Failed registration restores the old skill.
Assert-NoReparsePath $profile
$imported = Join-Path $profile 'skills\imported'
$target = Join-Path $imported $SkillId
Assert-NoReparsePath $target
if (Test-Path -LiteralPath $target) { @(Get-SafeTreeFiles $target) | Out-Null }
$transactionRoot = Join-Path $profile 'kit-transactions'
Assert-NoReparsePath $transactionRoot
[void][IO.Directory]::CreateDirectory($transactionRoot)
$lockPath = Join-Path $transactionRoot 'install.lock'
$lock = $null
try { $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
catch { throw 'Another kit installation is active for this profile.' }
$transaction = Join-Path $transactionRoot ([guid]::NewGuid().ToString('N'))
$staging = Join-Path $transaction 'staging'
$backup = Join-Path $transaction 'previous-skill'
$hadPrevious = $false
$placed = $false
try {
  Expand-VerifiedSkill $zip $staging $manifest.version $Lang
  [void][IO.Directory]::CreateDirectory($imported)
  if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $backup; $hadPrevious = $true }
  Move-Item -LiteralPath (Join-Path $staging $SkillId) -Destination $target
  $placed = $true
  if (-not $OfflineProfileRoot) {
    $registered = $false
    for ($i = 0; $i -lt 30 -and -not $registered; $i++) {
      $enabled = (Invoke-OSJson doctor --json).checks.skills.enabled
      $registered = ($enabled -contains "imported-$SkillId") -or ($enabled -contains $SkillId)
      if (-not $registered) { Start-Sleep -Seconds 2 }
    }
    if (-not $registered) { throw 'Skill registration timed out; restoring previous installation.' }
  }
  $receipt = [ordered]@{ schema_version = 1; kit_version = $manifest.version; language = $Lang;
    package_sha256 = (Get-PayloadSHA256 $zip);
    target = $target; previous_skill = $(if ($hadPrevious) { $backup } else { $null });
    mode = $(if ($OfflineProfileRoot) { 'offline' } else { 'app' }); state = 'committed' }
  [IO.File]::WriteAllText((Join-Path $transaction 'receipt.json'), ($receipt | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
} catch {
  if ($placed -and (Test-Path -LiteralPath $target)) { Move-Item -LiteralPath $target -Destination (Join-Path $transaction 'failed-skill') }
  if ($hadPrevious -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $target }
  throw
} finally { if ($lock) { $lock.Dispose() } }
Write-Host "Skill installed transactionally: $target"
if ($hadPrevious) { Write-Host "Previous version retained: $backup" }
if ($OfflineProfileRoot) { Write-Host 'Offline skill installation complete; no app was launched.'; return }
if (-not $RepoRoot) {
  Write-Host "Copy the public source from $(Join-Path $Kit 'project') to a separate workspace, then run setup_openscience.ps1 -RepoRoot <workspace>."
  Write-Host "Import six specialist ZIPs in the app from: $(Join-Path $Kit "packages\$Lang")"
  return
}
& (Join-Path $Kit 'setup_openscience.ps1') -AppPath $AppPath -RepoRoot $RepoRoot -EnableConnector $EnableConnector -UpdateProjectContext:$UpdateProjectContext -ApplySessionDefaults:$ApplySessionDefaults
Write-Host "Import six specialist ZIPs in the app from: $(Join-Path $Kit "packages\$Lang")"
