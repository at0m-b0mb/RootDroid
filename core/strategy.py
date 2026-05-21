from core.device import DeviceInfo

MTK_BROM       = "mtk_brom"
FASTBOOT_MAGISK = "fastboot_magisk"
ALREADY_ROOTED  = "already_rooted"
UNKNOWN         = "unknown"


def choose(device: DeviceInfo) -> tuple[str, str]:
    """Return (strategy_id, human_readable_reason)."""

    if device.is_rooted:
        return ALREADY_ROOTED, "Device is already rooted — Magisk may already be installed."

    if device.is_mediatek:
        return MTK_BROM, (
            "MediaTek chipset detected. "
            "Will use the BROM exploit (via mtkclient) — "
            "no bootloader unlock required."
        )

    if device.bootloader == "unlocked":
        return FASTBOOT_MAGISK, (
            "Bootloader is unlocked. "
            "Will patch boot.img with Magisk and flash via fastboot."
        )

    return UNKNOWN, (
        "Could not find a supported automatic rooting path.\n"
        "  Options:\n"
        "    • Enable OEM unlock in Developer Options, reboot to fastboot, run 'fastboot flashing unlock', then retry.\n"
        "    • If your device is MediaTek but was not detected, run: rootdroid.py detect --force-mtk"
    )
