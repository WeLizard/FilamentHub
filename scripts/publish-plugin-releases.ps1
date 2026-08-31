[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('all', 'orcaslicer', 'octoprint', 'print-farm')]
    [string[]]$Component = @('all'),

    [Parameter()]
    [string]$Remote = 'origin',

    [Parameter()]
    [string]$Branch = 'main',

    [Parameter()]
    [string]$PrintFarmPath,

    [Parameter()]
    [ValidateRange(15, 600)]
    [int]$RunDiscoveryTimeoutSeconds = 120,

    [Parameter()]
    [switch]$HideReleaseNotes,

    [Parameter()]
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Не найдена обязательная команда '$Name' в PATH."
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$WorkingDirectory,
        [switch]$Capture
    )

    $previous = Get-Location
    try {
        if ($WorkingDirectory) {
            Set-Location -LiteralPath $WorkingDirectory
        }
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "Команда завершилась с ошибкой (${exitCode}): $FilePath $($Arguments -join ' ')`n$($output -join "`n")"
        }
        if ($Capture) {
            return ($output -join "`n").Trim()
        }
        foreach ($line in $output) {
            Write-Host $line
        }
    } finally {
        Set-Location -LiteralPath $previous
    }
}

function Get-RepositoryName {
    param([Parameter(Mandatory)][string]$RepositoryPath)

    return Invoke-Checked gh @(
        'repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner'
    ) -WorkingDirectory $RepositoryPath -Capture
}

function Get-Release {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag
    )

    $json = & gh release view $Tag --repo $Repository `
        --json tagName,isDraft,isPrerelease,publishedAt,url,assets 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($json | ConvertFrom-Json)
}

function Get-PublishedComponent {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$AssetPattern,
        [Parameter(Mandatory)][string[]]$TagPatterns
    )

    $json = Invoke-Checked gh @(
        'release', 'list', '--repo', $Repository, '--limit', '50',
        '--json', 'tagName,isDraft,isPrerelease,publishedAt'
    ) -Capture
    $summaries = @($json | ConvertFrom-Json)

    foreach ($tagPattern in $TagPatterns) {
        foreach ($summary in $summaries) {
            if ($summary.isDraft -or $summary.isPrerelease -or
                [string]$summary.tagName -notmatch $tagPattern) {
                continue
            }
            $release = Get-Release -Repository $Repository -Tag ([string]$summary.tagName)
            if (-not $release -or $release.isDraft -or $release.isPrerelease) {
                continue
            }
            $asset = @($release.assets) |
                Where-Object { [string]$_.name -match $AssetPattern } |
                Select-Object -First 1
            if (-not $asset) {
                continue
            }
            $match = [regex]::Match([string]$asset.name, $AssetPattern)
            return [pscustomobject]@{
                Tag = [string]$release.tagName
                Version = $match.Groups['version'].Value
                Url = [string]$release.url
            }
        }
    }
    return $null
}

function Get-RemoteTagCommit {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$Tag
    )

    $peeled = & git -C $RepositoryPath ls-remote $RemoteName "refs/tags/$Tag^{}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить тег '$Tag' в $RepositoryPath."
    }
    if ($peeled) {
        return (($peeled -split "`t")[0]).Trim()
    }
    $direct = & git -C $RepositoryPath ls-remote $RemoteName "refs/tags/$Tag" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить тег '$Tag' в $RepositoryPath."
    }
    if ($direct) {
        return (($direct -split "`t")[0]).Trim()
    }
    return $null
}

