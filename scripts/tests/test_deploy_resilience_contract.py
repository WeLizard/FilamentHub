from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_images_are_built_sequentially() -> None:
    worker = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

    backend = "docker compose build backend"
    frontend = "docker compose build frontend"
    assert backend in worker
    assert frontend in worker
    assert worker.index(backend) < worker.index(frontend)
    assert "docker compose build backend frontend" not in worker


def test_remote_deploy_is_a_durable_reattachable_job() -> None:
    console = (ROOT / "scripts/deploy-server.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run-deploy-job.sh").read_text(encoding="utf-8")

    assert "Invoke-DurableProductionDeploy -Revision $Candidate.Sha" in console
    assert "--status', '--run-id', $runId, '--from-line'" in console
    assert "задача на VDS продолжает работу" in console
    assert "nohup" in runner
    assert "FH_DEPLOY_JOB_STATUS_V1" in runner
    assert "${XDG_STATE_HOME:-$HOME/.local/state}/filamenthub/deploys" in runner
