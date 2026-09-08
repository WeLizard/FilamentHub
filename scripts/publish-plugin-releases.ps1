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

    [Parameter(HelpMessage = 'Owner-tested wheel SHA-256 by component ID: orcaslicer, octoprint, print-farm.')]
    [hashtable]$OwnerApprovedSha256 = @{},

    [Parameter()]
    [switch]$PromptForOwnerApproval,

    [Parameter()]
    [switch]$CheckVersions,

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

function Assert-OrcaCloudPublishWorkflowContent {
    param(
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string]$Name
    )

    $safeMetadataForm = '--form-string "metadata=$metadata"'
    $unsafeMetadataForm = '-F "metadata=$metadata"'
    if (-not $Workflow.Contains($safeMetadataForm)) {
        throw "$Name не передаёт metadata через curl --form-string; JSON с ';', '@' или ',' может быть искажён."
    }
    if ($Workflow.Contains($unsafeMetadataForm)) {
        throw "$Name использует небезопасный curl -F для JSON metadata."
    }
    foreach ($required in @(
        'types: [published]',
        'id-token: write',
        'audience=orcacloud',
        '-F "files=@$PLUGIN_FILE"'
    )) {
        if (-not $Workflow.Contains($required)) {
            throw "$Name не соответствует OrcaCloud publish contract: отсутствует '$required'."
        }
    }
}

function Assert-OrcaCloudPublishWorkflow {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name
    )

    Assert-OrcaCloudPublishWorkflowContent `
        -Workflow (Get-Content -LiteralPath $Path -Raw) -Name $Name
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

function Get-TrustedPublishRun {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$TagCommit,
        [Parameter(Mandatory)][datetime]$NotBefore
    )

    $json = Invoke-Checked gh @(
        'run', 'list', '--repo', $Repository, '--workflow', $Workflow,
        '--event', 'release', '--limit', '50',
        '--json', 'databaseId,headBranch,headSha,createdAt,status,conclusion,url'
    ) -Capture
    return @($json | ConvertFrom-Json) |
        Where-Object {
            $_.headBranch -eq $Tag -and
            $_.headSha -eq $TagCommit -and
            [datetime]$_.createdAt -ge $NotBefore
        } |
        Sort-Object { [datetime]$_.createdAt } -Descending |
        Select-Object -First 1
}

function Get-PublishedComponent {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$AssetPattern,
        [Parameter(Mandatory)][string[]]$TagPatterns
    )

    # One paginated, checked API read includes assets. A failed lookup must
    # never turn an existing release into an apparently unpublished version.
    $json = Invoke-Checked gh @(
        'api', "repos/$Repository/releases?per_page=100", '--paginate', '--slurp'
    ) -Capture
    $releases = @($json | ConvertFrom-Json | ForEach-Object { $_ } | ForEach-Object { $_ })
    $candidates = @(foreach ($release in $releases) {
        if ($release.draft -or $release.prerelease) { continue }
        if (-not @($TagPatterns | Where-Object { $release.tag_name -match $_ }).Count) {
            continue
        }
        $assets = @($release.assets | Where-Object { [string]$_.name -match $AssetPattern })
        if ($assets.Count -ne 1) {
            throw "Release '$($release.tag_name)' must contain exactly one matching wheel."
        }
        $match = [regex]::Match([string]$assets[0].name, $AssetPattern)
        [pscustomobject]@{
            Tag = [string]$release.tag_name
            Version = $match.Groups['version'].Value
            Url = [string]$release.html_url
            PublishedAt = [datetime]$release.published_at
        }
    })
    return $candidates | Sort-Object { [version]$_.Version } -Descending | Select-Object -First 1
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

function Assert-TrustedPublishRepairable {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$WorkflowPath
    )

    try {
        $taggedWorkflow = Invoke-Checked git @(
            '-C', $RepositoryPath, 'show', "${Tag}:$WorkflowPath"
        ) -Capture
        Assert-OrcaCloudPublishWorkflowContent `
            -Workflow $taggedWorkflow -Name "$Name workflow в immutable-теге $Tag"
    } catch {
        throw "${Name}: нельзя безопасно повторить OrcaCloud для '$Tag'. Trusted release event всегда выполняет workflow из immutable-тега, а этот workflow устарел. Подготовь новую версию и новый тег вместо перепубликации старого release.`n$($_.Exception.Message)"
    }
}

