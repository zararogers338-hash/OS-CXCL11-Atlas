<# SHA256 verifies integrity, not publisher identity. Trust the source of this script and manifest. #>
param([string]$KitRoot = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-PayloadSHA256([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  $algorithm = [Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
  finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Assert-SafeRelativePath([string]$Name) {
  if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Contains('\') -or $Name.StartsWith('/') -or
      $Name -match '[\x00-\x1f<>:"|?*]' -or $Name.EndsWith('/')) { throw "Unsafe payload path: $Name" }
  foreach ($part in $Name.Split('/')) {
    if ($part -in @('', '.', '..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
        $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { throw "Unsafe payload path: $Name" }
  }
}
function Assert-NoReparsePath([string]$Path) {
  $itemPath = [IO.Path]::GetFullPath($Path)
  while ($itemPath) {
    if (Test-Path -LiteralPath $itemPath) {
      if ((Get-Item -LiteralPath $itemPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Symlink/junction/reparse point refused: $itemPath"
      }
    }
    $parent = [IO.Path]::GetDirectoryName($itemPath)
    if ($parent -eq $itemPath) { break }
    $itemPath = $parent
  }
}
function Get-SafeTreeFiles([string]$Root) {
  Assert-NoReparsePath $Root
  $pending = New-Object 'System.Collections.Generic.Stack[string]'
  $pending.Push([IO.Path]::GetFullPath($Root))
  while ($pending.Count -gt 0) {
    foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point refused: $($item.FullName)" }
      if ($item.PSIsContainer) { $pending.Push($item.FullName) } else { $item }
    }
  }
}
function Assert-PayloadPath([string]$Name) {
  Assert-SafeRelativePath $Name
  if ($Name -cmatch '^(INSTALL\.md|LICENSE|install\.cmd|install_kit\.ps1|setup_openscience\.ps1|verify_kit\.ps1|project_agent_context\.md)$') { return }
  if ($Name -cmatch '^packages/(en|zh)/[a-z0-9-]+-\d+\.\d+\.\d+-(en|zh)\.zip$') { return }
  if ($Name -cmatch '^installer/aipoch-open-science-\d+\.\d+\.\d+-win-x64-setup\.exe$') { return }
  if ($Name -cmatch '^third_party/(Open-Science-LICENSE\.txt|README\.txt)$') { return }
  if ($Name -cmatch '^project/(config|workflow|py|R|style|tests|ai)/' -or
      $Name -cmatch '^project/docs/data_cards/' -or
      $Name -cmatch '^project/(README\.md|AGENTS\.md|LICENSE|pyproject\.toml|uv\.lock|renv\.lock|\.Rprofile|renv/activate\.R|renv/settings\.json|docs/ARCHITECTURE\.md|docs/RELEASE-0\.4\.0\.md)$') {
    if ($Name -match '(?i)(^|/)(private|data|results|logs|\.git|\.venv|\.claude|manuscript|\.env[^/]*|\.Renviron|credentials|secrets|__pycache__)(/|$)' -or $Name -match '\.py[co]$') {
      throw "Private/generated path refused: $Name"
    }
    return
  }
  throw "Unexpected payload path: $Name"
}
function Test-SafePackage([string]$Archive, [string]$Version, [string]$Language) {
  $skill = 'cxcl11-osteosarcoma-tme'
  $ids = @($skill, 'research-steward', 'bioinfo-analyst', 'figure-artist', 'manuscript-writer', 'reviewer-2', 'reproducibility-auditor')
  $filename = [IO.Path]::GetFileName($Archive)
  $id = $null
  foreach ($candidate in $ids) { if ($filename -ceq "$candidate-$Version-$Language.zip") { $id = $candidate } }
  if (-not $id) { throw "Unknown or mismatched package: $filename" }
  $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
  try {
    if ($zip.Entries.Count -eq 0 -or $zip.Entries.Count -gt 2000) { throw "Invalid entry count: $filename" }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    [long]$total = 0
    foreach ($entry in $zip.Entries) {
      $name = $entry.FullName
      Assert-SafeRelativePath $name
      if (-not $seen.Add($name)) { throw "Duplicate/case-colliding ZIP entry: $name" }
      $mode = ($entry.ExternalAttributes -shr 16) -band 0xF000
      if ($mode -ne 0 -and $mode -ne 0x8000) { throw "Nonregular ZIP entry refused: $name" }
      if (($entry.ExternalAttributes -band 0x400) -ne 0) { throw "Reparse ZIP entry refused: $name" }
      if ($entry.Length -gt 20MB) { throw "Oversized ZIP entry: $name" }
      $total += $entry.Length
      if ($total -gt 80MB) { throw "Oversized ZIP package: $filename" }
      if ($id -eq $skill) {
        if (-not $name.StartsWith("$skill/", [StringComparison]::Ordinal)) { throw "Unexpected skill entry: $name" }
      } elseif ($name -cnotin @('manifest.json', 'specialist.json', 'README.txt') -and
                -not $name.StartsWith("skills/$skill/", [StringComparison]::Ordinal)) { throw "Unexpected specialist entry: $name" }
      $stream = $entry.Open()
      try {
        $buffer = New-Object byte[] 65536
        [long]$actual = 0
        while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
          $actual += $count
          if ($actual -gt $entry.Length -or $actual -gt 20MB) { throw "Decompressed ZIP size exceeds metadata: $name" }
        }
        if ($actual -ne $entry.Length) { throw "Decompressed ZIP size differs from metadata: $name" }
      } finally { $stream.Dispose() }
    }
    foreach ($name in $seen) {
      $parts = $name.Split('/')
      for ($index = 1; $index -lt $parts.Count; $index++) {
        $ancestor = ($parts[0..($index - 1)] -join '/')
        if ($seen.Contains($ancestor)) { throw "ZIP file/directory collision: $name" }
      }
    }
    $required = if ($id -eq $skill) { "$skill/SKILL.md" } else { "skills/$skill/SKILL.md" }
    if (-not $seen.Contains($required)) { throw "Missing SKILL.md: $filename" }
    if ($id -ne $skill) {
      foreach ($needed in @('manifest.json', 'specialist.json', 'README.txt')) {
        if (-not $seen.Contains($needed)) { throw "Missing $needed in $filename" }
      }
      $reader = New-Object IO.StreamReader ($zip.GetEntry('specialist.json').Open())
      try { $spec = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
      if ($spec.name -cne $id -or @($spec.skill_ids).Count -ne 1 -or $spec.skill_ids[0] -cne $skill) { throw "Specialist identity mismatch: $filename" }
      $reader = New-Object IO.StreamReader ($zip.GetEntry('manifest.json').Open())
      try { $meta = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
      if ($meta.schema_version -ne 1 -or $meta.id -cne $id -or $meta.version -cne $Version) { throw "Package metadata mismatch: $filename" }
    }
  } finally { $zip.Dispose() }
}
function Test-Kit([string]$Root) {
  Assert-NoReparsePath $Root
  $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
  $manifestPath = Join-Path $rootPath 'manifest.json'
  if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "manifest.json missing: build/extract the v0.4.0 kit first" }
  $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($manifest.schema_version -ne 1 -or $manifest.hash_algorithm -cne 'sha256' -or
      $manifest.version -notmatch '^\d+\.\d+\.\d+$' -or @($manifest.files).Count -eq 0) { throw 'Invalid kit manifest schema' }
  $expected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
  $languages = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($record in $manifest.files) {
    $name = [string]$record.path
    Assert-PayloadPath $name
    if (-not $expected.Add($name)) { throw "Duplicate/case-colliding manifest path: $name" }
    if ($record.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $record.size -isnot [ValueType] -or $record.size -lt 0) { throw "Invalid hash/size: $name" }
    $path = Join-Path $rootPath $name
    Assert-NoReparsePath $path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing payload: $name" }
    if ((Get-Item -LiteralPath $path).Length -ne $record.size -or
        (Get-PayloadSHA256 $path) -cne $record.sha256) { throw "Payload hash/size mismatch: $name" }
    if ($name -cmatch '^packages/(en|zh)/') {
      $language = $Matches[1]
      [void]$languages.Add($language)
      Test-SafePackage $path $manifest.version $language
    }
  }
  foreach ($file in Get-SafeTreeFiles $rootPath) {
    $relative = $file.FullName.Substring($rootPath.Length + 1).Replace('\', '/')
    if ($relative -cne 'manifest.json' -and -not $expected.Contains($relative)) { throw "Unmanifested payload: $relative" }
  }
  foreach ($required in @('INSTALL.md', 'LICENSE', 'install.cmd', 'install_kit.ps1', 'setup_openscience.ps1', 'verify_kit.ps1', 'project_agent_context.md',
      'project/py/governance.py', 'project/py/research_plan.py', 'project/config/config.yaml', 'project/workflow/Snakefile',
      'project/ai/skills/cxcl11-osteosarcoma-tme/scripts/governance.py',
      'project/ai/skills/cxcl11-osteosarcoma-tme/scripts/research_plan.py',
      'project/ai/skills/cxcl11-osteosarcoma-tme/assets/governance-policy.json',
      'project/ai/skills/cxcl11-osteosarcoma-tme/assets/research-plan.json',
      'project/.Rprofile', 'project/renv/activate.R', 'project/renv/settings.json')) {
    if (-not $expected.Contains($required)) { throw "Missing required kit payload: $required" }
  }
  if ($languages.Count -eq 0) { throw 'No AI packages in kit' }
  foreach ($language in $languages) {
    foreach ($id in @('cxcl11-osteosarcoma-tme', 'research-steward', 'bioinfo-analyst', 'figure-artist', 'manuscript-writer', 'reviewer-2', 'reproducibility-auditor')) {
      if (-not $expected.Contains("packages/$language/$id-$($manifest.version)-$language.zip")) { throw "Incomplete $language package set: $id" }
    }
  }
  return $manifest
}
function Expand-VerifiedSkill([string]$Archive, [string]$Destination, [string]$Version, [string]$Language) {
  Test-SafePackage $Archive $Version $Language
  Assert-NoReparsePath $Destination
  if (Test-Path -LiteralPath $Destination) { throw "Extraction destination must be new: $Destination" }
  [void][IO.Directory]::CreateDirectory($Destination)
  $prefix = [IO.Path]::GetFullPath($Destination).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
  $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
  try {
    foreach ($entry in $zip.Entries) {
      $target = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
      if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Extraction escapes staging: $($entry.FullName)" }
      [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
      [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
    }
  } finally { $zip.Dispose() }
}
if ($MyInvocation.InvocationName -ne '.') {
  $verified = Test-Kit $KitRoot
  Write-Host "Verified kit $($verified.version): $(@($verified.files).Count) SHA256 payloads and all nested packages."
}
