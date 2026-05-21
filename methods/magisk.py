"""
Magisk boot image patcher.

Implements the same ramdisk injection that Magisk's boot_patch.sh performs,
but runs entirely on the host (macOS/Linux) using Python + system cpio.

Injection steps (Magisk v27 format):
  1. Backup /init → /.backup/init
  2. Replace /init with magiskinit binary
  3. Create overlay.d/sbin/ with magisk32.xz + magisk64.xz
  4. Write /.magisk/config
"""

import os
import shutil
import stat
from pathlib import Path

from core.boot_image import BootImage, BootImageError
from utils.downloader import magisk_apk, magisk_binary, magisk_xz, ASSETS_DIR
from utils.logger import info, success, step, warning


class MagiskPatchError(Exception):
    pass


def _fetch_binaries(abi: str) -> tuple[Path, Path | None, Path | None]:
    """Return (magiskinit, magisk32_xz, magisk64_xz). xz blobs may be None."""
    step("Fetching Magisk binaries ...")

    init_bin = magisk_binary("magiskinit", abi)

    m32 = m64 = None
    try:
        m32 = magisk_xz("magisk32")
    except FileNotFoundError:
        warning("magisk32.xz not found in APK — 32-bit support will be absent")
    try:
        m64 = magisk_xz("magisk64")
    except FileNotFoundError:
        warning("magisk64.xz not found in APK — 64-bit support will be absent")

    if m32 is None and m64 is None:
        raise MagiskPatchError("Neither magisk32.xz nor magisk64.xz could be extracted from the Magisk APK.")

    return init_bin, m32, m64


def _inject(extract_dir: Path, init_bin: Path, m32: Path | None, m64: Path | None) -> None:
    """Modify the extracted ramdisk directory in-place."""

    # 1. Back up original init
    original_init = extract_dir / "init"
    backup_dir    = extract_dir / ".backup"
    backup_dir.mkdir(exist_ok=True)
    if original_init.exists():
        shutil.move(str(original_init), str(backup_dir / "init"))

    # 2. Place magiskinit as new /init
    dest_init = extract_dir / "init"
    shutil.copy(init_bin, dest_init)
    dest_init.chmod(dest_init.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # 3. Create overlay structure
    overlay_sbin = extract_dir / "overlay.d" / "sbin"
    overlay_sbin.mkdir(parents=True, exist_ok=True)

    if m32 and m32.exists():
        shutil.copy(m32, overlay_sbin / "magisk32.xz")
    if m64 and m64.exists():
        shutil.copy(m64, overlay_sbin / "magisk64.xz")

    # 4. Write Magisk config
    magisk_dir = extract_dir / ".magisk"
    magisk_dir.mkdir(exist_ok=True)
    config = magisk_dir / "config"
    config.write_text(
        "KEEPVERITY=false\n"
        "KEEPFORCEENCRYPT=false\n"
        "PATCHVBMETA=false\n"
        "RECOVERYMODE=false\n"
    )


def patch(boot_img_path: Path, abi: str = "arm64-v8a") -> Path:
    """
    Patch boot.img at boot_img_path with Magisk.
    Returns path to the patched image.
    """
    info(f"Loading boot image: {boot_img_path}")
    try:
        img = BootImage.from_file(boot_img_path)
    except BootImageError as e:
        raise MagiskPatchError(f"Failed to parse boot image: {e}")

    init_bin, m32, m64 = _fetch_binaries(abi)

    step("Patching ramdisk ...")
    img.patch_ramdisk(lambda d: _inject(d, init_bin, m32, m64))

    out_path = ASSETS_DIR / "magisk_patched.img"
    img.save(out_path)
    success(f"Patched image saved → {out_path}")
    return out_path