function Test-ComponentNeedsRelease {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$CurrentVersion,
        $Published,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string[]]$SourcePaths,
        [string[]]$IgnoredPaths = @(),
        [switch]$CheckVersions
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
    $arguments = @('-C', $RepositoryPath, 'diff', '--name-only', $Published.Tag, '--') + $SourcePaths
    $changed = Invoke-Checked git $arguments -Capture
    $untracked = Invoke-Checked git (@('-C', $RepositoryPath, 'ls-files', '--others', '--exclude-standard', '--') + $SourcePaths) -Capture
    $changedPaths = @(
        @(("$changed`n$untracked") -split "`r?`n") | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and $_ -notin $IgnoredPaths -and
            $_ -notmatch '(^|/)(tests?/|test_[^/]*\.py$)'
        } | Select-Object -Unique
    )
    if ($changedPaths.Count -gt 0) {
        if ($CheckVersions) {
            $nextVersion = '{0}.{1}.{2}' -f $current.Major, $current.Minor, ($current.Build + 1)
            Write-Host "$Name`: опубликована $CurrentVersion; подготовь $nextVersion, синхронизируй версию и changelog." -ForegroundColor Yellow
            Write-Host ($changedPaths -join "`n")
            return $true
        }
        throw "$Name изменён после $($Published.Tag), но версия осталась $CurrentVersion. Обнови версию и changelog:`n$($changedPaths -join "`n")"
    }
    return $false
}

function Test-TrustedPublishNeedsRepair {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)]$Published
    )

    Ensure-LocalTag `
        -RepositoryPath $RepositoryPath -RemoteName $RemoteName -Tag $Published.Tag
    $tagCommit = Invoke-Checked git @(
        '-C', $RepositoryPath, 'rev-list', '-n', '1', $Published.Tag
    ) -Capture
    $run = Get-TrustedPublishRun `
        -Repository $Repository -Workflow $Workflow -Tag $Published.Tag `
        -TagCommit $tagCommit `
        -NotBefore $Published.PublishedAt.AddSeconds(-5)
    if ($run -and [string]$run.status -ne 'completed') {
        throw "${Name}: trusted publishing ещё выполняется: $($run.url)"
    }
    $needsRepair = -not $run -or [string]$run.conclusion -ne 'success'
    if (-not $needsRepair) {
        return $false
    }
    Assert-TrustedPublishRepairable `
        -Name $Name -RepositoryPath $RepositoryPath -Tag $Published.Tag `
        -WorkflowPath ".github/workflows/$Workflow"
    return $true
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
            '--json', 'databaseId,headBranch,headSha,createdAt,url'
        ) -Capture
        $run = @($json | ConvertFrom-Json) |
            Where-Object { $_.headBranch -eq $Tag -and $_.headSha -eq $TagCommit } |
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
            '--json', 'databaseId,headBranch,headSha,createdAt,url'
        ) -Capture
        $run = @($json | ConvertFrom-Json) |
            Where-Object {
                $_.headBranch -eq $Tag -and
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

function Get-LocalCandidateSha256 {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$WheelPath,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
        [string]$ChecksumPath
    )

    if (-not (Test-Path -LiteralPath $WheelPath -PathType Leaf)) {
        throw "${Name}: не найден локальный release candidate '$WheelPath'. Сначала собери и проверь его в целевом приложении."
    }
    $actual = (Get-FileHash -LiteralPath $WheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "${Name}: local candidate differs from the owner-approved SHA-256. Test and approve the exact wheel before publication."
    }
    if ($ChecksumPath) {
        if (-not (Test-Path -LiteralPath $ChecksumPath -PathType Leaf)) {
            throw "${Name}: рядом с release candidate отсутствует SHA256SUMS."
        }
        $wheelName = Split-Path -Leaf $WheelPath
        $matching = @(
            Get-Content -LiteralPath $ChecksumPath | Where-Object {
                $_ -match '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?:\./)?(?:wheels/)?(?<name>[^/\\]+)$' -and
                $Matches.name -eq $wheelName
            }
        )
        if ($matching.Count -ne 1) {
            throw "${Name}: SHA256SUMS должен содержать ровно одну запись для '$wheelName'."
        }
        $null = $matching[0] -match '^(?<hash>[0-9a-fA-F]{64})'
        if ($Matches.hash.ToLowerInvariant() -ne $actual) {
            throw "${Name}: локальный wheel не совпадает с SHA256SUMS."
        }
    }
    return $actual
}

function Get-RemoteBranchCommit {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$BranchName
    )

    $line = & git -C $RepositoryPath ls-remote $RemoteName "refs/heads/$BranchName" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить ветку '$RemoteName/$BranchName' в $RepositoryPath."
    }
    if (-not $line) { return $null }
    return (($line -split "`t")[0]).Trim()
}

