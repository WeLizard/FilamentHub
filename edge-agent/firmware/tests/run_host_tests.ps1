$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$binary = Join-Path $env:TEMP 'fh_edge_core_test.exe'
gcc -std=c11 -Wall -Wextra -Werror -I (Join-Path $root 'src') `
    (Join-Path $root 'src/core.c') (Join-Path $PSScriptRoot 'test_core.c') `
    -lm -o $binary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $binary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$jsonDir = Join-Path $env:USERPROFILE '.platformio/packages/framework-espidf/components/json/cJSON'
$jsonSource = Join-Path $jsonDir 'cJSON.c'
if (-not (Test-Path -LiteralPath $jsonSource)) {
    throw 'ESP-IDF cJSON source is unavailable; install the scoped PlatformIO firmware packages first.'
}
$jsonObject = Join-Path $env:TEMP 'fh_edge_cjson.o'
$configBinary = Join-Path $env:TEMP 'fh_edge_config_snapshot_test.exe'
gcc -std=c11 -w -c $jsonSource -o $jsonObject
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
gcc -std=c11 -Wall -Wextra -Werror -I (Join-Path $root 'src') `
    -I (Join-Path $PSScriptRoot 'mocks') -I $jsonDir `
    (Join-Path $root 'src/core.c') (Join-Path $root 'src/config.c') `
    (Join-Path $root 'src/report.c') `
    (Join-Path $root 'src/snapshot.c') (Join-Path $PSScriptRoot 'test_config_snapshot.c') `
    $jsonObject -lm -o $configBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $configBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$amsBinary = Join-Path $env:TEMP 'fh_edge_ams_test.exe'
gcc -std=c11 -Wall -Wextra -Werror -I (Join-Path $root 'src') `
    -I $jsonDir (Join-Path $root 'src/core.c') (Join-Path $root 'src/ams.c') `
    (Join-Path $PSScriptRoot 'test_ams.c') $jsonObject -lm -o $amsBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $amsBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$journalBinary = Join-Path $env:TEMP 'fh_edge_ams_journal_test.exe'
gcc -std=c11 -Wall -Wextra -Werror -I (Join-Path $root 'src') `
    -I $jsonDir (Join-Path $root 'src/core.c') (Join-Path $root 'src/ams.c') `
    (Join-Path $root 'src/ams_journal.c') `
    (Join-Path $PSScriptRoot 'test_ams_journal.c') $jsonObject -lm -o $journalBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $journalBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ntagBinary = Join-Path $env:TEMP 'fh_edge_ntag_test.exe'
gcc -std=c11 -Wall -Wextra -Werror -I (Join-Path $root 'src') `
    (Join-Path $root 'src/ntag.c') (Join-Path $PSScriptRoot 'test_ntag.c') `
    -o $ntagBinary
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $ntagBinary
exit $LASTEXITCODE
