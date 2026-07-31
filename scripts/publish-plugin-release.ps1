[CmdletBinding()]
param(
    [Parameter()]
    [string]$Tag,

    [Parameter()]
    [string]$Remote = 'origin',

    [Parameter()]
    [string]$Branch = 'main',

    [Parameter()]
    [ValidateRange(15, 600)]
    [int]$RunDiscoveryTimeoutSeconds = 120,

    [Parameter()]
    [switch]$Publish,

    [Parameter()]
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Get-BridgeVersion {
    $pyprojectPath = 'octoprint-plugin/pyproject.toml'
    $pluginPath = 'octoprint-plugin/octoprint_filamenthub_bridge/__init__.py'

    $pyprojectContent = Get-Content -LiteralPath $pyprojectPath -Raw
    $pyprojectMatch = [regex]::Match(
        $pyprojectContent,
        '(?m)^version\s*=\s*"(?<version>[^"]+)"\s*$'
    )
    if (-not $pyprojectMatch.Success) {
        throw "Could not read the package version from '$pyprojectPath'."
    }

    $pluginContent = Get-Content -LiteralPath $pluginPath -Raw
    $pluginMatch = [regex]::Match(
        $pluginContent,
        '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>[^"]+)"\s*$'
    )
    if (-not $pluginMatch.Success) {
        throw "Could not read PLUGIN_VERSION from '$pluginPath'."
    }

    $packageVersion = $pyprojectMatch.Groups['version'].Value
    $runtimeVersion = $pluginMatch.Groups['version'].Value
    if ($packageVersion -ne $runtimeVersion) {
        throw "Bridge version mismatch: pyproject.toml=$packageVersion, PLUGIN_VERSION=$runtimeVersion."
    }
    if ($packageVersion -notmatch '^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$') {
        throw "Bridge version '$packageVersion' cannot be used as a release version."
    }

    return $packageVersion
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$Capture
    )

    if ($Capture) {
        $output = & $FilePath @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')`n$($output -join "`n")"
        }
        return ($output -join "`n").Trim()
    }

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Get-Release {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$ReleaseTag
    )

    $json = & gh release view $ReleaseTag --repo $Repository --json isDraft,url,assets 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($json | ConvertFrom-Json)
}

function Get-RemoteTagCommit {
    param(
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$ReleaseTag
    )

    $peeled = & git ls-remote $RemoteName "refs/tags/$ReleaseTag^{}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect tag '$ReleaseTag' on remote '$RemoteName'."
    }
    if ($peeled) {
        return (($peeled -split "`t")[0]).Trim()
    }

    $direct = & git ls-remote $RemoteName "refs/tags/$ReleaseTag" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect tag '$ReleaseTag' on remote '$RemoteName'."
    }
    if ($direct) {
        return (($direct -split "`t")[0]).Trim()
    }
    return $null
}

function Assert-ReleaseAssets {
    param(
        [Parameter(Mandatory)]$Release,
        [Parameter(Mandatory)][string]$BridgeVersion
    )

    $assetNames = @($Release.assets | ForEach-Object { $_.name })
    $escapedVersion = [regex]::Escape($BridgeVersion)
    $requiredPatterns = @(
        "^octoprint_filamenthubbridge-$escapedVersion-.*\.whl$",
        "^octoprint_filamenthubbridge-$escapedVersion\.tar\.gz$",
        '^SHA256SUMS$'
    )

    foreach ($pattern in $requiredPatterns) {
        if (-not ($assetNames | Where-Object { $_ -match $pattern })) {
            throw "Draft release is missing an expected asset matching '$pattern'. Assets: $($assetNames -join ', ')"
        }
    }
}

Assert-Command -Name git
Assert-Command -Name gh

$repositoryRoot = Invoke-Checked -FilePath git -Arguments @('rev-parse', '--show-toplevel') -Capture
Set-Location -LiteralPath $repositoryRoot

$versionFiles = @(
    'octoprint-plugin/pyproject.toml',
    'octoprint-plugin/octoprint_filamenthub_bridge/__init__.py'
)
& git diff --quiet -- $versionFiles
if ($LASTEXITCODE -ne 0) {
    throw 'Commit the Bridge version changes before preparing a release.'
}
& git diff --cached --quiet -- $versionFiles
if ($LASTEXITCODE -ne 0) {
    throw 'Commit the staged Bridge version changes before preparing a release.'
}

$bridgeVersion = Get-BridgeVersion
$expectedTag = "plugins-v$bridgeVersion"
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = $expectedTag
} elseif ($Tag -notmatch '^plugins-v\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$') {
    throw "Tag '$Tag' does not match the plugins-vX.Y.Z release format."
} elseif ($Tag -ne $expectedTag) {
    throw "Tag '$Tag' does not match the committed Bridge version '$bridgeVersion' (expected '$expectedTag')."
}

