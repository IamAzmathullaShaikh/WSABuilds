#!/usr/bin/python3
# =============================================================================
# extractMagisk.py — Extract Magisk binaries from stable ZIP for WSABuilds
#
# Reads a Magisk APK/ZIP (which is a ZIP file containing architecture-specific
# shared libraries), extracts the binaries needed by the initrd patcher, and
# records the version information in WSA_WORK_ENV.
#
# Extracted files (placed in <workdir>/magisk/):
#   magisk64        — main 64-bit daemon (x86_64 / arm64)
#   magisk32        — 32-bit shim daemon (x86 / armeabi-v7a) — if present
#   magisk          — single-ABI binary — if magisk64 is absent
#   init-ld         — dynamic linker bootstrap — if present
#   magiskinit      — init replacement binary (target arch)
#   magiskboot      — bootimg / cpio tool (host arch, run during build)
#
# Usage:
#   python3 extractMagisk.py <arch> <magisk_zip> <workdir>
#
# Arguments:
#   arch        Build target architecture: "x64" or "arm64"
#   magisk_zip  Path to magisk-stable.zip (or app-stable.apk)
#   workdir     Temp working directory.  magisk/ subdir is created here.
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

from __future__ import annotations

import os
import platform
import sys
import zipfile
from pathlib import Path
from typing import Any, OrderedDict

# ---------------------------------------------------------------------------
# Prop — simple Android .prop file parser / serialiser
# ---------------------------------------------------------------------------

class Prop(OrderedDict):
    """Parse and serialise Android .prop files while preserving all lines."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        for idx, line in enumerate(text.splitlines(keepends=False)):
            if "=" in line:
                key, _, value = line.partition("=")
                self[key] = value
            else:
                # Non-key=value lines (comments, blanks) are stored under a
                # synthetic dotted key so they survive a round-trip.
                self[f".{idx}"] = line

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: ANN401
        self[name] = value

    def __repr__(self) -> str:
        return "\n".join(
            self[k] if k.startswith(".") else f"{k}={self[k]}"
            for k in self
        )

    def get_or_fail(self, key: str) -> str:
        """Return value for key, or raise KeyError with a clear message."""
        if key not in self:
            raise KeyError(
                f"extractMagisk: expected key '{key}' not found in Magisk ZIP comment. "
                "The ZIP may be corrupt or from an unsupported version."
            )
        return self[key]


# ---------------------------------------------------------------------------
# Architecture mapping
# ---------------------------------------------------------------------------

# Maps build target arch → (primary ABI, secondary ABI)
_ABI_MAP: dict[str, tuple[str, str]] = {
    "x64":   ("x86_64",    "x86"),
    "arm64": ("arm64-v8a", "armeabi-v7a"),
}

def _host_arch() -> str:
    """Return the *host* build arch ("x64" or "arm64") based on the runner's machine type."""
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    print(
        f"extractMagisk: WARNING — unrecognised host machine '{platform.machine()}'; "
        "defaulting to x64 for magiskboot selection.",
        flush=True,
    )
    return "x64"


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_as(zf: zipfile.ZipFile, src_name: str, dest_name: str, dest_dir: Path) -> None:
    """Extract <src_name> from <zf> into <dest_dir> saving it as <dest_name>."""
    info = zf.getinfo(src_name)
    info.filename = dest_name          # redirect extraction path
    zf.extract(info, dest_dir)


