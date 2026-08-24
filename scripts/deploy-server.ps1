<#
.SYNOPSIS
Главная интерактивная консоль владельца FilamentHub.

.DESCRIPTION
Консоль объединяет local dev, проверку инструментов OrcaSlicer, GitHub,
независимые релизы плагинов и owner-run production-операции. Backup,
миграции и переключение production-контейнеров выполняются только на VDS.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('Menu', 'Publish', 'Preflight', 'Deploy', 'Status', 'Backup', 'PruneBuildCache', 'ListReleases', 'DownloadRelease', 'CheckDownloadPage', 'PrepareRelease', 'PublishRelease', 'UpdateCatalogSource')]
    [string]$Action = 'Menu',

    # Деплой всегда идёт на один и тот же VDS через алиас SSH config, поэтому
    # адрес не спрашивается: переменная окружения и -Server остаются для
    # переезда на другую машину.
    [Parameter()]
    [string]$Server = $(if ([string]::IsNullOrWhiteSpace($env:FILAMENTHUB_DEPLOY_TARGET)) { 'server' } else { $env:FILAMENTHUB_DEPLOY_TARGET }),

    [Parameter()]
    [string]$RemoteProjectDirectory = 'FilamentHub',

    [Parameter()]
    [string]$ReleaseTag,

    [Parameter()]
    [string]$PublicBaseUrl = 'https://filamenthub.ru'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Ожидание — это не отказ. Сообщения с этой пометкой печатаются жёлтым, чтобы
# «CI ещё идёт» не выглядело как упавший деплой.
$script:WaitingPrefix = 'ОЖИДАНИЕ:'
$script:DeployPollIntervalSeconds = 5
$script:DeployReconnectGraceSeconds = 300
$script:DeployJobTimeoutSeconds = 7200

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Не найдена обязательная команда '$Name' в PATH."
    }
}

function Confirm-Action {
    param([Parameter(Mandatory)][string]$Question)

    return (Read-Host "$Question [y/N]").Trim() -match '^(y|yes|д|да)$'
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

function Invoke-OwnerScript {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string[]]$Arguments = @()
    )

    $path = Join-Path $PSScriptRoot $Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Не найден скрипт: $path"
    }

    & $path @Arguments
    if (-not $?) {
        throw "Скрипт '$Name' завершился с ошибкой."
    }
}

function Write-OperationError {
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)

    $message = $ErrorRecord.Exception.Message
    $colour = if ($message.StartsWith($script:WaitingPrefix)) { 'Yellow' } else { 'Red' }
    Write-Host $message -ForegroundColor $colour
}

function Write-MenuOption {
    param(
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Description
    )

    Write-Host (" {0,2}. {1}" -f $Key, $Title)
    Write-Host ("     {0}" -f $Description) -ForegroundColor DarkGray
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
    if ($run.status -ne 'completed') {
        throw "$script:WaitingPrefix CI для $remoteHead ещё выполняется (статус=$($run.status)): $($run.url)"
    }
    if ($run.conclusion -ne 'success') {
        throw "CI для $remoteHead не зелёный (результат=$($run.conclusion)): $($run.url)"
    }

    return [pscustomobject]@{
        Sha = $remoteHead
        Repository = $repository
        CiUrl = $run.url
    }
}

