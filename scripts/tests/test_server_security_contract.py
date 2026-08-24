import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ServerSecurityContractTest(unittest.TestCase):
    def test_ssh_hardening_requires_both_live_key_confirmations(self) -> None:
        script = (ROOT / "scripts/server-security/apply-ssh-hardening.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("00-filamenthub-hardening.conf", script)
        self.assertIn("--confirmed-lizard-key-session", script)
        self.assertIn("--confirmed-watchdog-key-session", script)
        self.assertIn("sudo --preserve-env=SSH_CONNECTION", script)
        self.assertIn("PasswordAuthentication no", script)
        self.assertIn("PermitRootLogin no", script)
        self.assertIn("PubkeyAuthentication yes", script)
        self.assertIn("effective_users=", script)
        self.assertIn("LC_ALL=C sort -u", script)
        self.assertIn("filamenthub-watchdog\\nlizard", script)
        self.assertLess(script.index("sshd -t"), script.index("systemctl reload ssh"))

    def test_watchdog_key_is_restricted_to_one_root_owned_probe(self) -> None:
        script = (
            ROOT / "scripts/server-security/install-watchdog-access.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('authorized_key="restrict,command=', script)
        self.assertIn("/usr/bin/sudo -n $PROBE_TARGET", script)
        self.assertIn("NOPASSWD: %s", script)
        self.assertNotIn("NOPASSWD: ALL", script)
        self.assertIn('-g "$WATCHDOG_USER" -m 0750', script)
        self.assertIn('-m 0640', script)
        self.assertIn('sudo -u "$WATCHDOG_USER" test -r', script)

    def test_fail2ban_is_secondary_and_uses_bounded_incremental_bans(self) -> None:
        script = (ROOT / "scripts/server-security/install-fail2ban.sh").read_text(
            encoding="utf-8"
        )

        hardening_check = script.index("passwordauthentication no")
        package_install = script.index("apt-get install")
        self.assertLess(hardening_check, package_install)
        self.assertIn("bantime.increment = true", script)
        self.assertIn("bantime.maxtime = 7d", script)
        self.assertIn("banaction = nftables-multiport", script)
        self.assertIn("for _ in {1..20}", script)
        self.assertIn("sleep 0.25", script)
        self.assertNotIn("enable --now", script)

    def test_public_frontend_cannot_share_data_or_docker_api_networks(self) -> None:
        source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            compose_file = temp_root / "docker-compose.yml"
            env_file = temp_root / ".env"
            compose_file.write_text(source, encoding="utf-8")
            env_file.write_text(
                "POSTGRES_PASSWORD=contract-only\nREDIS_PASSWORD=contract-only\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--file",
                    str(compose_file),
                    "--env-file",
                    str(env_file),
                    "config",
                    "--format",
                    "json",
                ],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        compose = json.loads(result.stdout)
        services = compose["services"]

        self.assertEqual(set(services["frontend"]["networks"]), {"filamenthub_network"})
        self.assertEqual(set(services["postgres"]["networks"]), {"filamenthub_data"})
        self.assertEqual(set(services["redis"]["networks"]), {"filamenthub_data"})
        self.assertEqual(
            set(services["docker-socket-proxy"]["networks"]),
            {"filamenthub_metrics"},
        )
        self.assertEqual(
            set(services["backend"]["networks"]),
            {"filamenthub_network", "filamenthub_data", "filamenthub_metrics"},
        )
        self.assertEqual(
            services["backend"]["networks"]["filamenthub_network"]["gw_priority"],
            1,
        )
        self.assertTrue(compose["networks"]["filamenthub_data"]["internal"])
        self.assertTrue(compose["networks"]["filamenthub_metrics"]["internal"])


if __name__ == "__main__":
    unittest.main()
