import shutil
import subprocess
from pathlib import Path


class ADBError(Exception):
    pass


class ADB:
    def __init__(self, adb_path: str = "adb"):
        resolved = shutil.which(adb_path)
        if not resolved:
            raise ADBError(
                "adb not found in PATH.\n"
                "  Install it with:  brew install android-platform-tools"
            )
        self._bin = resolved

    def _run(self, *args, timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._bin, *args],
            capture_output=True, text=True, timeout=timeout,
        )

    def start_server(self) -> None:
        self._run("start-server", timeout=10)

    def devices(self) -> list[dict]:
        result = self._run("devices", "-l")
        devices = []
        for line in result.stdout.strip().splitlines()[1:]:
            if "\tdevice" in line:
                parts = line.split()
                serial = parts[0]
                props: dict[str, str] = {}
                for part in parts[2:]:
                    if ":" in part:
                        k, v = part.split(":", 1)
                        props[k] = v
                devices.append({"serial": serial, **props})
        return devices

    def shell(self, serial: str, cmd: str, timeout: int = 15) -> str:
        r = self._run("-s", serial, "shell", cmd, timeout=timeout)
        return r.stdout.strip()

    def get_prop(self, serial: str, prop: str) -> str:
        return self.shell(serial, f"getprop {prop}")

    def pull(self, serial: str, remote: str, local: str, timeout: int = 120) -> bool:
        r = self._run("-s", serial, "pull", remote, local, timeout=timeout)
        return r.returncode == 0

    def push(self, serial: str, local: str, remote: str, timeout: int = 120) -> bool:
        r = self._run("-s", serial, "push", local, remote, timeout=timeout)
        return r.returncode == 0

    def install(self, serial: str, apk: str, timeout: int = 90) -> bool:
        r = self._run("-s", serial, "install", "-r", apk, timeout=timeout)
        return r.returncode == 0 and "Success" in r.stdout

    def reboot(self, serial: str, mode: str = "") -> None:
        args = ["-s", serial, "reboot"]
        if mode:
            args.append(mode)
        self._run(*args, timeout=10)

    def root(self, serial: str) -> bool:
        r = self._run("-s", serial, "root", timeout=15)
        return r.returncode == 0 and "cannot" not in r.stdout

    def remount(self, serial: str) -> bool:
        r = self._run("-s", serial, "remount", timeout=15)
        return r.returncode == 0

    def is_connected(self, serial: str) -> bool:
        return any(d["serial"] == serial for d in self.devices())