function Assert-ReleaseCommitPublished {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$RemoteName,
        [Parameter(Mandatory)][string]$BranchName,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Repository,
        [string]$RequiredCiWorkflow
    )

    $head = Invoke-Checked git @('-C', $RepositoryPath, 'rev-parse', 'HEAD') -Capture
    $remote = Get-RemoteBranchCommit `
        -RepositoryPath $RepositoryPath -RemoteName $RemoteName -BranchName $BranchName
    if ($remote -ne $head) {
        throw "$Name`: локальный HEAD $head ещё не опубликован как $RemoteName/$BranchName. Сначала отдельно опубликуй коммиты, дождись зелёного CI, затем снова запусти выпуск плагина."
    }
    if (-not $RequiredCiWorkflow) { return }

    $json = Invoke-Checked gh @(
        'run', 'list', '--repo', $Repository, '--workflow', $RequiredCiWorkflow,
        '--commit', $head, '--event', 'push', '--limit', '10',
        '--json', 'headSha,status,conclusion,url,createdAt'
    ) -Capture
    $run = @($json | ConvertFrom-Json) |
        Where-Object { $_.headSha -eq $head } |
        Sort-Object { [datetime]$_.createdAt } -Descending |
        Select-Object -First 1
    if (-not $run) {
        throw "$Name`: для опубликованного commit $head не найден обязательный CI '$RequiredCiWorkflow'."
    }
    if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') {
        throw "$Name`: обязательный CI '$RequiredCiWorkflow' для $head не зелёный (status=$($run.status), result=$($run.conclusion)): $($run.url)"
    }
}

function Read-OwnerApprovalKey {
    if ([Console]::IsInputRedirected) {
        throw 'Для подтверждения нужен интерактивный терминал; автоматический запуск использует -OwnerApprovedSha256.'
    }
    return [Console]::ReadKey($true).KeyChar
}

function Confirm-OwnerTestedCandidate {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$WheelPath,
        [Parameter(Mandatory)][string]$Sha256
    )

    Write-Host "`n$Name — пакет для выпуска:" -ForegroundColor Cyan
    Write-Host $WheelPath
    Write-Host "SHA-256 проверен автоматически: $Sha256" -ForegroundColor DarkGray
    Write-Host 'Этот пакет проверен в приложении и принят? Y / Д — да; любая другая клавиша — пропустить.'
    return (Read-OwnerApprovalKey) -cin @('y', 'Y', 'д', 'Д')
}