function Get-ServerTarget {
    $target = "$script:Server".Trim()
    if ([string]::IsNullOrWhiteSpace($target)) {
        throw 'SSH-адрес VDS не задан: передай -Server или задай FILAMENTHUB_DEPLOY_TARGET.'
    }
    if ($target -notmatch '^[A-Za-z0-9._@:\-\[\]]+$') {
        throw "SSH-адрес '$target' содержит недопустимые символы. Используй имя из SSH config или user@host."
    }
    if ($RemoteProjectDirectory -notmatch '^[A-Za-z0-9_./\-]+$') {
        throw 'Путь к проекту на VDS должен быть относительным от SSH home или абсолютным и не может содержать ~.'
    }
    $script:Server = $target
    return $target
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

function ConvertFrom-DurableDeployResponse {
    param([Parameter(Mandatory)][string]$Output)

    $lines = @($Output -split "`r?`n")
    $metadataIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index].StartsWith('FH_DEPLOY_JOB_STATUS_V1|')) {
            $metadataIndex = $index
            break
        }
    }
    if ($metadataIndex -lt 0) {
        throw "Удалённый deploy runner вернул ответ без status marker:`n$Output"
    }

    $parts = $lines[$metadataIndex] -split '\|', 6
    if ($parts.Count -ne 6 -or $parts[3] -notmatch '^(?:-|[0-9]+)$' -or
        $parts[4] -notmatch '^[0-9]+$') {
        throw "Удалённый deploy runner вернул повреждённый status marker: $($lines[$metadataIndex])"
    }
    if ($metadataIndex -gt 0) {
        $lines[0..($metadataIndex - 1)] | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    }
    $logLines = if ($metadataIndex + 1 -lt $lines.Count) {
        @($lines[($metadataIndex + 1)..($lines.Count - 1)])
    } else {
        @()
    }

    [pscustomobject]@{
        RunId = $parts[1]
        Status = $parts[2]
        ExitCode = $parts[3]
        LineCount = [int]$parts[4]
        LogPath = $parts[5]
        LogLines = $logLines
    }
}

function Invoke-DurableDeployCommand {
    param(
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Revision,
        [Parameter(Mandatory)][string[]]$RunnerArguments
    )

    $quotedArguments = @($RunnerArguments | ForEach-Object {
        if ($_ -notmatch '^[A-Za-z0-9_./:\-]+$') {
            throw "Недопустимый аргумент durable deploy: $_"
        }
        "'$_'"
    })
    $remoteCommand = "set -o pipefail && cd '$RemoteProjectDirectory' && git cat-file -e '$($Revision)^{commit}' && git show '$($Revision):scripts/run-deploy-job.sh' | awk 'NR == 2 { compatible = (`$0 == `"# FILAMENTHUB_DEPLOY_JOB_PROTOCOL=1`") } END { exit !compatible }' && git show '$($Revision):scripts/run-deploy-job.sh' | PROJECT_DIR=`"`$PWD`" bash -s -- $($quotedArguments -join ' ')"
    $output = & ssh `
        -o 'ConnectTimeout=15' `
        -o 'ServerAliveInterval=15' `
        -o 'ServerAliveCountMax=4' `
        $Target $remoteCommand 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "SSH временно недоступен (код $LASTEXITCODE):`n$($output -join "`n")"
    }
    return ConvertFrom-DurableDeployResponse -Output ($output -join "`n")
}

