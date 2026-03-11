param(
  [string]$PayloadPath,
  [string]$OutputPath,
  [string]$ProjectUrl = "https://chatgpt.com/g/g-p-69afcec40f908191b65f5b13357d45cf-codexjeonyong/project",
  [string]$ModelLabel = "ChatGPT 5.4 Pro",
  [ValidateSet("select", "current", "ignore")]
  [string]$ModelStrategy = "current",
  [int]$TimeoutMs = 900000,
  [string]$BeginMarker,
  [string]$EndMarker,
  [switch]$BootstrapLogin,
  [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"

$runnerDir = Join-Path $env:LOCALAPPDATA "CodexChatGPTRunner"
$stdoutPath = Join-Path $runnerDir "pinchtab-server.out.log"
$stderrPath = Join-Path $runnerDir "pinchtab-server.err.log"
$sessionPath = Join-Path $runnerDir "pinchtab-session.json"
$baseUrl = "http://127.0.0.1:9867"
$defaultLoginUrl = "https://chatgpt.com/"

function Write-Utf8NoBom {
  param(
    [string]$Path,
    [string]$Content
  )

  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Ensure-RunnerDir {
  New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null
}

function Resolve-PinchtabExe {
  $binDir = Join-Path $env:USERPROFILE ".pinchtab\bin"
  $candidates = @(Get-ChildItem -Path $binDir -Filter "pinchtab-windows-amd64.exe" -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending)
  if ($candidates.Count -eq 0) {
    throw "Pinchtab Windows binary was not found under $binDir"
  }
  return $candidates[0].FullName
}

function Test-Health {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/health" -TimeoutSec 3
    if ([string]::IsNullOrWhiteSpace($response.Content)) {
      return $null
    }
    return ($response.Content | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Ensure-Server {
  $health = Test-Health
  if ($null -ne $health) {
    return $health
  }

  Ensure-RunnerDir
  $pinchtabExe = Resolve-PinchtabExe

  Start-Process `
    -FilePath $pinchtabExe `
    -WorkingDirectory $runnerDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath | Out-Null

  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $health = Test-Health
    if ($null -ne $health) {
      return $health
    }
  }

  throw "Pinchtab server did not become healthy."
}

function Read-ErrorResponse {
  param($Exception)

  if ($null -eq $Exception -or $null -eq $Exception.Response) {
    return $Exception
  }

  try {
    $reader = New-Object System.IO.StreamReader($Exception.Response.GetResponseStream())
    return $reader.ReadToEnd()
  } catch {
    return $Exception
  }
}

function Invoke-JsonApi {
  param(
    [string]$Method,
    [string]$Path,
    $Body = $null
  )

  $params = @{
    Uri = "$baseUrl$Path"
    Method = $Method
    UseBasicParsing = $true
  }

  if ($null -ne $Body) {
    $params.ContentType = "application/json; charset=utf-8"
    $params.Body = ($Body | ConvertTo-Json -Compress -Depth 20)
  }

  try {
    $response = Invoke-WebRequest @params
  } catch {
    $message = Read-ErrorResponse -Exception $_.Exception
    throw "API $Method $Path failed: $message"
  }

  if ([string]::IsNullOrWhiteSpace($response.Content)) {
    return $null
  }

  return ($response.Content | ConvertFrom-Json)
}

function Load-Session {
  if (-not (Test-Path $sessionPath)) {
    return $null
  }

  try {
    return (Get-Content -Raw $sessionPath | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Save-Session {
  param($Session)

  Ensure-RunnerDir
  Write-Utf8NoBom -Path $sessionPath -Content ($Session | ConvertTo-Json -Depth 10)
}

function Get-Instances {
  $instances = Invoke-JsonApi -Method "GET" -Path "/instances"
  if ($null -eq $instances) {
    return @()
  }
  return @($instances)
}

function Get-RunningInstanceById {
  param([string]$InstanceId)

  if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    return $null
  }

  foreach ($instance in Get-Instances) {
    if ($instance.id -eq $InstanceId -and $instance.status -eq "running") {
      return $instance
    }
  }
  return $null
}

function Wait-ForInstance {
  param([string]$InstanceId)

  for ($i = 0; $i -lt 60; $i++) {
    foreach ($instance in Get-Instances) {
      if ($instance.id -eq $InstanceId) {
        if ($instance.status -eq "running") {
          return $instance
        }
        if ($instance.status -eq "error") {
          throw "Pinchtab instance '$InstanceId' entered error state."
        }
      }
    }
    Start-Sleep -Seconds 1
  }

  throw "Timed out waiting for Pinchtab instance '$InstanceId' to start."
}

function Start-HeadedSession {
  $started = Invoke-JsonApi -Method "POST" -Path "/instances/start" -Body @{
    mode = "headed"
  }

  $instance = Wait-ForInstance -InstanceId $started.id
  $session = [ordered]@{
    instanceId = $started.id
    profileId = $started.profileId
    profileName = $started.profileName
    mode = "headed"
    startedAt = (Get-Date).ToString("o")
  }
  Save-Session -Session $session
  return $instance
}

function Get-OrCreateBootstrapInstance {
  $session = Load-Session
  if ($null -ne $session) {
    $existing = Get-RunningInstanceById -InstanceId $session.instanceId
    if ($null -ne $existing -and (Test-InstanceUsable -InstanceId $existing.id)) {
      return $existing
    }
  }

  foreach ($instance in Get-Instances) {
    if ($instance.mode -eq "headed" -and $instance.status -eq "running" -and (Test-InstanceUsable -InstanceId $instance.id)) {
      $adopted = [ordered]@{
        instanceId = $instance.id
        profileId = ""
        profileName = ""
        mode = "headed"
        startedAt = (Get-Date).ToString("o")
      }
      Save-Session -Session $adopted
      return $instance
    }
  }

  return (Start-HeadedSession)
}

function Get-ReviewInstance {
  $session = Load-Session
  if ($null -ne $session) {
    $existing = Get-RunningInstanceById -InstanceId $session.instanceId
    if ($null -ne $existing -and (Test-InstanceUsable -InstanceId $existing.id)) {
      return $existing
    }
  }

  foreach ($instance in Get-Instances) {
    if ($instance.mode -eq "headed" -and $instance.status -eq "running" -and (Test-InstanceUsable -InstanceId $instance.id)) {
      $adopted = [ordered]@{
        instanceId = $instance.id
        profileId = ""
        profileName = ""
        mode = "headed"
        startedAt = (Get-Date).ToString("o")
      }
      Save-Session -Session $adopted
      return $instance
    }
  }

  return $null
}

function Open-Tab {
  param(
    [string]$InstanceId,
    [string]$Url
  )

  $targetUrl = $Url
  if ([string]::IsNullOrWhiteSpace($targetUrl)) {
    $targetUrl = $defaultLoginUrl
  }

  return (Invoke-JsonApi -Method "POST" -Path "/instances/$InstanceId/tabs/open" -Body @{
    url = $targetUrl
  })
}

function Get-Tabs {
  param([string]$InstanceId)

  $tabs = Invoke-JsonApi -Method "GET" -Path "/instances/$InstanceId/tabs"
  if ($null -eq $tabs -or $null -eq $tabs.tabs) {
    return @()
  }
  return @($tabs.tabs)
}

function Get-PrimaryTab {
  param([string]$InstanceId)

  $tabs = Get-Tabs -InstanceId $InstanceId
  if ($tabs.Count -eq 0) {
    return $null
  }

  $preferred = @($tabs | Where-Object { $_.url -and $_.url -ne "about:blank" })
  if ($preferred.Count -gt 0) {
    return $preferred[$preferred.Count - 1]
  }
  return $tabs[$tabs.Count - 1]
}

function Get-TabById {
  param(
    [string]$InstanceId,
    [string]$TabId
  )

  if ([string]::IsNullOrWhiteSpace($TabId)) {
    return $null
  }

  foreach ($tab in Get-Tabs -InstanceId $InstanceId) {
    if ($tab.id -eq $TabId) {
      return $tab
    }
  }

  return $null
}

function Get-TabText {
  param([string]$TabId)

  $response = Invoke-JsonApi -Method "GET" -Path "/tabs/$TabId/text?mode=raw"
  if ($null -eq $response) {
    return ""
  }
  return [string]$response.text
}

function Invoke-TabAction {
  param(
    [string]$TabId,
    [hashtable]$Action
  )

  return (Invoke-JsonApi -Method "POST" -Path "/tabs/$TabId/action" -Body $Action)
}

function Wait-ForPageText {
  param([string]$TabId)

  for ($i = 0; $i -lt 60; $i++) {
    $text = Get-TabText -TabId $TabId
    if (-not [string]::IsNullOrWhiteSpace($text)) {
      return $text
    }
    Start-Sleep -Seconds 2
  }

  return ""
}

function Test-LoginRequired {
  param(
    [string]$Url,
    [string]$Text
  )

  if ($Url -like "*auth/login*") {
    return $true
  }

  $normalized = ""
  if ($null -ne $Text) {
    $normalized = $Text.ToLowerInvariant()
  }

  $requiresLogin = (
    $normalized.Contains("log in") -or
    $normalized.Contains("sign in") -or
    $normalized.Contains("continue with google") -or
    $normalized.Contains("continue with apple")
  )

  return $requiresLogin
}

function Test-HumanVerificationRequired {
  param(
    [string]$Url,
    [string]$Text,
    [string]$Title
  )

  $combined = @($Url, $Text, $Title) -join " "
  $normalized = $combined.ToLowerInvariant()

  return (
    $normalized.Contains("verify you are human") -or
    $normalized.Contains("just a moment") -or
    $normalized.Contains("cloudflare")
  )
}

function Test-InstanceUsable {
  param([string]$InstanceId)

  if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    return $false
  }

  try {
    $null = Get-Tabs -InstanceId $InstanceId
    return $true
  } catch {
    return $false
  }
}

function Submit-Prompt {
  param(
    [string]$TabId,
    [string]$PromptText
  )

  $null = Invoke-TabAction -TabId $TabId -Action @{
    kind = "click"
    selector = "#prompt-textarea"
  }
  $null = Invoke-TabAction -TabId $TabId -Action @{
    kind = "fill"
    selector = "#prompt-textarea"
    text = $PromptText
  }
  $null = Invoke-TabAction -TabId $TabId -Action @{
    kind = "press"
    key = "Enter"
  }
}

function Wait-ForMarkers {
  param([string]$TabId)

  $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
  while ([DateTime]::UtcNow -lt $deadline) {
    $body = Get-TabText -TabId $TabId
    if (-not [string]::IsNullOrWhiteSpace($body)) {
      $beginMatches = ([regex]::Matches($body, [regex]::Escape($BeginMarker))).Count
      $endMatches = ([regex]::Matches($body, [regex]::Escape($EndMarker))).Count
      $beginIndex = $body.LastIndexOf($BeginMarker)
      $endIndex = $body.LastIndexOf($EndMarker)

      if ($beginMatches -ge 2 -and $endMatches -ge 2 -and $beginIndex -ge 0 -and $endIndex -gt $beginIndex) {
        return $body.Substring($beginIndex + $BeginMarker.Length, $endIndex - ($beginIndex + $BeginMarker.Length)).Trim()
      }
    }

    Start-Sleep -Seconds 3
  }

  throw "Timed out waiting for review markers."
}

function Show-Status {
  $session = Load-Session
  $summary = [ordered]@{
    health = (Test-Health)
    session = $session
    instances = @((Get-Instances))
  }
  $summary | ConvertTo-Json -Depth 10
}

function Open-LoginSession {
  $instance = Get-OrCreateBootstrapInstance
  $tab = Open-Tab -InstanceId $instance.id -Url $ProjectUrl
  Start-Sleep -Seconds 2
  $currentTab = $null
  if ($null -ne $tab -and $tab.tabId) {
    $currentTab = Get-TabById -InstanceId $instance.id -TabId $tab.tabId
  }
  if ($null -eq $currentTab) {
    $currentTab = Get-PrimaryTab -InstanceId $instance.id
  }
  $text = ""
  if ($null -ne $currentTab) {
    $text = Wait-ForPageText -TabId $currentTab.id
  }
  $currentUrl = ""
  $currentTitle = ""
  if ($null -ne $currentTab) {
    $currentUrl = $currentTab.url
    $currentTitle = $currentTab.title
  }

  [ordered]@{
    status = "ready"
    session = (Load-Session)
    instance = $instance
    tab = $currentTab
    humanVerificationRequired = (Test-HumanVerificationRequired -Url $currentUrl -Text $text -Title $currentTitle)
    loginRequired = (Test-LoginRequired -Url $currentUrl -Text $text)
  } | ConvertTo-Json -Depth 10
}

Ensure-RunnerDir
$null = Ensure-Server

if ($StatusOnly) {
  Write-Output (Show-Status)
  exit 0
}

if ($BootstrapLogin) {
  Write-Output (Open-LoginSession)
  exit 0
}

if ([string]::IsNullOrWhiteSpace($PayloadPath) -or [string]::IsNullOrWhiteSpace($OutputPath)) {
  throw "PayloadPath and OutputPath are required for review runs."
}

if ($ModelStrategy -eq "select") {
  Write-Warning "Pinchtab migration keeps the current ChatGPT model. Select mode is not automated yet."
}

$payload = [System.IO.File]::ReadAllText($PayloadPath, [System.Text.Encoding]::UTF8)
$instance = Get-ReviewInstance
if ($null -eq $instance) {
  throw "No running Pinchtab ChatGPT session was found. Run chatgpt-browser-up, keep that browser open, sign in once if needed, then retry."
}

$tab = Open-Tab -InstanceId $instance.id -Url $ProjectUrl
Start-Sleep -Seconds 2
$currentTab = $null
if ($null -ne $tab -and $tab.tabId) {
  $currentTab = Get-TabById -InstanceId $instance.id -TabId $tab.tabId
}
if ($null -eq $currentTab) {
  $currentTab = Get-PrimaryTab -InstanceId $instance.id
}
if ($null -eq $currentTab) {
  throw "Pinchtab opened the project, but no active tab was found."
}

$pageText = Wait-ForPageText -TabId $currentTab.id
if (Test-HumanVerificationRequired -Url $currentTab.url -Text $pageText -Title $currentTab.title) {
  throw "Cloudflare human verification is blocking the active Pinchtab browser tab. Complete the checkbox once in that window, wait for ChatGPT to load, then retry."
}
if (Test-LoginRequired -Url $currentTab.url -Text $pageText) {
  throw "ChatGPT login is required for the active Pinchtab browser. Run chatgpt-browser-up, sign in there once, keep it open, then retry."
}

Submit-Prompt -TabId $currentTab.id -PromptText $payload
$review = Wait-ForMarkers -TabId $currentTab.id

Write-Utf8NoBom -Path $OutputPath -Content $review
Write-Output $review