$currentBranch = Invoke-Checked -FilePath git -Arguments @('branch', '--show-current') -Capture
if ($currentBranch -ne $Branch) {
    throw "Current branch is '$currentBranch'. Switch to '$Branch' before preparing a release."
}

$headCommit = Invoke-Checked -FilePath git -Arguments @('rev-parse', 'HEAD') -Capture
$localTag = Invoke-Checked -FilePath git -Arguments @('tag', '--list', $Tag) -Capture
$tagExistsLocally = -not [string]::IsNullOrWhiteSpace($localTag)
if ($tagExistsLocally) {
    $tagCommit = Invoke-Checked -FilePath git -Arguments @('rev-list', '-n', '1', $Tag) -Capture
    & git merge-base --is-ancestor $tagCommit $headCommit
    if ($LASTEXITCODE -ne 0) {
        throw "Tag '$Tag' ($tagCommit) is not part of the current '$Branch' history."
    }
} else {
    $tagCommit = $headCommit
}

$repository = Invoke-Checked -FilePath gh -Arguments @('repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner') -Capture
Invoke-Checked -FilePath gh -Arguments @('auth', 'status')

$pendingChanges = Invoke-Checked -FilePath git -Arguments @('status', '--porcelain') -Capture
if ($pendingChanges) {
    Write-Warning 'The working tree has uncommitted changes. They will not be included in the release.'
}

Write-Host "Repository : $repository"
Write-Host "Branch     : $Branch ($headCommit)"
Write-Host "Version    : $bridgeVersion"
Write-Host "Release tag: $Tag ($tagCommit)$(if (-not $tagExistsLocally) { ' [will be created]' })"
Write-Host "Mode       : $(if ($Publish) { 'prepare and publish' } else { 'prepare draft only' })"

if ($DryRun) {
    Write-Host 'Dry run complete. No pushes, workflow runs, or release changes were made.'
    return
}

if (-not $tagExistsLocally) {
    Invoke-Checked -FilePath git -Arguments @('tag', '-a', $Tag, '-m', "FilamentHub plugins $bridgeVersion")
    $tagCommit = Invoke-Checked -FilePath git -Arguments @('rev-list', '-n', '1', $Tag) -Capture
    Write-Host "Created local release tag '$Tag' at $tagCommit."
}

Invoke-Checked -FilePath git -Arguments @('push', $Remote, $Branch)

$remoteTagCommit = Get-RemoteTagCommit -RemoteName $Remote -ReleaseTag $Tag
if ($remoteTagCommit) {
    if ($remoteTagCommit -ne $tagCommit) {
        throw "Remote tag '$Tag' points to $remoteTagCommit, expected $tagCommit. Refusing to overwrite it."
    }
    Write-Host "Remote tag '$Tag' already points to the expected commit."
} else {
    Invoke-Checked -FilePath git -Arguments @('push', $Remote, "refs/tags/$Tag")
}

$release = Get-Release -Repository $repository -ReleaseTag $Tag
if (-not $release) {
    $deadline = (Get-Date).AddSeconds($RunDiscoveryTimeoutSeconds)
    $run = $null

    do {
        $runsJson = Invoke-Checked -FilePath gh -Arguments @(
            'run', 'list',
            '--repo', $repository,
            '--workflow', 'release-plugins.yml',
            '--event', 'push',
            '--limit', '20',
            '--json', 'databaseId,headSha,createdAt,status,url'
        ) -Capture
        $runs = @($runsJson | ConvertFrom-Json)
        $run = $runs |
            Where-Object { $_.headSha -eq $tagCommit } |
            Sort-Object { [datetime]$_.createdAt } -Descending |
            Select-Object -First 1

        if (-not $run) {
            Start-Sleep -Seconds 2
        }
    } while (-not $run -and (Get-Date) -lt $deadline)

    if (-not $run) {
        throw "The release workflow run for '$Tag' did not appear within $RunDiscoveryTimeoutSeconds seconds."
    }

    Write-Host "Watching workflow run: $($run.url)"
    Invoke-Checked -FilePath gh -Arguments @('run', 'watch', [string]$run.databaseId, '--repo', $repository, '--exit-status')
    $release = Get-Release -Repository $repository -ReleaseTag $Tag
}

if (-not $release) {
    throw "Workflow completed but release '$Tag' was not found."
}

Assert-ReleaseAssets -Release $release -BridgeVersion $bridgeVersion

if (-not $release.isDraft) {
    Write-Host "Release is already published: $($release.url)"
    return
}

if ($Publish) {
    Invoke-Checked -FilePath gh -Arguments @('release', 'edit', $Tag, '--repo', $repository, '--draft=false')
    $release = Get-Release -Repository $repository -ReleaseTag $Tag
    Write-Host "Release published: $($release.url)"
} else {
    Write-Host "Draft release is ready: $($release.url)"
    Write-Host "Review it, then publish with: .\scripts\publish-plugin-release.ps1 -Tag $Tag -Publish"
}
