#!/usr/bin/python3
#
# This file is part of MagiskOnWSALocal.
#
# MagiskOnWSALocal is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# MagiskOnWSALocal is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with MagiskOnWSALocal.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright (C) 2024 LSPosed Contributors
#

from datetime import datetime
import sys

import requests
import json
import re
from pathlib import Path

arch = sys.argv[1]
arg4 = sys.argv[2]
download_dir = Path.cwd().parent / "download" if arg4 == "" else Path(arg4)
tempScript = sys.argv[3]
file_name = sys.argv[4]
print(f"Generating MindTheGapps download link: arch={arch}", flush=True)
abi_map = {"x64": "x86_64", "arm64": "arm64"}
res = requests.get(f"https://api.github.com/repos/YT-Advanced/MindTheGappsBuilder/releases/latest")
json_data = json.loads(res.content)
link = ""
if res.status_code == 200:
    assets = json_data["assets"]
    for asset in assets:
        if re.match(f'.*13\\.0\\.0.{abi_map[arch]}.*.zip$', asset["name"]):
            link = asset["browser_download_url"]
            break
elif res.status_code == 403 and res.headers.get("x-ratelimit-remaining") == '0':
    message = json_data["message"]
    print(f"Github API Error: {message}", flush=True)
    ratelimit_reset = res.headers.get("x-ratelimit-reset")
    if ratelimit_reset:
        print(f"The current rate limit window resets in {datetime.fromtimestamp(int(ratelimit_reset))}", flush=True)
    exit(1)
else:
    print(f"Github API Error: {res.status_code} - {json_data.get('message', '')}", flush=True)
    exit(1)

if not link:
    print(f"Error: No MindTheGapps asset found for arch={abi_map[arch]}", flush=True)
    exit(1)

print(f"download link: {link}", flush=True)

with open(download_dir/tempScript, 'a') as f:
    f.writelines(f'{link}\n')
    f.writelines(f'  dir={download_dir}\n')
    f.writelines(f'  out={file_name}\n')