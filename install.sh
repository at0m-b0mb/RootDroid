#!/usr/bin/env bash
# RootDroid macOS setup script
set -e

echo ""
echo "╔═══════════════════════════════════╗"
echo "║  RootDroid — macOS Setup          ║"
echo "╚═══════════════════════════════════╝"
echo ""

# --- Homebrew ---
if ! command -v brew &>/dev/null; then
    echo "[!] Homebrew not found. Install it from https://brew.sh then re-run this script."
    exit 1
fi

echo "[*] Installing system dependencies via Homebrew..."
brew install libusb android-platform-tools 2>/dev/null || true

# --- Python packages ---
echo "[*] Installing Python packages..."
pip3 install --upgrade -r "$(dirname "$0")/requirements.txt"

# --- ADB / fastboot check ---
if ! command -v adb &>/dev/null; then
    echo "[!] adb still not found after brew install. Check your PATH."
    exit 1
fi
echo "[+] adb: $(adb version | head -1)"

# --- libusb check ---
if ! brew list libusb &>/dev/null; then
    echo "[!] libusb not installed — mtkclient may fail. Run: brew install libusb"
fi

# --- done ---
echo ""
echo "[+] Setup complete!"
echo ""
echo "    Detect your device:"
echo "      python3 rootdroid.py detect"
echo ""
echo "    Root your device (auto method):"
echo "      python3 rootdroid.py root"
echo ""
echo "    Root via MTK BROM (for your MediaTek phone):"
echo "      python3 rootdroid.py root --method mtk_brom"
echo ""
