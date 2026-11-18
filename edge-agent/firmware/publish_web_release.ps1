# Copies a built firmware into the site's static files and rewrites the index
# the browser installer reads. Run after `pio run` and create_flash_manifest.ps1.
# A published version is never replaced: a rebuild with different bytes needs a
# new version number.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$site = Join-Path $repo 'frontend/public/firmware/edge'

$dirty = git -C $repo status --porcelain -- 'edge-agent/firmware'
if ($LASTEXITCODE -ne 0) { throw 'git status failed.' }
if ($dirty) { throw 'Commit the firmware sources first: the index records the commit a build came from.' }
$commit = (git -C $repo log -1 --format=%H -- 'edge-agent/firmware').Trim()

$ini = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'platformio.ini') -Raw
if ($ini -notmatch 'FH_EDGE_VERSION=\\"(\d+\.\d+\.\d+)\\"') { throw 'FH_EDGE_VERSION is missing in platformio.ini.' }
$version = $Matches[1]

$profiles = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'hardware-profiles.json') -Raw | ConvertFrom-Json
$kits = foreach ($kit in $profiles.kits) {
    $build = Join-Path $PSScriptRoot ".pio/build/$($kit.build)"
    $manifestPath = Join-Path $build 'flash-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Run create_flash_manifest.ps1 for $($kit.build) first." }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $target = Join-Path $site "$($kit.build)/$version"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $images = foreach ($image in $manifest.images) {
        $source = Join-Path $build $image.file
        $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $image.sha256) { throw "$($image.file) changed after the manifest was written; rebuild the manifest." }
        $published = Join-Path $target $image.file
        if (Test-Path -LiteralPath $published) {
            $existing = (Get-FileHash -LiteralPath $published -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($existing -ne $hash) { throw "$($kit.build) $version is already published with different bytes; raise FH_EDGE_VERSION." }
        } else {
            Copy-Item -LiteralPath $source -Destination $published
        }
        [ordered]@{
            offset = [Convert]::ToInt32($image.offset, 16)
            path = "$($kit.build)/$version/$($image.file)"
            bytes = $image.bytes
            sha256 = $hash
        }
    }
    [ordered]@{
        id = $kit.id
        status = $kit.status
        chip = $kit.chip
        board = $kit.board
        reader = $kit.reader
        nfc_pins = $kit.nfc_pins
        firmware = [ordered]@{
            version = $version
            source_commit = $commit
            flash = [ordered]@{ mode = 'dio'; freq = '80m'; size = $manifest.flash_size }
            partition_table_offset = 0x8000
            app_offset = 0x20000
            images = @($images)
        }
    }
}
$index = [ordered]@{ schema = 1; kits = @($kits) }
$json = ($index | ConvertTo-Json -Depth 8) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText((Join-Path $site 'index.json'), $json + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "Published firmware $version ($commit) for: $(($profiles.kits | ForEach-Object id) -join ', ')"