function Invoke-DurableProductionDeploy {
    param([Parameter(Mandatory)][string]$Revision)

    Assert-Command ssh
    $target = Get-ServerTarget
    $runId = "deploy-$Revision"
    $startCommand = "set -o pipefail && cd '$RemoteProjectDirectory' && git fetch --no-recurse-submodules origin main && git cat-file -e '$($Revision)^{commit}' && git merge-base --is-ancestor '$Revision' origin/main"
    Invoke-Checked ssh @(
        '-o', 'ConnectTimeout=15',
        '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=4',
        $target, $startCommand
    )

    $response = $null
    $startDeadline = (Get-Date).AddSeconds($script:DeployReconnectGraceSeconds)
    do {
        try {
            $response = Invoke-DurableDeployCommand `
                -Target $target -Revision $Revision `
                -RunnerArguments @(
                    '--start', '--run-id', $runId, '--worker-revision', $Revision,
                    '--', '--revision', $Revision, '--yes'
                )
        } catch {
            if ((Get-Date) -ge $startDeadline) {
                throw "Не удалось запустить или обнаружить durable deploy за $script:DeployReconnectGraceSeconds секунд. Повторный запуск безопасно проверит ту же задачу. Последняя ошибка: $($_.Exception.Message)"
            }
            Write-Host 'SSH оборвался во время запуска; проверяю, успела ли задача стартовать на VDS...' -ForegroundColor Yellow
            Start-Sleep -Seconds $script:DeployPollIntervalSeconds
        }
    } while (-not $response)
    if ($response.Status -in @('failed', 'stale')) {
        if (-not (Confirm-Action "Предыдущая попытка $($Revision.Substring(0, 8)) завершилась неуспешно. Запустить заново?")) {
            throw "Повторный деплой отменён. Журнал на VDS: $($response.LogPath)"
        }
        $response = Invoke-DurableDeployCommand `
            -Target $target -Revision $Revision `
            -RunnerArguments @(
                '--start', '--run-id', $runId, '--worker-revision', $Revision,
                '--restart-failed', '--', '--revision', $Revision, '--yes'
            )
    }

    $fromLine = 0
    $startedAt = Get-Date
    $lastSuccessfulContact = Get-Date
    while ($true) {
        foreach ($line in @($response.LogLines)) {
            if (-not [string]::IsNullOrEmpty($line)) {
                Write-Host $line
            }
        }
        $fromLine = $response.LineCount

        switch ($response.Status) {
            'succeeded' {
                Write-Host "Production deployment завершён. Журнал: $($response.LogPath)" -ForegroundColor Green
                return
            }
            'failed' {
                throw "Production deployment завершился с кодом $($response.ExitCode). Журнал: $($response.LogPath)"
            }
            'stale' {
                throw "Production deployment потерял worker-процесс. Журнал: $($response.LogPath)"
            }
            'missing' {
                throw "Production deployment не создал durable job '$runId'."
            }
            'running' { }
            default { throw "Неизвестный статус durable deploy: $($response.Status)" }
        }

        if (((Get-Date) - $startedAt).TotalSeconds -ge $script:DeployJobTimeoutSeconds) {
            throw "Деплой всё ещё выполняется после $script:DeployJobTimeoutSeconds секунд. Повторный запуск консоли подключится к той же задаче. Журнал: $($response.LogPath)"
        }

        Start-Sleep -Seconds $script:DeployPollIntervalSeconds
        try {
            $response = Invoke-DurableDeployCommand `
                -Target $target -Revision $Revision `
                -RunnerArguments @('--status', '--run-id', $runId, '--from-line', "$fromLine")
            $lastSuccessfulContact = Get-Date
        } catch {
            $disconnectedFor = ((Get-Date) - $lastSuccessfulContact).TotalSeconds
            if ($disconnectedFor -ge $script:DeployReconnectGraceSeconds) {
                throw "SSH недоступен уже $([int]$disconnectedFor) секунд. Удалённая задача не остановлена; повторный запуск консоли подключится к ней. Последняя ошибка: $($_.Exception.Message)"
            }
            $response.LogLines = @()
            Write-Host "SSH-связь прервалась, задача на VDS продолжает работу; повторяю подключение..." -ForegroundColor Yellow
            Start-Sleep -Seconds $script:DeployPollIntervalSeconds
        }
    }
}

function Get-DeploymentCandidate {
    Assert-Command git

    $published = Get-VerifiedPublishedMain

    # Разворачивается ровно origin/main, поэтому состояние рабочего дерева и
    # локальной ветки на результат не влияет — о расхождении достаточно сказать.
    $dirty = Invoke-Checked git @('status', '--porcelain', '--untracked-files=normal') -Capture
    if ($dirty) {
        $changedCount = @($dirty -split "`r?`n").Count
        Write-Host "Локальных изменений в дереве: $changedCount — в деплой они не попадают." -ForegroundColor DarkGray
    }

    $head = Invoke-Checked git @('rev-parse', 'HEAD') -Capture
    if ($head -ne $published.Sha) {
        $ahead = Invoke-Checked git @('rev-list', '--count', "$($published.Sha)..HEAD") -Capture
        $behind = Invoke-Checked git @('rev-list', '--count', "HEAD..$($published.Sha)") -Capture
        Write-Host "Локально не опубликовано коммитов: $ahead, не получено: $behind — разворачивается origin/main." -ForegroundColor DarkGray
    }

    [pscustomobject]@{
        Sha = $published.Sha
        ShortSha = $published.Sha.Substring(0, 8)
        Repository = $published.Repository
        CiUrl = $published.CiUrl
    }
}