function Assert-OwnerApprovedCandidates {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Plans,
        [Parameter(Mandatory)][hashtable]$ApprovedSha256,
        [switch]$PromptForOwnerApproval
    )

    foreach ($plan in @($Plans | Where-Object { $_.Needed -or $_.Repair })) {
        $approvedHash = if ($ApprovedSha256.ContainsKey($plan.Id)) {
            $ApprovedSha256[$plan.Id]
        } elseif ($PromptForOwnerApproval) {
            $candidateHash = (Get-FileHash -LiteralPath $plan.CandidateWheel -Algorithm SHA256).Hash.ToLowerInvariant()
            $candidateHash = Get-LocalCandidateSha256 `
                -Name $plan.Name -WheelPath $plan.CandidateWheel `
                -ChecksumPath $plan.CandidateChecksums -ExpectedSha256 $candidateHash
            if (-not (Confirm-OwnerTestedCandidate -Name $plan.Name -WheelPath $plan.CandidateWheel -Sha256 $candidateHash)) {
                throw "$($plan.Name): выпуск пропущен — проверка пакета в приложении не подтверждена."
            }
            $candidateHash
        } else {
            throw "$($plan.Name): provide -OwnerApprovedSha256 with the exact SHA-256 tested and accepted by the owner for '$($plan.Id)' before publication or repair."
        }
        $plan | Add-Member -NotePropertyName CandidateSha256 -NotePropertyValue (
            Get-LocalCandidateSha256 `
                -Name $plan.Name -WheelPath $plan.CandidateWheel `
                -ChecksumPath $plan.CandidateChecksums -ExpectedSha256 $approvedHash
        )
        $plan | Add-Member -NotePropertyName CandidateAssetPattern -NotePropertyValue (
            '^' + [regex]::Escape((Split-Path -Leaf $plan.CandidateWheel)) + '$'
        )
    }
}

