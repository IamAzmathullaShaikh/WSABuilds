#!/usr/bin/python3
# =============================================================================
# generateMagiskLink.py — Download Magisk Stable for WSABuilds
#
# Fetches the latest Magisk *stable* release link from topjohnwu/magisk-files
# and queues it in an aria2c input file.  Also fetches the LSPosed/WSA-Addon
# cust.img overlay used by the build.
#
# Usage:
#   python3 generateMagiskLink.py <download_dir> <aria2_list_file>
#
# Arguments:
#   download_dir      Directory where downloaded files will be stored.
#   aria2_list_file   Path to the aria2c input file to append entries to.
#
# Environment:
#   GITHUB_TOKEN (optional)  GitHub personal access token to raise API rate
#                             limits. Read from a file named 'token' in the
#                             current working directory as a fallback.
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# GitHub authentication — raises rate limit from 60 to 5000 req/h
# ---------------------------------------------------------------------------

class _BearerAuth(requests.auth.AuthBase):
    """Attach a Bearer token to every outgoing request."""

    def __init__(self, token: str) -> None:
        self.token = token.strip()

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


def _load_github_auth() -> _BearerAuth | None:
    """Return a BearerAuth object from GITHUB_TOKEN env var or local token file."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token_path = Path.cwd() / "token"
        if token_path.is_file():
            token = token_path.read_text().strip()
            print("generateMagiskLink: using token file for authentication", flush=True)
    if token:
        return _BearerAuth(token)
    return None


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> tuple[Path, str]:
    if len(sys.argv) != 3:
        print(
            "Usage: generateMagiskLink.py <download_dir> <aria2_list_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    download_dir = Path(sys.argv[1]) if sys.argv[1] else Path.cwd().parent / "download"
    aria2_list = sys.argv[2]
    return download_dir, aria2_list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JSDELIVR_FALLBACK = (
    "https://fastly.jsdelivr.net/gh/topjohnwu/magisk-files@master/stable.json"
)
_GITHUB_PRIMARY = (
    "https://github.com/topjohnwu/magisk-files/raw/master/stable.json"
)


def _fetch_magisk_stable_link() -> str:
    """Return the APK/ZIP download URL for the latest Magisk stable release."""
    print("generateMagiskLink: fetching Magisk stable link …", flush=True)

    for url in (_GITHUB_PRIMARY, _JSDELIVR_FALLBACK):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                link = data["magisk"]["link"]
                version = data["magisk"].get("version", "?")
                vcode  = data["magisk"].get("versionCode", "?")
                print(
                    f"generateMagiskLink: Magisk stable {version} ({vcode}) — {link}",
                    flush=True,
                )
                return link
            print(
                f"generateMagiskLink: {url} returned HTTP {resp.status_code}, "
                "trying fallback …",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"generateMagiskLink: request failed ({exc}), trying fallback …", flush=True)

    print("generateMagiskLink: ERROR — could not fetch Magisk stable link from any source.", file=sys.stderr)
    sys.exit(1)


def _fetch_wsa_addon_cust_img(auth: _BearerAuth | None) -> str:
    """Return the browser_download_url for cust.img from LSPosed/WSA-Addon latest release."""
    print("generateMagiskLink: fetching cust.img from LSPosed/WSA-Addon …", flush=True)

    api_url = "https://api.github.com/repos/LSPosed/WSA-Addon/releases/latest"
    resp = requests.get(api_url, auth=auth, timeout=30)

    if resp.status_code == 200:
        assets = resp.json().get("assets", [])
        for asset in assets:
            if re.fullmatch(r"cust\.img", asset["name"]):
                url = asset["browser_download_url"]
                print(f"generateMagiskLink: cust.img — {url}", flush=True)
                return url
        print(
            "generateMagiskLink: ERROR — cust.img not found in WSA-Addon release assets.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Rate-limit handling
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        reset_ts = resp.headers.get("x-ratelimit-reset")
        reset_dt = (
            datetime.fromtimestamp(int(reset_ts)).isoformat()
            if reset_ts
            else "unknown"
        )
        print(
            f"generateMagiskLink: ERROR — GitHub API rate-limited. "
            f"Resets at {reset_dt}. "
            "Set GITHUB_TOKEN or place a token in a file named 'token'.",
            file=sys.stderr,
        )
        sys.exit(1)

    msg = resp.json().get("message", "(no message)")
    print(
        f"generateMagiskLink: ERROR — GitHub API {resp.status_code}: {msg}",
        file=sys.stderr,
    )
    sys.exit(1)


def _append_aria2_entry(list_path: Path, url: str, dest_dir: Path, filename: str) -> None:
    """Append one aria2c download entry to the list file."""
    with open(list_path, "a") as f:
        f.write(f"{url}\n")
        f.write(f"  dir={dest_dir}\n")
        f.write(f"  out={filename}\n")
    print(f"generateMagiskLink: queued {filename}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    download_dir, aria2_list_file = _parse_args()
    download_dir.mkdir(parents=True, exist_ok=True)

    auth = _load_github_auth()
    list_path = download_dir / aria2_list_file

    # 1. Magisk stable ZIP
    magisk_url = _fetch_magisk_stable_link()
    _append_aria2_entry(list_path, magisk_url, download_dir, "magisk-stable.zip")

    # 2. WSA-Addon cust.img (LSPosed overlay required by Magisk integration)
    cust_url = _fetch_wsa_addon_cust_img(auth)
    _append_aria2_entry(list_path, cust_url, download_dir, "cust.img")


if __name__ == "__main__":
    main()