function Publish-RepositoryCommits {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][string]$Title
    )

    $git = @('-C', $Directory)
    Invoke-Checked git ($git + @('fetch', '--no-recurse-submodules', 'origin', 'main')) | Out-Null

    $branch = Invoke-Checked git ($git + @('branch', '--show-current')) -Capture
    if ($branch -ne 'main') {
        Write-Host "$Title`: публикуется только main, сейчас выбрана '$branch'." -ForegroundColor Yellow
        return
    }

    $candidateLines = Invoke-Checked git ($git + @(
        'log', '--first-parent', '--reverse', '--format=%H%x09%h%x09%s',
        'origin/main..HEAD'
    )) -Capture
    if (-not $candidateLines) {
        Write-Host "$Title`: публиковать нечего." -ForegroundColor DarkGray
        return
    }

    $candidates = @($candidateLines -split "`r?`n" | ForEach-Object {
        $parts = $_ -split "`t", 3
        if ($parts.Count -ne 3 -or $parts[0] -notmatch '^[0-9a-f]{40}$') {
            throw "Git вернул некорректное описание коммита: $_"
        }
        [pscustomobject]@{
            Sha = $parts[0]
            ShortSha = $parts[1]
            Subject = $parts[2]
        }
    })

    Write-Host ''
    Write-Host "$Title — неопубликованные точки main:" -ForegroundColor Cyan
    for ($index = 0; $index -lt $candidates.Count; $index++) {
        $candidate = $candidates[$index]
        Write-Host (' {0,3}. {1} {2}' -f ($index + 1), $candidate.ShortSha, $candidate.Subject)
    }
    Write-Host '   0. Отмена'

    $answer = (Read-Host 'Выбери коммит, до которого опубликовать main').Trim()
    $selection = 0
    if (-not [int]::TryParse($answer, [ref]$selection) -or
        $selection -lt 0 -or $selection -gt $candidates.Count) {
        throw "Нужно выбрать номер от 0 до $($candidates.Count)."
    }
    if ($selection -eq 0) {
        Write-Host 'Публикация отменена.' -ForegroundColor Yellow
        return
    }

    $selected = $candidates[$selection - 1]
    Invoke-Checked git ($git + @('merge-base', '--is-ancestor', 'origin/main', $selected.Sha)) | Out-Null
    Invoke-Checked git ($git + @('merge-base', '--is-ancestor', $selected.Sha, 'HEAD')) | Out-Null

    $publishLines = Invoke-Checked git ($git + @(
        'log', '--reverse', '--format=%h %s', "origin/main..$($selected.Sha)"
    )) -Capture
    $commitsToPublish = @($publishLines -split "`r?`n" | Where-Object { $_ })
    $remainingCount = [int](Invoke-Checked git ($git + @('rev-list', '--count', "$($selected.Sha)..HEAD")) -Capture)

    Write-Host ''
    Write-Host "$Title — в origin/main попадут:" -ForegroundColor Cyan
    $commitsToPublish | ForEach-Object { Write-Host "  $_" }
    if ($commitsToPublish.Count -gt 1) {
        Write-Host 'Git публикует выбранный коммит вместе со всеми его неопубликованными предками.' -ForegroundColor Yellow
    }
    if ($remainingCount -gt 0) {
        Write-Host "Более новых локальных коммитов останется: $remainingCount." -ForegroundColor DarkGray
    }

    if (-not (Confirm-Action "Опубликовать выбранные коммиты до $($selected.ShortSha)?")) {
        Write-Host 'Публикация отменена.' -ForegroundColor Yellow
        return
    }

    # Push exact SHA instead of the moving local main ref. A concurrent remote
    # update is rejected by Git's normal non-fast-forward protection.
    Invoke-Checked git ($git + @('push', 'origin', "$($selected.Sha):refs/heads/main"))
    $remoteState = Invoke-Checked git ($git + @('ls-remote', '--heads', 'origin', 'refs/heads/main')) -Capture
    $remoteSha = ($remoteState -split '\s+')[0]
    if ($remoteSha -ne $selected.Sha) {
        throw "После push origin/main указывает на $remoteSha вместо $($selected.Sha)."
    }

    Write-Host "$Title`: опубликовано до $($selected.ShortSha)." -ForegroundColor Green
}

