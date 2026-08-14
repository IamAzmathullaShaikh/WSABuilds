#!/usr/bin/python3
"""Check for a newer Windows Subsystem for Android (Insider Fast / WIF) build
via Microsoft's FE3 delivery service and update the WIF.appversion file.

The FE3 XML request templates are read from the directory given in the
WSA_XML_DIR environment variable (GitHub runner layout independent), falling
back to the repo's own MagiskOnWSA/xml directory.
"""

import base64
import os
import html
import re
import sys
import requests
import logging
import subprocess

from typing import Any, OrderedDict
from xml.dom import minidom

from requests import Session
from packaging import version


class Prop(OrderedDict):
    def __init__(self, props: str = ...) -> None:
        super().__init__()
        for i, line in enumerate(props.splitlines(False)):
            if '=' in line:
                k, v = line.split('=', 1)
                self[k] = v
            else:
                self[f".{i}"] = line

    def __setattr__(self, __name: str, __value: Any) -> None:
        self[__name] = __value

    def __repr__(self):
        return '\n'.join(f'{item}={self[item]}' for item in self)


logging.captureWarnings(True)
env_file = os.getenv('GITHUB_ENV')

# Category ID of the Windows Subsystem for Android feed
cat_id = '858014f3-3934-4abe-8078-4aa193e74ca8'

release_type = "WIF"

session = Session()
session.verify = True

# Create the update branch from the current HEAD instead of discarding the
# whole working tree with an orphan branch when the branch does not exist yet.
git = (
    "git checkout -f update 2>/dev/null || git checkout -b update"
)

# Runner layout independent path to the FE3 XML request templates
xml_dir = os.environ.get(
    "WSA_XML_DIR",
    os.path.join(os.getcwd(), "MagiskOnWSA", "xml"),
)

# Fetch the Microsoft account user code (required to access the insider feed)
user_code = ""
try:
    response = requests.get(
        "https://api.github.com/repos/bubbles-wow/MS-Account-Token/contents/token.cfg",
        timeout=30)
    if response.status_code == 200:
        content = base64.b64decode(
            response.json()["content"].encode("utf-8")).decode("utf-8")
        props = Prop(content)
        user_code = props.get("user_code") or ""
        print("Successfully get user token from server!")
        print(f"Last update time: {props.get('update_time')}\n")
    else:
        print(f"Failed to get user token from server! Error code: {response.status_code}\n")
except Exception as exc:
    print(f"Failed to get user token from server! {exc}\n")

try:
    currentver = requests.get(
        "https://raw.githubusercontent.com/MustardChef/WSABuilds/update/WIF.appversion",
        timeout=30).text.replace('\n', '')
except Exception:
    currentver = ""

# Write for pushing later (keeps the stored version even if FE3 is unreachable)
try:
    with open('WIF.appversion', 'w') as file:
        file.write(currentver)
    print("WIF.appversion file written.")
except Exception as e:
    print(f"Error writing to file: {e}")

# Validate the stored version (first run / missing branch yields HTML garbage)
try:
    current = version.parse(currentver)
except Exception:
    print(f"Stored version '{currentver[:40]}' is not a valid version, treating as none")
    current = version.parse("0")


