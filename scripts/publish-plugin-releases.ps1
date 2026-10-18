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
    [switch]$DryRun,

    [Parameter()]
    [string]$PublicBaseUrl = 'https://filamenthub.ru',

    # Plugin API level of the site revision the owner is about to deploy. Used
    # only by -DryRun; a real release always reads the live site.
    [Parameter()]
    [ValidateRange(0, 1000)]
    [int]$PlannedSiteApiLevel = 0,

    [Parameter()]
    [ValidatePattern('^([0-9a-f]{40})?$')]
    [string]$ExpectedReleaseCommit = '',

    [Parameter(DontShow)]
    [switch]$EmitComponentResult
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:OrcaCloudOutcome = $null

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Не найдена обязательная команда '$Name' в PATH."
    }
}

function Stop-WithFix {
    param(
        [Parameter(Mandatory)][string]$Problem,
        [Parameter(Mandatory)][string]$Fix
    )

    throw "$Problem`nИсправить: $Fix"
}

function Get-GitConfigValue {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Key
    )

    $value = & git -C $RepositoryPath config --get $Key 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    return "$value".Trim()
}

function Assert-GitIdentity {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath
    )

    # An annotated version tag records its author; without one git refuses
    # to create the tag, which used to happen only after the owner's approval.
    foreach ($key in @('user.name', 'user.email')) {
        if (-not (Get-GitConfigValue -RepositoryPath $RepositoryPath -Key $key)) {
            $suggested = Get-GitConfigValue -RepositoryPath $script:MainRepositoryRoot -Key $key
            if (-not $suggested) {
                $suggested = if ($key -eq 'user.name') { 'Твоё имя' } else { 'твоя@почта' }
            }
            Stop-WithFix `
                -Problem "${Name}: в git не записано, от чьего имени ставить метку версии ($key)." `
                -Fix "git -C `"$RepositoryPath`" config $key `"$suggested`""
        }
    }
}

function Get-RequiredPluginApiLevel {
    param([Parameter(Mandatory)][string]$Id)

    $path = Join-Path $script:MainRepositoryRoot 'scripts/plugin-required-api-level.json'
    $requirements = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $property = $requirements.PSObject.Properties[$Id]
    if (-not $property) { return $null }
    if ($property.Value -isnot [long] -and $property.Value -isnot [int] -or [int]$property.Value -lt 1) {
        throw "plugin-required-api-level.json: для '$Id' нужен целый уровень от 1."
    }
    return [int]$property.Value
}

function Get-SitePluginApiLevel {
    param([Parameter(Mandatory)][string]$BaseUrl)

    $endpoint = "$($BaseUrl.TrimEnd('/'))/health"
    try {
        $health = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 20
    } catch {
        Stop-WithFix `
            -Problem "Сайт не ответил на проверку ($endpoint), поэтому нельзя убедиться, что он подходит плагину." `
            -Fix "проверь сайт и повтори; состояние сервера: .\scripts\deploy-server.ps1 -Action Status"
    }
    if ("$($health.status)" -ne 'ok') {
        Stop-WithFix `
            -Problem "Сайт отвечает, но сообщает status=$($health.status) вместо ok." `
            -Fix '.\scripts\deploy-server.ps1 -Action Status'
    }
    $property = $health.PSObject.Properties['plugin_api_level']
    # Deployments made before the level existed serve level 1.
    if (-not $property) { return 1 }
    $level = 0
    if (-not [int]::TryParse("$($property.Value)", [ref]$level) -or $level -lt 1) {
        throw "Сайт вернул некорректный plugin_api_level: $($property.Value)"
    }
    return $level
}