function Assert-ReleaseChecksums {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$ExpectedAssetPattern
    )

    $systemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $verifyDir = Join-Path $systemTemp ("filamenthub-release-verify-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $verifyDir | Out-Null
    try {
        Invoke-Checked gh @(
            'release', 'download', $Tag, '--repo', $Repository,
            '--dir', $verifyDir
        )
        $checksumPath = Join-Path $verifyDir 'SHA256SUMS'
        if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
            throw "Релиз '$Tag' не содержит SHA256SUMS."
        }

        $assetHashes = @{}
        foreach ($line in Get-Content -LiteralPath $checksumPath) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            if ($line -notmatch '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?:\./)?(?<name>[^/\\]+)$') {
                throw "Некорректная строка SHA256SUMS в релизе '$Tag': $line"
            }
            $assetName = $Matches.name
            $assetPath = Join-Path $verifyDir $assetName
            if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
                throw "SHA256SUMS ссылается на отсутствующий asset '$assetName'."
            }
            $actual = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $Matches.hash.ToLowerInvariant()) {
                throw "Asset '$assetName' не совпадает с SHA256SUMS."
            }
            $assetHashes[$assetName] = $actual
        }

        $wheels = @(Get-ChildItem -LiteralPath $verifyDir -File -Filter '*.whl')
        if ($wheels.Count -ne 1 -or $wheels[0].Name -notmatch $ExpectedAssetPattern) {
            throw "Release '$Tag' must contain exactly the owner-approved wheel '$ExpectedAssetPattern'."
        }
        $approvedName = $wheels[0].Name
        if (-not $assetHashes.ContainsKey($approvedName)) {
            throw "SHA256SUMS must include the owner-approved wheel '$approvedName'."
        }
        if ($assetHashes[$approvedName] -ne $ExpectedSha256.ToLowerInvariant()) {
            throw "GitHub asset '$approvedName' отличается от локального wheel, проверенного владельцем."
        }
    } finally {
        $resolvedVerifyDir = [System.IO.Path]::GetFullPath($verifyDir)
        if (-not $resolvedVerifyDir.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Отказ удалять временный каталог вне системного temp: $resolvedVerifyDir"
        }
        Remove-Item -LiteralPath $resolvedVerifyDir -Recurse -Force -ErrorAction SilentlyContinue
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
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$ExpectedAssetPattern,
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
    Assert-ReleaseChecksums `
        -Repository $Repository -Tag $Tag `
        -ExpectedSha256 $ExpectedSha256 -ExpectedAssetPattern $ExpectedAssetPattern
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

function Repair-TrustedPublishComponent {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$TrustedPublishWorkflow,
        [Parameter(Mandatory)][string[]]$RequiredPatterns,
        [Parameter(Mandatory)][string[]]$ForbiddenPatterns,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$ExpectedAssetPattern
    )

    $release = Get-Release -Repository $Repository -Tag $Tag
    if (-not $release -or $release.isDraft -or $release.isPrerelease) {
        throw "Для восстановления trusted publishing нужен опубликованный release '$Tag'."
    }
    Assert-ReleaseAssets `
        -Release $release -RequiredPatterns $RequiredPatterns -ForbiddenPatterns $ForbiddenPatterns
    Assert-ReleaseChecksums `
        -Repository $Repository -Tag $Tag `
        -ExpectedSha256 $ExpectedSha256 -ExpectedAssetPattern $ExpectedAssetPattern
    Ensure-LocalTag -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    Assert-TrustedPublishRepairable `
        -Name $Name -RepositoryPath $RepositoryPath -Tag $Tag `
        -WorkflowPath ".github/workflows/$TrustedPublishWorkflow"
    $tagCommit = Invoke-Checked git @(
        '-C', $RepositoryPath, 'rev-list', '-n', '1', $Tag
    ) -Capture

    Write-Host "${Name}: повторно публикую проверенный GitHub Release, чтобы создать новый trusted release event."
    Invoke-Checked gh @('release', 'edit', $Tag, '--repo', $Repository, '--draft')
    $draft = Get-Release -Repository $Repository -Tag $Tag
    if (-not $draft -or -not $draft.isDraft) {
        throw "Релиз '$Tag' не перешёл во временное draft-состояние."
    }

    $triggerStartedAt = Get-Date
    Invoke-Checked gh @('release', 'edit', $Tag, '--repo', $Repository, '--draft=false')
    $release = Get-Release -Repository $Repository -Tag $Tag
    if (-not $release -or $release.isDraft -or $release.isPrerelease) {
        throw "Релиз '$Tag' не вернулся в опубликованное состояние."
    }
    Wait-ForWorkflowRun `
        -Repository $Repository -Workflow $TrustedPublishWorkflow -Event 'release' `
        -TagCommit $tagCommit -Tag $Tag -NotBefore $triggerStartedAt.AddSeconds(-5)
    Write-Host "$Name опубликован в OrcaCloud: $($release.url)" -ForegroundColor Green
}

function Invoke-ReleaseBatch {
    param(
        [Parameter(Mandatory)][string[]]$Components,
        [Parameter(Mandatory)][scriptblock]$Operation,
        [Parameter(Mandatory)][string]$Phase
    )

    $index = 0
    foreach ($id in $Components) {
        $index += 1
        Write-Host "`n[$index/$($Components.Count)] $id — $Phase" -ForegroundColor Cyan
        try {
            $global:FilamentHubPluginReleaseResult = $null
            & $Operation $id | Out-Host
            $componentResult = $global:FilamentHubPluginReleaseResult
            if ($componentResult) {
                [pscustomobject]@{
                    Component = $id
                    Status = $componentResult.Status
                    Detail = $componentResult.Detail
                }
            } else {
                [pscustomobject]@{ Component = $id; Status = 'OK'; Detail = $Phase }
            }
        } catch {
            $detail = $_.Exception.Message
            Write-Host "$id — ОШИБКА: $detail" -ForegroundColor Yellow
            [pscustomobject]@{ Component = $id; Status = 'ERROR'; Detail = $detail }
        }
    }
}