function Ensure-LocalTag {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$Tag
    )

    $local = Invoke-Checked git @('-C', $RepositoryPath, 'tag', '--list', $Tag) -Capture
    if (-not [string]::IsNullOrWhiteSpace($local)) {
        return
    }
    $remoteCommit = Get-RemoteTagCommit `
        -RepositoryPath $RepositoryPath -RemoteName $RemoteName -Tag $Tag
    if (-not $remoteCommit) {
        return
    }
    Invoke-Checked git @(
        '-C', $RepositoryPath, 'fetch', '--no-tags', $RemoteName,
        "refs/tags/${Tag}:refs/tags/${Tag}"
    )
}

function Test-ComponentNeedsRelease {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$CurrentVersion,
        $Published,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string[]]$SourcePaths
    )

    if (-not $Published) {
        return $true
    }
    $current = [version]$CurrentVersion
    $released = [version]$Published.Version
    if ($current -lt $released) {
        throw "$Name имеет версию $CurrentVersion, но уже опубликована более новая $($Published.Version)."
    }
    if ($current -gt $released) {
        return $true
    }

    Ensure-LocalTag -RepositoryPath $RepositoryPath -RemoteName $RemoteName -Tag $Published.Tag
    $arguments = @('-C', $RepositoryPath, 'diff', '--name-only', "$($Published.Tag)..HEAD", '--') + $SourcePaths
    $changed = Invoke-Checked git $arguments -Capture
    if (-not [string]::IsNullOrWhiteSpace($changed)) {
        throw "$Name изменён после $($Published.Tag), но версия осталась $CurrentVersion. Обнови версию и changelog:`n$changed"
    }
    return $false
}