function Test-SiteServesPlugin {
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][int]$Required,
        [Parameter(Mandatory)][int]$Live,
        [int]$Planned = 0
    )

    if ($Live -ge $Required) { return $false }
    if ($Planned -ge $Required) { return $true }
    if ($Planned -gt 0) {
        Stop-WithFix `
            -Problem "${Name}: плагину нужен сайт уровня $Required, а даже выкатываемая версия сайта даёт уровень $Planned." `
            -Fix 'передай агенту: уровень сайта для плагинов не поднят (backend/app/core/config.py, PLUGIN_API_LEVEL)'
    }
    Stop-WithFix `
        -Problem "${Name}: плагину нужен сайт уровня $Required, а на сервере уровень $Live. Сначала нужно выкатить сайт." `
        -Fix ".\scripts\release.ps1 -Item site,$Id   (сайт выйдет первым, плагин — после него)"
}

function Assert-TagAvailable {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$ReleaseCommit
    )

    $remoteCommit = Get-RemoteTagCommit -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    if ($remoteCommit -and $remoteCommit -ne $ReleaseCommit) {
        Stop-WithFix `
            -Problem "${Name}: метка $Tag на GitHub уже стоит на другом коммите ($($remoteCommit.Substring(0, 8))). Эту версию выпустить нельзя." `
            -Fix 'передай агенту: нужна следующая версия плагина'
    }
    $local = Invoke-Checked git @('-C', $RepositoryPath, 'tag', '--list', $Tag) -Capture
    if ($local) {
        $localCommit = Invoke-Checked git @('-C', $RepositoryPath, 'rev-list', '-n', '1', $Tag) -Capture
        if ($localCommit -ne $ReleaseCommit) {
            $fix = if ($remoteCommit) {
                "git -C `"$RepositoryPath`" fetch --force $Remote `"refs/tags/${Tag}:refs/tags/$Tag`""
            } else {
                "git -C `"$RepositoryPath`" tag -d $Tag"
            }
            Stop-WithFix `
                -Problem "${Name}: на компьютере осталась старая метка $Tag на другом коммите ($($localCommit.Substring(0, 8)))." `
                -Fix $fix
        }
    }
    return $remoteCommit
}

function Assert-TagPushAllowed {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$ReleaseCommit
    )

    # A dry-run push authenticates and asks the remote to accept the tag
    # without creating anything.
    $output = & git -C $RepositoryPath push --dry-run --porcelain $Remote "${ReleaseCommit}:refs/tags/$Tag" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Stop-WithFix `
            -Problem "${Name}: GitHub не даёт отправить метку версии (пробная отправка не прошла): $(@($output)[-1])" `
            -Fix 'gh auth login   (затем: gh auth setup-git)'
    }
}

function Assert-ReleaseRights {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Repository
    )

    $canPush = & gh api "repos/$Repository" --jq '.permissions.push' 2>$null
    if ($LASTEXITCODE -ne 0 -or "$canPush".Trim() -ne 'true') {
        Stop-WithFix `
            -Problem "${Name}: у текущего входа в GitHub нет права публиковать в $Repository." `
            -Fix 'gh auth login'
    }
}

function Assert-CandidateMatchesSource {
    param([Parameter(Mandatory)]$Plan)

    if (-not (Test-Path -LiteralPath $Plan.CandidateWheel -PathType Leaf)) {
        Stop-WithFix `
            -Problem "$($Plan.Name): пакет $($Plan.Version) ещё не собран." `
            -Fix "передай агенту: собрать и проверить пакет (cd `"$($Plan.RepositoryPath)`"; python $($Plan.Builder))"
    }
    & python -m build --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-WithFix `
            -Problem 'Для сверки пакета нужен сборщик Python, он не установлен.' `
            -Fix 'python -m pip install build'
    }
    $systemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $buildDir = Join-Path $systemTemp ("filamenthub-candidate-check-" + [guid]::NewGuid().ToString('N'))
    try {
        Invoke-Checked python @($Plan.Builder, '--output', $buildDir) `
            -WorkingDirectory $Plan.RepositoryPath -Capture | Out-Null
        $rebuilt = Join-Path $buildDir $Plan.BuiltWheelRelative
        if (-not (Test-Path -LiteralPath $rebuilt -PathType Leaf)) {
            throw "$($Plan.Name): сборщик не создал '$($Plan.BuiltWheelRelative)'."
        }
        $expected = (Get-FileHash -LiteralPath $rebuilt -Algorithm SHA256).Hash
        $actual = (Get-FileHash -LiteralPath $Plan.CandidateWheel -Algorithm SHA256).Hash
        if ($expected -ne $actual) {
            Stop-WithFix `
                -Problem "$($Plan.Name): собранный пакет устарел — он не совпадает с текущим кодом плагина." `
                -Fix "передай агенту: пересобрать пакет $($Plan.Version); новый пакет снова нужно проверить в приложении"
        }
    } finally {
        $resolved = [System.IO.Path]::GetFullPath($buildDir)
        if ($resolved.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-OrcaCloudHeldForReview {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][string]$RunId
    )

    # OrcaCloud accepts a flagged upload and queues it for moderation; another
    # upload of the same version would only duplicate it.
    $log = & gh run view $RunId --repo $Repository --log 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    return [bool](@($log) -match '"status"\s*:\s*"held_for_review"')
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

function Test-ContentIdenticalRelocation {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$Tag,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$OldRoot,
        [Parameter(Mandatory)][string]$NewRoot
    )

    $oldPrefix = "$OldRoot/"
    $newPrefix = "$NewRoot/"
    if ($Path.StartsWith($oldPrefix, [StringComparison]::Ordinal)) {
        $suffix = $Path.Substring($oldPrefix.Length)
    } elseif ($Path.StartsWith($newPrefix, [StringComparison]::Ordinal)) {
        $suffix = $Path.Substring($newPrefix.Length)
    } else {
        return $false
    }

    $previous = "$oldPrefix$suffix"
    $current = Join-Path $RepositoryPath "$newPrefix$suffix"
    if (-not (Test-Path -LiteralPath $current -PathType Leaf)) {
        return $false
    }
    try {
        $before = Invoke-Checked git @('-C', $RepositoryPath, 'rev-parse', "${Tag}:$previous") -Capture
        $after = Invoke-Checked git @('-C', $RepositoryPath, 'hash-object', $current) -Capture
        return $before.Trim() -eq $after.Trim()
    } catch {
        return $false
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
        [string]$RelocatedFrom,
        [string]$RelocatedTo,
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
            -not [string]::IsNullOrWhiteSpace($_) -and $_ -notmatch '^warning: ' -and
            $_ -notin $IgnoredPaths -and
            $_ -notmatch '(^|/)(tests?/|test_[^/]*\.py$)'
        } | Select-Object -Unique
    )
    if ($RelocatedFrom -and $RelocatedTo) {
        $changedPaths = @($changedPaths | Where-Object {
            -not (Test-ContentIdenticalRelocation `
                -RepositoryPath $RepositoryPath -Tag $Published.Tag -Path $_ `
                -OldRoot $RelocatedFrom -NewRoot $RelocatedTo)
        })
    }
    if ($changedPaths.Count -gt 0) {
        if ($CheckVersions) {
            $nextVersion = '{0}.{1}.{2}' -f $current.Major, $current.Minor, ($current.Build + 1)
            Write-Host "$Name`: опубликована $CurrentVersion; подготовь $nextVersion, синхронизируй версию и changelog." -ForegroundColor Yellow
            Write-Host ($changedPaths -join "`n")
            return $true
        }
        Stop-WithFix `
            -Problem "$Name изменён после выпуска $($Published.Tag), но версия осталась $CurrentVersion." `
            -Fix 'передай агенту: подготовить новую версию плагина (версия, список изменений, пакет)'
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
    if (Test-OrcaCloudHeldForReview -Repository $Repository -RunId ([string]$run.databaseId)) {
        Write-Host "${Name}: $($Published.Tag) загружен в OrcaCloud и ждёт их модерации. Повторять загрузку не нужно." -ForegroundColor Yellow
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
        Stop-WithFix `
            -Problem "${Name}: есть незакоммиченные изменения ($(@($changes).Count) шт.), выпускать можно только закоммиченный код." `
            -Fix "передай агенту: закоммитить или убрать их (список: git -C `"$RepositoryPath`" status --short -- $($Paths -join ' '))"
    }
}

function Assert-Branch {
    param(
        [Parameter(Mandatory)][string]$RepositoryPath,
        [Parameter(Mandatory)][string]$ExpectedBranch
    )

    $current = Invoke-Checked git @('-C', $RepositoryPath, 'branch', '--show-current') -Capture
    if ($current -ne $ExpectedBranch) {
        Stop-WithFix `
            -Problem "В $RepositoryPath выбрана ветка '$current', выпускать можно только из '$ExpectedBranch'." `
            -Fix "git -C `"$RepositoryPath`" switch $ExpectedBranch"
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

    $source = Join-Path $RepositoryPath 'plugins/print-farm/printers_plugin.py'
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
    & gh run watch ([string]$run.databaseId) --repo $Repository --exit-status
    $watchExitCode = $LASTEXITCODE
    if (Test-OrcaCloudHeldForReview -Repository $Repository -RunId ([string]$run.databaseId)) {
        $script:OrcaCloudOutcome = 'held_for_review'
        Write-Host "Пакет загружен в OrcaCloud и ждёт их модерации. Повторять загрузку не нужно." -ForegroundColor Yellow
        return
    }
    if ($watchExitCode -ne 0) {
        throw "Загрузка в OrcaCloud не прошла: $($run.url)"
    }
    $script:OrcaCloudOutcome = 'accepted'
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
        [Parameter(Mandatory)][string[]]$ReleasePaths,
        [string]$RequiredCiWorkflow
    )

    $remote = Get-RemoteBranchCommit `
        -RepositoryPath $RepositoryPath -RemoteName $RemoteName -BranchName $BranchName
    if (-not $remote) {
        throw "$Name`: не удалось определить опубликованный commit $RemoteName/$BranchName."
    }
    $unpublishedPaths = Invoke-Checked git (@(
        '-C', $RepositoryPath, 'diff', '--name-only', $remote, '--'
    ) + $ReleasePaths) -Capture
    if ($unpublishedPaths) {
        $publishAction = if ($RepositoryPath -eq $script:MainRepositoryRoot) { 'Publish' } else { 'PublishPluginCommits' }
        Stop-WithFix `
            -Problem "$Name`: коммиты с этим плагином ещё не отправлены в GitHub ($RemoteName/$BranchName)." `
            -Fix ".\scripts\deploy-server.ps1 -Action $publishAction   (потом дождись зелёных проверок GitHub и повтори)"
    }
    if (-not $RequiredCiWorkflow) { return $remote }

    $json = Invoke-Checked gh @(
        'run', 'list', '--repo', $Repository, '--workflow', $RequiredCiWorkflow,
        '--commit', $remote, '--event', 'push', '--limit', '10',
        '--json', 'headSha,status,conclusion,url,createdAt'
    ) -Capture
    $run = @($json | ConvertFrom-Json) |
        Where-Object { $_.headSha -eq $remote } |
        Sort-Object { [datetime]$_.createdAt } -Descending |
        Select-Object -First 1
    if (-not $run) {
        Stop-WithFix `
            -Problem "$Name`: проверки GitHub для последнего коммита ($($remote.Substring(0, 8))) ещё не запускались." `
            -Fix 'подожди пару минут и повтори: .\scripts\release.ps1'
    }
    if ($run.status -ne 'completed') {
        Stop-WithFix `
            -Problem "ОЖИДАНИЕ: $Name`: проверки GitHub ещё идут: $($run.url)" `
            -Fix 'дождись окончания и повтори: .\scripts\release.ps1'
    }
    if ($run.conclusion -ne 'success') {
        Stop-WithFix `
            -Problem "$Name`: проверки GitHub красные ($($run.conclusion)): $($run.url)" `
            -Fix 'передай агенту ссылку выше: нужно починить проверки'
    }
    return $remote
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
    Write-Host 'Этот пакет проверен в приложении и принят? Y / Д — да (в любой раскладке); любая другая клавиша — пропустить.'
    # Y and Д are meant as keys, not letters: in the other layout the same keys give Н and L.
    return (Read-OwnerApprovalKey) -cin @('y', 'Y', 'н', 'Н', 'д', 'Д', 'l', 'L')
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
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReleaseCommit,
        [Parameter(Mandatory)][string]$Workflow,
        [Parameter(Mandatory)][string[]]$RequiredPatterns,
        [Parameter(Mandatory)][string[]]$ForbiddenPatterns,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
        [Parameter(Mandatory)][string]$ExpectedAssetPattern,
        [switch]$OwnerPublishesDraft,
        [string]$TrustedPublishWorkflow
    )

    $remoteTagCommit = Get-RemoteTagCommit `
        -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    if ($remoteTagCommit -and $remoteTagCommit -ne $ReleaseCommit) {
        throw "Remote-тег '$Tag' указывает на $remoteTagCommit, а опубликованный релизный commit — $ReleaseCommit."
    }
    Ensure-LocalTag -RepositoryPath $RepositoryPath -RemoteName $Remote -Tag $Tag
    $localTag = Invoke-Checked git @('-C', $RepositoryPath, 'tag', '--list', $Tag) -Capture
    if ($localTag) {
        $localCommit = Invoke-Checked git @('-C', $RepositoryPath, 'rev-list', '-n', '1', $Tag) -Capture
        if ($localCommit -ne $ReleaseCommit) {
            throw "Локальный тег '$Tag' указывает на $localCommit, а опубликованный релизный commit — $ReleaseCommit."
        }
    } else {
        Invoke-Checked git @('-C', $RepositoryPath, 'tag', '-a', $Tag, $ReleaseCommit, '-m', "$Name $Tag")
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
            $operationOutput = @(& $Operation $id)
            $componentResults = @($operationOutput | Where-Object {
                $_ -and $_.PSObject.Properties['FilamentHubPluginReleaseResult'] -and
                $_.FilamentHubPluginReleaseResult
            })
            @($operationOutput | Where-Object {
                -not (
                    $_ -and $_.PSObject.Properties['FilamentHubPluginReleaseResult'] -and
                    $_.FilamentHubPluginReleaseResult
                )
            }) | Out-Host
            if ($componentResults.Count -gt 1) {
                throw "Компонент '$id' вернул несколько результатов проверки."
            }
            if ($componentResults.Count -eq 1) {
                $componentResult = $componentResults[0]
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
    $preflightArguments.EmitComponentResult = $true
    $results = @(Invoke-ReleaseBatch -Components $selected -Phase 'проверка' -Operation {
        param($id)
        & $entryPath @preflightArguments -Component $id
    })
    if (-not $DryRun -and -not $CheckVersions) {
        $ready = @(
            $results |
                Where-Object { $_.Status -in @('OK', 'READY') } |
                ForEach-Object Component
        )
        $failed = @($results | Where-Object Status -eq 'ERROR')
        $current = @($results | Where-Object Status -eq 'CURRENT')
        $completed = @()
        if ($ready.Count) {
            $childArguments.EmitComponentResult = $true
            $completed = @(Invoke-ReleaseBatch -Components $ready -Phase 'выпуск' -Operation {
                param($id)
                & $entryPath @childArguments -Component $id
            })
        }
        $results = @($failed) + @($current) + @($completed)
    }
    Write-Host "`nИтог по компонентам:" -ForegroundColor Cyan
    $summaryResults = @(foreach ($id in $selected) {
        $matchedResults = @($results | Where-Object { $_.Component -eq $id })
        if ($matchedResults.Count -ne 1) {
            $result = [pscustomobject]@{
                Component = $id
                Status = 'ERROR'
                Detail = "внутренняя ошибка сводки: получено результатов — $($matchedResults.Count)"
            }
        } else {
            $result = $matchedResults[0]
        }
        $result
    })
    foreach ($result in $summaryResults) {
        $id = $result.Component
        Write-Host "  $id — $($result.Status): $($result.Detail)"
    }
    if (@($summaryResults | Where-Object Status -eq 'ERROR').Count) {
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

$orcaSourcePaths = @('orca-plugin', ':(exclude)orca-plugin/description.md')
$plans = @()
if ($selected -contains 'orcaslicer') {
    $version = Get-OrcaVersion
    $published = Get-PublishedComponent `
        -Repository $mainRepository `
        -AssetPattern '^filamenthub-(?<version>\d+\.\d+\.\d+)-.*\.whl$' `
        -TagPatterns @('^v\d+\.\d+\.\d+$', '^plugins-v\d+\.\d+\.\d+$')
    $needed = Test-ComponentNeedsRelease `
        -Name 'FilamentHub for OrcaSlicer' -CurrentVersion $version -Published $published `
        -RepositoryPath $script:MainRepositoryRoot -RemoteName $Remote -SourcePaths $orcaSourcePaths `
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
        ReleasePaths = $orcaSourcePaths + @('scripts/publish-plugin-releases.ps1', 'scripts/render_plugin_release_notes.py', '.github/workflows/release-filamenthub.yml', '.github/workflows/publish-orcacloud.yml', 'scripts/plugin-required-api-level.json')
        Workflow = 'release-filamenthub.yml'; TrustedPublishWorkflow = 'publish-orcacloud.yml'
        CandidateWheel = Join-Path $script:MainRepositoryRoot "orca-plugin/dist/release-$version/wheels/filamenthub-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $script:MainRepositoryRoot "orca-plugin/dist/release-$version/SHA256SUMS"
        Builder = 'orca-plugin/build_package.py'
        BuiltWheelRelative = "wheels/filamenthub-$version-py3-none-any.whl"
        RequiredApiLevel = Get-RequiredPluginApiLevel -Id 'orcaslicer'
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
        ReleasePaths = @('octoprint-plugin', 'scripts/render_plugin_release_notes.py', '.github/workflows/release-octoprint.yml', 'scripts/plugin-required-api-level.json')
        Workflow = 'release-octoprint.yml'; TrustedPublishWorkflow = $null
        CandidateWheel = Join-Path $script:MainRepositoryRoot "octoprint-plugin/dist/release-$version/octoprint_filamenthubbridge-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $script:MainRepositoryRoot "octoprint-plugin/dist/release-$version/SHA256SUMS"
        Builder = 'octoprint-plugin/build_package.py'
        BuiltWheelRelative = "octoprint_filamenthubbridge-$version-py3-none-any.whl"
        RequiredApiLevel = Get-RequiredPluginApiLevel -Id 'octoprint'
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
        -SourcePaths @('plugins/printers', 'plugins/print-farm') `
        -IgnoredPaths @(
            'plugins/printers/test_release_workflow.py', 'plugins/print-farm/test_release_workflow.py',
            'plugins/printers/build_package.py', 'plugins/print-farm/build_package.py',
            'plugins/printers/PUBLISHING.md', 'plugins/print-farm/PUBLISHING.md'
        ) `
        -RelocatedFrom 'plugins/printers' -RelocatedTo 'plugins/print-farm' `
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
        ReleasePaths = @('plugins/print-farm', '.github/workflows/release-printers.yml', '.github/workflows/publish-orcacloud.yml')
        Workflow = 'release-printers.yml'; TrustedPublishWorkflow = 'publish-orcacloud.yml'
        CandidateWheel = Join-Path $printFarmRepositoryRoot "plugins/print-farm/dist/release-$version/wheels/printers-$version-py3-none-any.whl"
        CandidateChecksums = Join-Path $printFarmRepositoryRoot "plugins/print-farm/dist/release-$version/SHA256SUMS"
        Builder = 'plugins/print-farm/build_package.py'
        BuiltWheelRelative = "wheels/printers-$version-py3-none-any.whl"
        RequiredApiLevel = Get-RequiredPluginApiLevel -Id 'print-farm'
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
foreach ($plan in @($plans | Where-Object Needed)) {
    if ($plan.Id -in @('orcaslicer', 'octoprint')) {
        $componentName = if ($plan.Id -eq 'orcaslicer') { 'orca' } else { 'bridge' }
        # The release workflow renders the same notes after the tag is pushed.
        try {
            $releaseNotes = Invoke-Checked python @(
                'scripts/render_plugin_release_notes.py', '--component', $componentName
            ) -WorkingDirectory $script:MainRepositoryRoot -Capture
        } catch {
            Stop-WithFix `
                -Problem "$($plan.Name): не собирается текст выпуска $($plan.Version) из списка изменений." `
                -Fix 'передай агенту: дополнить список изменений (CHANGELOG) для этой версии'
        }
        if (-not $HideReleaseNotes) {
            Write-Host ''
            Write-Host "$($plan.Name) — release notes:" -ForegroundColor Cyan
            Write-Host $releaseNotes
        }
    }
}

$mainReleasePaths = @(
    'scripts/render_plugin_release_notes.py', 'scripts/plugin-required-api-level.json'
)
if ($selected -contains 'orcaslicer') {
    $mainReleasePaths += $orcaSourcePaths + @('scripts/publish-plugin-releases.ps1', '.github/workflows/release-filamenthub.yml', '.github/workflows/publish-orcacloud.yml')
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
        -Paths @('plugins/print-farm', '.github/workflows/release-printers.yml', '.github/workflows/publish-orcacloud.yml') `
        -Name 'Print Farm'
}

foreach ($repositoryGroup in @($plans | Where-Object { $_.Needed -or $_.Repair } |
    Group-Object RepositoryPath)) {
    $repositoryPlans = @($repositoryGroup.Group)
    $repositoryPlan = $repositoryPlans[0]
    $releasePaths = @($repositoryPlans | ForEach-Object ReleasePaths | Select-Object -Unique)
    $releaseCommit = Assert-ReleaseCommitPublished `
        -RepositoryPath $repositoryPlan.RepositoryPath -RemoteName $Remote `
        -BranchName $Branch -Name $repositoryPlan.Name `
        -Repository $repositoryPlan.Repository -ReleasePaths $releasePaths `
        -RequiredCiWorkflow $repositoryPlan.RequiredCiWorkflow
    foreach ($plan in $repositoryPlans) {
        $plan | Add-Member -NotePropertyName ReleaseCommit -NotePropertyValue $releaseCommit
    }
}

# Everything that can stop a release is checked here, before the owner is
# asked anything and before any tag or release exists.
$actionablePlans = @($plans | Where-Object { $_.Needed -or $_.Repair })
foreach ($plan in $actionablePlans) {
    $plan | Add-Member -NotePropertyName NeedsSiteDeploy -NotePropertyValue $false
    if ($ExpectedReleaseCommit -and $plan.ReleaseCommit -ne $ExpectedReleaseCommit) {
        Stop-WithFix `
            -Problem "$($plan.Name): после проверки на GitHub появились новые коммиты; выпуск остановлен, чтобы не выпустить непроверенное." `
            -Fix '.\scripts\release.ps1'
    }
    Assert-ReleaseRights -Name $plan.Name -Repository $plan.Repository
    if (-not $plan.Needed) { continue }
    Assert-GitIdentity -Name $plan.Name -RepositoryPath $plan.RepositoryPath
    $existingRemoteTag = Assert-TagAvailable `
        -Name $plan.Name -RepositoryPath $plan.RepositoryPath -Tag $plan.Tag -ReleaseCommit $plan.ReleaseCommit
    if (-not $existingRemoteTag) {
        Assert-TagPushAllowed `
            -Name $plan.Name -RepositoryPath $plan.RepositoryPath -Tag $plan.Tag -ReleaseCommit $plan.ReleaseCommit
    }
    Assert-CandidateMatchesSource -Plan $plan
    if ($null -ne $plan.RequiredApiLevel) {
        $liveSiteLevel = Get-SitePluginApiLevel -BaseUrl $PublicBaseUrl
        $plan.NeedsSiteDeploy = Test-SiteServesPlugin `
            -Id $plan.Id -Name $plan.Name -Required $plan.RequiredApiLevel -Live $liveSiteLevel `
            -Planned $(if ($DryRun) { $PlannedSiteApiLevel } else { 0 })
    }
}

