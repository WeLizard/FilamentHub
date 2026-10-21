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
    [ValidateSet('Menu', 'Release', 'Publish', 'PublishPluginCommits', 'Preflight', 'Deploy', 'Status', 'Backup', 'PruneBuildCache', 'ListReleases', 'DownloadRelease', 'CheckDownloadPage', 'PrepareRelease', 'PublishRelease', 'UpdateCatalogSource', 'PublishCatalogSource')]
    [string]$Action = 'Menu',

    # What -Action Release releases; without it the owner picks from a menu.
    [Parameter()]
    [ValidateSet('site', 'orcaslicer', 'octoprint', 'print-farm')]
    [string[]]$Item = @(),

    [Parameter()]
    [switch]$CheckOnly,

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

function Stop-WithFix {
    param(
        [Parameter(Mandatory)][string]$Problem,
        [Parameter(Mandatory)][string]$Fix
    )

    throw "$Problem`nИсправить: $Fix"
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
        Stop-WithFix `
            -Problem "Проверки GitHub для последнего коммита ($($remoteHead.Substring(0, 8))) ещё не запускались." `
            -Fix 'подожди пару минут и повтори: .\scripts\release.ps1'
    }
    if ($run.status -ne 'completed') {
        Stop-WithFix `
            -Problem "$script:WaitingPrefix проверки GitHub для $($remoteHead.Substring(0, 8)) ещё идут: $($run.url)" `
            -Fix 'дождись окончания и повтори: .\scripts\release.ps1'
    }
    if ($run.conclusion -ne 'success') {
        Stop-WithFix `
            -Problem "Проверки GitHub для $($remoteHead.Substring(0, 8)) красные ($($run.conclusion)): $($run.url)" `
            -Fix 'передай агенту ссылку выше: нужно починить проверки'
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
    param(
        [Parameter(Mandatory)][string]$Revision,
        [switch]$RebuildAll,
        # Decided by the owner before the release starts, so the run itself
        # never stops to ask.
        [switch]$RestartFailed
    )

    Assert-Command ssh
    $target = Get-ServerTarget
    $runId = "deploy-$Revision"
    $workerArguments = @('--revision', $Revision, '--yes')
    if ($RebuildAll) {
        # A finished job with the same id is reported, not rerun, so a forced rebuild gets its own id.
        $runId = "deploy-$Revision-rebuild-$(Get-Date -Format 'yyyyMMddHHmm')"
        $workerArguments += '--rebuild-all'
    }
    $startCommand = "set -o pipefail && cd '$RemoteProjectDirectory' && git fetch --no-recurse-submodules origin main && git cat-file -e '$($Revision)^{commit}' && git merge-base --is-ancestor '$Revision' origin/main"

    $response = $null
    $startDeadline = (Get-Date).AddSeconds($script:DeployReconnectGraceSeconds)
    do {
        try {
            Invoke-Checked ssh @(
                '-o', 'ConnectTimeout=15',
                '-o', 'ServerAliveInterval=15',
                '-o', 'ServerAliveCountMax=4',
                $target, $startCommand
            )
            $response = Invoke-DurableDeployCommand `
                -Target $target -Revision $Revision `
                -RunnerArguments (@(
                    '--start', '--run-id', $runId, '--worker-revision', $Revision,
                    '--'
                ) + $workerArguments)
        } catch {
            if ((Get-Date) -ge $startDeadline) {
                throw "Не удалось запустить или обнаружить durable deploy за $script:DeployReconnectGraceSeconds секунд. Повторный запуск безопасно проверит ту же задачу. Последняя ошибка: $($_.Exception.Message)"
            }
            Write-Host 'SSH оборвался во время подготовки или запуска; безопасно повторяю проверку VDS...' -ForegroundColor Yellow
            Start-Sleep -Seconds $script:DeployPollIntervalSeconds
        }
    } while (-not $response)
    if ($response.Status -in @('failed', 'stale')) {
        if (-not $RestartFailed) {
            Stop-WithFix `
                -Problem "Прошлая выкладка $($Revision.Substring(0, 8)) не удалась (журнал на сервере: $($response.LogPath))." `
                -Fix '.\scripts\release.ps1 -Item site   (скрипт спросит, запустить ли её заново)'
        }
        $response = Invoke-DurableDeployCommand `
            -Target $target -Revision $Revision `
            -RunnerArguments (@(
                '--start', '--run-id', $runId, '--worker-revision', $Revision,
                '--restart-failed', '--'
            ) + $workerArguments)
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

function Assert-PublicationPaths {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][string]$BaseRevision,
        [Parameter(Mandatory)][string]$TargetRevision,
        [Parameter(Mandatory)][string[]]$AllowedPaths
    )

    $git = @('-C', $Directory)
    $commits = Invoke-Checked git ($git + @(
        'rev-list', '--reverse', "$BaseRevision..$TargetRevision"
    )) -Capture
    $violations = [System.Collections.Generic.List[string]]::new()
    foreach ($commit in @($commits -split "`r?`n" | Where-Object { $_ })) {
        # Inspect history, including every merge parent and reverted changes.
        # Disabling rename detection preserves both sides of a moved path.
        $changed = Invoke-Checked git ($git + @(
            'diff-tree', '--root', '-m', '-r', '--no-renames', '--no-commit-id',
            '--name-only', '-z', $commit
        )) -Capture
        $outside = @($changed -split "`0" | Where-Object { $_ } | Where-Object {
            $path = $_
            $allowed = $false
            foreach ($entry in $AllowedPaths) {
                if ($path.Equals($entry, [StringComparison]::Ordinal) -or
                    ($entry.EndsWith('/') -and $path.StartsWith($entry, [StringComparison]::Ordinal))) {
                    $allowed = $true
                    break
                }
            }
            -not $allowed
        } | Sort-Object -Unique)
        if ($outside.Count -gt 0) {
            $summary = Invoke-Checked git ($git + @('show', '-s', '--format=%h %s', $commit)) -Capture
            $violations.Add("  $summary")
            foreach ($path in $outside) {
                $violations.Add("    $path")
            }
        }
    }
    if ($violations.Count -gt 0) {
        throw ("Публикация плагинов остановлена: в историю выбранного коммита входят посторонние изменения:`n" +
            ($violations -join "`n") + "`nВыбери более ранний готовый коммит или подготовь изменения плагина отдельно от опубликованной origin/main. " +
            'Для намеренной публикации общей истории используй раздел GitHub.')
    }
}