function Assert-CleanPaths {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string[]]$Paths,
        [Parameter(Mandatory)][string]$Name
    )

    $changes = & git -C $RepositoryPath status --porcelain --untracked-files=normal -- @Paths
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить рабочее дерево $Name."
    }
    if ($changes) {
        throw "Перед релизом закоммить изменения ${Name}:`n$($changes -join "`n")"
    }
}

function Assert-Branch {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$ExpectedBranch
    )

    $current = Invoke-Checked git @('-C', $RepositoryPath, 'branch', '--show-current') -Capture
    if ($current -ne $ExpectedBranch) {
        throw "В $RepositoryPath выбрана ветка '$current', ожидалась '$ExpectedBranch'."
    }
}

function Resolve-PrintFarmRepository {
    param([string]$RequestedPath)

    if ($RequestedPath) {
        return (Resolve-Path -LiteralPath $RequestedPath).Path
    }
    $candidate = Join-Path (Split-Path $script:MainRepositoryRoot -Parent) 'orca-plugins'
    if (-not (Test-Path -LiteralPath (Join-Path $candidate '.git'))) {
        throw 'Не найден репозиторий Print Farm. Передай -PrintFarmPath.'
    }
    $worktrees = Invoke-Checked git @('-C', $candidate, 'worktree', 'list', '--porcelain') -Capture
    $currentPath = $null
    foreach ($line in $worktrees -split "`r?`n") {
        if ($line -match '^worktree (?<path>.+)$') {
            $currentPath = $Matches.path
            continue
        }
        if ($line -eq 'branch refs/heads/main' -and $currentPath) {
            return $currentPath
        }
    }
    return $candidate
}

function Get-OrcaVersion {
    $content = Get-Content -LiteralPath (Join-Path $script:MainRepositoryRoot 'orca-plugin/filamenthub_plugin.py') -Raw
    if ($content -notmatch '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"\s*$') {
        throw 'Не удалось прочитать версию FilamentHub plugin.'
    }
    return $Matches.version
}

function Get-BridgeVersion {
    $project = Get-Content -LiteralPath (Join-Path $script:MainRepositoryRoot 'octoprint-plugin/pyproject.toml') -Raw
    $runtime = Get-Content -LiteralPath (Join-Path $script:MainRepositoryRoot 'octoprint-plugin/octoprint_filamenthub_bridge/__init__.py') -Raw
    if ($project -notmatch '(?m)^version\s*=\s*"(?<version>\d+\.\d+\.\d+)"\s*$') {
        throw 'Не удалось прочитать package version OctoPrint Bridge.'
    }
    $packageVersion = $Matches.version
    if ($runtime -notmatch '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"\s*$') {
        throw 'Не удалось прочитать runtime version OctoPrint Bridge.'
    }
    if ($packageVersion -ne $Matches.version) {
        throw "Версии OctoPrint Bridge расходятся: $packageVersion и $($Matches.version)."
    }
    return $packageVersion
}

function Get-PrintFarmVersion {
    param([Parameter(Mandatory)][string]$RepositoryPath)

    $source = Join-Path $RepositoryPath 'plugins/printers/printers_plugin.py'
    $content = Get-Content -LiteralPath $source -Raw
    if ($content -notmatch '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"\s*$') {
        throw "Не удалось прочитать версию Print Farm из $source."
    }
    return $Matches.version
}

function Wait-ForRelease {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string]$TagCommit,
        [Parameter(Mandatory)][string]$Tag,
        [switch]$AllowDraft,
        [switch]$RequireWorkflow
    )

    $release = Get-Release -Repository $Repository -Tag $Tag
    if ($release -and (-not $release.isDraft -or $AllowDraft) -and -not $RequireWorkflow) {
        return $release
    }
    $deadline = (Get-Date).AddSeconds($RunDiscoveryTimeoutSeconds)
    $run = $null
    do {
        $json = Invoke-Checked gh @(
            'run', 'list', '--repo', $Repository, '--workflow', $Workflow,
            '--event', 'push', '--limit', '20',
            '--json', 'databaseId,headSha,createdAt,url'
        ) -Capture
        $run = @($json | ConvertFrom-Json) |
            Where-Object { $_.headSha -eq $TagCommit } |
            Sort-Object { [datetime]$_.createdAt } -Descending |
            Select-Object -First 1
        if (-not $run) {
            Start-Sleep -Seconds 2
        }
    } while (-not $run -and (Get-Date) -lt $deadline)

    if (-not $run) {
        throw "Workflow $Workflow для '$Tag' не появился за $RunDiscoveryTimeoutSeconds секунд."
    }
    Write-Host "Ожидаю workflow: $($run.url)"
    Invoke-Checked gh @('run', 'watch', [string]$run.databaseId, '--repo', $Repository, '--exit-status')
    $release = Get-Release -Repository $Repository -Tag $Tag
    if (-not $release -or ($release.isDraft -and -not $AllowDraft)) {
        throw "Workflow завершился, но готовый релиз '$Tag' не найден."
    }
    return $release
}

function Wait-ForWorkflowRun {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string]$Event,
        [Parameter(Mandatory)][string]$TagCommit,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][datetime]$NotBefore
    )

    $deadline = (Get-Date).AddSeconds($RunDiscoveryTimeoutSeconds)
    $run = $null
    do {
        $json = Invoke-Checked gh @(
            'run', 'list', '--repo', $Repository, '--workflow', $Workflow,
            '--event', $Event, '--limit', '20',
            '--json', 'databaseId,headSha,createdAt,url'
        ) -Capture
        $run = @($json | ConvertFrom-Json) |
            Where-Object {
                $_.headSha -eq $TagCommit -and
                [datetime]$_.createdAt -ge $NotBefore
            } |
            Sort-Object { [datetime]$_.createdAt } |
            Select-Object -First 1
        if (-not $run) {
            Start-Sleep -Seconds 2
        }
    } while (-not $run -and (Get-Date) -lt $deadline)

    if (-not $run) {
        throw "Workflow $Workflow для '$Tag' не появился за $RunDiscoveryTimeoutSeconds секунд."
    }
    Write-Host "Ожидаю trusted publishing: $($run.url)"
    Invoke-Checked gh @('run', 'watch', [string]$run.databaseId, '--repo', $Repository, '--exit-status')
}

function Assert-ReleaseAssets {
    param(
        [Parameter(Mandatory)]$Release,
        [Parameter(Mandatory)][string[]]$RequiredPatterns,
        [Parameter(Mandatory)][string[]]$ForbiddenPatterns
    )

    $names = @($Release.assets | ForEach-Object { [string]$_.name })
    foreach ($pattern in $RequiredPatterns) {
        if (@($names | Where-Object { $_ -match $pattern }).Count -ne 1) {
            throw "Релиз $($Release.tagName) должен содержать ровно один файл '$pattern'. Файлы: $($names -join ', ')"
        }
    }
    foreach ($pattern in $ForbiddenPatterns) {
        if ($names | Where-Object { $_ -match $pattern }) {
            throw "Релиз $($Release.tagName) смешивает разные плагины: найден '$pattern'."
        }
    }
}

function Publish-Component {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string[]]$RequiredPatterns,
        [Parameter(Mandatory)][string[]]$ForbiddenPatterns,
        [switch]$OwnerPublishesDraft,
        [string]$TrustedPublishWorkflow
    )

    $head = Invoke-Checked git @('-C', $RepositoryPath, 'rev-parse', 'HEAD') -Capture
    $remoteTagCommit = Get-RemoteTagCommit `
        -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    if ($remoteTagCommit -and $remoteTagCommit -ne $head) {
        throw "Remote-тег '$Tag' указывает на $remoteTagCommit, а релизный HEAD — $head."
    }
    Ensure-LocalTag -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    $localTag = Invoke-Checked git @('-C', $RepositoryPath, 'tag', '--list', $Tag) -Capture
    if ($localTag) {
        $localCommit = Invoke-Checked git @('-C', $RepositoryPath, 'rev-list', '-n', '1', $Tag) -Capture
        if ($localCommit -ne $head) {
            throw "Локальный тег '$Tag' указывает на $localCommit, а релизный HEAD — $head."
        }
    } else {
        Invoke-Checked git @('-C', $RepositoryPath, 'tag', '-a', $Tag, '-m', "$Name $Tag")
    }
    $tagWasPushed = -not $remoteTagCommit
    if ($tagWasPushed) {
        Invoke-Checked git @('-C', $RepositoryPath, 'push', $Remote, "refs/tags/$Tag")
    }
    $tagCommit = Invoke-Checked git @('-C', $RepositoryPath, 'rev-list', '-n', '1', $Tag) -Capture
    $release = Wait-ForRelease `
        -Repository $Repository -Workflow $Workflow -TagCommit $tagCommit -Tag $Tag `
        -AllowDraft:$OwnerPublishesDraft -RequireWorkflow:$tagWasPushed
    Assert-ReleaseAssets `
        -Release $release -RequiredPatterns $RequiredPatterns -ForbiddenPatterns $ForbiddenPatterns
    if ($OwnerPublishesDraft -and $release.isDraft) {
        Write-Host "Файлы проверены. Публикую GitHub Release через авторизованную сессию владельца."
        Invoke-Checked gh @('release', 'edit', $Tag, '--repo', $Repository, '--draft=false')
        $release = Get-Release -Repository $Repository -Tag $Tag
        if (-not $release -or $release.isDraft -or $release.isPrerelease) {
            throw "Релиз '$Tag' не перешёл из draft в опубликованное состояние."
        }
    }
    if ($TrustedPublishWorkflow) {
        if (-not $release.publishedAt) {
            throw "У релиза '$Tag' отсутствует время публикации; trusted publishing не запущен."
        }
        Wait-ForWorkflowRun `
            -Repository $Repository -Workflow $TrustedPublishWorkflow -Event 'release' `
            -TagCommit $tagCommit -Tag $Tag `
            -NotBefore ([datetime]$release.publishedAt).AddSeconds(-5)
    }
    Write-Host "$Name опубликован: $($release.url)" -ForegroundColor Green
}

