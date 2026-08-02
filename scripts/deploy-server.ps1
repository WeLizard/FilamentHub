<#
.SYNOPSIS
Интерактивная консоль владельца для деплоя FilamentHub и релизов плагинов.

.DESCRIPTION
Backup, миграции и переключение контейнеров выполняются только на VDS. Эта
консоль проверяет точный SHA origin/main и соответствующий запуск GitHub CI,
просит владельца подтвердить SHA и запускает серверный worker по SSH. Она
никогда не добавляет файлы в Git, не создаёт коммиты и не отправляет код.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('Menu', 'Preflight', 'Deploy', 'Status', 'Backup', 'PruneBuildCache', 'ListReleases', 'DownloadRelease', 'CheckDownloadPage', 'PrepareRelease', 'PublishRelease')]
    [string]$Action = 'Menu',

    [Parameter()]
    [string]$Server = $env:FILAMENTHUB_DEPLOY_TARGET,

    [Parameter()]
    [string]$RemoteProjectDirectory = 'FilamentHub',

    [Parameter()]
    [string]$ReleaseTag,

    [Parameter()]
    [string]$PublicBaseUrl = 'https://filamenthub.ru'
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

function Get-RepositoryName {
    Assert-Command gh
    return Invoke-Checked gh @('repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner') -Capture
}

function Get-VerifiedPublishedMain {
    Assert-Command git
    Assert-Command gh

    Invoke-Checked git @('fetch', '--no-recurse-submodules', 'origin', 'main')
    $remoteHead = Invoke-Checked git @('rev-parse', 'origin/main') -Capture
    if ($remoteHead -notmatch '^[0-9a-f]{40}$') {
        throw "origin/main вернул некорректный SHA: $remoteHead"
    }

    $repository = Get-RepositoryName
    $runsJson = Invoke-Checked gh @(
        'run', 'list',
        '--repo', $repository,
        '--workflow', 'ci.yml',
        '--commit', $remoteHead,
        '--limit', '10',
        '--json', 'headSha,status,conclusion,url,createdAt,event'
    ) -Capture
    $runs = @($runsJson | ConvertFrom-Json)
    $run = $runs |
        Where-Object { $_.headSha -eq $remoteHead -and $_.event -eq 'push' } |
        Sort-Object { [datetime]$_.createdAt } -Descending |
        Select-Object -First 1
    if (-not $run) {
        throw "Для точного коммита $remoteHead не найден CI, запущенный после push."
    }
    if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') {
        throw "CI для $remoteHead не зелёный (статус=$($run.status), результат=$($run.conclusion)): $($run.url)"
    }

    return [pscustomobject]@{
        Sha = $remoteHead
        Repository = $repository
        CiUrl = $run.url
    }
}

function Get-ServerTarget {
    if ([string]::IsNullOrWhiteSpace($script:Server)) {
        $script:Server = Read-Host 'SSH-адрес VDS (например user@server или имя из SSH config)'
    }
    if ($script:Server -notmatch '^[A-Za-z0-9._@:\-\[\]]+$') {
        throw 'SSH-адрес содержит недопустимые символы. Используй имя из SSH config или user@host.'
    }
    if ($RemoteProjectDirectory -notmatch '^[A-Za-z0-9_./\-]+$') {
        throw 'Путь к проекту на VDS должен быть относительным от SSH home или абсолютным и не может содержать ~.'
    }
    return $script:Server
}

