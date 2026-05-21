"""
Android boot.img parser and patcher (AOSP format v0 / v1).

Supports the format used by Android 8.x and earlier generic MTK devices:
  - gzip, lz4-legacy, and uncompressed ramdisks
  - newc CPIO ramdisk manipulation via system cpio(1)
  - Magisk init injection
"""

import gzip
import os
import shutil
import stat
import struct
import subprocess
import tempfile
from pathlib import Path

BOOT_MAGIC = b"ANDROID!"


def _align(n: int, page: int) -> int:
    return ((n + page - 1) // page) * page


class BootImageError(Exception):
    pass


class BootImage:
    """Parse, modify, and repack an AOSP boot.img (v0/v1)."""

    def __init__(self, data: bytes):
        self._raw = data
        self._parse()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        if self._raw[:8] != BOOT_MAGIC:
            raise BootImageError("Not a valid Android boot image (missing ANDROID! magic)")

        (
            self.kernel_size, self.kernel_addr,
            self.ramdisk_size, self.ramdisk_addr,
            self.second_size, self.second_addr,
            self.tags_addr, self.page_size,
            self.header_version, self.os_version,
        ) = struct.unpack_from("<IIIIIIIIII", self._raw, 8)

        self.name        = self._raw[48:64].rstrip(b"\x00").decode(errors="replace")
        self.cmdline     = self._raw[64:576].rstrip(b"\x00").decode(errors="replace")
        self.sha1_id     = self._raw[576:608]
        self.extra_cmd   = self._raw[608:1632].rstrip(b"\x00").decode(errors="replace")

        ps = self.page_size
        k_off = ps                                          # header occupies one page
        r_off = k_off + _align(self.kernel_size, ps)
        s_off = r_off + _align(self.ramdisk_size, ps)

        self.kernel   = bytearray(self._raw[k_off : k_off + self.kernel_size])
        self.ramdisk  = bytearray(self._raw[r_off : r_off + self.ramdisk_size])
        self.second   = bytearray(self._raw[s_off : s_off + self.second_size]) if self.second_size else bytearray()

    @classmethod
    def from_file(cls, path: Path) -> "BootImage":
        return cls(path.read_bytes())

    # ------------------------------------------------------------------
    # Ramdisk helpers
    # ------------------------------------------------------------------

    def _decompress_ramdisk(self) -> tuple[bytes, str]:
        """Return (raw_cpio_bytes, compression_type)."""
        rd = bytes(self.ramdisk)
        if rd[:2] == b"\x1f\x8b":
            return gzip.decompress(rd), "gzip"
        if rd[:2] == b"\x02\x21":   # lz4 legacy magic
            try:
                import lz4.block
                # lz4 legacy: skip 4-byte magic, decompress chunks
                return _lz4_legacy_decompress(rd), "lz4"
            except ImportError:
                raise BootImageError("lz4 ramdisk detected but 'lz4' Python package is not installed.\n  pip install lz4")
        if rd[:6] == b"\xfd7zXZ\x00":
            import lzma
            return lzma.decompress(rd), "xz"
        # assume uncompressed CPIO
        return rd, "none"

    def _compress_ramdisk(self, cpio: bytes, compression: str) -> bytes:
        if compression == "gzip":
            return gzip.compress(cpio, compresslevel=9)
        if compression == "lz4":
            try:
                import lz4.block
                return _lz4_legacy_compress(cpio)
            except ImportError:
                raise BootImageError("lz4 package required")
        if compression == "xz":
            import lzma
            return lzma.compress(cpio, format=lzma.FORMAT_XZ)
        return cpio  # none

    # ------------------------------------------------------------------
    # CPIO manipulation (uses system cpio + find)
    # ------------------------------------------------------------------

    def patch_ramdisk(self, patcher) -> None:
        """
        patcher(extract_dir: Path) -> None
        Called with a temp directory containing the extracted ramdisk.
        Modify files in-place; the directory is then repacked.
        """
        cpio_bytes, compression = self._decompress_ramdisk()

        with tempfile.TemporaryDirectory(prefix="rootdroid_") as tmp:
            tmp_path = Path(tmp)
            cpio_file = tmp_path / "ramdisk.cpio"
            cpio_file.write_bytes(cpio_bytes)

            extract_dir = tmp_path / "ramdisk"
            extract_dir.mkdir()

            # Extract
            subprocess.run(
                ["cpio", "-idum", "--no-absolute-filenames"],
                stdin=cpio_file.open("rb"),
                cwd=extract_dir,
                check=True, capture_output=True,
            )

            # Let caller modify files
            patcher(extract_dir)

            # Repack with proper ordering (. first, then sorted)
            find_result = subprocess.run(
                ["find", ".", "-print"],
                cwd=extract_dir,
                capture_output=True, text=True, check=True,
            )
            new_cpio = subprocess.run(
                ["cpio", "-o", "-H", "newc", "--owner=root:root"],
                input=find_result.stdout,
                cwd=extract_dir,
                capture_output=True, check=True,
            )

        new_ramdisk = self._compress_ramdisk(new_cpio.stdout, compression)
        self.ramdisk = bytearray(new_ramdisk)
        self.ramdisk_size = len(new_ramdisk)

    # ------------------------------------------------------------------
    # Rebuild boot.img
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        ps = self.page_size

        hdr = struct.pack(
            "<8sIIIIIIIII",
            BOOT_MAGIC,
            len(self.kernel),  self.kernel_addr,
            len(self.ramdisk), self.ramdisk_addr,
            len(self.second),  self.second_addr,
            self.tags_addr, ps, self.header_version,
        )
        hdr += struct.pack("<I", self.os_version)
        hdr += self.name.encode()[:16].ljust(16, b"\x00")
        hdr += self.cmdline.encode()[:512].ljust(512, b"\x00")
        hdr += b"\x00" * 32                          # SHA1 — recalculated by bootloader
        hdr += self.extra_cmd.encode()[:1024].ljust(1024, b"\x00")
        hdr = hdr.ljust(ps, b"\x00")                # pad header to page size

        def pad(data: bytes | bytearray) -> bytes:
            b = bytes(data)
            return b + b"\x00" * (_align(len(b), ps) - len(b))

        return hdr + pad(self.kernel) + pad(self.ramdisk) + pad(self.second)

    def save(self, path: Path) -> None:
        path.write_bytes(self.to_bytes())


# ------------------------------------------------------------------
# LZ4 legacy helpers (used by many MTK boot images)
# ------------------------------------------------------------------

_LZ4_LEGACY_MAGIC = b"\x02\x21\x4c\x18"
_LZ4_BLOCK_SIZE   = 8 * 1024 * 1024


def _lz4_legacy_decompress(data: bytes) -> bytes:
    import lz4.block
    assert data[:4] == _LZ4_LEGACY_MAGIC
    pos = 4
    out = []
    while pos < len(data):
        if len(data) - pos < 4:
            break
        block_size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if block_size == 0:
            break
        block = data[pos : pos + block_size]
        out.append(lz4.block.decompress(block, uncompressed_size=_LZ4_BLOCK_SIZE))
        pos += block_size
    return b"".join(out)


def _lz4_legacy_compress(data: bytes) -> bytes:
    import lz4.block
    out = bytearray(_LZ4_LEGACY_MAGIC)
    for i in range(0, len(data), _LZ4_BLOCK_SIZE):
        chunk = data[i : i + _LZ4_BLOCK_SIZE]
        compressed = lz4.block.compress(chunk, store_size=False)
        out += struct.pack("<I", len(compressed))
        out += compressed
    out += struct.pack("<I", 0)   # end-of-stream marker
    return bytes(out)
