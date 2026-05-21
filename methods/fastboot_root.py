"""
Root via fastboot: for devices with an unlocked bootloader.

Flow:
  1. Wait for device in fastboot mode
  2. Verify bootloader is unlocked
  3. Pull stock boot.img from the running device (via ADB) — or ask user to provide it
  4. Patch with Magisk
  5. Flash via fastboot
  6. Reboot and verify
"""

from pathlib import Path

from core.adb import ADB
from core.device import DeviceInfo
from core.fastboot import Fastboot
from methods.magisk import patch as magisk_patch
from utils.downloader import ASSETS_DIR
from utils.logger import info, success, warning, error, step


class FastbootRootError(Exception):
    pass


def _pull_boot_img(device: DeviceInfo, adb: ADB) -> Path:
    """Try to pull boot.img from the live device via dd + ADB."""
    out = ASSETS_DIR / "boot.img"
    if out.exists():
        info(f"Using existing boot.img: {out}")
        return out

    step("Trying to read boot partition via ADB ...")
    # Find the boot block device
    boot_dev = adb.shell(device.serial, "ls -l /dev/block/by-name/boot 2>/dev/null | awk '{print $NF}'")
    if not boot_dev:
        boot_dev = adb.shell(device.serial, "ls /dev/block/by-name/boot 2>/dev/null")
    if not boot_dev:
        raise FastbootRootError(
            "Cannot find boot partition block device via ADB.\n"
            f"  Please manually place the stock boot.img at: {out}"
        )

    info(f"Boot partition: {boot_dev}")
    tmp_remote = "/data/local/tmp/boot.img"
    adb.shell(device.serial, f"dd if={boot_dev} of={tmp_remote} bs=4096 2>/dev/null")
    if not adb.pull(device.serial, tmp_remote, str(out)):
        raise FastbootRootError(
            f"ADB pull failed. Manually place the stock boot.img at: {out}"
        )
    adb.shell(device.serial, f"rm {tmp_remote}")
    success(f"boot.img pulled → {out}")
    return out


def run(device: DeviceInfo, adb: ADB | None = None) -> None:
    fb = Fastboot()

    # ------------------------------------------------------------------
    # Step 1: Get boot.img (from ADB if available, else require manual)
    # ------------------------------------------------------------------
    boot_img = ASSETS_DIR / "boot.img"
    if not boot_img.exists():
        if adb and adb.is_connected(device.serial):
            boot_img = _pull_boot_img(device, adb)
        else:
            raise FastbootRootError(
                f"boot.img not found. Please place the stock boot.img at:\n  {boot_img}"
            )

    # ------------------------------------------------------------------
    # Step 2: Patch with Magisk
    # ------------------------------------------------------------------
    patched = magisk_patch(boot_img, abi=device.abi)

    # ------------------------------------------------------------------
    # Step 3: Reboot to fastboot and flash
    # ------------------------------------------------------------------
    info("Rebooting to fastboot mode ...")
    if adb and adb.is_connected(device.serial):
        adb.reboot(device.serial, "bootloader")

    input("\n[Press ENTER when the device is in fastboot mode (shows 'FASTBOOT' on screen)] ")

    fb_devs = fb.devices()
    if not fb_devs:
        raise FastbootRootError("No device found in fastboot mode.")
    serial = fb_devs[0]

    if not fb.is_unlocked(serial):
        raise FastbootRootError(
            "Bootloader is LOCKED. Cannot flash.\n"
            "  Enable OEM unlock in Developer Options, then run:\n"
            "    fastboot flashing unlock"
        )

    step("Flashing Magisk-patched boot image ...")
    if not fb.flash(serial, "boot", str(patched)):
        raise FastbootRootError("fastboot flash failed. Check output above.")

    success("Boot partition flashed!")

    step("Rebooting device ...")
    fb.reboot(serial)

    info("Device is rebooting. After it starts:")
    info("  1. Open Magisk app (install it if needed)")
    info("  2. Magisk will finish setting up root on first boot")
    success("Root installation complete via fastboot.")