function Publish-Commits {
    Assert-Command git

    Publish-RepositoryCommits -Directory $repositoryRoot -Title 'Код'

    # Документация живёт отдельным приватным репозиторием внутри рабочего дерева.
    # Спрашиваем о ней только когда там правда есть что публиковать.
    $documentation = Join-Path $repositoryRoot '.docs'
    if (Test-Path -LiteralPath (Join-Path $documentation '.git')) {
        Publish-RepositoryCommits -Directory $documentation -Title 'Документация'
    }

    Write-Host ''
    Write-Host 'GitHub CI начнёт прогон сам. Деплой не пропустит коммит, пока прогон не зелёный.' -ForegroundColor DarkGray
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
    $Candidate = Show-Preflight
    Write-Host ''
    if (-not (Confirm-Action "Задеплоить $($Candidate.ShortSha) в production?")) {
        Write-Host 'Деплой отменён.' -ForegroundColor Yellow
        return
    }

    Invoke-DurableProductionDeploy -Revision $Candidate.Sha
}

function Show-ProductionStatus {
    Invoke-RemoteWorker -Arguments @('--status') -UseDeployedRevision
}

function Start-ProductionBackup {
    if (-not (Confirm-Action 'Создать и проверить зашифрованную копию production-базы?')) {
        Write-Host 'Создание backup отменено.' -ForegroundColor Yellow
        return
    }
    Invoke-RemoteWorker -Arguments @('--backup-only') -UseDeployedRevision
}

function Start-BuildCacheCleanup {
    $retentionHours = $null
    while ($null -eq $retentionHours) {
        Write-Host ''
        Write-Host 'Какой build-cache удалить?' -ForegroundColor Cyan
        Write-Host '  1. Старше 7 дней  — освободит больше места'
        Write-Host '  2. Старше 14 дней — рекомендуется после обычного деплоя'
        Write-Host '  0. Отмена'

        $retentionHours = switch ((Read-Host 'Выбери срок').Trim()) {
            '1' { 168 }
            '2' { 336 }
            '0' {
                Write-Host 'Очистка build-cache отменена.' -ForegroundColor Yellow
                return
            }
            default {
                Write-Host 'Неизвестный срок.' -ForegroundColor Yellow
                $null
            }
        }
    }

    $retentionDays = [int]($retentionHours / 24)
    if (-not (Confirm-Action "Удалить build-cache Docker старше $retentionDays дней?")) {
        Write-Host 'Очистка build-cache отменена.' -ForegroundColor Yellow
        return
    }
    Invoke-RemoteWorker -Arguments @(
        '--prune-build-cache',
        '--build-cache-retention', "${retentionHours}h",
        '--yes'
    ) -UseDeployedRevision
}

function Show-PluginReleases {
    $repository = Get-RepositoryName
    $json = Invoke-Checked gh @(
        'release', 'list', '--repo', $repository, '--limit', '30',
        '--json', 'tagName,name,isDraft,isPrerelease,publishedAt'
    ) -Capture
    $releases = @($json | ConvertFrom-Json | Where-Object {
        $_.tagName -match '^(v|octoprint-v)\d+\.\d+\.\d+$'
    })
    if ($releases.Count -eq 0) {
        Write-Host 'GitHub Releases не найдены.' -ForegroundColor Yellow
    } else {
        Write-Host 'WeLizard/FilamentHub' -ForegroundColor Cyan
        $releases |
            Select-Object tagName, name, isDraft, isPrerelease, publishedAt, @{
                Name = 'url'
                Expression = { "https://github.com/$repository/releases/tag/$($_.tagName)" }
            } |
            Format-Table -AutoSize
    }

    $printFarmRepository = 'WeLizard/orca-plugins'
    $printFarmJson = Invoke-Checked gh @(
        'release', 'list', '--repo', $printFarmRepository, '--limit', '20',
        '--json', 'tagName,name,isDraft,isPrerelease,publishedAt'
    ) -Capture
    Write-Host 'WeLizard/orca-plugins (Print Farm)' -ForegroundColor Cyan
    @($printFarmJson | ConvertFrom-Json) |
        Select-Object tagName, name, isDraft, isPrerelease, publishedAt, @{
            Name = 'url'
            Expression = { "https://github.com/$printFarmRepository/releases/tag/$($_.tagName)" }
        } |
        Format-Table -AutoSize
}

