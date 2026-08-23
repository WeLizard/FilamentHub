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
    [switch]$HideReleaseNotes,

    [Parameter()]
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

throw "Смешанные plugins-v* releases отключены. Используй scripts/publish-plugin-releases.ps1: каждый плагин публикуется отдельным GitHub release."

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Не найдена обязательная команда '$Name' в PATH."
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
        throw "Не удалось прочитать версию пакета из '$pyprojectPath'."
    }

    $pluginContent = Get-Content -LiteralPath $pluginPath -Raw
    $pluginMatch = [regex]::Match(
        $pluginContent,
        '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>[^"]+)"\s*$'
    )
    if (-not $pluginMatch.Success) {
        throw "Не удалось прочитать PLUGIN_VERSION из '$pluginPath'."
    }

    $packageVersion = $pyprojectMatch.Groups['version'].Value
    $runtimeVersion = $pluginMatch.Groups['version'].Value
    if ($packageVersion -ne $runtimeVersion) {
        throw "Версии Bridge расходятся: pyproject.toml=$packageVersion, PLUGIN_VERSION=$runtimeVersion."
    }
    if ($packageVersion -notmatch '^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$') {
        throw "Версию Bridge '$packageVersion' нельзя использовать для релиза."
    }

    return $packageVersion
}

function Get-OrcaPluginVersion {
    $pluginPath = 'orca-plugin/filamenthub_plugin.py'
    $pluginContent = Get-Content -LiteralPath $pluginPath -Raw
    $pluginMatch = [regex]::Match(
        $pluginContent,
        '(?m)^PLUGIN_VERSION\s*=\s*"(?<version>[^"]+)"\s*$'
    )
    if (-not $pluginMatch.Success) {
        throw "Не удалось прочитать PLUGIN_VERSION из '$pluginPath'."
    }

    $version = $pluginMatch.Groups['version'].Value
    if ($version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Версию FilamentHub '$version' нельзя использовать для Plugin Hub."
    }
    return $version
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
            throw "Команда завершилась с ошибкой ($LASTEXITCODE): $FilePath $($Arguments -join ' ')`n$($output -join "`n")"
        }
        return ($output -join "`n").Trim()
    }

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Команда завершилась с ошибкой ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
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
        throw "Не удалось проверить тег '$ReleaseTag' в remote '$RemoteName'."
    }
    if ($peeled) {
        return (($peeled -split "`t")[0]).Trim()
    }

    $direct = & git ls-remote $RemoteName "refs/tags/$ReleaseTag" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить тег '$ReleaseTag' в remote '$RemoteName'."
    }
    if ($direct) {
        return (($direct -split "`t")[0]).Trim()
    }
    return $null
}

function Get-NextBundleTag {
    param([Parameter(Mandatory)][string]$RemoteName)

    $remoteTags = & git ls-remote --tags --refs $RemoteName 'refs/tags/plugins-v*' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось получить список release-тегов из remote '$RemoteName'."
    }

    $versions = @(
        foreach ($line in $remoteTags) {
            $reference = ($line -split "`t")[-1]
            if ($reference -match '^refs/tags/plugins-v(?<version>\d+\.\d+\.\d+)$') {
                [version]$Matches['version']
            }
        }
    )
    if ($versions.Count -eq 0) {
        return 'plugins-v0.1.0'
    }

    $latest = $versions | Sort-Object -Descending | Select-Object -First 1
    return "plugins-v$($latest.Major).$($latest.Minor).$($latest.Build + 1)"
}

function Assert-ReleaseAssets {
    param(
        [Parameter(Mandatory)]$Release,
        [Parameter(Mandatory)][string]$BridgeVersion
    )

    $assetNames = @($Release.assets | ForEach-Object { $_.name })
    $escapedVersion = [regex]::Escape($BridgeVersion)
    $requiredPatterns = @(
        '^filamenthub-\d+\.\d+\.\d+(?:[^/]*)\.whl$',
        "^octoprint_filamenthubbridge-$escapedVersion-.*\.whl$",
        "^octoprint_filamenthubbridge-$escapedVersion\.tar\.gz$",
        '^SHA256SUMS$'
    )

    foreach ($pattern in $requiredPatterns) {
        if (-not ($assetNames | Where-Object { $_ -match $pattern })) {
            throw "В draft-релизе нет обязательного файла по шаблону '$pattern'. Файлы: $($assetNames -join ', ')"
        }
    }
}

