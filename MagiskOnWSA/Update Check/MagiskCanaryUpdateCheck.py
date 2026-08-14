#!/usr/bin/python3
"""Check whether a newer Magisk canary release is available and update the
magiskcanary.appversion file + GITHUB_ENV message."""

import os
import json
import requests
import logging
import subprocess

logging.captureWarnings(True)
env_file = os.getenv('GITHUB_ENV')

# Create the update branch from the current HEAD instead of discarding the
# whole working tree with an orphan branch when the branch does not exist yet.
git = (
    "git checkout -f update 2>/dev/null || git checkout -b update"
)


def looks_like_version(value: str) -> bool:
    """Reject garbage (e.g. a 404 HTML page from a missing update branch)."""
    return bool(value) and len(value) < 40 and any(ch.isdigit() for ch in value)


try:
    currentver = requests.get(
        "https://raw.githubusercontent.com/MustardChef/WSABuilds/update/magiskcanary.appversion",
        timeout=30).text.replace('\n', '')
except Exception:
    currentver = ""

if not looks_like_version(currentver):
    print(f"Stored version '{currentver[:40]}' is not a valid version, bootstrapping from latest.")
    currentver = ""

with open('magiskcanary.appversion', 'w') as file:
    file.write(currentver)

try:
    latestver = json.loads(requests.get(
        "https://github.com/topjohnwu/magisk-files/raw/master/canary.json",
        timeout=30).content)['magisk']['version'].replace('\n', '')
except Exception as exc:
    print(f"Failed to fetch latest Magisk canary version: {exc}")
    exit(1)

if currentver != latestver:
    print("New version found: " + latestver)
    subprocess.Popen(git, shell=True, stdout=None, stderr=None, executable='/bin/bash').wait()
    with open('magiskcanary.appversion', 'w') as file:
        file.write(latestver)
    magiskcanarymsg = f"Update Magisk Canary Version from `v{currentver}` to `v{latestver}`"
else:
    magiskcanarymsg = "Magisk Canary Version: `" + latestver + "`"

if env_file:
    with open(env_file, "a") as wr:
        wr.write(f"MAGISK_CANARY_MSG={magiskcanarymsg}\n")
