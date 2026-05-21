from dataclasses import dataclass, field
from core.adb import ADB
from utils.logger import info, warning


@dataclass
class DeviceInfo:
    serial: str
    brand: str = "unknown"
    model: str = "unknown"
    device: str = "unknown"
    android_version: str = "unknown"
    security_patch: str = "unknown"
    chipset: str = "unknown"
    platform: str = "unknown"
    hardware: str = "unknown"
    kernel_version: str = "unknown"
    build_id: str = "unknown"
    abi: str = "arm64-v8a"
    chipset_vendor: str = "unknown"   # mediatek | qualcomm | samsung | unisoc | unknown
    bootloader: str = "unknown"       # locked | unlocked | unknown
    baseband: str = ""
    is_rooted: bool = False

    @property
    def is_mediatek(self) -> bool:
        return self.chipset_vendor == "mediatek"

    @property
    def is_qualcomm(self) -> bool:
        return self.chipset_vendor == "qualcomm"

    def summary(self) -> str:
        rooted = "[green]YES[/green]" if self.is_rooted else "[red]no[/red]"
        bl = {
            "unlocked": "[green]UNLOCKED[/green]",
            "locked": "[red]locked[/red]",
        }.get(self.bootloader, self.bootloader)
        return (
            f"  Brand      : {self.brand} {self.model} ({self.device})\n"
            f"  Android    : {self.android_version}  (patch: {self.security_patch})\n"
            f"  Chipset    : {self.chipset}  [{self.chipset_vendor.upper()}]\n"
            f"  ABI        : {self.abi}\n"
            f"  Kernel     : {self.kernel_version}\n"
            f"  Build      : {self.build_id}\n"
            f"  Bootloader : {bl}\n"
            f"  Rooted     : {rooted}"
        )


def _vendor(platform: str, hardware: str, baseband: str) -> str:
    s = f"{platform} {hardware} {baseband}".lower()
    if any(k in s for k in ("mt", "mediatek", "moly", "helio", "dimensity", "alps")):
        return "mediatek"
    if any(k in s for k in ("qcom", "qualcomm", "msm", "sdm", "sm8", "sm7", "sm6")):
        return "qualcomm"
    if any(k in s for k in ("exynos", "universal")):
        return "samsung"
    if any(k in s for k in ("unisoc", "spreadtrum", "sc9", "ums")):
        return "unisoc"
    return "unknown"


def fetch_device_info(serial: str, adb: ADB) -> DeviceInfo:
    info(f"Reading device info for {serial} ...")

    def p(prop: str) -> str:
        return adb.get_prop(serial, prop)

    platform  = p("ro.board.platform")
    hardware  = p("ro.hardware")
    baseband  = p("gsm.version.baseband")
    mtk_chip  = p("ro.mediatek.platform")

    uid_line  = adb.shell(serial, "id")
    is_rooted = "uid=0" in uid_line

    abi_list = p("ro.product.cpu.abilist")
    if "arm64" in abi_list:
        abi = "arm64-v8a"
    elif "armeabi" in abi_list:
        abi = "armeabi-v7a"
    else:
        abi = "arm64-v8a"

    vendor = _vendor(platform, hardware, baseband)
    # If MTK, prefer the mtk-specific chip name
    chipset = mtk_chip if vendor == "mediatek" and mtk_chip else platform

    return DeviceInfo(
        serial=serial,
        brand=p("ro.product.brand"),
        model=p("ro.product.model"),
        device=p("ro.product.device"),
        android_version=p("ro.build.version.release"),
        security_patch=p("ro.build.version.security_patch"),
        chipset=chipset,
        platform=platform,
        hardware=hardware,
        kernel_version=adb.shell(serial, "uname -r"),
        build_id=p("ro.build.display.id"),
        abi=abi,
        chipset_vendor=vendor,
        bootloader="unknown",
        baseband=baseband,
        is_rooted=is_rooted,
    )
