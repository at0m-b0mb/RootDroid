import json
import stat
import urllib.request
import zipfile
from pathlib import Path

from utils.logger import info, success, error

ASSETS_DIR = Path(__file__).parent.parent / "assets"
MAGISK_API = "https://api.github.com/repos/topjohnwu/Magisk/releases/latest"


def _github_latest_asset(api_url: str, suffix: str) -> tuple[str, str]:
    req = urllib.request.Request(api_url, headers={"User-Agent": "RootDroid/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    for asset in data.get("assets", []):
        if asset["name"].endswith(suffix):
            return asset["browser_download_url"], asset["name"]
    raise FileNotFoundError(f"No asset ending in '{suffix}' found in {api_url}")


def _download(url: str, dest: Path, label: str = "") -> Path:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    info(f"Downloading {label or dest.name} ...")

    def _progress(count, block, total):
        if total > 0:
            pct = min(count * block * 100 // total, 100)
            print(f"\r  {pct:3d}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=_progress)
    print()
    success(f"Saved → {dest}")
    return dest


def magisk_apk() -> Path:
    path = ASSETS_DIR / "magisk.apk"
    if path.exists():
        return path
    url, name = _github_latest_asset(MAGISK_API, ".apk")
    return _download(url, path, f"Magisk ({name})")


def _extract_from_apk(apk: Path, internal: str, dest: Path) -> Path:
    with zipfile.ZipFile(apk) as z:
        try:
            data = z.read(internal)
        except KeyError:
            raise FileNotFoundError(f"{internal} not found inside {apk.name}")
    dest.write_bytes(data)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return dest


def magisk_binary(name: str, abi: str = "arm64-v8a") -> Path:
    """Extract a binary (e.g. magiskinit, magisk64) from the Magisk APK for the given ABI."""
    apk = magisk_apk()
    dest = ASSETS_DIR / f"{name}_{abi}"
    if dest.exists():
        return dest
    internal = f"lib/{abi}/lib{name}.so"
    return _extract_from_apk(apk, internal, dest)


def magisk_xz(name: str, abi: str = "arm64-v8a") -> Path:
    """Extract a .xz blob (magisk32.xz / magisk64.xz) bundled inside the Magisk APK."""
    apk = magisk_apk()
    dest = ASSETS_DIR / f"{name}.xz"
    if dest.exists():
        return dest
    # Magisk stores these under assets/ inside the APK
    for candidate in [f"assets/{name}.xz", f"{name}.xz"]:
        try:
            return _extract_from_apk(apk, candidate, dest)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(f"{name}.xz not found in Magisk APK")
