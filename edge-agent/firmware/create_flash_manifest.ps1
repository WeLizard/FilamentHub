$ErrorActionPreference = 'Stop'
$build = Join-Path $PSScriptRoot '.pio/build/esp32-c3-devkitm-1'
$idfArgsPath = Join-Path $build 'flasher_args.json'
if (-not (Test-Path -LiteralPath $idfArgsPath)) {
    throw 'Build first: generated flash offsets are unavailable.'
}
$idfArgs = Get-Content -LiteralPath $idfArgsPath -Raw | ConvertFrom-Json
if ($idfArgs.flash_settings.flash_size -ne '4MB' -or
    $idfArgs.flash_settings.flash_mode -ne 'dio' -or
    $idfArgs.flash_settings.flash_freq -ne '80m' -or
    -not $idfArgs.flash_files.PSObject.Properties['0x0'] -or
    -not $idfArgs.flash_files.PSObject.Properties['0x8000'] -or
    -not $idfArgs.flash_files.PSObject.Properties['0x20000']) {
    throw 'Generated flash layout differs from the reviewed ESP32-C3 layout.'
}
$partitionBytes = [System.IO.File]::ReadAllBytes((Join-Path $build 'partitions.bin'))
$partitionLayout = @{}
for ($at = 0; $at + 32 -le $partitionBytes.Length; $at += 32) {
    if ($partitionBytes[$at] -ne 0xAA -or $partitionBytes[$at + 1] -ne 0x50) { continue }
    $label = [System.Text.Encoding]::ASCII.GetString($partitionBytes, $at + 12, 16).TrimEnd([char]0)
    $partitionLayout[$label] = @{
        type = $partitionBytes[$at + 2]
        subtype = $partitionBytes[$at + 3]
        offset = [BitConverter]::ToUInt32($partitionBytes, $at + 4)
        size = [BitConverter]::ToUInt32($partitionBytes, $at + 8)
    }
}
foreach ($expected in @(
    @{ label = 'nvs'; type = 1; subtype = 2; offset = 0x9000; size = 0x10000 },
    @{ label = 'factory'; type = 0; subtype = 0; offset = 0x20000; size = 0x300000 },
    @{ label = 'ams_journal'; type = 1; subtype = 0x40; offset = 0x320000; size = 0x40000 }
)) {
    $actual = $partitionLayout[$expected.label]
    if (-not $actual -or $actual.type -ne $expected.type -or
        $actual.subtype -ne $expected.subtype -or
        $actual.offset -ne $expected.offset -or $actual.size -ne $expected.size) {
        throw "Generated partition layout differs for $($expected.label)."
    }
}
$files = @(
    @{ offset = '0x0'; name = 'bootloader.bin' },
    @{ offset = '0x8000'; name = 'partitions.bin' },
    @{ offset = '0x20000'; name = 'firmware.bin' }
)
$images = foreach ($entry in $files) {
    $path = Join-Path $build $entry.name
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing $($entry.name)" }
    $file = Get-Item -LiteralPath $path
    [ordered]@{
        offset = $entry.offset
        file = $entry.name
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
if ($images[2].bytes -gt 0x300000) { throw 'Application exceeds the factory partition.' }
$manifest = [ordered]@{
    target = 'esp32-c3-devkitm-1'
    flash_size = '4MB'
    write_flash_args = @('--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '4MB',
                         '0x0', 'bootloader.bin', '0x8000', 'partitions.bin',
                         '0x20000', 'firmware.bin')
    images = @($images)
}
$output = Join-Path $build 'flash-manifest.json'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $output -Encoding utf8
Get-Content -LiteralPath $output -Raw
