#!/usr/bin/env python3
"""
RootDroid — Android Root Framework
For security research on devices you own.

Usage:
  python rootdroid.py detect           # detect connected Android device
  python rootdroid.py root             # auto-root (picks best method)
  python rootdroid.py root --method mtk_brom
  python rootdroid.py root --method fastboot
  python rootdroid.py patch <boot.img> # just patch a boot image with Magisk
"""

import argparse
import sys
from pathlib import Path


# --- ensure project root is on the import path ---
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import banner, info, success, warning, error, console
from rich.panel import Panel
from rich.table import Table


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _require_adb():
    from core.adb import ADB, ADBError
    try:
        return ADB()
    except ADBError as e:
        error(str(e))
        sys.exit(1)


def _pick_device(adb) -> dict:
    devs = adb.devices()
    if not devs:
        error("No Android device found via ADB.")
        info("Make sure:")
        info("  • USB debugging is enabled on the phone  (Settings → Developer Options → USB Debugging)")
        info("  • The USB cable supports data transfer (not charge-only)")
        info("  • You accepted the fingerprint prompt on the phone")
        sys.exit(1)
    if len(devs) == 1:
        return devs[0]
    console.print("\n[bold]Multiple devices found:[/bold]")
    for i, d in enumerate(devs):
        console.print(f"  [{i}] {d['serial']}  {d.get('model', '')}")
    idx = int(input("Select device number: ").strip())
    return devs[idx]


def _show_device(info_obj) -> None:
    from rich.markup import escape
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key",   style="dim")
    table.add_column("value", style="bold white")
    rows = [
        ("Brand",      f"{info_obj.brand} {info_obj.model}"),
        ("Android",    f"{info_obj.android_version}  (patch: {info_obj.security_patch})"),
        ("Chipset",    f"{info_obj.chipset}  [{info_obj.chipset_vendor.upper()}]"),
        ("ABI",        info_obj.abi),
        ("Kernel",     info_obj.kernel_version),
        ("Build",      info_obj.build_id),
        ("Bootloader", info_obj.bootloader),
        ("Rooted",     "YES" if info_obj.is_rooted else "no"),
    ]
    for k, v in rows:
        table.add_row(k, escape(v))
    console.print(Panel(table, title="[bold cyan]Device Info[/bold cyan]", border_style="cyan"))


# ──────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────

def cmd_detect(args) -> None:
    adb = _require_adb()
    dev = _pick_device(adb)

    from core.device import fetch_device_info
    from core.strategy import choose

    device_info = fetch_device_info(dev["serial"], adb)
    _show_device(device_info)

    strategy, reason = choose(device_info)
    console.print(f"\n[bold]Recommended strategy:[/bold] [green]{strategy}[/green]")
    console.print(f"[dim]{reason}[/dim]")


def cmd_root(args) -> None:
    from core.strategy import MTK_BROM, FASTBOOT_MAGISK, ALREADY_ROOTED, UNKNOWN

    # Determine method
    method = args.method  # may be None → auto-detect

    adb = None
    device_info = None

    if method != "mtk_brom":
        # Only need ADB for non-BROM paths
        try:
            adb = _require_adb()
            dev = _pick_device(adb)
            from core.device import fetch_device_info
            device_info = fetch_device_info(dev["serial"], adb)
            _show_device(device_info)
        except SystemExit:
            if method is None:
                warning("No ADB device found. Falling back to MTK BROM mode.")
                method = "mtk_brom"

    if method is None and device_info is not None:
        from core.strategy import choose
        method, reason = choose(device_info)
        info(f"Auto-selected method: {method}")
        info(f"Reason: {reason}")

    if method in (MTK_BROM, "mtk_brom"):
        abi = device_info.abi if device_info else "arm64-v8a"
        _do_mtk_brom(abi)

    elif method in (FASTBOOT_MAGISK, "fastboot"):
        if device_info is None:
            error("Device info unavailable. ADB connection required for fastboot method.")
            sys.exit(1)
        _do_fastboot(device_info, adb)

    elif method == ALREADY_ROOTED:
        success("Device is already rooted!")
        info("You can install Magisk Manager from the assets/ directory if it's not already installed.")

    else:
        error(f"Unsupported or unknown method: {method}")
        info("Run:  python rootdroid.py detect  to see the recommended method for your device.")
        sys.exit(1)


def _do_mtk_brom(abi: str) -> None:
    from methods.mtk_brom import run as brom_run, MTKBROMError
    try:
        brom_run(abi=abi)
    except MTKBROMError as e:
        error(f"MTK BROM failed:\n{e}")
        sys.exit(1)


def _do_fastboot(device_info, adb) -> None:
    from methods.fastboot_root import run as fb_run, FastbootRootError
    try:
        fb_run(device_info, adb)
    except FastbootRootError as e:
        error(f"Fastboot root failed:\n{e}")
        sys.exit(1)


def cmd_patch(args) -> None:
    from methods.magisk import patch as magisk_patch, MagiskPatchError
    boot_img = Path(args.boot_img)
    if not boot_img.exists():
        error(f"File not found: {boot_img}")
        sys.exit(1)
    abi = args.abi
    try:
        out = magisk_patch(boot_img, abi=abi)
        success(f"Patched image → {out}")
        info("Flash it with:  fastboot flash boot magisk_patched.img")
    except MagiskPatchError as e:
        error(str(e))
        sys.exit(1)


def cmd_install_magisk(args) -> None:
    """Push and install the Magisk APK to a connected ADB device."""
    adb = _require_adb()
    dev = _pick_device(adb)
    from utils.downloader import magisk_apk
    apk = magisk_apk()
    step_msg = f"Installing Magisk ({apk.name}) on {dev['serial']} ..."
    info(step_msg)
    if adb.install(dev["serial"], str(apk)):
        success("Magisk APK installed. Open it on the phone to finish setup.")
    else:
        error("APK install failed. Try manually: adb install assets/magisk.apk")


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    banner()

    parser = argparse.ArgumentParser(
        prog="rootdroid",
        description="Android root framework for security research.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # detect
    sub.add_parser("detect", help="Detect connected device and recommend rooting method")

    # root
    p_root = sub.add_parser("root", help="Root the connected device (auto or manual method)")
    p_root.add_argument(
        "--method",
        choices=["auto", "mtk_brom", "fastboot"],
        default="auto",
        help="Rooting method (default: auto-detect)",
    )

    # patch
    p_patch = sub.add_parser("patch", help="Patch a boot.img with Magisk (no device needed)")
    p_patch.add_argument("boot_img", help="Path to stock boot.img")
    p_patch.add_argument("--abi", default="arm64-v8a",
                         choices=["arm64-v8a", "armeabi-v7a"],
                         help="Target CPU ABI (default: arm64-v8a)")

    # install-magisk
    sub.add_parser("install-magisk", help="Download and install the Magisk APK via ADB")

    args = parser.parse_args()
    if args.method == "auto":
        args.method = None  # trigger auto-detect inside cmd_root

    dispatch = {
        "detect":          cmd_detect,
        "root":            cmd_root,
        "patch":           cmd_patch,
        "install-magisk":  cmd_install_magisk,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