function Invoke-RemoteWorker {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$WorkerRevision,
        [switch]$UseDeployedRevision
    )

    Assert-Command ssh
    $target = Get-ServerTarget
    $quotedArguments = @($Arguments | ForEach-Object {
        if ($_ -notmatch '^[A-Za-z0-9_./:\-]+$') {
            throw "Недопустимый аргумент удалённой команды: $_"
        }
        "'$_'"
    })

    if ($UseDeployedRevision) {
        if (-not [string]::IsNullOrWhiteSpace($WorkerRevision)) {
            throw 'Нельзя одновременно выбрать deployed worker и передать WorkerRevision.'
        }
        # Read-only/status and explicitly confirmed maintenance actions use the
        # worker committed in the deployed HEAD. This remains available during
        # a GitHub outage, but the marker makes an old/incompatible checkout
        # fail closed instead of interpreting unknown flags as a full deploy.
        $remoteCommand = "set -o pipefail && cd '$RemoteProjectDirectory' && git show 'HEAD:scripts/deploy.sh' | awk 'NR == 2 { compatible = (`$0 == `"# FILAMENTHUB_DEPLOY_PROTOCOL=2`") } END { exit !compatible }' && git show 'HEAD:scripts/deploy.sh' | PROJECT_DIR=`"`$PWD`" bash -s -- $($quotedArguments -join ' ')"
        Invoke-Checked ssh @($target, $remoteCommand)
        return
    }

    if ($WorkerRevision -notmatch '^[0-9a-f]{40}$') {
        throw 'Для деплоя обязателен точный 40-символьный WorkerRevision.'
    }
    # Worker берётся непосредственно из проверенного SHA, а не из старого
    # checkout на VDS. Поэтому защитный workflow действует уже при первом
    # деплое и не отстаёт от кода на одну публикацию.
    $remoteCommand = "set -o pipefail && cd '$RemoteProjectDirectory' && git fetch --no-recurse-submodules origin main && git cat-file -e '$($WorkerRevision)^{commit}' && git merge-base --is-ancestor '$WorkerRevision' origin/main && git show '$($WorkerRevision):scripts/deploy.sh' | awk 'NR == 2 { compatible = (`$0 == `"# FILAMENTHUB_DEPLOY_PROTOCOL=2`") } END { exit !compatible }' && git show '$($WorkerRevision):scripts/deploy.sh' | PROJECT_DIR=`"`$PWD`" bash -s -- $($quotedArguments -join ' ')"
    Invoke-Checked ssh @($target, $remoteCommand)
}

function Get-DeploymentCandidate {
    Assert-Command git

    $branch = Invoke-Checked git @('branch', '--show-current') -Capture
    if ($branch -ne 'main') {
        throw "Деплой нужно готовить из ветки main; сейчас выбрана '$branch'."
    }

    $dirty = Invoke-Checked git @('status', '--porcelain', '--untracked-files=normal') -Capture
    if ($dirty) {
        Write-Host 'В рабочем дереве есть локальные изменения; они не попадут в деплой:' -ForegroundColor Yellow
        Write-Host $dirty
        Write-Host 'Деплой использует только точный уже опубликованный SHA origin/main.' -ForegroundColor Yellow
    }

    $published = Get-VerifiedPublishedMain
    $head = Invoke-Checked git @('rev-parse', 'HEAD') -Capture
    $remoteHead = $published.Sha
    if ($head -ne $remoteHead) {
        throw "Локальный HEAD ($head) не совпадает с origin/main ($remoteHead). Сначала отправь или получи изменения main."
    }

    [pscustomobject]@{
        Sha = $head
        ShortSha = $head.Substring(0, 8)
        Repository = $published.Repository
        CiUrl = $published.CiUrl
    }
}

function Show-Preflight {
    $candidate = Get-DeploymentCandidate
    Write-Host ''
    Write-Host 'Кандидат на деплой готов' -ForegroundColor Green
    Write-Host "  Репозиторий: $($candidate.Repository)"
    Write-Host "  Коммит:      $($candidate.Sha)"
    Write-Host "  CI:         $($candidate.CiUrl)"
    return $candidate
}

function Start-ProductionDeploy {
    $candidate = Show-Preflight
    Write-Host ''
    $confirmation = Read-Host "Введи ДЕПЛОЙ $($candidate.ShortSha), чтобы развернуть именно этот коммит"
    if ($confirmation -ne "ДЕПЛОЙ $($candidate.ShortSha)") {
        throw 'Деплой отменён.'
    }

    Invoke-RemoteWorker -Arguments @('--revision', $candidate.Sha, '--yes') -WorkerRevision $candidate.Sha
}

function Show-ProductionStatus {
    Invoke-RemoteWorker -Arguments @('--status') -UseDeployedRevision
}

function Start-ProductionBackup {
    $confirmation = Read-Host 'Введи БЭКАП, чтобы создать и проверить зашифрованную копию production-базы'
    if ($confirmation -ne 'БЭКАП') {
        throw 'Создание backup отменено.'
    }
    Invoke-RemoteWorker -Arguments @('--backup-only') -UseDeployedRevision
}

function Start-BuildCacheCleanup {
    $confirmation = Read-Host 'Введи ОЧИСТИТЬ КЭШ, чтобы удалить только build-cache Docker старше 14 дней'
    if ($confirmation -ne 'ОЧИСТИТЬ КЭШ') {
        throw 'Очистка build-cache отменена.'
    }
    Invoke-RemoteWorker -Arguments @('--prune-build-cache', '--yes') -UseDeployedRevision
}

