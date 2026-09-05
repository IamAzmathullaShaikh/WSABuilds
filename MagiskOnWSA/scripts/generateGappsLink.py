#!/usr/bin/python3
# =============================================================================
# generateGappsLink.py — Download Pico-equivalent GApps for WSABuilds
#
# Fetches the latest minimal GApps image (gapps-13.0-x86_64.img) and the
# corresponding initrd mount script (gapps-13.0.rc) from LSPosed/WSA-Addon.
#
# This image contains the minimal GApps package (Play Store, Play Services,
# Services Framework) packaged as a ready-to-mount ext4 image for WSA Android 13.
#
# Usage:
#   python3 generateGappsLink.py <download_dir> <aria2_list_file> <android_api>
#
# Arguments:
#   download_dir      Directory where downloaded files will be stored.
#   aria2_list_file   Path to the aria2c input file to append entries to.
#   android_api       Android API level integer, e.g. 33
#
# Environment:
#   GITHUB_TOKEN (optional)   GitHub PAT. Falls back to ./token file.
#   WSA_WORK_ENV (optional)   Path to the build ENV file; metadata written here.
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class _BearerAuth(requests.auth.AuthBase):
    def __init__(self, token: str) -> None:
        self.token = token.strip()

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


def _load_github_auth() -> _BearerAuth | None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token_path = Path.cwd() / "token"
        if token_path.is_file():
            token = token_path.read_text().strip()
            print("generateGappsLink: using token file for authentication", flush=True)
    return _BearerAuth(token) if token else None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ANDROID_API_TO_RELEASE: dict[str, str] = {
    "30": "11.0",
    "32": "12.1",
    "33": "13.0",
}

_GAPPS_ARCH = "x86_64"
_WSA_ADDON_OWNER = "LSPosed"
_WSA_ADDON_REPO = "WSA-Addon"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> tuple[Path, str, str]:
    if len(sys.argv) < 3:
        print(
            "Usage: generateGappsLink.py <download_dir> <aria2_list_file> [android_api]",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_dir = sys.argv[1]
    list_file = sys.argv[2]
    android_api = sys.argv[3] if len(sys.argv) > 3 else "33"

    download_dir = Path(raw_dir) if raw_dir else Path.cwd().parent / "download"

    if android_api not in _ANDROID_API_TO_RELEASE:
        android_api = "33"

    return download_dir, list_file, android_api


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def _github_latest_release(owner: str, repo: str, auth: _BearerAuth | None) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    resp = requests.get(url, auth=auth, timeout=30)

    if resp.status_code == 200:
        return resp.json()

    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        reset_ts = resp.headers.get("x-ratelimit-reset")
        reset_dt = (
            datetime.fromtimestamp(int(reset_ts)).isoformat() if reset_ts else "unknown"
        )
        print(
            f"generateGappsLink: ERROR — GitHub API rate-limited for {owner}/{repo}. "
            f"Resets at {reset_dt}. Set GITHUB_TOKEN or place a token in ./token.",
            file=sys.stderr,
        )
        sys.exit(1)

    msg = resp.json().get("message", "(no message)") if resp.content else "(empty response)"
    print(
        f"generateGappsLink: ERROR — GitHub API {resp.status_code} for {owner}/{repo}: {msg}",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _append_aria2_entry(list_path: Path, url: str, dest_dir: Path, filename: str) -> None:
    with open(list_path, "a") as f:
        f.write(f"{url}\n")
        f.write(f"  dir={dest_dir}\n")
        f.write(f"  out={filename}\n")
    print(f"generateGappsLink: queued {filename}", flush=True)


def _write_env(key: str, value: str) -> None:
    env_path = os.environ.get("WSA_WORK_ENV")
    if env_path and os.path.isfile(env_path):
        with open(env_path, "a") as env_file:
            env_file.write(f"{key}={value}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    download_dir, aria2_list_file, android_api = _parse_args()
    download_dir.mkdir(parents=True, exist_ok=True)

    auth = _load_github_auth()
    list_path = download_dir / aria2_list_file
    release_str = _ANDROID_API_TO_RELEASE[android_api]

    print(
        f"generateGappsLink: fetching GApps artifacts for android={release_str}, arch={_GAPPS_ARCH} …",
        flush=True,
    )

    release = _github_latest_release(_WSA_ADDON_OWNER, _WSA_ADDON_REPO, auth)
    tag = release.get("tag_name", "v2")
    assets = release.get("assets", [])

    img_found = False
    rc_found = False

    img_pattern = re.compile(rf"gapps.*{re.escape(release_str)}.*{re.escape(_GAPPS_ARCH)}.*\.img$", re.I)
    rc_pattern = re.compile(rf"gapps.*{re.escape(release_str)}.*\.rc$", re.I)

    for asset in assets:
        name = asset["name"]
        url = asset["browser_download_url"]
        if img_pattern.search(name):
            _append_aria2_entry(list_path, url, download_dir, name)
            _write_env("GAPPS_IMAGE_NAME", name)
            img_found = True
            print(f"generateGappsLink: found GApps image: {name}", flush=True)
        elif rc_pattern.search(name):
            _append_aria2_entry(list_path, url, download_dir, name)
            _write_env("GAPPS_RC_NAME", name)
            rc_found = True
            print(f"generateGappsLink: found GApps RC: {name}", flush=True)

    if not img_found or not rc_found:
        print(
            f"generateGappsLink: ERROR — missing GApps image or RC in release {tag}. "
            f"Available assets: {[a['name'] for a in assets]}",
            file=sys.stderr,
        )
        sys.exit(1)

    _write_env("GAPPS_ADDON_TAG", tag)
    _write_env("GAPPS_VARIANT", "pico")

    print("generateGappsLink: done — GApps image & RC queued for download.", flush=True)


if __name__ == "__main__":
    main()
