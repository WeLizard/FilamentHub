<#
.SYNOPSIS
Выпуск FilamentHub: сайт и плагины, каждый сам по себе.

.DESCRIPTION
Без параметров показывает меню. Сначала проверяет всё выбранное и ни о чём
не спрашивает; если что-то не так, пишет, что исправить, и ничего не меняет.
Потом задаёт все вопросы сразу и только после них выкатывает сайт (первым) и
выпускает плагины.

.EXAMPLE
.\scripts\release.ps1

.EXAMPLE
.\scripts\release.ps1 -Item site,orcaslicer

.EXAMPLE
.\scripts\release.ps1 -Item octoprint -CheckOnly
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet('site', 'orcaslicer', 'octoprint', 'print-farm')]
    [string[]]$Item = @(),

    [Parameter()]
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'deploy-server.ps1') -Action Release -Item $Item -CheckOnly:$CheckOnly
