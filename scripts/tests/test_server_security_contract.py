from pathlib import Path
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
        self.assertIn("PasswordAuthentication no", script)
        self.assertIn("PermitRootLogin no", script)
        self.assertIn("PubkeyAuthentication yes", script)
        self.assertLess(script.index("sshd -t"), script.index("systemctl reload ssh"))

    def test_watchdog_key_is_restricted_to_one_root_owned_probe(self) -> None:
        script = (
            ROOT / "scripts/server-security/install-watchdog-access.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('authorized_key="restrict,command=', script)
        self.assertIn("/usr/bin/sudo -n $PROBE_TARGET", script)
        self.assertIn("NOPASSWD: %s", script)
        self.assertNotIn("NOPASSWD: ALL", script)

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


if __name__ == "__main__":
    unittest.main()
