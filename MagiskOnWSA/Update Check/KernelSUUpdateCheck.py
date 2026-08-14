#!/usr/bin/python3
"""Check whether a newer KernelSU release is available and update the
kernelsu.appversion file + GITHUB_ENV message."""

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
        "https://raw.githubusercontent.com/MustardChef/WSABuilds/update/kernelsu.appversion",
        timeout=30).text.replace('\n', '')
except Exception:
    currentver = ""

if not looks_like_version(currentver):
    print(f"Stored version '{currentver[:40]}' is not a valid version, bootstrapping from latest.")
    currentver = ""

with open('kernelsu.appversion', 'w') as file:
    file.write(currentver)

try:
    latestver = json.loads(requests.get(
        "https://api.github.com/repos/tiann/kernelsu/releases/latest",
        timeout=30).content)['tag_name'].replace('v', '').replace('\n', '')
except Exception as exc:
    print(f"Failed to fetch latest KernelSU version: {exc}")
    exit(1)

if currentver != latestver:
    print("New version found: " + latestver)
    subprocess.Popen(git, shell=True, stdout=None, stderr=None, executable='/bin/bash').wait()
    with open('kernelsu.appversion', 'w') as file:
        file.write(latestver)
    kernelsumsg = f"Update KernelSU Version from `v{currentver}` to `v{latestver}`"
else:
    kernelsumsg = "KernelSU Version: `" + latestver + "`"

if env_file:
    with open(env_file, "a") as wr:
        wr.write(f"KERNEL_SU_MSG={kernelsumsg}\n")
