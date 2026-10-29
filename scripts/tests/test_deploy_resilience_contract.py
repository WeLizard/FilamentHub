import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

POWERSHELL_FUNCTION_LOADER = r"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:CONSOLE_SCRIPT, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}
"""


class DeployResilienceContractTest(unittest.TestCase):
    def test_production_images_are_built_sequentially(self) -> None:
        worker = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

        backend = 'build_service_if_needed backend "$planned_builds"'
        frontend = 'build_service_if_needed frontend "$planned_builds"'
        self.assertIn(backend, worker)
        self.assertIn(frontend, worker)
        self.assertLess(worker.index(backend), worker.index(frontend))
        self.assertIn('docker compose build "$service"', worker)
        self.assertNotIn("docker compose build backend frontend", worker)

    def test_remote_deploy_is_a_durable_reattachable_job(self) -> None:
        console = (ROOT / "scripts/deploy-server.ps1").read_text(encoding="utf-8")
        runner = (ROOT / "scripts/run-deploy-job.sh").read_text(encoding="utf-8")

        self.assertIn(
            "Invoke-DurableProductionDeploy -Revision $Candidate.Sha", console
        )
        self.assertIn("--status', '--run-id', $runId, '--from-line'", console)
        self.assertIn("задача на VDS продолжает работу", console)
        self.assertIn("nohup", runner)
        self.assertIn("FH_DEPLOY_JOB_STATUS_V1", runner)
        self.assertIn(
            "${XDG_STATE_HOME:-$HOME/.local/state}/filamenthub/deploys",
            runner,
        )
        self.assertIn("trap cleanup_start_lock RETURN EXIT", runner)

        durable_function = console.split(
            "function Invoke-DurableProductionDeploy", maxsplit=1
        )[1].split("function ", maxsplit=1)[0]
        retry_start = durable_function.index("do {")
        bootstrap = durable_function.index("Invoke-BoundedSshCommand -Target $target")
        retry_handler = durable_function.index("} catch {")
        self.assertLess(retry_start, bootstrap)
        self.assertLess(bootstrap, retry_handler)

        self.assertIn("Invoke-BoundedSshCommand -Target $Target", console)
        self.assertIn(
            "Invoke-BoundedSshCommand -Target $target -RemoteCommand $startCommand",
            durable_function,
        )
        self.assertIn("DeploySshCommandTimeoutSeconds", console)
        self.assertIn("DeployLogHeartbeatSeconds", console)
        self.assertIn("$PSVersionTable.PSVersion.Major -eq 5", console)
        self.assertIn("Windows PowerShell 5.1 не может ограничить ожидание", console)
        self.assertIn("GetType().GetProperty('ArgumentList')", console)

    @unittest.skipUnless(shutil.which("pwsh"), "needs PowerShell 7")
    def test_empty_running_poll_reports_progress_and_timeout_retries_same_job(self) -> None:
        script = POWERSHELL_FUNCTION_LOADER + r"""
$ErrorActionPreference = 'Stop'
$RemoteProjectDirectory = 'FilamentHub'
$script:DeployReconnectGraceSeconds = 30
$script:DeployJobTimeoutSeconds = 60
$script:DeployPollIntervalSeconds = 0
$script:DeployLogHeartbeatSeconds = 0
$global:deployCalls = [System.Collections.Generic.List[object]]::new()
$global:messages = [System.Collections.Generic.List[string]]::new()

function Assert-Command { param([string]$Name) }
function Get-ServerTarget { return 'server' }
function Start-Sleep { param([int]$Seconds) }
function Write-Host { param([object]$Object, [string]$ForegroundColor); $global:messages.Add([string]$Object) }
function Invoke-BoundedSshCommand { param([string]$Target, [string]$RemoteCommand, [string]$Purpose); return '' }
function Invoke-DurableDeployCommand {
    param([string]$Target, [string]$Revision, [string[]]$RunnerArguments)
    $kind = if ('--start' -in $RunnerArguments) { 'start' } else { 'status' }
    $global:deployCalls.Add([pscustomobject]@{ kind = $kind; args = ($RunnerArguments -join ' ') })
    if ('--start' -in $RunnerArguments) {
        return [pscustomobject]@{ Status = 'running'; ExitCode = '-'; LineCount = 0; LogLines = @(); LogPath = 'job.log' }
    }
    if ($global:deployCalls.Count -eq 2) {
        throw [System.TimeoutException]::new('simulated local SSH timeout')
    }
    return [pscustomobject]@{ Status = 'succeeded'; ExitCode = '0'; LineCount = 0; LogLines = @(); LogPath = 'job.log' }
}

