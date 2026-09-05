#!/usr/bin/python3
# =============================================================================
# fixGappsProp.py — Patch WSA build.prop files for GApps compatibility
#
# Google Play Services performs device certification checks using the values in
# /system/build.prop and /vendor/build.prop.  This script:
#
#   1. Sets brand/manufacturer to Google (required for GApps to activate)
#   2. Sets product/device/model to the spoofed device model (redfin = Pixel 5)
#   3. Recomputes ro.build.description and ro.build.fingerprint consistently
#   4. Stamps the build with the GApps variant name (pico) for diagnostics
#
# Usage:
#   python3 fixGappsProp.py <output_dir> <device_name> <device_model> [gapps_variant]
#
# Arguments:
#   output_dir      Path to the WSA output directory (contains system/, vendor/)
#   device_name     Android device codename, e.g. "redfin"
#   device_model    Android device model string, e.g. "Pixel 5"
#   gapps_variant   GApps variant label, e.g. "pico"  (default: pico)
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

from __future__ import annotations

import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Any, OrderedDict


# ---------------------------------------------------------------------------
# Prop — Android .prop file parser / serialiser
# ---------------------------------------------------------------------------

class Prop(OrderedDict):
    """Parse and round-trip Android .prop files, preserving comment lines."""

    def __init__(self, file: TextIOWrapper) -> None:
        super().__init__()
        for idx, line in enumerate(file.read().splitlines(keepends=False)):
            if "=" in line:
                key, _, value = line.partition("=")
                self[key] = value
            else:
                self[f".{idx}"] = line

    def __str__(self) -> str:
        return "\n".join(
            v if k.startswith(".") else f"{k}={v}"
            for k, v in self.items()
        )

    def __iadd__(self, comment: str) -> "Prop":
        """Append a bare comment / blank line."""
        self[f".{len(self)}"] = comment
        return self

    def get_safe(self, key: str, default: str = "") -> str:
        """Return value for key or default — never raises KeyError."""
        return self.get(key, default)


# ---------------------------------------------------------------------------
# Fingerprint / description helpers
# ---------------------------------------------------------------------------

def _description(section: str, p: Prop) -> str:
    """Reconstruct ro.<section>.build.description from component fields."""
    parts = [
        p.get_safe(f"ro.{section}.build.flavor"),
        p.get_safe(f"ro.{section}.build.version.release_or_codename"),
        p.get_safe(f"ro.{section}.build.id"),
        p.get_safe(f"ro.{section}.build.version.incremental"),
        p.get_safe(f"ro.{section}.build.tags"),
    ]
    return " ".join(parts)


def _fingerprint(section: str, p: Prop) -> str:
    """Reconstruct ro.<section>.build.fingerprint from component fields."""
    brand   = p.get_safe(f"ro.product.{section}.brand")
    name    = p.get_safe(f"ro.product.{section}.name")
    device  = p.get_safe(f"ro.product.{section}.device")
    release = p.get_safe(f"ro.{section}.build.version.release")
    build_id = p.get_safe(f"ro.{section}.build.id")
    incremental = p.get_safe(f"ro.{section}.build.version.incremental")
    build_type  = p.get_safe(f"ro.{section}.build.type")
    tags        = p.get_safe(f"ro.{section}.build.tags")
    return f"{brand}/{name}/{device}:{release}/{build_id}/{incremental}:{build_type}/{tags}"


# ---------------------------------------------------------------------------
# Core patcher
# ---------------------------------------------------------------------------

def _fix_prop(
    section: str,
    prop_path: str,
    device_name: str,
    device_model: str,
    gapps_variant: str,
) -> None:
    """Apply GApps-compatibility patches to a single build.prop file."""
    path = Path(prop_path)

    if not path.is_file():
        print(
            f"fixGappsProp: skipping missing file — {prop_path}",
            flush=True,
        )
        return

    print(f"fixGappsProp: patching {prop_path} …", flush=True)

    with open(path, "r") as f:
        p = Prop(f)

    # ── Annotation banner ────────────────────────────────────────────────────
    p += ""
    p += "# ── Extra props added by WSABuilds fixGappsProp.py ────────────────"
    p += f"# GApps variant : {gapps_variant}"
    p += f"# Device        : {device_name} / {device_model}"

    # ── Brand / manufacturer spoofing ────────────────────────────────────────
    # Play Services uses these to verify the device is a Google device.
    google_props: dict[tuple[str, str], str] = {
        ("product",  "brand"):        "google",
        ("system",   "brand"):        "google",
        ("product",  "manufacturer"): "Google",
        ("system",   "manufacturer"): "Google",
        ("build",    "product"):      device_name,
        ("product",  "name"):         device_name,
        ("system",   "name"):         device_name,
        ("product",  "device"):       device_name,
        ("system",   "device"):       device_name,
        ("product",  "model"):        device_model,
        ("system",   "model"):        device_model,
        ("build",    "flavor"):       f"{device_name}-user",
    }

    for (namespace, key), value in google_props.items():
        p[f"ro.{namespace}.{key}"] = value

        # Duplicate into the per-section namespace that GApps also reads
        if namespace == "build":
            p[f"ro.{section}.{namespace}.{key}"] = value
        elif namespace == "product":
            p[f"ro.{namespace}.{section}.{key}"] = value

    # ── GApps variant diagnostic stamp ──────────────────────────────────────
    p["ro.gapps.variant"] = gapps_variant

    # ── Fingerprint / description rebuild ────────────────────────────────────
    desc  = _description(section, p)
    fprint = _fingerprint(section, p)

    p["ro.build.description"]                = desc
    p["ro.build.fingerprint"]               = fprint
    p[f"ro.{section}.build.description"]    = desc
    p[f"ro.{section}.build.fingerprint"]    = fprint
    p["ro.bootimage.build.fingerprint"]     = fprint

    with open(path, "w") as f:
        f.write(str(p))

    print(f"fixGappsProp: done — {path.name}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 4:
        print(
            "Usage: fixGappsProp.py <output_dir> <device_name> <device_model> [gapps_variant]",
            file=sys.stderr,
        )
        sys.exit(1)

    sys_path      = sys.argv[1]
    device_name   = sys.argv[2]
    device_model  = sys.argv[3]
    gapps_variant = sys.argv[4] if len(sys.argv) > 4 else "pico"

    # Map of section → prop file path (relative to sys_path)
    prop_files: dict[str, str] = {
        "system":      f"{sys_path}/system/build.prop",
        "vendor":      f"{sys_path}/vendor/build.prop",
        "odm":         f"{sys_path}/vendor/odm/etc/build.prop",
        "vendor_dlkm": f"{sys_path}/vendor/vendor_dlkm/etc/build.prop",
    }

    for section, prop_path in prop_files.items():
        _fix_prop(section, prop_path, device_name, device_model, gapps_variant)

    print("fixGappsProp: all prop files patched.", flush=True)


if __name__ == "__main__":
    main()
