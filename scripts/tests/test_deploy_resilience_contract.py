from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DeployResilienceContractTest(unittest.TestCase):
    def test_production_images_are_built_sequentially(self) -> None:
        worker = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")

        backend = "docker compose build backend"
        frontend = "docker compose build frontend"
        self.assertIn(backend, worker)
        self.assertIn(frontend, worker)
        self.assertLess(worker.index(backend), worker.index(frontend))
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
        bootstrap = durable_function.index("Invoke-Checked ssh")
        retry_handler = durable_function.index("} catch {")
        self.assertLess(retry_start, bootstrap)
        self.assertLess(bootstrap, retry_handler)


if __name__ == "__main__":
    unittest.main()