def _try_extract_as(
    zf: zipfile.ZipFile,
    src_name: str,
    dest_name: str,
    dest_dir: Path,
) -> bool:
    """Like _extract_as but returns False (rather than raising) if src_name is absent."""
    if src_name in zf.namelist():
        _extract_as(zf, src_name, dest_name, dest_dir)
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) != 4:
        print(
            "Usage: extractMagisk.py <arch> <magisk_zip> <workdir>",
            file=sys.stderr,
        )
        sys.exit(1)

    arch       = sys.argv[1]
    magisk_zip = sys.argv[2]
    workdir    = Path(sys.argv[3])

    if arch not in _ABI_MAP:
        print(
            f"extractMagisk: ERROR — unsupported arch '{arch}'. "
            f"Expected one of: {list(_ABI_MAP.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)

    primary_abi, secondary_abi = _ABI_MAP[arch]
    host_arch   = _host_arch()
    host_abi, _ = _ABI_MAP[host_arch]

    magisk_dir = workdir / "magisk"
    magisk_dir.mkdir(parents=True, exist_ok=True)

    print(f"extractMagisk: opening {magisk_zip} …", flush=True)

    with zipfile.ZipFile(magisk_zip) as zf:
        # ── Version metadata ────────────────────────────────────────────────
        # Magisk embeds version info in the ZIP comment as NUL-separated
        # "key=value" pairs.  We convert NULs to newlines for our Prop parser.
        comment_text = zf.comment.decode(errors="replace").replace("\x00", "\n")
        props = Prop(comment_text)

        try:
            version_name = props.get_or_fail("version")
            version_code = props.get_or_fail("versionCode")
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        print(f"extractMagisk: Magisk {version_name} (code {version_code})", flush=True)

        # Enforce minimum version requirement (Magisk 26.0 / code 26000)
        try:
            if int(version_code) < 26000:
                print(
                    f"extractMagisk: ERROR — Magisk {version_name} ({version_code}) is too old. "
                    "WSABuilds requires Magisk 26.0+ (code ≥ 26000).",
                    file=sys.stderr,
                )
                sys.exit(1)
        except ValueError:
            print(
                f"extractMagisk: WARNING — could not parse versionCode '{version_code}' as int; "
                "skipping minimum version check.",
                flush=True,
            )

        # Write version to WSA_WORK_ENV so build.sh can use it in artifact naming
        env_path = os.environ.get("WSA_WORK_ENV")
        if env_path and Path(env_path).is_file():
            existing = Prop(Path(env_path).read_text())
            existing.MAGISK_VERSION_NAME = version_name
            existing.MAGISK_VERSION_CODE = version_code
            Path(env_path).write_text(repr(existing) + "\n")

        # ── Binary extraction ────────────────────────────────────────────────
        namelist = zf.namelist()

        # magisk64 + magisk32  (dual-ABI build, the norm for Magisk ≥ 24)
        if f"lib/{primary_abi}/libmagisk64.so" in namelist:
            _extract_as(zf, f"lib/{primary_abi}/libmagisk64.so",   "magisk64", magisk_dir)
            _extract_as(zf, f"lib/{secondary_abi}/libmagisk32.so", "magisk32", magisk_dir)
            print("extractMagisk: extracted magisk64 + magisk32", flush=True)
        else:
            # Single-ABI fallback (rare but possible for arm64-only builds)
            _extract_as(zf, f"lib/{primary_abi}/libmagisk.so", "magisk", magisk_dir)
            print("extractMagisk: extracted magisk (single-ABI)", flush=True)

        # init-ld  (introduced in Magisk 26.x for dynamic linker bootstrapping)
        if _try_extract_as(
            zf,
            f"lib/{primary_abi}/libinit-ld.so",
            "init-ld",
            magisk_dir,
        ):
            print("extractMagisk: extracted init-ld", flush=True)

        # magiskinit  (replaces /init in the ramdisk)
        _extract_as(zf, f"lib/{primary_abi}/libmagiskinit.so", "magiskinit", magisk_dir)
        print("extractMagisk: extracted magiskinit", flush=True)

        # magiskboot — must run on the *host* (build machine), not the target
        import shutil
        if sys.platform == "win32" or platform.system() == "Windows":
            host_mb = shutil.which("magiskboot") or shutil.which("magiskboot.exe") or r"C:\Users\BangerSoul\bin\magiskboot.exe"
            if host_mb and Path(host_mb).is_file():
                shutil.copy2(host_mb, magisk_dir / "magiskboot.exe")
                shutil.copy2(host_mb, magisk_dir / "magiskboot")
                print(f"extractMagisk: copied native Windows magiskboot from {host_mb}", flush=True)
            else:
                _extract_as(zf, f"lib/{host_abi}/libmagiskboot.so", "magiskboot", magisk_dir)
        else:
            _extract_as(zf, f"lib/{host_abi}/libmagiskboot.so", "magiskboot", magisk_dir)
            print(
                f"extractMagisk: extracted magiskboot (host={host_arch}/{host_abi})",
                flush=True,
            )

    print(f"extractMagisk: done — binaries in {magisk_dir}", flush=True)


if __name__ == "__main__":
    main()