function Show-PluginReleases {
    $repository = Get-RepositoryName
    $json = Invoke-Checked gh @(
        'release', 'list', '--repo', $repository, '--limit', '30',
        '--json', 'tagName,name,isDraft,isPrerelease,publishedAt'
    ) -Capture
    $releases = @($json | ConvertFrom-Json | Where-Object { $_.tagName -like 'plugins-v*' })
    if ($releases.Count -eq 0) {
        Write-Host 'GitHub Releases не найдены.' -ForegroundColor Yellow
        return
    }
    $releases |
        Select-Object tagName, name, isDraft, isPrerelease, publishedAt, @{
            Name = 'url'
            Expression = { "https://github.com/$repository/releases/tag/$($_.tagName)" }
        } |
        Format-Table -AutoSize
}

function Read-ReleaseTag {
    if ([string]::IsNullOrWhiteSpace($script:ReleaseTag)) {
        $script:ReleaseTag = Read-Host 'Тег GitHub Release (например plugins-v0.1.0)'
    }
    if ($script:ReleaseTag -notmatch '^plugins-v\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$') {
        throw "Неподдерживаемый тег релиза плагинов: $script:ReleaseTag"
    }
    return $script:ReleaseTag
}

function Get-PluginReleaseAssets {
    Assert-Command gh
    $repository = Get-RepositoryName
    $tag = Read-ReleaseTag
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $destination = Join-Path ([IO.Path]::GetTempPath()) "FilamentHub\releases\$tag-$timestamp"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null

    Invoke-Checked gh @('release', 'download', $tag, '--repo', $repository, '--dir', $destination)
    $checksumsPath = Join-Path $destination 'SHA256SUMS'
    if (-not (Test-Path -LiteralPath $checksumsPath -PathType Leaf)) {
        throw "В релизе '$tag' нет SHA256SUMS. Скачанные файлы оставлены в $destination"
    }

    $verified = 0
    foreach ($line in Get-Content -LiteralPath $checksumsPath) {
        if ($line -notmatch '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<name>.+)$') {
            throw "Некорректная строка SHA256SUMS: $line"
        }
        $assetPath = Join-Path $destination $Matches.name
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "В SHA256SUMS указан отсутствующий файл: $($Matches.name)"
        }
        $actual = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash
        if ($actual -ne $Matches.hash) {
            throw "Не совпала контрольная сумма файла $($Matches.name)"
        }
        $verified++
    }

    if ($verified -eq 0) {
        throw 'В SHA256SUMS не найдено ни одного файла.'
    }
    Write-Host "Проверено файлов релиза: $verified. Папка: $destination" -ForegroundColor Green
}

function Test-DownloadPageRelease {
    $tag = Read-ReleaseTag
    $endpoint = "$($PublicBaseUrl.TrimEnd('/'))/api/v1/downloads/plugins"
    try {
        $response = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 20
    } catch {
        throw "Не удалось прочитать публичный API плагинов $endpoint`: $($_.Exception.Message)"
    }

    if (-not $response.release_url -or $response.release_url -notmatch "/releases/tag/$([regex]::Escape($tag))$") {
        Write-Host "Страница Download пока не выбрала $tag." -ForegroundColor Yellow
        Write-Host 'Опубликованный релиз подхватится автоматически; метаданные могут кешироваться до 15 минут.' -ForegroundColor Yellow
        if ($response.release_url) {
            Write-Host "Текущий релиз: $($response.release_url)"
        }
        return $false
    }

    $packages = @($response.packages)
    $expectedPlugins = @('orcaslicer', 'octoprint')
    foreach ($plugin in $expectedPlugins) {
        $matches = @($packages | Where-Object { $_.plugin -eq $plugin })
        if ($matches.Count -ne 1) {
            Write-Host "Релиз $tag не готов: пакет '$plugin' должен присутствовать ровно один раз." -ForegroundColor Yellow
            return $false
        }

        $package = $matches[0]
        if ([string]::IsNullOrWhiteSpace([string]$package.filename) -or
            [string]$package.checksum -notmatch '^[0-9a-fA-F]{64}$' -or
            [string]::IsNullOrWhiteSpace([string]$package.download_url)) {
            Write-Host "Релиз $tag не готов: у пакета '$plugin' неполные метаданные или некорректный SHA-256." -ForegroundColor Yellow
            return $false
        }

        try {
            $downloadUri = [Uri][string]$package.download_url
            $publicUri = [Uri]$PublicBaseUrl
            if ($downloadUri.Scheme -ne $publicUri.Scheme -or $downloadUri.Authority -ne $publicUri.Authority) {
                Write-Host "Релиз $tag не готов: пакет '$plugin' ссылается не на наш публичный сервер." -ForegroundColor Yellow
                return $false
            }

            # GET через наш endpoint заставляет backend получить файл из релиза,
            # проверить его checksum и только после этого начать отдачу. Range
            # уменьшает трафик, если HTTP-слой его поддерживает.
            $downloadResponse = Invoke-WebRequest -Uri $downloadUri -Method Get -Headers @{ Range = 'bytes=0-0' } -TimeoutSec 60
            if ([int]$downloadResponse.StatusCode -notin @(200, 206)) {
                Write-Host "Релиз $tag не готов: файл '$($package.filename)' вернул HTTP $($downloadResponse.StatusCode)." -ForegroundColor Yellow
                return $false
            }
        } catch {
            Write-Host "Релиз $tag не готов: файл '$($package.filename)' не скачивается через FilamentHub: $($_.Exception.Message)" -ForegroundColor Yellow
            return $false
        }
    }

    $filenames = @($packages | Where-Object { $_.plugin -in $expectedPlugins } | ForEach-Object { $_.filename })
    Write-Host "Страница Download использует и раздаёт $tag ($($filenames -join ', '))." -ForegroundColor Green
    return $true
}