Invoke-DurableProductionDeploy -Revision ('c' * 40)
@{ calls = @($global:deployCalls.ToArray()); messages = @($global:messages.ToArray()) } |
    ConvertTo-Json -Compress -Depth 4
"""
        result = _run_powershell(script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        calls = payload["calls"]
        starts = [call for call in calls if call["kind"] == "start"]
        status_calls = [call["args"] for call in calls if call["kind"] == "status"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(status_calls), 2)
        self.assertEqual(status_calls[0], status_calls[1])
        self.assertIn("--from-line 0", status_calls[0])
        self.assertIn(
            "Выкладка на VDS выполняется; новых строк журнала пока нет.",
            payload["messages"],
        )
        self.assertIn(
            "Production deployment завершён. Журнал: job.log",
            payload["messages"],
        )

    @unittest.skipUnless(shutil.which("pwsh"), "needs PowerShell 7")
    def test_bounded_process_timeout_stops_local_child(self) -> None:
        script = POWERSHELL_FUNCTION_LOADER + r"""
$script:DeploySshHeartbeatSeconds = 30
try {
    Invoke-BoundedNativeCommand `
        -FilePath $env:PWSH `
        -Arguments @('-NoProfile', '-NonInteractive', '-Command', 'Start-Sleep -Seconds 10') `
        -TimeoutSeconds 1 `
        -TimeoutMessage 'simulated timeout'
    throw 'expected timeout was not raised'
} catch [System.TimeoutException] {
    if ($_.Exception.Message -notmatch 'simulated timeout') { throw }
    $timedOutProcessId = $_.Exception.Data['LocalProcessId']
    if (-not $timedOutProcessId) { throw 'timeout did not report the local process id' }
    if (Get-Process -Id $timedOutProcessId -ErrorAction SilentlyContinue) {
        throw "local child $timedOutProcessId is still running"
    }
    if ($_.Exception.Message -notmatch 'локальный SSH-клиент остановлен') {
        throw 'timeout did not confirm local process shutdown'
    }
    'timeout observed and local child stopped'
}
"""
        result = _run_powershell(script, extra_env={"PWSH": shutil.which("pwsh")})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("timeout observed and local child stopped", result.stdout)

    def test_deploy_cleanup_keeps_current_and_previous_images(self) -> None:
        worker = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
        console = (ROOT / "scripts/deploy-server.ps1").read_text(encoding="utf-8")

        self.assertIn("docker builder prune -af --filter", worker)
        self.assertIn("docker image prune -f", worker)
        self.assertNotIn("docker system prune", worker)
        self.assertNotIn("docker image prune -a", worker)
        self.assertNotIn("docker volume prune", worker)
        self.assertIn("Старше 1 часа", console)
        self.assertIn("'3' { '1h' }", console)

        deploy = worker.split("deploy() {", maxsplit=1)[1].split(
            "while (( $# > 0 ))", maxsplit=1
        )[0]
        verification = deploy.index("if ! verify_release; then")
        cleanup = deploy.index("prune_superseded_docker_artifacts")
        success = deploy.index("Deployment completed and verified")
        self.assertLess(verification, cleanup)
        self.assertLess(cleanup, success)

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_only_images_built_from_other_code_are_rebuilt(self) -> None:
        bash = _git_bash()
        if bash is None:
            self.skipTest("needs Git Bash")
        worker = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
        functions = "\n".join(
            _shell_function(worker, name)
            for name in ("image_revision", "service_needs_build", "services_to_build")
        )
        # The worker reads each image's build revision through docker; the stub
        # answers from BACKEND_IMAGE / FRONTEND_IMAGE.
        docker_stub = (
            'docker() { case "${@: -1}" in '
            'filamenthub-backend:latest) printf %s "$BACKEND_IMAGE" ;; '
            'filamenthub-frontend:latest) printf %s "$FRONTEND_IMAGE" ;; esac; }'
        )
        script = f"set -Eeuo pipefail\n{docker_stub}\n{functions}\nservices_to_build"

        with tempfile.TemporaryDirectory() as repo:
            def git(*args: str) -> str:
                return subprocess.run(
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t",
                     "-c", "commit.gpgsign=false", *args],
                    cwd=repo, check=True, capture_output=True, text=True,
                ).stdout.strip()

            def commit(*paths: str) -> str:
                for path in paths:
                    file = Path(repo, path)
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text(file.read_text() + "x" if file.exists() else "x")
                git("add", "-A")
                git("commit", "-q", "-m", "change")
                return git("rev-parse", "HEAD")

            def planned(target: str, backend: str, frontend: str, rebuild_all: str = "false") -> list[str]:
                env = {
                    "TARGET_REVISION": target, "REBUILD_ALL": rebuild_all,
                    "BACKEND_IMAGE": backend, "FRONTEND_IMAGE": frontend,
                }
                result = subprocess.run(
                    [bash, "-c", script], cwd=repo, check=True, capture_output=True, text=True,
                    env={**os.environ, **env},
                )
                return result.stdout.split()

            git("init", "-q")
            base = commit("backend/app/main.py", "frontend/src/App.tsx", "docker-compose.yml")
            tests_only = commit(
                "backend/tests/x_test.py", "frontend/src/tests/x.test.ts",
                "frontend/src/App.test.tsx", "backend/README.md",
            )
            self.assertEqual(planned(tests_only, base, base), [])
            backend = commit("backend/app/main.py")
            self.assertEqual(planned(backend, base, base), ["backend"])
            frontend = commit("frontend/src/App.tsx")
            self.assertEqual(planned(frontend, backend, backend), ["frontend"])
            # After a rollback the frontend image is older than HEAD: still rebuilt.
            self.assertEqual(planned(frontend, frontend, base), ["frontend"])
            self.assertEqual(planned(frontend, frontend, frontend), [])
            self.assertEqual(planned(frontend, "unknown", ""), ["backend", "frontend"])
            self.assertEqual(planned(frontend, frontend, frontend, "true"), ["backend", "frontend"])
            compose = commit("docker-compose.yml")
            self.assertEqual(planned(compose, frontend, frontend), ["backend", "frontend"])
            # Thousands of paths: an early-exiting reader must not hide the change.
            bulk = commit(*(f"backend/app/m{i}.py" for i in range(3000)))
            self.assertEqual(planned(bulk, compose, compose), ["backend"])


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{.*?^\}}$", source, re.S | re.M)
    assert match is not None, name
    return match.group(0)


def _git_bash() -> str | None:
    if sys.platform != "win32":
        return shutil.which("bash")
    # On Windows a bare "bash" is the WSL stub; Git Bash lives next to git.exe.
    git = shutil.which("git")
    if git is None:
        return None
    for root in Path(git).resolve().parents:
        candidate = root / "bin" / "bash.exe"
        if candidate.is_file() and "system32" not in str(candidate).lower():
            return str(candidate)
    return None


def _run_powershell(script: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("pwsh")
    assert shell is not None
    task_temp = Path(os.environ.get("TEMP", r"F:\Temp"))
    task_temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fh-deploy-contract-", dir=task_temp) as temp_dir:
        runner = Path(temp_dir, "runner.ps1")
        runner.write_text(script, encoding="utf-8-sig")
        return subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
            env={
                **os.environ,
                "CONSOLE_SCRIPT": str(ROOT / "scripts/deploy-server.ps1"),
                "TEMP": str(task_temp),
                "TMP": str(task_temp),
                **(extra_env or {}),
            },
        )


if __name__ == "__main__":
    unittest.main()
