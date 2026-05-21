import shutil
import subprocess


class FastbootError(Exception):
    pass


class Fastboot:
    def __init__(self, fastboot_path: str = "fastboot"):
        resolved = shutil.which(fastboot_path)
        if not resolved:
            raise FastbootError(
                "fastboot not found in PATH.\n"
                "  Install it with:  brew install android-platform-tools"
            )
        self._bin = resolved

    def _run(self, *args, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._bin, *args],
            capture_output=True, text=True, timeout=timeout,
        )

    def devices(self) -> list[str]:
        r = self._run("devices")
        return [
            line.split()[0]
            for line in r.stdout.strip().splitlines()
            if "\tfastboot" in line
        ]

    def get_var(self, serial: str, var: str) -> str:
        r = self._run("-s", serial, "getvar", var)
        combined = r.stdout + r.stderr
        for line in combined.splitlines():
            if var in line and ":" in line:
                return line.split(":", 1)[-1].strip()
        return ""

    def is_unlocked(self, serial: str) -> bool:
        return self.get_var(serial, "unlocked").lower() == "yes"

    def flash(self, serial: str, partition: str, image: str, timeout: int = 180) -> bool:
        r = self._run("-s", serial, "flash", partition, image, timeout=timeout)
        return r.returncode == 0

    def boot(self, serial: str, image: str, timeout: int = 60) -> bool:
        r = self._run("-s", serial, "boot", image, timeout=timeout)
        return r.returncode == 0

    def reboot(self, serial: str) -> None:
        self._run("-s", serial, "reboot", timeout=15)

    def oem_unlock(self, serial: str) -> bool:
        r = self._run("-s", serial, "oem", "unlock", timeout=30)
        return r.returncode == 0

    def flashing_unlock(self, serial: str) -> bool:
        r = self._run("-s", serial, "flashing", "unlock", timeout=30)
        return r.returncode == 0