function Get-PluginReleaseAssets {
    $endpoint = "$($PublicBaseUrl.TrimEnd('/'))/api/v1/downloads/plugins"
    $response = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 20
    $packages = @($response.packages)
    if ($packages.Count -eq 0) {
        throw "Публичный API не вернул пакеты: $endpoint"
    }
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $destination = Join-Path ([IO.Path]::GetTempPath()) "FilamentHub\releases\$timestamp"
    New-Item -ItemType Directory -Path $destination -Force | Out-Null

    foreach ($package in $packages) {
        if ([string]$package.checksum -notmatch '^[0-9a-fA-F]{64}$') {
            throw "У $($package.plugin) отсутствует корректный SHA-256."
        }
        $target = Join-Path $destination ([string]$package.filename)
        Invoke-WebRequest -Uri ([string]$package.download_url) -OutFile $target -TimeoutSec 60
        $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($actual -ne [string]$package.checksum) {
            throw "Не совпала контрольная сумма файла $($package.filename)."
        }
    }
    Write-Host "Проверено пакетов: $($packages.Count). Папка: $destination" -ForegroundColor Green
}

function Test-DownloadPageRelease {
    $endpoint = "$($PublicBaseUrl.TrimEnd('/'))/api/v1/downloads/plugins"
    try {
        $response = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 20
    } catch {
        throw "Не удалось прочитать публичный API плагинов $endpoint`: $($_.Exception.Message)"
    }

    $packages = @($response.packages)
    $expectedPlugins = @('orcaslicer', 'octoprint', 'print_farm')
    foreach ($plugin in $expectedPlugins) {
        $matches = @($packages | Where-Object { $_.plugin -eq $plugin })
        if ($matches.Count -ne 1) {
            Write-Host "Страница Download не готова: пакет '$plugin' должен присутствовать ровно один раз." -ForegroundColor Yellow
            return $false
        }

        $package = $matches[0]
        if ([string]::IsNullOrWhiteSpace([string]$package.filename) -or
            [string]$package.checksum -notmatch '^[0-9a-fA-F]{64}$' -or
            [string]::IsNullOrWhiteSpace([string]$package.download_url)) {
            Write-Host "Страница Download не готова: у '$plugin' неполные метаданные или некорректный SHA-256." -ForegroundColor Yellow
            return $false
        }

        try {
            $downloadUri = [Uri][string]$package.download_url
            $publicUri = [Uri]$PublicBaseUrl
            if ($downloadUri.Scheme -ne $publicUri.Scheme -or $downloadUri.Authority -ne $publicUri.Authority) {
                Write-Host "Страница Download не готова: '$plugin' ссылается не на наш публичный сервер." -ForegroundColor Yellow
                return $false
            }

            # GET через наш endpoint заставляет backend получить файл из релиза,
            # проверить его checksum и только после этого начать отдачу. Range
            # уменьшает трафик, если HTTP-слой его поддерживает.
            $downloadResponse = Invoke-WebRequest -Uri $downloadUri -Method Get -Headers @{ Range = 'bytes=0-0' } -TimeoutSec 60
            if ([int]$downloadResponse.StatusCode -notin @(200, 206)) {
                Write-Host "Страница Download не готова: '$($package.filename)' вернул HTTP $($downloadResponse.StatusCode)." -ForegroundColor Yellow
                return $false
            }
        } catch {
            Write-Host "Страница Download не готова: '$($package.filename)' не скачивается через FilamentHub: $($_.Exception.Message)" -ForegroundColor Yellow
            return $false
        }
    }

    $filenames = @($packages | Where-Object { $_.plugin -in $expectedPlugins } | ForEach-Object { $_.filename })
    Write-Host "Страница Download раздаёт все три пакета ($($filenames -join ', '))." -ForegroundColor Green
    return $true
}

