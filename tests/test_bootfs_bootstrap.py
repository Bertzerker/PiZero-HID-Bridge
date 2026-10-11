import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("BOOTFS_TEST_BASH") or shutil.which("bash")
BOOT_OPTIONS = (
    "systemd.run_success_action=reboot "
    "systemd.run_failure_action=none "
    "systemd.unit=kernel-command-line.target"
)


@unittest.skipUnless(BASH, "Bash is required for bootstrap integration tests")
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bootfs = Path(self.directory.name)
        self.script = self.bootfs / "bootstrap-wifi.sh"
        source = (PROJECT_ROOT / "bootfs/bootstrap-wifi.sh").read_text()
        # Redirect the service write and mock system commands to isolate the test.
        source = source.replace(
            'SERVICE_FILE="/etc/systemd/system/bootfs-wifi-update.service"',
            'SERVICE_FILE="$BOOTFS_TEST_SERVICE_FILE"',
        )
        self.script.write_text(source, newline="\n")
        (self.bootfs / "update-wifi.sh").write_text("#!/bin/bash\n")
        self.credentials = self.bootfs / "wifi-credentials.txt"
        self.credentials.write_text("SSID=Test network\nPASSWORD=Test password\n")
        self.cmdline = self.bootfs / "cmdline.txt"
        self.service = self.bootfs / "bootfs-wifi-update.service"
        self.calls = self.bootfs / "calls.txt"

    def run_bootstrap(self, *args):
        environment = os.environ.copy()
        environment.update({
            "BOOTFS_TEST_SERVICE_FILE": self.service.as_posix(),
            "BOOTFS_TEST_CALLS": self.calls.as_posix(),
            "BOOTFS_TEST_PYTHON": Path(sys.executable).as_posix(),
        })
        commands = '''
id() { printf '0\\n'; }
systemctl() { printf '%s\\n' "$*" >> "$BOOTFS_TEST_CALLS"; }
sync() { :; }
python3() { "$BOOTFS_TEST_PYTHON" "$@"; }
export -f id systemctl sync python3
bash "$@"
'''
        return subprocess.run(
            [BASH, "-c", commands, "test", self.script.as_posix(), *args],
            env=environment, capture_output=True, text=True, timeout=20,
        )

    def test_bootstrap_preserves_normal_boot_and_credentials(self):
        original = (
            "console=tty1 root=PARTUUID=1234-02 rootwait "
            "modules-load=dwc2,libcomposite custom=systemd.unit=keep"
        )
        for boot_path in ("/boot/firmware", "/boot"):
            with self.subTest(boot_path=boot_path):
                self.cmdline.write_text(
                    f"{original} systemd.run={boot_path}/bootstrap-wifi.sh {BOOT_OPTIONS}\n"
                )
                result = self.run_bootstrap()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.cmdline.read_text(), original + "\n")
                self.assertTrue(self.credentials.exists())
                self.assertIn("ExecStart=/bin/bash ", self.service.read_text())
                self.assertIn("RequiresMountsFor=", self.service.read_text())
                self.assertIn("enable bootfs-wifi-update.service", self.calls.read_text())
                result = self.run_bootstrap()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.cmdline.read_text(), original + "\n")

    def test_install_only_needs_no_cmdline_and_preserves_it(self):
        result = self.run_bootstrap("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.service.exists())
        self.assertFalse(self.cmdline.exists())
        self.cmdline.write_text("root=PARTUUID=1234-02 " + BOOT_OPTIONS + "\n")
        original = self.cmdline.read_text()
        result = self.run_bootstrap("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cmdline.read_text(), original)

    def test_missing_updater_leaves_boot_configuration_intact(self):
        original = "rootwait systemd.run=/boot/firmware/bootstrap-wifi.sh\n"
        self.cmdline.write_text(original)
        (self.bootfs / "update-wifi.sh").unlink()
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.cmdline.read_text(), original)
        self.assertFalse(self.service.exists())
        self.assertTrue(self.credentials.exists())

    def test_missing_cmdline_does_not_install_service(self):
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.service.exists())


if __name__ == "__main__":
    unittest.main()