function Publish-RepositoryCommits {
    param(
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][string]$Title,
        [string[]]$AllowedPaths = @()
    )

    $git = @('-C', $Directory)
    Invoke-Checked git ($git + @('fetch', '--no-recurse-submodules', 'origin', 'main')) | Out-Null
    $baseRevision = Invoke-Checked git ($git + @('rev-parse', 'origin/main')) -Capture

    $branch = Invoke-Checked git ($git + @('branch', '--show-current')) -Capture
    if ($branch -ne 'main') {
        Write-Host "$Title`: публикуется только main, сейчас выбрана '$branch'." -ForegroundColor Yellow
        return
    }

    $candidateLines = Invoke-Checked git ($git + @(
        'log', '--first-parent', '--reverse', '--format=%H%x09%h%x09%s',
        "$baseRevision..HEAD"
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
    Invoke-Checked git ($git + @('merge-base', '--is-ancestor', $baseRevision, $selected.Sha)) | Out-Null
    Invoke-Checked git ($git + @('merge-base', '--is-ancestor', $selected.Sha, 'HEAD')) | Out-Null

    if ($AllowedPaths.Count -gt 0) {
        Assert-PublicationPaths -Directory $Directory -BaseRevision $baseRevision `
            -TargetRevision $selected.Sha -AllowedPaths $AllowedPaths
    }

    $publishLines = Invoke-Checked git ($git + @(
        'log', '--reverse', '--format=%h %s', "$baseRevision..$($selected.Sha)"
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

function Publish-PluginCommits {
    Assert-Command git

    Write-Host ''
    Write-Host 'Отправка подготовленных коммитов плагинов' -ForegroundColor Cyan
    Write-Host 'Сначала будет обновлено состояние origin/main, затем ты выберешь готовый коммит.' -ForegroundColor DarkGray
    Write-Host 'Коммиты с изменениями вне плагинов и их релизных файлов будут заблокированы.' -ForegroundColor DarkGray
    Write-Host 'Релиз, тег и production этим действием не создаются.' -ForegroundColor DarkGray
    Publish-RepositoryCommits -Directory $repositoryRoot -Title 'FilamentHub и OctoPrint Bridge' -AllowedPaths @(
        'orca-plugin/', 'octoprint-plugin/', 'scripts/render_plugin_release_notes.py',
        '.github/workflows/release-filamenthub.yml', '.github/workflows/release-octoprint.yml',
        '.github/workflows/publish-orcacloud.yml'
    )

    $printFarmCandidate = Join-Path (Split-Path $repositoryRoot -Parent) 'orca-plugins'
    if (Test-Path -LiteralPath (Join-Path $printFarmCandidate '.git')) {
        Publish-RepositoryCommits -Directory $printFarmCandidate -Title 'Print Farm' -AllowedPaths @(
            'plugins/printers/', 'plugins/print-farm/',
            '.github/workflows/release-printers.yml', '.github/workflows/publish-orcacloud.yml'
        )
    } else {
        Write-Host 'Print Farm: локальный репозиторий рядом с FilamentHub не найден; этот шаг пропущен.' -ForegroundColor DarkGray
    }

    Write-Host ''
    Write-Host 'Дальше, когда проверки GitHub станут зелёными: .\scripts\release.ps1' -ForegroundColor DarkGray
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
    $cleanupMode = $null
    while ($null -eq $cleanupMode) {
        Write-Host ''
        Write-Host 'Какой build-cache удалить?' -ForegroundColor Cyan
        Write-Host '  1. Старше 7 дней  — освободит больше места'
        Write-Host '  2. Старше 14 дней — рекомендуется после обычного деплоя'
        Write-Host '  3. Старше 1 часа — срочная очистка перед деплоем'
        Write-Host '  0. Отмена'

        $cleanupMode = switch ((Read-Host 'Выбери срок').Trim()) {
            '1' { '168h' }
            '2' { '336h' }
            '3' { '1h' }
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

    $retentionLabel = switch ($cleanupMode) {
        '1h' { '1 часа' }
        '168h' { '7 дней' }
        '336h' { '14 дней' }
        default { throw "Неизвестный срок очистки: $cleanupMode" }
    }
    if (-not (Confirm-Action "Удалить build-cache Docker старше ${retentionLabel}?")) {
        Write-Host 'Очистка build-cache отменена.' -ForegroundColor Yellow
        return
    }
    $workerArguments = @(
        '--prune-build-cache',
        '--build-cache-retention', $cleanupMode,
        '--yes'
    )
    Invoke-RemoteWorker -Arguments $workerArguments -UseDeployedRevision
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
    param([string[]]$Plugins = @('orcaslicer', 'octoprint', 'print_farm'))

    $endpoint = "$($PublicBaseUrl.TrimEnd('/'))/api/v1/downloads/plugins"
    try {
        $response = Invoke-RestMethod -Uri $endpoint -Method Get -TimeoutSec 20
    } catch {
        throw "Не удалось прочитать публичный API плагинов $endpoint`: $($_.Exception.Message)"
    }

    $packages = @($response.packages)
    $expectedPlugins = @($Plugins)
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
    Write-Host "Страница Download раздаёт: $($filenames -join ', ')." -ForegroundColor Green
    return $true
}

function Get-ReleaseCatalogue {
    return @(
        [pscustomobject]@{ Id = 'site'; Key = '1'; Name = 'Сайт'; DownloadId = $null }
        [pscustomobject]@{ Id = 'orcaslicer'; Key = '2'; Name = 'FilamentHub для OrcaSlicer'; DownloadId = 'orcaslicer' }
        [pscustomobject]@{ Id = 'octoprint'; Key = '3'; Name = 'Мост для OctoPrint'; DownloadId = 'octoprint' }
        [pscustomobject]@{ Id = 'print-farm'; Key = '4'; Name = 'Print Farm'; DownloadId = 'print_farm' }
    )
}

function Read-ReleaseSelection {
    $catalogue = Get-ReleaseCatalogue
    while ($true) {
        Write-Host ''
        Write-Host 'Что выпускаем?' -ForegroundColor Cyan
        foreach ($entry in $catalogue) {
            Write-Host "  $($entry.Key). $($entry.Name)"
        }
        Write-Host '  0. Отмена'
        Write-Host '  Можно несколько через запятую, например: 2 или 1,2' -ForegroundColor DarkGray
        $answer = (Read-Host 'Выбери').Trim()
        if ($answer -in @('', '0')) {
            return @()
        }
        $keys = @($answer -split '[,;\s]+' | Where-Object { $_ })
        $unknown = @($keys | Where-Object { $_ -notin @($catalogue.Key) })
        if ($unknown.Count -eq 0) {
            return @($catalogue | Where-Object { $_.Key -in $keys } | ForEach-Object Id)
        }
        Write-Host "Не понимаю: $($unknown -join ', '). Введи номера из списка." -ForegroundColor Yellow
    }
}

function Set-ReleaseState {
    param(
        [Parameter(Mandatory)]$State,
        [Parameter(Mandatory)][ValidateSet('READY', 'CURRENT', 'ERROR', 'SKIPPED', 'DONE')][string]$Status,
        [string]$Detail = '',
        [string]$Fix = ''
    )

    $State.Status = $Status
    $State.Detail = $Detail
    $State.Fix = $Fix
}

function Set-ReleaseFailure {
    param(
        [Parameter(Mandatory)]$State,
        [Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    $lines = @("$($ErrorRecord.Exception.Message)" -split "`r?`n" |
        ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $problem = if ($lines.Count) { $lines[0] } else { 'неизвестная ошибка' }
    $fix = @($lines | Where-Object { $_.StartsWith('Исправить:') } | Select-Object -First 1)
    Set-ReleaseState -State $State -Status ERROR -Detail $problem `
        -Fix $(if ($fix.Count) { $fix[0].Substring('Исправить:'.Length).Trim() } else { '' })
    Write-Host "$($State.Name): СТОП — $problem" -ForegroundColor Red
}

function Show-ReleaseSummary {
    param(
        [Parameter(Mandatory)][object[]]$States,
        [Parameter(Mandatory)][string]$Title
    )

    Write-Host ''
    Write-Host $Title -ForegroundColor Cyan
    foreach ($state in $States) {
        $label, $colour = switch ($state.Status) {
            'READY' { 'можно выпускать', 'Green' }
            'CURRENT' { 'уже актуально', 'DarkGray' }
            'DONE' { 'готово', 'Green' }
            'SKIPPED' { 'не выпускается', 'Yellow' }
            default { 'СТОП', 'Red' }
        }
        Write-Host "  $($state.Name): $label — $($state.Detail)" -ForegroundColor $colour
        if ($state.Fix) {
            Write-Host "      Исправить: $($state.Fix)" -ForegroundColor Yellow
        }
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-OwnerKey {
    if ([Console]::IsInputRedirected) {
        throw 'Для подтверждения нужен интерактивный терминал.'
    }
    return [Console]::ReadKey($true).KeyChar
}

function Confirm-OwnerTestedPackage {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Version,
        [Parameter(Mandatory)][string]$WheelPath,
        [Parameter(Mandatory)][string]$Sha256
    )

    Write-Host ''
    Write-Host "$Name $Version — пакет для выпуска:" -ForegroundColor Cyan
    Write-Host $WheelPath
    Write-Host "SHA-256 проверен автоматически: $Sha256" -ForegroundColor DarkGray
    Write-Host 'Этот пакет проверен в приложении и принят? Y / Д — да (в любой раскладке); любая другая клавиша — пропустить.'
    # Y and Д are meant as keys, not letters: in the other layout the same keys give Н and L.
    return (Read-OwnerKey) -cin @('y', 'Y', 'н', 'Н', 'д', 'Д', 'l', 'L')
}

function Get-SitePluginApiLevelAt {
    param([Parameter(Mandatory)][string]$Revision)

    $config = Invoke-Checked git @('show', "${Revision}:backend/app/core/config.py") -Capture
    # Revisions from before the level existed serve level 1.
    if ($config -notmatch '(?m)^PLUGIN_API_LEVEL\s*=\s*(?<level>\d+)\s*$') {
        return 1
    }
    return [int]$Matches.level
}

function Get-SiteReleasePlan {
    param([switch]$RebuildAll)

    $candidate = Get-DeploymentCandidate
    # The worker's dry run checks on the server what the real deploy checks
    # first: clean checkout, main branch, fast-forward and certificates.
    try {
        Invoke-RemoteWorker -Arguments @('--revision', $candidate.Sha, '--dry-run') -WorkerRevision $candidate.Sha
    } catch {
        Stop-WithFix `
            -Problem 'Сервер не готов принять выкладку или недоступен (причина в строках выше).' `
            -Fix '.\scripts\deploy-server.ps1 -Action Status'
    }

    $previousAttemptFailed = $false
    $alreadyDeployed = $false
    if (-not $RebuildAll) {
        $job = Invoke-DurableDeployCommand -Target (Get-ServerTarget) -Revision $candidate.Sha `
            -RunnerArguments @('--status', '--run-id', "deploy-$($candidate.Sha)", '--from-line', '0')
        $previousAttemptFailed = $job.Status -in @('failed', 'stale')
        $alreadyDeployed = $job.Status -eq 'succeeded'
    }

    [pscustomobject]@{
        Sha = $candidate.Sha
        ShortSha = $candidate.ShortSha
        CiUrl = $candidate.CiUrl
        PluginApiLevel = Get-SitePluginApiLevelAt -Revision $candidate.Sha
        PreviousAttemptFailed = $previousAttemptFailed
        AlreadyDeployed = $alreadyDeployed
    }
}

function Invoke-PluginReleaseScript {
    param(
        [Parameter(Mandatory)][string]$Id,
        [hashtable]$Arguments = @{}
    )

    $scriptPath = Join-Path $PSScriptRoot 'publish-plugin-releases.ps1'
    $output = @(& $scriptPath -Component $Id -EmitComponentResult @Arguments)
    $results = @($output | Where-Object { $_ -and $_.PSObject.Properties['FilamentHubPluginReleaseResult'] })
    @($output | Where-Object { -not ($_ -and $_.PSObject.Properties['FilamentHubPluginReleaseResult']) }) | Out-Host
    if ($results.Count -ne 1) {
        throw "Скрипт плагина '$Id' вернул результатов: $($results.Count) вместо одного."
    }
    return $results[0]
}

function Invoke-Release {
    param(
        [string[]]$Items = @(),
        [switch]$CheckOnly,
        [switch]$RebuildAll
    )

    $catalogue = Get-ReleaseCatalogue
    if ($Items.Count -eq 0) {
        $Items = @(Read-ReleaseSelection)
    }
    if ($Items.Count -eq 0) {
        Write-Host 'Выпуск отменён.' -ForegroundColor Yellow
        return
    }
    $states = @(foreach ($entry in $catalogue) {
        if ($entry.Id -in $Items) {
            [pscustomobject]@{
                Id = $entry.Id; Name = $entry.Name; DownloadId = $entry.DownloadId
                Status = 'READY'; Detail = ''; Fix = ''; Plan = $null
            }
        }
    })
    $siteState = @($states | Where-Object Id -eq 'site') | Select-Object -First 1
    $pluginStates = @($states | Where-Object Id -ne 'site')

    Write-Host ''
    Write-Host 'Проверяю только выбранное. Пока ничего не меняется и ни о чём не спрашиваю.' -ForegroundColor Cyan
    $Candidate = $null
    if ($siteState) {
        Write-Host "`n— $($siteState.Name): проверка" -ForegroundColor Cyan
        try {
            $Candidate = Get-SiteReleasePlan -RebuildAll:$RebuildAll
            $siteState.Plan = $Candidate
            if ($Candidate.AlreadyDeployed) {
                Set-ReleaseState -State $siteState -Status CURRENT -Detail "коммит $($Candidate.ShortSha) уже выкачен"
            } else {
                $detail = "коммит $($Candidate.ShortSha), проверки GitHub зелёные, сервер готов"
                if ($Candidate.PreviousAttemptFailed) {
                    $detail += '; прошлая попытка выкладки не удалась'
                }
                Set-ReleaseState -State $siteState -Status READY -Detail $detail
            }
        } catch {
            Set-ReleaseFailure -State $siteState -ErrorRecord $_
        }
    }
    foreach ($state in $pluginStates) {
        Write-Host "`n— $($state.Name): проверка" -ForegroundColor Cyan
        $arguments = @{ DryRun = $true }
        if ($siteState -and $siteState.Status -eq 'READY') {
            $arguments.PlannedSiteApiLevel = $Candidate.PluginApiLevel
        }
        try {
            $result = Invoke-PluginReleaseScript -Id $state.Id -Arguments $arguments
            $state.Plan = $result
            $status = if ($result.Status -eq 'READY') { 'READY' } else { 'CURRENT' }
            Set-ReleaseState -State $state -Status $status -Detail $result.Detail
        } catch {
            Set-ReleaseFailure -State $state -ErrorRecord $_
        }
    }

    Show-ReleaseSummary -States $states -Title 'Итог проверки:'
    $ready = @($states | Where-Object Status -eq 'READY')
    if ($ready.Count -eq 0) {
        Write-Host 'Выпускать нечего.' -ForegroundColor Yellow
        return
    }
    if ($CheckOnly) {
        Write-Host "Это была только проверка, ничего не выпущено. Выпустить: .\scripts\release.ps1 -Item $(@($ready.Id) -join ',')" -ForegroundColor Green
        return
    }

    Write-Host ''
    Write-Host 'Вопросы перед выпуском. После них скрипт работает сам и больше ничего не спрашивает.' -ForegroundColor Cyan
    if ($siteState -and $siteState.Status -eq 'READY') {
        $question = "Выкатить сайт (коммит $($Candidate.ShortSha))"
        if ($RebuildAll) { $question += ' с полной пересборкой' }
        if ($Candidate.PreviousAttemptFailed) { $question += '? Прошлая попытка не удалась, она запустится заново. Продолжить' }
        if (-not (Confirm-Action "$($question)?")) {
            Set-ReleaseState -State $siteState -Status SKIPPED -Detail 'ты решил не выкатывать'
        }
    }
    $siteGoes = $siteState -and $siteState.Status -eq 'READY'
    foreach ($state in @($pluginStates | Where-Object Status -eq 'READY')) {
        $plan = $state.Plan
        if ($plan.NeedsSiteDeploy -and -not $siteGoes) {
            Set-ReleaseState -State $state -Status SKIPPED -Detail 'плагину нужен сайт новее, а сайт сейчас не выкатывается' `
                -Fix ".\scripts\release.ps1 -Item site,$($state.Id)"
            continue
        }
        try {
            if ((Get-FileSha256 -Path $plan.CandidateWheel) -ne $plan.Sha256) {
                Stop-WithFix -Problem 'пакет изменился после проверки.' -Fix ".\scripts\release.ps1 -Item $($state.Id)"
            }
            if (-not (Confirm-OwnerTestedPackage -Name $state.Name -Version $plan.Version `
                    -WheelPath $plan.CandidateWheel -Sha256 $plan.Sha256)) {
                Set-ReleaseState -State $state -Status SKIPPED -Detail 'пакет не подтверждён'
                continue
            }
            if ((Get-FileSha256 -Path $plan.CandidateWheel) -ne $plan.Sha256) {
                Stop-WithFix -Problem 'пакет изменился, пока ты подтверждал.' -Fix ".\scripts\release.ps1 -Item $($state.Id)"
            }
        } catch {
            Set-ReleaseFailure -State $state -ErrorRecord $_
        }
    }

    if ($siteGoes) {
        Write-Host "`n— $($siteState.Name): выкладка" -ForegroundColor Cyan
        try {
            Invoke-DurableProductionDeploy -Revision $Candidate.Sha -RebuildAll:$RebuildAll `
                -RestartFailed:$Candidate.PreviousAttemptFailed
            Set-ReleaseState -State $siteState -Status DONE -Detail "выкачен и проверен ($($Candidate.ShortSha))"
        } catch {
            Set-ReleaseFailure -State $siteState -ErrorRecord $_
        }
    }
    foreach ($state in @($pluginStates | Where-Object Status -eq 'READY')) {
        $plan = $state.Plan
        if ($plan.NeedsSiteDeploy -and (-not $siteState -or $siteState.Status -ne 'DONE')) {
            Set-ReleaseState -State $state -Status SKIPPED -Detail 'сайт не выкатился, поэтому плагин не выпущен' `
                -Fix ".\scripts\release.ps1 -Item site,$($state.Id)"
            continue
        }
        Write-Host "`n— $($state.Name): выпуск" -ForegroundColor Cyan
        try {
            $result = Invoke-PluginReleaseScript -Id $state.Id -Arguments @{
                OwnerApprovedSha256 = @{ $state.Id = $plan.Sha256 }
                ExpectedReleaseCommit = $plan.ReleaseCommit
                HideReleaseNotes = $true
            }
            Set-ReleaseState -State $state -Status DONE -Detail $result.Detail
        } catch {
            Set-ReleaseFailure -State $state -ErrorRecord $_
        }
    }

    $released = @($pluginStates | Where-Object { $_.Status -eq 'DONE' -and -not $_.Plan.Repair } | ForEach-Object DownloadId)
    if ($released.Count) {
        try {
            if (-not (Test-DownloadPageRelease -Plugins $released)) {
                Write-Host 'Страница «Скачать» на сайте обновится в течение 15 минут (кеш). Это не ошибка.' -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "Страницу «Скачать» проверить не удалось: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }
    Show-ReleaseSummary -States $states -Title 'Итог выпуска:'
}

function Update-CatalogSource {
    Assert-Command python

    $refresher = Join-Path $repositoryRoot 'scripts\refresh_orca_catalog_source.py'
    $bundle = Join-Path $repositoryRoot 'backend\data\catalog_sources\orca\bundle.zip'
    $sourceLock = Join-Path $repositoryRoot 'backend\data\catalog_sources\orca\source-lock.json'

    Write-Host ''
    Write-Host 'Читаю профили OrcaSlicer и сравниваю с текущим источником...' -ForegroundColor Cyan
    & python $refresher
    $refreshStatus = $LASTEXITCODE
    $acceptFieldDelta = $false
    if ($refreshStatus -eq 2) {
        Write-Host ''
        Write-Host 'Orca изменила набор или форму полей пресетов.' -ForegroundColor Yellow
        Write-Host 'Это не обычное обновление каталога: сначала нужно разложить дельту по редакторам и passthrough-контракту.'
        if (-not (Confirm-Action 'Дельта полей уже проверена, а версия реестра обновлена?')) {
            Write-Host 'Источник не принят. Рабочее дерево не изменено.' -ForegroundColor Yellow
            return
        }
        $acceptFieldDelta = $true
        Invoke-Checked python @($refresher, '--accept-field-delta')
    } elseif ($refreshStatus -ne 0) {
        throw "Проверка источника Orca завершилась с ошибкой ($refreshStatus)."
    }

    if (-not (Confirm-Action 'Принять показанную версию источника и обновить локальный bundle.zip?')) {
        Write-Host 'Источник каталога оставлен без изменений.' -ForegroundColor Yellow
        return
    }

    $writeArguments = @($refresher, '--write')
    if ($acceptFieldDelta) {
        $writeArguments += '--accept-field-delta'
    }
    Invoke-Checked python $writeArguments

    Write-Host ''
    Write-Host "Готовый архив: $bundle" -ForegroundColor Green
    Write-Host "Метаданные источника для Git: $sourceLock" -ForegroundColor Green
    Write-Host ''
    Write-Host 'Дальше:' -ForegroundColor Cyan
    Write-Host '  1) закоммить source-lock.json и отправь коммит в main'
    Write-Host '  2) дождись зелёного CI'
    Write-Host '  3) выбери отдельный пункт «Опубликовать принятый источник на VDS»'
    Write-Host '  4) в админке запусти импорт источника каталога'
    Write-Host 'Обычный deploy для обновления каталога не нужен.' -ForegroundColor Green
}

function Publish-CatalogSource {
    Assert-Command git
    Assert-Command gh
    Assert-Command python
    Assert-Command ssh
    Assert-Command scp

    $bundle = Join-Path $repositoryRoot 'backend\data\catalog_sources\orca\bundle.zip'
    $sourceLock = Join-Path $repositoryRoot 'backend\data\catalog_sources\orca\source-lock.json'
    $sourceLockRelative = 'backend/data/catalog_sources/orca/source-lock.json'
    $verifier = Join-Path $repositoryRoot 'scripts\verify_orca_catalog_source.py'
    if (-not (Test-Path -LiteralPath $bundle -PathType Leaf)) {
        throw "Не найден принятый архив: $bundle"
    }

    Invoke-Checked python @($verifier, '--bundle', $bundle, '--source-lock', $sourceLock)
    $published = Get-VerifiedPublishedMain
    $localLockBlob = Invoke-Checked git @('hash-object', '--', $sourceLock) -Capture
    $publishedLockSpec = "$($published.Sha):$sourceLockRelative"
    $publishedLockBlob = Invoke-Checked git @('rev-parse', $publishedLockSpec) -Capture
    if ($localLockBlob -ne $publishedLockBlob) {
        throw 'Локальный source-lock.json ещё не опубликован в зелёном origin/main.'
    }

    $lock = Get-Content -LiteralPath $sourceLock -Raw -Encoding UTF8 | ConvertFrom-Json
    $expectedSha = "$($lock.bundle_sha256)"
    if ($expectedSha -notmatch '^[0-9a-f]{64}$') {
        throw 'source-lock.json содержит некорректный bundle_sha256.'
    }
    if (-not (Confirm-Action "Опубликовать Orca bundle $($lock.commit) на production VDS?")) {
        Write-Host 'Публикация источника отменена.' -ForegroundColor Yellow
        return
    }

    $target = Get-ServerTarget
    $remoteDirectory = "$RemoteProjectDirectory/backend/data/catalog_sources/orca"
    $remoteTemporary = "$remoteDirectory/.bundle.zip.upload-$PID"
    $mountCheck = "docker inspect filamenthub_backend_prod --format '{{range .Mounts}}{{println .Destination}}{{end}}' | grep -Fx '/app/data/catalog_sources/orca' >/dev/null"
    Invoke-Checked ssh @($target, $mountCheck)
    Invoke-Checked ssh @($target, "mkdir -p '$remoteDirectory'")
    Invoke-Checked scp @($bundle, "${target}:$remoteTemporary")
    $installCommand = "set -e && echo '$expectedSha  $remoteTemporary' | sha256sum -c - && mv -f '$remoteTemporary' '$remoteDirectory/bundle.zip' && echo '$expectedSha  $remoteDirectory/bundle.zip' | sha256sum -c -"
    Invoke-Checked ssh @($target, $installCommand)

    Write-Host ''
    Write-Host 'Принятый источник Orca опубликован на VDS без пересборки приложения.' -ForegroundColor Green
    Write-Host 'Теперь открой админку и запусти импорт источника каталога.'
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
        Write-Host '  1. Проверить готовность сайта к выкладке (ничего не меняет)'
        Write-Host '  2. Выкатить сайт'
        Write-Host '  3. Проверить состояние production'
        Write-Host '  4. Создать зашифрованный backup production-базы'
        Write-Host '  5. Очистить устаревший Docker build-cache на VDS'
        Write-Host '  6. Задеплоить с полной пересборкой (после правки .env на VDS)'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Invoke-Release -Items @('site') -CheckOnly }
                '2' { Invoke-Release -Items @('site') }
                '3' { Show-ProductionStatus }
                '4' { Start-ProductionBackup }
                '5' { Start-BuildCacheCleanup }
                '6' { Invoke-Release -Items @('site') -RebuildAll }
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
        Write-Host '  4. Отправить подготовленные коммиты плагинов в GitHub'
        Write-Host '     Проверит всех неопубликованных предков; посторонние изменения заблокируют push.' -ForegroundColor DarkGray
        Write-Host '  5. Проверить готовность к выпуску'
        Write-Host '     Только выбранные плагины; ничего не публикует.' -ForegroundColor DarkGray
        Write-Host '  6. Выпустить выбранные плагины'
        Write-Host '     Каждый выходит сам по себе; все вопросы задаются до выпуска.' -ForegroundColor DarkGray
        Write-Host '  7. Только проверить версии и показать, что агенту нужно подготовить'
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
                '4' { Publish-PluginCommits }
                '5' { Invoke-Release -CheckOnly }
                '6' { Invoke-Release }
                '7' {
                    $chosen = @(Read-ReleaseSelection | Where-Object { $_ -ne 'site' })
                    if ($chosen.Count) {
                        & (Join-Path $PSScriptRoot 'publish-plugin-releases.ps1') -Component $chosen -CheckVersions
                    }
                }
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
        Write-Host '  1. Проверить и принять источник каталога принтеров'
        Write-Host '  2. Опубликовать принятый источник на VDS'
        Write-Host '  3. Проверить инструменты для сборки OrcaSlicer'
        Write-Host '  0. Назад'

        try {
            switch ((Read-Host 'Выбери действие').Trim()) {
                '1' { Update-CatalogSource }
                '2' { Publish-CatalogSource }
                '3' { Invoke-OwnerScript -Name 'check_tools.ps1' }
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
        Write-MenuOption '6' 'Выпуск' 'Сайт и плагины: выбираешь что, скрипт всё проверит и выпустит.'
        Write-Host '  0. Выход'

        try {
            switch ((Read-Host 'Выбери раздел').Trim()) {
                '1' { Show-LocalDevelopmentMenu }
                '2' { Show-GitHubMenu }
                '3' { Show-ProductionMenu }
                '4' { Show-PluginMenu }
                '5' { Show-OrcaToolsMenu }
                '6' { Invoke-Release }
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
    'Release' { Invoke-Release -Items $Item -CheckOnly:$CheckOnly }
    'Publish' { Publish-Commits }
    'PublishPluginCommits' { Publish-PluginCommits }
    'Preflight' { Invoke-Release -Items @('site') -CheckOnly }
    'Deploy' { Invoke-Release -Items @('site') }
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
    'PrepareRelease' { Invoke-Release -Items $Item -CheckOnly:$CheckOnly }
    'PublishRelease' { Invoke-Release -Items $Item -CheckOnly:$CheckOnly }
    'UpdateCatalogSource' { Update-CatalogSource }
    'PublishCatalogSource' { Publish-CatalogSource }
}