Assert-Command -Name git
Assert-Command -Name gh
Assert-Command -Name python

$repositoryRoot = Invoke-Checked -FilePath git -Arguments @('rev-parse', '--show-toplevel') -Capture
Set-Location -LiteralPath $repositoryRoot

$releaseSources = @(
    'orca-plugin',
    'octoprint-plugin',
    '.github/workflows/release-plugins.yml',
    'scripts/render_plugin_release_notes.py',
    'scripts/tests/test_render_plugin_release_notes.py'
)
$releaseSourceChanges = & git status --porcelain --untracked-files=normal -- $releaseSources
if ($LASTEXITCODE -ne 0) {
    throw 'Не удалось проверить исходники плагинов для релиза.'
}
if ($releaseSourceChanges) {
    throw "Перед подготовкой релиза закоммить все изменения плагинов и release-workflow:`n$($releaseSourceChanges -join "`n")"
}

$orcaVersion = Get-OrcaPluginVersion
$bridgeVersion = Get-BridgeVersion
$orcaCloudTag = "v$orcaVersion"
$releaseNotes = Invoke-Checked -FilePath python -Arguments @('scripts/render_plugin_release_notes.py') -Capture
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = Get-NextBundleTag -RemoteName $Remote
} elseif ($Tag -notmatch '^plugins-v\d+\.\d+\.\d+$') {
    throw "Тег '$Tag' не соответствует формату plugins-vX.Y.Z."
}
$currentBranch = Invoke-Checked -FilePath git -Arguments @('branch', '--show-current') -Capture
if ($currentBranch -ne $Branch) {
    throw "Сейчас выбрана ветка '$currentBranch'. Перед релизом переключись на '$Branch'."
}

$headCommit = Invoke-Checked -FilePath git -Arguments @('rev-parse', 'HEAD') -Capture
$localTag = Invoke-Checked -FilePath git -Arguments @('tag', '--list', $Tag) -Capture
$tagExistsLocally = -not [string]::IsNullOrWhiteSpace($localTag)
if ($tagExistsLocally) {
    $tagCommit = Invoke-Checked -FilePath git -Arguments @('rev-list', '-n', '1', $Tag) -Capture
    if ($tagCommit -ne $headCommit) {
        throw "Тег '$Tag' указывает на $tagCommit, а текущий HEAD — $headCommit. Увеличь версию комплекта в теге plugins-vX.Y.Z: старый релиз не должен молча пропускать новый код."
    }
} else {
    $tagCommit = $headCommit
}

$localOrcaCloudTag = Invoke-Checked -FilePath git -Arguments @('tag', '--list', $orcaCloudTag) -Capture
$orcaCloudTagExistsLocally = -not [string]::IsNullOrWhiteSpace($localOrcaCloudTag)
$remoteOrcaCloudTagCommit = Get-RemoteTagCommit -RemoteName $Remote -ReleaseTag $orcaCloudTag
if ($orcaCloudTagExistsLocally) {
    $orcaCloudTagCommit = Invoke-Checked -FilePath git -Arguments @('rev-list', '-n', '1', $orcaCloudTag) -Capture
    if ($remoteOrcaCloudTagCommit -and $remoteOrcaCloudTagCommit -ne $orcaCloudTagCommit) {
        throw "Local и remote теги '$orcaCloudTag' указывают на разные коммиты. Перезапись запрещена."
    }
    if (-not $remoteOrcaCloudTagCommit -and $orcaCloudTagCommit -ne $headCommit) {
        throw "Локальный тег '$orcaCloudTag' указывает на $orcaCloudTagCommit, а текущий HEAD — $headCommit."
    }
} else {
    $orcaCloudTagCommit = if ($remoteOrcaCloudTagCommit) {
        $remoteOrcaCloudTagCommit
    } else {
        $headCommit
    }
}

$repository = Invoke-Checked -FilePath gh -Arguments @('repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner') -Capture
Invoke-Checked -FilePath gh -Arguments @('auth', 'status')

$pendingChanges = Invoke-Checked -FilePath git -Arguments @('status', '--porcelain') -Capture
if ($pendingChanges) {
    Write-Warning 'В рабочем дереве есть незакоммиченные изменения. Они не попадут в релиз.'
}

Write-Host "Репозиторий: $repository"
Write-Host "Ветка      : $Branch ($headCommit)"
Write-Host "FilamentHub: $orcaVersion"
Write-Host "OctoPrint  : $bridgeVersion"
Write-Host "Тег релиза : $Tag ($tagCommit)$(if (-not $tagExistsLocally) { ' [будет создан]' })"
Write-Host "Orca Cloud : $orcaCloudTag ($orcaCloudTagCommit)$(if (-not $remoteOrcaCloudTagCommit) { ' [будет опубликован]' } else { ' [уже опубликован]' })"
Write-Host 'Режим      : автоматическая публикация после успешной проверки workflow'
if (-not $HideReleaseNotes) {
    Write-Host ''
    Write-Host 'Текст GitHub Release из changelog:' -ForegroundColor Cyan
    Write-Host $releaseNotes
}
if ($Publish) {
    Write-Warning 'Ключ -Publish больше не требуется для tag-triggered релиза и сохранён только для восстановления старого draft.'
}

if ($DryRun) {
    Write-Host 'Dry-run завершён. Push, workflow и изменения релиза не выполнялись.'
    return
}

if (-not $tagExistsLocally) {
    Invoke-Checked -FilePath git -Arguments @('tag', '-a', $Tag, '-m', "FilamentHub plugins $Tag")
    $tagCommit = Invoke-Checked -FilePath git -Arguments @('rev-list', '-n', '1', $Tag) -Capture
    Write-Host "Создан локальный тег релиза '$Tag' на $tagCommit."
}

Invoke-Checked -FilePath git -Arguments @('push', $Remote, $Branch)

$remoteTagCommit = Get-RemoteTagCommit -RemoteName $Remote -ReleaseTag $Tag
if ($remoteTagCommit) {
    if ($remoteTagCommit -ne $tagCommit) {
        throw "Remote-тег '$Tag' указывает на $remoteTagCommit, ожидался $tagCommit. Перезапись запрещена."
    }
    Write-Host "Remote-тег '$Tag' уже указывает на ожидаемый коммит."
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
        throw "Workflow релиза для '$Tag' не появился за $RunDiscoveryTimeoutSeconds секунд."
    }

    Write-Host "Ожидаю завершения workflow: $($run.url)"
    Invoke-Checked -FilePath gh -Arguments @('run', 'watch', [string]$run.databaseId, '--repo', $repository, '--exit-status')
    $release = Get-Release -Repository $repository -ReleaseTag $Tag
}

if (-not $release) {
    throw "Workflow завершился, но релиз '$Tag' не найден."
}

Assert-ReleaseAssets -Release $release -BridgeVersion $bridgeVersion

if (-not $release.isDraft) {
    Write-Host "Релиз опубликован: $($release.url)"
} else {
    if ($Publish) {
        Invoke-Checked -FilePath gh -Arguments @('release', 'edit', $Tag, '--repo', $repository, '--draft=false')
        $release = Get-Release -Repository $repository -ReleaseTag $Tag
        Write-Host "Релиз опубликован: $($release.url)"
    } else {
        throw "Workflow оставил релиз '$Tag' в draft: $($release.url). Проверь завершение шага Publish tag-triggered release перед ручной публикацией."
    }
}

if (-not $remoteOrcaCloudTagCommit) {
    if (-not $orcaCloudTagExistsLocally) {
        Invoke-Checked -FilePath git -Arguments @(
            'tag', '-a', $orcaCloudTag, '-m', "FilamentHub for OrcaSlicer $orcaVersion"
        )
        $orcaCloudTagCommit = Invoke-Checked -FilePath git -Arguments @(
            'rev-list', '-n', '1', $orcaCloudTag
        ) -Capture
        Write-Host "Создан Orca Cloud tag '$orcaCloudTag' на $orcaCloudTagCommit."
    }
    Invoke-Checked -FilePath git -Arguments @('push', $Remote, "refs/tags/$orcaCloudTag")
    Write-Host "Запущен GitHub Release и Orca Cloud trusted publishing для '$orcaCloudTag'."
} else {
    Write-Host "Orca Cloud tag '$orcaCloudTag' уже существует; повторная публикация не запускалась."
}