function Invoke-PluginReleasePreparation {
    param([switch]$ChooseComponent)

    $components = @('all')
    if ($ChooseComponent) {
        Write-Host '  1. FilamentHub for OrcaSlicer'
        Write-Host '  2. FilamentHub Bridge for OctoPrint'
        Write-Host '  3. Print Farm'
        $components = switch ((Read-Host 'Выбери компонент').Trim()) {
            '1' { @('orcaslicer') }
            '2' { @('octoprint') }
            '3' { @('print-farm') }
            default { throw 'Неизвестный компонент.' }
        }
    }
    $scriptPath = Join-Path $PSScriptRoot 'publish-plugin-releases.ps1'
    & $scriptPath -Component $components -DryRun
    if (-not $?) {
        throw 'Предварительная проверка независимых релизов завершилась с ошибкой.'
    }
    if (-not (Confirm-Action 'Опубликовать перечисленные независимые релизы?')) {
        throw 'Публикация релиза отменена.'
    }

    & $scriptPath -Component $components -HideReleaseNotes
    if (-not $?) {
        throw 'Скрипт публикации плагинов завершился с ошибкой.'
    }
    if (-not (Test-DownloadPageRelease)) {
        Write-Host 'GitHub Releases готовы, но Download ещё не обновился. Повтори пункт 9 после деплоя backend или истечения 15-минутного кеша.' -ForegroundColor Yellow
    }
}

function Update-CatalogSource {
    Assert-Command python

    $refresher = Join-Path $repositoryRoot 'scripts\refresh_orca_catalog_source.py'
    $bundle = Join-Path $repositoryRoot 'backend\data\catalog_sources\orca\bundle.zip'

    Write-Host ''
    Write-Host 'Читаю профили OrcaSlicer и сравниваю с текущим источником...' -ForegroundColor Cyan
    Invoke-Checked python @($refresher)

    if (-not (Confirm-Action 'Обновить bundle.zip в рабочем дереве?')) {
        Write-Host 'Источник каталога оставлен без изменений.' -ForegroundColor Yellow
        return
    }

    Invoke-Checked python @($refresher, '--write')

    Write-Host ''
    Write-Host "Готовый архив: $bundle" -ForegroundColor Green
    Write-Host ''
    Write-Host 'ПОЛОЖИ АРХИВ НА СЕРВЕР — сам он туда не поедет:' -ForegroundColor Yellow
    Write-Host "  1) залей файл в $RemoteProjectDirectory/backend/data/catalog_sources/orca/bundle.zip"
    Write-Host '  2) задеплой пунктом 3: архив попадает в образ только при пересборке'
    Write-Host '  3) в админке нажми импорт источника каталога'
    Write-Host ''
    Write-Host 'Архив не версионируется, поэтому чистоту рабочего дерева на сервере он не ломает.'
}

function Invoke-LocalDevelopmentCommand {
    param([Parameter(Mandatory)][ValidateSet('up', 'down', 'logs', 'ps')][string]$Command)

    if ($Command -eq 'down' -and
        -not (Confirm-Action 'Остановить все контейнеры local dev?')) {
        Write-Host 'Остановка local dev отменена.' -ForegroundColor Yellow
        return
    }

    Invoke-OwnerScript -Name 'start.ps1' -Arguments @($Command)
}