Assert-Command git
Assert-Command gh
Assert-Command python

$script:MainRepositoryRoot = Invoke-Checked git @('rev-parse', '--show-toplevel') -Capture
$selected = if ($Component -contains 'all') {
    @('orcaslicer', 'octoprint', 'print-farm')
} else {
    @($Component | Select-Object -Unique)
}

Invoke-Checked gh @('auth', 'status')
$mainRepository = Get-RepositoryName -RepositoryPath $script:MainRepositoryRoot
$printFarmRepositoryRoot = $null
$printFarmRepository = $null
if ($selected -contains 'print-farm') {
    $printFarmRepositoryRoot = Resolve-PrintFarmRepository -RequestedPath $PrintFarmPath
    $printFarmRepository = Get-RepositoryName -RepositoryPath $printFarmRepositoryRoot
}

Invoke-Checked git @(
    '-C', $script:MainRepositoryRoot, 'fetch', '--no-tags', $Remote,
    "refs/heads/${Branch}:refs/remotes/${Remote}/${Branch}"
)
if ($printFarmRepositoryRoot) {
    Invoke-Checked git @(
        '-C', $printFarmRepositoryRoot, 'fetch', '--no-tags', $Remote,
        "refs/heads/${Branch}:refs/remotes/${Remote}/${Branch}"
    )
}

