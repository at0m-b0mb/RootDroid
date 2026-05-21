"""
MediaTek BROM (Boot ROM) root method.

Uses mtkclient (https://github.com/bkerler/mtkclient) to communicate
with the MediaTek preloader in BROM mode — no bootloader unlock needed.

BROM mode entry (most MT6xxx chips):
  Power off → hold Vol-Down → plug USB
  Some chips: hold Vol-Up instead, or Vol-Up+Vol-Down

Flow:
  1. Guide user to enter BROM mode
  2. Use mtkclient to read the boot partition → boot.img
  3. Patch with Magisk
  4. Write patched image back via mtkclient
  5. Reboot normally
  6. Install Magisk APK for the management UI
"""

import shutil
import subprocess
import sys
from pathlib import Path

from methods.magisk import patch as magisk_patch
from utils.downloader import ASSETS_DIR, magisk_apk
from utils.logger import info, success, warning, error, step, console


class MTKBROMError(Exception):
    pass


def _check_mtkclient() -> str:
    """Return the mtkclient executable path or raise."""
    exe = shutil.which("mtk")
    if exe:
        return exe
    # Try running as a Python module
    result = subprocess.run(
        [sys.executable, "-m", "mtkclient.tools.mtk", "--help"],
        capture_output=True,
    )
    if result.returncode in (0, 1):   # some tools exit 1 on --help
        return f"{sys.executable} -m mtkclient.tools.mtk"
    raise MTKBROMError(
        "mtkclient is not installed.\n"
        "  Install with:  pip install mtkclient\n"
        "  Also need:     brew install libusb"
    )


def _run_mtk(mtk_exe: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    if mtk_exe.startswith(sys.executable):
        cmd = [sys.executable, "-m", "mtkclient.tools.mtk", *args]
    else:
        cmd = [mtk_exe, *args]
    return subprocess.run(cmd, capture_output=False, timeout=timeout)


def _brom_guide(abi: str) -> None:
    console.print("\n[bold yellow]━━━  Enter BROM Mode  ━━━[/bold yellow]")
    console.print(
        "  1. [bold]Power OFF[/bold] the phone completely\n"
        "  2. Hold [bold]Vol-Down[/bold] (try Vol-Up if this fails)\n"
        "  3. While holding the button, [bold]plug in the USB cable[/bold]\n"
        "  4. Keep holding for ~3 seconds after plugging in\n"
        "  5. The screen will stay black — this is normal\n"
        "\n  [dim]If BROM detection fails, try the other volume button combination.[/dim]"
    )
    input("\n[Press ENTER when you have done the above steps] ")


def run(abi: str = "arm64-v8a") -> None:
    """Execute the full MTK BROM rooting flow."""

    # ------------------------------------------------------------------
    # Pre-flight checks
    # ------------------------------------------------------------------
    mtk_exe = _check_mtkclient()
    success(f"mtkclient found: {mtk_exe}")

    boot_dump   = ASSETS_DIR / "boot.img"
    boot_patched = ASSETS_DIR / "magisk_patched.img"
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Enter BROM mode
    # ------------------------------------------------------------------
    _brom_guide(abi)

    # ------------------------------------------------------------------
    # Step 2: Dump boot partition
    # ------------------------------------------------------------------
    step("Reading boot partition via BROM ...")
    info("  mtkclient will now try to connect to the device.\n"
         "  If it hangs for more than 30 s, unplug USB and retry BROM mode.")

    result = _run_mtk(mtk_exe, "r", "boot", str(boot_dump), timeout=90)
    if result.returncode != 0 or not boot_dump.exists():
        raise MTKBROMError(
            "Failed to read boot partition.\n"
            "  Possible reasons:\n"
            "    • Device did not enter BROM mode correctly — retry the button combo\n"
            "    • libusb not installed: brew install libusb\n"
            "    • On macOS, you may need to allow the USB device in System Settings → Privacy & Security\n"
            "    • Your chip may need a different mtkclient version: pip install mtkclient --upgrade"
        )
    success(f"boot.img dumped → {boot_dump}  ({boot_dump.stat().st_size // 1024} KB)")

    # ------------------------------------------------------------------
    # Step 3: Patch with Magisk
    # ------------------------------------------------------------------
    boot_patched = magisk_patch(boot_dump, abi=abi)

    # ------------------------------------------------------------------
    # Step 4: Flash patched image back
    # ------------------------------------------------------------------
    info("\n[bold yellow]━━━  Re-enter BROM Mode to flash  ━━━[/bold yellow]")
    console.print(
        "  The device may have exited BROM mode during the read.\n"
        "  Repeat the same steps:"
    )
    _brom_guide(abi)

    step("Writing patched boot image via BROM ...")
    result = _run_mtk(mtk_exe, "w", "boot", str(boot_patched), timeout=90)
    if result.returncode != 0:
        raise MTKBROMError(
            "Failed to write boot partition.\n"
            f"  Patched image is at: {boot_patched}\n"
            "  You can flash it manually with MTK SP Flash Tool (Download Only mode on the boot partition)."
        )
    success("Patched boot image written successfully!")

    # ------------------------------------------------------------------
    # Step 5: Reboot
    # ------------------------------------------------------------------
    step("Rebooting device ...")
    _run_mtk(mtk_exe, "reset", timeout=15)

    # ------------------------------------------------------------------
    # Done — guide user to install Magisk app
    # ------------------------------------------------------------------
    apk = magisk_apk()
    console.print("\n[bold green]━━━  Root installed!  ━━━[/bold green]")
    info("After the phone boots:")
    info(f"  Install the Magisk app:  adb install {apk}")
    info("  Open Magisk — it will complete setup on first run.")
    info("  Grant root to SuperUser requests as needed.")
    success("MediaTek BROM root complete.")