$selected = @(if ($Component -contains 'all') {
    @('orcaslicer', 'octoprint', 'print-farm')
} else {
    @($Component | Select-Object -Unique)
})
if ($selected.Count -gt 1) {
    $entryPath = $PSCommandPath
    $childArguments = @{} + $PSBoundParameters
    $childArguments.Remove('Component')
    # Check every component before any public operation; only successful
    # components proceed, and each keeps its own exact-artifact approval gate.
    $preflightArguments = @{} + $childArguments
    $preflightArguments.DryRun = $true
    $results = @(Invoke-ReleaseBatch -Components $selected -Phase 'проверка' -Operation {
        param($id)
        & $entryPath @preflightArguments -Component $id
    })
    if (-not $DryRun -and -not $CheckVersions) {
        $ready = @($results | Where-Object Status -eq 'OK' | ForEach-Object Component)
        $failed = @($results | Where-Object Status -eq 'ERROR')
        $completed = @()
        if ($ready.Count) {
            $completed = @(Invoke-ReleaseBatch -Components $ready -Phase 'выпуск' -Operation {
                param($id)
                & $entryPath @childArguments -Component $id
            })
        }
        $results = @($failed) + @($completed)
    }
    Write-Host "`nИтог по компонентам:" -ForegroundColor Cyan
    foreach ($id in $selected) {
        $result = $results | Where-Object Component -eq $id
        Write-Host "  $id — $($result.Status): $($result.Detail)"
    }
    if (@($results | Where-Object Status -eq 'ERROR').Count) {
        throw 'Не все компоненты прошли выбранный этап. Результаты остальных сохранены; причины указаны выше.'
    }
    return
}

Assert-Command git
Assert-Command gh
Assert-Command python

$script:MainRepositoryRoot = Invoke-Checked git @('rev-parse', '--show-toplevel') -Capture

Invoke-Checked gh @('auth', 'status') -Capture | Out-Null
$mainRepository = Get-RepositoryName -RepositoryPath $script:MainRepositoryRoot
Write-Host "GitHub: $mainRepository; проверяю актуальный release и исходники." -ForegroundColor DarkGray
$printFarmRepositoryRoot = $null
$printFarmRepository = $null
if ($selected -contains 'print-farm') {
    $printFarmRepositoryRoot = Resolve-PrintFarmRepository -RequestedPath $PrintFarmPath
    $printFarmRepository = Get-RepositoryName -RepositoryPath $printFarmRepositoryRoot
}