$plans = @()
if ($selected -contains 'orcaslicer') {
    $version = Get-OrcaVersion
    $published = Get-PublishedComponent `
        -Repository $mainRepository `
        -AssetPattern '^filamenthub-(?<version>\d+\.\d+\.\d+)-.*\.whl$' `
        -TagPatterns @('^v\d+\.\d+\.\d+$', '^plugins-v\d+\.\d+\.\d+$')
    $needed = Test-ComponentNeedsRelease `
        -Name 'FilamentHub for OrcaSlicer' -CurrentVersion $version -Published $published `
        -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote -SourcePaths @('orca-plugin')
    $plans += [pscustomobject]@{
        Id = 'orcaslicer'; Name = 'FilamentHub for OrcaSlicer'; Version = $version
        Tag = "v$version"; Needed = $needed; Published = $published
        RepositoryPath = $script:MainRepositoryRoot; Repository = $mainRepository
        Workflow = 'release-filamenthub.yml'
    }
}
if ($selected -contains 'octoprint') {
    $version = Get-BridgeVersion
    $published = Get-PublishedComponent `
        -Repository $mainRepository `
        -AssetPattern '^octoprint[-_]filamenthubbridge-(?<version>\d+\.\d+\.\d+)-.*\.whl$' `
        -TagPatterns @('^octoprint-v\d+\.\d+\.\d+$', '^plugins-v\d+\.\d+\.\d+$')
    $needed = Test-ComponentNeedsRelease `
        -Name 'FilamentHub Bridge for OctoPrint' -CurrentVersion $version -Published $published `
        -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote -SourcePaths @('octoprint-plugin')
    $plans += [pscustomobject]@{
        Id = 'octoprint'; Name = 'FilamentHub Bridge for OctoPrint'; Version = $version
        Tag = "octoprint-v$version"; Needed = $needed; Published = $published
        RepositoryPath = $script:MainRepositoryRoot; Repository = $mainRepository
        Workflow = 'release-octoprint.yml'
    }
}
if ($selected -contains 'print-farm') {
    $version = Get-PrintFarmVersion -RepositoryPath $printFarmRepositoryRoot
    $published = Get-PublishedComponent `
        -Repository $printFarmRepository `
        -AssetPattern '^printers-(?<version>\d+\.\d+\.\d+)-.*\.whl$' `
        -TagPatterns @('^v\d+\.\d+\.\d+$', '^printers-v\d+\.\d+\.\d+$')
    $needed = Test-ComponentNeedsRelease `
        -Name 'Print Farm' -CurrentVersion $version -Published $published `
        -RepositoryPath $printFarmRepositoryRoot -RemoteName $Remote -SourcePaths @('plugins/printers')
    $plans += [pscustomobject]@{
        Id = 'print-farm'; Name = 'Print Farm'; Version = $version
        Tag = "v$version"; Needed = $needed; Published = $published
        RepositoryPath = $printFarmRepositoryRoot; Repository = $printFarmRepository
        Workflow = 'release-printers.yml'
    }
}

Write-Host ''
Write-Host 'План независимых релизов:' -ForegroundColor Cyan
foreach ($plan in $plans) {
    $publishedText = if ($plan.Published) {
        "$($plan.Published.Tag), версия $($plan.Published.Version)"
    } else {
        'не найден'
    }
    $action = if ($plan.Needed) { "ВЫПУСТИТЬ $($plan.Tag)" } else { 'пропустить' }
    Write-Host "  $($plan.Name): исходник $($plan.Version); опубликован $publishedText; $action"
}
$printFarmAhead = 0
if ($printFarmRepositoryRoot) {
    $printFarmAhead = [int](Invoke-Checked git @(
        '-C', $printFarmRepositoryRoot, 'rev-list', '--count', "$Remote/$Branch..HEAD"
    ) -Capture)
    if ($printFarmAhead -gt 0) {
        Write-Host "  Print Farm repository: опубликовать $printFarmAhead подготовленный коммит(ов) ветки $Branch."
    }
}

if (-not $HideReleaseNotes) {
    foreach ($plan in @($plans | Where-Object Needed)) {
        if ($plan.Id -in @('orcaslicer', 'octoprint')) {
            $componentName = if ($plan.Id -eq 'orcaslicer') { 'orca' } else { 'bridge' }
            Write-Host ''
            Write-Host "$($plan.Name) — release notes:" -ForegroundColor Cyan
            Write-Host (Invoke-Checked python @(
                'scripts/render_plugin_release_notes.py', '--component', $componentName
            ) -WorkingDirectory $script:MainRepositoryRoot -Capture)
        }
    }
}

$mainReleasePaths = @(
    'orca-plugin', 'octoprint-plugin',
    '.github/workflows/release-filamenthub.yml',
    '.github/workflows/release-octoprint.yml',
    '.github/workflows/publish-orcacloud.yml',
    'scripts/render_plugin_release_notes.py',
    'scripts/publish-plugin-releases.ps1'
)
if ($plans | Where-Object { $_.RepositoryPath -eq $script:MainRepositoryRoot -and $_.Needed }) {
    Assert-Branch -RepositoryPath $script:MainRepositoryRoot -ExpectedBranch $Branch
    Assert-CleanPaths `
        -RepositoryPath $script:MainRepositoryRoot -Paths $mainReleasePaths -Name 'основных плагинов'
}
if ($selected -contains 'print-farm') {
    Assert-Branch -RepositoryPath $printFarmRepositoryRoot -ExpectedBranch $Branch
    Assert-CleanPaths `
        -RepositoryPath $printFarmRepositoryRoot `
        -Paths @('plugins/printers', '.github/workflows/release-printers.yml', '.github/workflows/publish-orcacloud.yml') `
        -Name 'Print Farm'
}

if ($DryRun) {
    Write-Host 'Dry-run завершён. Push, теги и GitHub Releases не создавались.' -ForegroundColor Green
    return
}

$mainPlans = @($plans | Where-Object { $_.RepositoryPath -eq $script:MainRepositoryRoot -and $_.Needed })
if ($mainPlans.Count -gt 0) {
    Invoke-Checked git @('-C', $script:MainRepositoryRoot, 'push', $Remote, $Branch)
}
if ($selected -contains 'print-farm') {
    if ($printFarmAhead -gt 0) {
        Write-Host "Print Farm: публикую $printFarmAhead коммит(ов) ветки $Branch перед релизом."
        Invoke-Checked git @('-C', $printFarmRepositoryRoot, 'push', $Remote, $Branch)
    }
}

foreach ($plan in @($plans | Where-Object Needed)) {
    switch ($plan.Id) {
        'orcaslicer' {
            $publish = @{
                Name = $plan.Name; RepositoryPath = $plan.RepositoryPath
                Repository = $plan.Repository; Tag = $plan.Tag; Workflow = $plan.Workflow
                RequiredPatterns = @(
                    '^filamenthub-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$'
                )
                ForbiddenPatterns = @(
                    '^octoprint[-_]filamenthubbridge-', '^printers-'
                )
                OwnerPublishesDraft = $true
                TrustedPublishWorkflow = 'publish-orcacloud.yml'
            }
            Publish-Component @publish
        }
        'octoprint' {
            $publish = @{
                Name = $plan.Name; RepositoryPath = $plan.RepositoryPath
                Repository = $plan.Repository; Tag = $plan.Tag; Workflow = $plan.Workflow
                RequiredPatterns = @(
                    '^octoprint_filamenthubbridge-\d+\.\d+\.\d+-.*\.whl$',
                    '^octoprint_filamenthubbridge-\d+\.\d+\.\d+\.tar\.gz$',
                    '^SHA256SUMS$'
                )
                ForbiddenPatterns = @('^filamenthub-', '^printers-')
            }
            Publish-Component @publish
        }
        'print-farm' {
            $publish = @{
                Name = $plan.Name; RepositoryPath = $plan.RepositoryPath
                Repository = $plan.Repository; Tag = $plan.Tag; Workflow = $plan.Workflow
                RequiredPatterns = @('^printers-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$')
                ForbiddenPatterns = @('^filamenthub-', '^octoprint[-_]filamenthubbridge-')
                OwnerPublishesDraft = $true
                TrustedPublishWorkflow = 'publish-orcacloud.yml'
            }
            Publish-Component @publish
        }
    }
}

if (-not ($plans | Where-Object Needed)) {
    Write-Host 'Новых версий плагинов нет; GitHub Releases не создавались.' -ForegroundColor Green
}