def query_fe3():
    """Return the newest WSA build version from FE3, or None on failure."""
    try:
        with open(os.path.join(xml_dir, "GetCookie.xml"), "r") as f:
            cookie_content = f.read().format(user_code)
        out = session.post(
            'https://fe3.delivery.mp.microsoft.com/ClientWebService/client.asmx',
            data=cookie_content,
            headers={'Content-Type': 'application/soap+xml; charset=utf-8'},
            timeout=60)
        doc = minidom.parseString(out.text)
        cookie = doc.getElementsByTagName('EncryptedData')[0].firstChild.nodeValue
        with open(os.path.join(xml_dir, "WUIDRequest.xml"), "r") as f:
            cat_id_content = f.read().format(user_code, cookie, cat_id, release_type)
        out = session.post(
            'https://fe3.delivery.mp.microsoft.com/ClientWebService/client.asmx',
            data=cat_id_content,
            headers={'Content-Type': 'application/soap+xml; charset=utf-8'},
            timeout=60)
        doc = minidom.parseString(html.unescape(out.text))
    except Exception as exc:
        print(f"Network/XML error while querying FE3: {exc}")
        return None

    filenames = {}
    for node in doc.getElementsByTagName('ExtendedUpdateInfo')[0].getElementsByTagName('Updates')[0].getElementsByTagName('Update'):
        node_xml = node.getElementsByTagName('Xml')[0]
        node_files = node_xml.getElementsByTagName('Files')
        if not node_files:
            continue
        for node_file in node_files[0].getElementsByTagName('File'):
            if node_file.hasAttribute('InstallerSpecificIdentifier') and node_file.hasAttribute('FileName'):
                filenames[node.getElementsByTagName('ID')[0].firstChild.nodeValue] = (
                    f"{node_file.attributes['InstallerSpecificIdentifier'].value}_{node_file.attributes['FileName'].value}",
                    node_xml.getElementsByTagName('ExtendedProperties')[0].attributes['PackageIdentityName'].value)

    identities = {}
    for node in doc.getElementsByTagName('NewUpdates')[0].getElementsByTagName('UpdateInfo'):
        node_xml = node.getElementsByTagName('Xml')[0]
        if not node_xml.getElementsByTagName('SecuredFragment'):
            continue
        id_ = node.getElementsByTagName('ID')[0].firstChild.nodeValue
        update_identity = node_xml.getElementsByTagName('UpdateIdentity')[0]
        if id_ in filenames:
            fileinfo = filenames[id_]
            if fileinfo[0] not in identities:
                identities[fileinfo[0]] = ([update_identity.attributes['UpdateID'].value,
                                            update_identity.attributes['RevisionNumber'].value], fileinfo[1])

    wsa_build_ver = 0
    for filename in identities:
        if re.match(r"MicrosoftCorporationII\.WindowsSubsystemForAndroid_.*\.msixbundle", filename):
            tmp = re.search(r"\d{4}\.\d{5}\.\d{1,}\.\d{1,}", filename)
            if not tmp:
                continue
            tmp_wsa_build_ver = tmp.group()
            if wsa_build_ver == 0:
                wsa_build_ver = tmp_wsa_build_ver
            elif version.parse(wsa_build_ver) < version.parse(tmp_wsa_build_ver):
                wsa_build_ver = tmp_wsa_build_ver
    return wsa_build_ver


wsa_build_ver = query_fe3()
if wsa_build_ver in (None, 0):
    print("No WSA version information could be retrieved, skipping update check.")
    sys.exit(0)

try:
    latest = version.parse(wsa_build_ver)
except Exception:
    print(f"Invalid version returned by FE3: {wsa_build_ver}")
    sys.exit(0)

if current < latest:
    print(f"New version found: {wsa_build_ver}")
    subprocess.Popen(git, shell=True, stdout=None, stderr=None, executable='/bin/bash').wait()
    try:
        with open('WIF.appversion', 'w') as file:
            file.write(wsa_build_ver)
        print("WIF.appversion updated.")
    except Exception as e:
        print(f"Error writing to file: {e}")
    msg = f'Update WSA Version from `v{currentver}` to `v{wsa_build_ver}`'
    if env_file:
        with open(env_file, "a") as wr:
            wr.write("SHOULD_BUILD=yes\n")
            wr.write(f"RELEASE_TYPE={release_type}\n")
            wr.write(f"LATEST_WIF_VER={wsa_build_ver}\n")
            wr.write(f"MSG={msg}\n")
            wr.write("INSIDER_UPDATE=yes\n")
else:
    print(f"WSA WIF version is up to date: {currentver}")