if ($DryRun) {
    foreach ($plan in $actionablePlans) {
        if (-not (Test-Path -LiteralPath $plan.CandidateWheel -PathType Leaf)) {
            throw "$($plan.Name): не найден собранный пакет '$($plan.CandidateWheel)'. Агент должен сначала собрать и проверить release candidate."
        }
        $candidateHash = (Get-FileHash -LiteralPath $plan.CandidateWheel -Algorithm SHA256).Hash.ToLowerInvariant()
        Get-LocalCandidateSha256 `
            -Name $plan.Name -WheelPath $plan.CandidateWheel `
            -ChecksumPath $plan.CandidateChecksums -ExpectedSha256 $candidateHash | Out-Null
    }
    $actionable = $actionablePlans.Count
    $componentResult = if ($actionable) {
        $plan = $actionablePlans[0]
        [pscustomobject]@{
            FilamentHubPluginReleaseResult = $true
            Status = 'READY'
            Detail = if ($plan.NeedsSiteDeploy) {
                'всё проверено; выйдет только после выкатки сайта'
            } elseif ($plan.Repair) {
                "всё проверено; нужно повторить загрузку $($plan.Published.Tag) в OrcaCloud"
            } else {
                'commit опубликован, CI зелёный; пакет готов к отдельному выпуску'
            }
            Id = $plan.Id; Name = $plan.Name; Version = $plan.Version; Tag = $plan.Tag
            Repair = [bool]$plan.Repair; NeedsSiteDeploy = [bool]$plan.NeedsSiteDeploy
            ReleaseCommit = $plan.ReleaseCommit
            CandidateWheel = $plan.CandidateWheel; CandidateChecksums = $plan.CandidateChecksums
            Sha256 = (Get-FileHash -LiteralPath $plan.CandidateWheel -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    } else {
        [pscustomobject]@{
            FilamentHubPluginReleaseResult = $true
            Status = 'CURRENT'
            Detail = 'нового релиза не требуется'
        }
    }
    Write-Host 'Dry-run завершён. Push, теги и GitHub Releases не создавались.' -ForegroundColor Green
    Write-Host 'Приёмка пакета и файлы на GitHub на этом шаге не проверялись.' -ForegroundColor DarkGray
    if ($EmitComponentResult) {
        $componentResult
    }
    return
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
                Repository = $plan.Repository; Tag = $plan.Tag; ReleaseCommit = $plan.ReleaseCommit
                Workflow = $plan.Workflow
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
                Repository = $plan.Repository; Tag = $plan.Tag; ReleaseCommit = $plan.ReleaseCommit
                Workflow = $plan.Workflow
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
                Repository = $plan.Repository; Tag = $plan.Tag; ReleaseCommit = $plan.ReleaseCommit
                Workflow = $plan.Workflow
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
    $componentResult = [pscustomobject]@{
        FilamentHubPluginReleaseResult = $true
        Status = 'CURRENT'
        Detail = 'нового релиза не требуется'
    }
    Write-Host 'Новых версий плагинов нет; GitHub Releases не создавались.' -ForegroundColor Green
} else {
    $componentResult = [pscustomobject]@{
        FilamentHubPluginReleaseResult = $true
        Status = 'RELEASED'
        Detail = if ($script:OrcaCloudOutcome -eq 'held_for_review') {
            'выпущен; OrcaCloud принял пакет и проверяет его вручную, повторять не нужно'
        } else {
            'независимый релиз завершён'
        }
    }
}
if ($EmitComponentResult) {
    $componentResult
}
