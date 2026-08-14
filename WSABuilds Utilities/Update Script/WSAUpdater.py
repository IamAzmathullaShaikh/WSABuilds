# WSAUpdater
# Version: 0.1.0
#
# This file is part of the WSABuilds project.
#
# WSAUpdater is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# WSAUpdater is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with WSAUpdater.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright (C) 2023 MustardChef
#
# WSAUpdater updates an existing Windows Subsystem for Android installation
# to the latest matching WSABuilds release:
#   1. Detects the installed WSA package (version) via Get-AppxPackage.
#   2. Finds the newest WSABuilds GitHub release for the current OS/arch.
#   3. Downloads and extracts the .7z archive (requires 7-Zip).
#   4. Launches the extracted Install.ps1 (which performs the upgrade).
#
# Usage:  python WSAUpdater.py [--dry-run]
# Run as Administrator.

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = "MustardChef/WSABuilds"
API_URL = f"https://api.github.com/repos/{REPO}/releases"
PACKAGE_PREFIX = "MicrosoftCorporationII.WindowsSubsystemForAndroid"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_powershell(command):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", command],
        capture_output=True, text=True)
    return result.stdout.strip()


def get_windows_info():
    build = run_powershell(
        "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').CurrentBuild")
    try:
        build = int(build)
    except ValueError:
        build = 0
    is_win11 = build >= 22000
    arch = os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64").lower()
    arch = "arm64" if "arm64" in arch else "x64"
    return ("Windows 11" if is_win11 else "Windows 10"), arch, build


def get_installed_wsa():
    out = run_powershell(
        f"Get-AppxPackage *{PACKAGE_PREFIX}* | Select-Object -ExpandProperty Version")
    return out


def api_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "WSAUpdater"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_release(win_os, arch):
    """Return (tag, asset_name, asset_url) of the newest matching release."""
    page = 1
    while page <= 10:
        releases = api_get(f"{API_URL}?per_page=100&page={page}")
        if not releases:
            break
        for release in releases:
            tag = release.get("tag_name", "")
            if release.get("draft"):
                continue
            if win_os == "Windows 11":
                prefix = "Windows_11_"
            else:
                prefix = "Windows_10_"
            if not tag.startswith(prefix):
                continue
            if arch == "arm64":
                if not tag.endswith("_arm64"):
                    continue
            else:
                if tag.endswith("_arm64"):
                    continue
            # For Windows 10 the artifact carries a _Windows_10 suffix
            suffix = "_Windows_10.7z" if win_os == "Windows 10" else ".7z"
            for asset in release.get("assets", []):
                name = asset["name"]
                if name.endswith(suffix) and not name.endswith("_Windows_10.7z"):
                    pass
                if win_os == "Windows 10":
                    if not name.endswith("_Windows_10.7z"):
                        continue
                else:
                    if name.endswith("_Windows_10.7z"):
                        continue
                    if not name.endswith(".7z"):
                        continue
                return tag, name, asset["browser_download_url"]
        page += 1
    return None, None, None


def download(url, dest):
    print(f"Downloading {os.path.basename(dest)} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "WSAUpdater"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r  {pct}% ({done // (1024 * 1024)} MiB / {total // (1024 * 1024)} MiB)", end="", flush=True)
    print()


def find_7z():
    for candidate in (
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description="Update WSA to the latest WSABuilds release")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and report what would be updated without downloading")
    args = parser.parse_args()

    if not is_admin():
        print("Please run this script as an administrator.")
        sys.exit(1)

    win_os, arch, build = get_windows_info()
    print(f"Detected: {win_os} (build {build}), {arch}")

    installed = get_installed_wsa()
    if not installed:
        print(f"No WSA installation found ({PACKAGE_PREFIX}*). Nothing to update.")
        sys.exit(0)
    print(f"Installed WSA version: {installed}")

    print("Looking for the latest matching WSABuilds release ...")
    try:
        tag, asset_name, asset_url = find_release(win_os, arch)
    except Exception as exc:
        print(f"Failed to query GitHub releases: {exc}")
        sys.exit(1)

    if not tag:
        print(f"No matching release found for {win_os} {arch}.")
        sys.exit(1)
    print(f"Latest release: {tag} ({asset_name})")

    if args.dry_run:
        print("Dry run: nothing was downloaded.")
        sys.exit(0)

    seven_zip = find_7z()
    if not seven_zip:
        print("7-Zip was not found. Please install it from https://www.7-zip.org/")
        sys.exit(1)

    tmp = tempfile.mkdtemp(prefix="wsaupdater-")
    try:
        archive = os.path.join(tmp, asset_name)
        download(asset_url, archive)

        extract_dir = os.path.join(tmp, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        print("Extracting archive ...")
        result = subprocess.run([seven_zip, "x", f"-o{extract_dir}", archive],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Extraction failed:\n{result.stdout}\n{result.stderr}")
            sys.exit(1)

        # The archive contains a single WSA_* folder with Run.bat / Install.ps1
        install_ps1 = None
        for root, _dirs, files in os.walk(extract_dir):
            if "Install.ps1" in files:
                install_ps1 = os.path.join(root, "Install.ps1")
                break
        if not install_ps1:
            print("Install.ps1 not found in the extracted archive.")
            sys.exit(1)

        print(f"\nLaunching installer: {install_ps1}")
        print("Follow the on-screen prompts to complete the update.")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", install_ps1], cwd=os.path.dirname(install_ps1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