if (-not $CheckVersions -and $selected -contains 'orcaslicer') {
    Assert-OrcaCloudPublishWorkflow `
        -Path (Join-Path $script:MainRepositoryRoot '.github/workflows/publish-orcacloud.yml') `
        -Name 'FilamentHub OrcaCloud workflow'
}
if (-not $CheckVersions -and $selected -contains 'print-farm') {
    Assert-OrcaCloudPublishWorkflow `
        -Path (Join-Path $printFarmRepositoryRoot '.github/workflows/publish-orcacloud.yml') `
        -Name 'Print Farm OrcaCloud workflow'
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
        -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote -SourcePaths @('orca-plugin') `
        -IgnoredPaths @('orca-plugin/build_package.py') `
        -CheckVersions:$CheckVersions
    $repair = if (-not $CheckVersions -and -not $needed -and $published) {
        Test-TrustedPublishNeedsRepair `
            -Name 'FilamentHub for OrcaSlicer' `
            -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote `
            -Repository $mainRepository -Workflow 'publish-orcacloud.yml' `
            -Published $published
    } else {
        $false
    }
    $plans += [pscustomobject]@{
        Id = 'orcaslicer'; Name = 'FilamentHub for OrcaSlicer'; Version = $version
        Tag = "v$version"; Needed = $needed; Repair = $repair; Published = $published
        RepositoryPath = $script:MainRepositoryRoot; Repository = $mainRepository
        RequiredCiWorkflow = 'ci.yml'
        Workflow = 'release-filamenthub.yml'; TrustedPublishWorkflow = 'publish-orcacloud.yml'
        CandidateWheel = Join-Path $script:MainRepositoryRoot "orca-plugin/dist/release-$version/wheels/filamenthub-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $script:MainRepositoryRoot "orca-plugin/dist/release-$version/SHA256SUMS"
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
        -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote -SourcePaths @('octoprint-plugin') `
        -IgnoredPaths @('octoprint-plugin/build_package.py') `
        -CheckVersions:$CheckVersions
    $plans += [pscustomobject]@{
        Id = 'octoprint'; Name = 'FilamentHub Bridge for OctoPrint'; Version = $version
        Tag = "octoprint-v$version"; Needed = $needed; Repair = $false; Published = $published
        RepositoryPath = $script:MainRepositoryRoot; Repository = $mainRepository
        RequiredCiWorkflow = 'ci.yml'
        Workflow = 'release-octoprint.yml'; TrustedPublishWorkflow = $null
        CandidateWheel = Join-Path $script:MainRepositoryRoot "octoprint-plugin/dist/release-$version/octoprint_filamenthubbridge-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $script:MainRepositoryRoot "octoprint-plugin/dist/release-$version/SHA256SUMS"
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
        -RepositoryPath $printFarmRepositoryRoot -RemoteName $Remote `
        -SourcePaths @('plugins/printers') `
        -IgnoredPaths @('plugins/printers/test_release_workflow.py', 'plugins/printers/build_package.py') `
        -CheckVersions:$CheckVersions
    $repair = if (-not $CheckVersions -and -not $needed -and $published) {
        Test-TrustedPublishNeedsRepair `
            -Name 'Print Farm' `
            -RepositoryPath $printFarmRepositoryRoot -RemoteName $Remote `
            -Repository $printFarmRepository -Workflow 'publish-orcacloud.yml' `
            -Published $published
    } else {
        $false
    }
    $plans += [pscustomobject]@{
        Id = 'print-farm'; Name = 'Print Farm'; Version = $version
        Tag = "v$version"; Needed = $needed; Repair = $repair; Published = $published
        RepositoryPath = $printFarmRepositoryRoot; Repository = $printFarmRepository
        RequiredCiWorkflow = $null
        Workflow = 'release-printers.yml'; TrustedPublishWorkflow = 'publish-orcacloud.yml'
        CandidateWheel = Join-Path $printFarmRepositoryRoot "plugins/printers/dist/release-$version/wheels/printers-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $printFarmRepositoryRoot "plugins/printers/dist/release-$version/SHA256SUMS"
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
    $action = if ($CheckVersions -and $plan.Needed) {
        if ($plan.Published -and $plan.Published.Version -eq $plan.Version) {
            'повысить версию и обновить changelog'
        } else {
            'сохранить неопубликованную версию; дополнить changelog и пересобрать'
        }
    } elseif ($plan.Needed) {
        "ВЫПУСТИТЬ $($plan.Tag)"
    } elseif ($plan.Repair) {
        "ПОВТОРИТЬ ORCACLOUD $($plan.Published.Tag)"
    } else {
        'пропустить'
    }
    Write-Host "  $($plan.Name): исходник $($plan.Version); опубликован $publishedText; $action"
}
if ($CheckVersions) {
    Write-Host 'Проверка версий завершена. Это не проверка сборки или готовности к публикации.'
    return
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
    'scripts/render_plugin_release_notes.py',
    'scripts/publish-plugin-releases.ps1'
)
if ($selected -contains 'orcaslicer') {
    $mainReleasePaths += @('orca-plugin', '.github/workflows/release-filamenthub.yml', '.github/workflows/publish-orcacloud.yml')
}
if ($selected -contains 'octoprint') {
    $mainReleasePaths += @('octoprint-plugin', '.github/workflows/release-octoprint.yml')
}
if ($plans | Where-Object {
    $_.RepositoryPath -eq $script:MainRepositoryRoot -and ($_.Needed -or $_.Repair)
}) {
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
    $actionable = @($plans | Where-Object { $_.Needed -or $_.Repair }).Count
    $global:FilamentHubPluginReleaseResult = if ($actionable) {
        [pscustomobject]@{ Status = 'READY'; Detail = 'готов к отдельному выпуску после публикации коммита и зелёного CI' }
    } else {
        [pscustomobject]@{ Status = 'CURRENT'; Detail = 'нового релиза не требуется' }
    }
    Write-Host 'Dry-run завершён. Push, теги и GitHub Releases не создавались.' -ForegroundColor Green
    Write-Host 'Owner approval and release asset identity were not verified.'
    return
}

foreach ($repositoryPlan in @($plans | Where-Object { $_.Needed -or $_.Repair } |
    Group-Object RepositoryPath | ForEach-Object { $_.Group | Select-Object -First 1 })) {
    Assert-ReleaseCommitPublished `
        -RepositoryPath $repositoryPlan.RepositoryPath -RemoteName $Remote `
        -BranchName $Branch -Name $repositoryPlan.Name `
        -Repository $repositoryPlan.Repository `
        -RequiredCiWorkflow $repositoryPlan.RequiredCiWorkflow
}

Assert-OwnerApprovedCandidates -Plans $plans -ApprovedSha256 $OwnerApprovedSha256 `
    -PromptForOwnerApproval:$PromptForOwnerApproval

foreach ($plan in @($plans | Where-Object { $_.Needed -or $_.Repair })) {
    if ($plan.Repair) {
        $repair = @{
            Name = $plan.Name; RepositoryPath = $plan.RepositoryPath
            Repository = $plan.Repository; Tag = $plan.Published.Tag
            TrustedPublishWorkflow = $plan.TrustedPublishWorkflow
            ExpectedSha256 = $plan.CandidateSha256
            ExpectedAssetPattern = $plan.CandidateAssetPattern
        }
        switch ($plan.Id) {
            'orcaslicer' {
                $repair.RequiredPatterns = @(
                    '^filamenthub-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$'
                )
                $repair.ForbiddenPatterns = @(
                    '^octoprint[-_]filamenthubbridge-', '^printers-'
                )
            }
            'print-farm' {
                $repair.RequiredPatterns = @(
                    '^printers-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$'
                )
                $repair.ForbiddenPatterns = @(
                    '^filamenthub-', '^octoprint[-_]filamenthubbridge-'
                )
            }
            default {
                throw "$($plan.Name) не поддерживает восстановление trusted publishing."
            }
        }
        Repair-TrustedPublishComponent @repair
        continue
    }
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
                ExpectedSha256 = $plan.CandidateSha256
                ExpectedAssetPattern = $plan.CandidateAssetPattern
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
                ExpectedSha256 = $plan.CandidateSha256
                ExpectedAssetPattern = $plan.CandidateAssetPattern
                OwnerPublishesDraft = $true
            }
            Publish-Component @publish
        }
        'print-farm' {
            $publish = @{
                Name = $plan.Name; RepositoryPath = $plan.RepositoryPath
                Repository = $plan.Repository; Tag = $plan.Tag; Workflow = $plan.Workflow
                RequiredPatterns = @('^printers-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$')
                ForbiddenPatterns = @('^filamenthub-', '^octoprint[-_]filamenthubbridge-')
                ExpectedSha256 = $plan.CandidateSha256
                ExpectedAssetPattern = $plan.CandidateAssetPattern
                OwnerPublishesDraft = $true
                TrustedPublishWorkflow = 'publish-orcacloud.yml'
            }
            Publish-Component @publish
        }
    }
}

if (-not ($plans | Where-Object { $_.Needed -or $_.Repair })) {
    $global:FilamentHubPluginReleaseResult = [pscustomobject]@{
        Status = 'CURRENT'; Detail = 'нового релиза не требуется'
    }
    Write-Host 'Новых версий плагинов нет; GitHub Releases не создавались.' -ForegroundColor Green
} else {
    $global:FilamentHubPluginReleaseResult = [pscustomobject]@{
        Status = 'RELEASED'; Detail = 'независимый релиз завершён'
    }
}