function Invoke-PluginReleasePreparation {
    param([switch]$Publish)

    $tag = Read-ReleaseTag
    $verb = if ($Publish) { 'ОПУБЛИКОВАТЬ' } else { 'ПОДГОТОВИТЬ' }
    $confirmation = Read-Host "Введи $verb $tag, чтобы продолжить"
    if ($confirmation -ne "$verb $tag") {
        throw 'Действие с релизом отменено.'
    }

    $scriptPath = Join-Path $PSScriptRoot 'publish-plugin-release.ps1'
    & $scriptPath -Tag $tag -Publish:$Publish
    if (-not $?) {
        throw 'Скрипт публикации плагинов завершился с ошибкой.'
    }
    if ($Publish) {
        $script:ReleaseTag = $tag
        if (-not (Test-DownloadPageRelease)) {
            throw "Релиз $tag опубликован, но ещё не прошёл проверку публичной страницы Download. Повтори пункт 8 после обновления кеша."
        }
    }
}

function Show-Menu {
    while ($true) {
        Write-Host ''
        Write-Host 'Консоль владельца FilamentHub' -ForegroundColor Cyan
        Write-Host '  1. Проверить готовность к деплою (точный SHA + GitHub CI)'
        Write-Host '  2. Задеплоить production'
        Write-Host '  3. Проверить состояние production'
        Write-Host '  4. Создать зашифрованный backup production-базы'
        Write-Host '  5. Очистить устаревший Docker build-cache на VDS'
        Write-Host '  6. Показать GitHub Releases плагинов'
        Write-Host '  7. Скачать и проверить файлы релиза плагинов'
        Write-Host '  8. Проверить релиз плагинов на странице Download'
        Write-Host '  9. Подготовить черновик релиза плагинов'
        Write-Host ' 10. Опубликовать релиз плагинов'
        Write-Host '  0. Выход'
        $choice = Read-Host 'Выбери действие'

        try {
            switch ($choice) {
                '1' { Show-Preflight | Out-Null }
                '2' { Start-ProductionDeploy }
                '3' { Show-ProductionStatus }
                '4' { Start-ProductionBackup }
                '5' { Start-BuildCacheCleanup }
                '6' { Show-PluginReleases }
                '7' { $script:ReleaseTag = $null; Get-PluginReleaseAssets }
                '8' {
                    $script:ReleaseTag = $null
                    if (-not (Test-DownloadPageRelease)) {
                        throw 'Публичная страница Download пока не прошла проверку.'
                    }
                }
                '9' { $script:ReleaseTag = $null; Invoke-PluginReleasePreparation }
                '10' { $script:ReleaseTag = $null; Invoke-PluginReleasePreparation -Publish }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-Host $_.Exception.Message -ForegroundColor Red
        }
    }
}

Assert-Command git
$repositoryRoot = Invoke-Checked git @('rev-parse', '--show-toplevel') -Capture
Set-Location -LiteralPath $repositoryRoot

switch ($Action) {
    'Menu' { Show-Menu }
    'Preflight' { Show-Preflight | Out-Null }
    'Deploy' { Start-ProductionDeploy }
    'Status' { Show-ProductionStatus }
    'Backup' { Start-ProductionBackup }
    'PruneBuildCache' { Start-BuildCacheCleanup }
    'ListReleases' { Show-PluginReleases }
    'DownloadRelease' { Get-PluginReleaseAssets }
    'CheckDownloadPage' {
        if (-not (Test-DownloadPageRelease)) {
            throw 'Публичная страница Download пока не прошла проверку.'
        }
    }
    'PrepareRelease' { Invoke-PluginReleasePreparation }
    'PublishRelease' { Invoke-PluginReleasePreparation -Publish }
}