function Show-LocalDevelopmentMenu {
    while ($true) {
        Write-Host ''
        Write-Host 'Local dev (Docker)' -ForegroundColor Cyan
        Write-Host '  Работает только с docker-compose.dev.yml; production не затрагивается.' -ForegroundColor DarkGray
        Write-MenuOption '1' 'Показать состояние' 'Какие dev-контейнеры запущены и какие порты они используют.'
        Write-MenuOption '2' 'Собрать и запустить' 'Поднимает frontend, backend, PostgreSQL и Redis в фоне.'
        Write-MenuOption '3' 'Показать живые логи' 'Показывает вывод всех dev-сервисов; Ctrl+C останавливает просмотр.'
        Write-MenuOption '4' 'Остановить' 'Останавливает dev-контейнеры, но сохраняет базу и Docker volumes.'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Invoke-LocalDevelopmentCommand -Command 'ps' }
                '2' { Invoke-LocalDevelopmentCommand -Command 'up' }
                '3' { Invoke-LocalDevelopmentCommand -Command 'logs' }
                '4' { Invoke-LocalDevelopmentCommand -Command 'down' }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

function Show-GitHubMenu {
    while ($true) {
        Write-Host ''
        Write-Host 'GitHub' -ForegroundColor Cyan
        Write-Host '  1. Выборочно опубликовать коммиты на GitHub'
        Write-Host '     Покажет все неопубликованные коммиты и предков выбранного SHA.' -ForegroundColor DarkGray
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Publish-Commits }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

function Show-ProductionMenu {
    while ($true) {
        Write-Host ''
        Write-Host 'Production (VDS)' -ForegroundColor Cyan
        Write-Host "  Сервер: $script:Server" -ForegroundColor DarkGray
        Write-Host '  1. Проверить готовность к деплою (точный SHA + GitHub CI)'
        Write-Host '  2. Задеплоить production'
        Write-Host '  3. Проверить состояние production'
        Write-Host '  4. Создать зашифрованный backup production-базы'
        Write-Host '  5. Очистить устаревший Docker build-cache на VDS'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Show-Preflight | Out-Null }
                '2' { Start-ProductionDeploy }
                '3' { Show-ProductionStatus }
                '4' { Start-ProductionBackup }
                '5' { Start-BuildCacheCleanup }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

function Show-PluginMenu {
    while ($true) {
        Write-Host ''
        Write-Host 'Плагины и их релизы' -ForegroundColor Cyan
        Write-Host '  FilamentHub, OctoPrint Bridge и Print Farm выпускаются независимо.' -ForegroundColor DarkGray
        Write-Host '  1. Показать независимые GitHub Releases плагинов'
        Write-Host '  2. Скачать с сайта и проверить все три пакета'
        Write-Host '  3. Проверить все три плагина на странице Download'
        Write-Host '  4. Выпустить все изменившиеся плагины отдельными releases'
        Write-Host '  5. Выпустить один выбранный плагин отдельным release'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Show-PluginReleases }
                '2' { Get-PluginReleaseAssets }
                '3' {
                    if (-not (Test-DownloadPageRelease)) {
                        throw 'Публичная страница Download пока не прошла проверку.'
                    }
                }
                '4' { Invoke-PluginReleasePreparation }
                '5' { Invoke-PluginReleasePreparation -ChooseComponent }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

function Show-OrcaToolsMenu {
    while ($true) {
        Write-Host ''
        Write-Host 'OrcaSlicer' -ForegroundColor Cyan
        Write-Host '  1. Обновить источник каталога принтеров'
        Write-Host '  2. Проверить инструменты для сборки OrcaSlicer'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Update-CatalogSource }
                '2' { Invoke-OwnerScript -Name 'check_tools.ps1' }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

function Show-Menu {
    while ($true) {
        Write-Host ''
        Write-Host 'Консоль владельца FilamentHub' -ForegroundColor Cyan
        Write-MenuOption '1' 'Local dev (Docker)' 'Статус, запуск, логи и остановка dev-стека.'
        Write-MenuOption '2' 'GitHub' 'Выборочная публикация коммитов main.'
        Write-MenuOption '3' 'Production (VDS)' 'Preflight, deploy, status, backup и очистка build-cache.'
        Write-MenuOption '4' 'Плагины и их релизы' 'GitHub Releases, wheels, Download и выпуск каждого плагина.'
        Write-MenuOption '5' 'OrcaSlicer' 'Источник каталога и проверка инструментов сборки.'
        Write-Host '  0. Выход'

        try {
            switch ((Read-Host 'Выбери раздел').Trim()) {
                '1' { Show-LocalDevelopmentMenu }
                '2' { Show-GitHubMenu }
                '3' { Show-ProductionMenu }
                '4' { Show-PluginMenu }
                '5' { Show-OrcaToolsMenu }
                '0' { return }
                default { Write-Host 'Неизвестный пункт меню.' -ForegroundColor Yellow }
            }
        } catch {
            Write-OperationError $_
        }
    }
}

Assert-Command git
$repositoryRoot = Invoke-Checked git @('rev-parse', '--show-toplevel') -Capture
Set-Location -LiteralPath $repositoryRoot

switch ($Action) {
    'Menu' { Show-Menu }
    'Publish' { Publish-Commits }
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
    'PublishRelease' { Invoke-PluginReleasePreparation }
    'UpdateCatalogSource' { Update-CatalogSource }
}
