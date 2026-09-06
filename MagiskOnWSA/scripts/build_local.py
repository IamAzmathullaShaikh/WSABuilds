"""
build_local.py — Native Windows standalone builder for WSABuilds

Enables building, assembling, and patching WSA packages with Magisk Stable
and OpenGApps Pico natively on Windows without requiring WSL or Linux.

Usage:
    python build_local.py
"""

from __future__ import annotations

import io
import lzma
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path


class CpioEntry:
    def __init__(self, name: str, data: bytes = b"", mode: int = 0o100644,
                 ino: int = 1, uid: int = 0, gid: int = 0, nlink: int = 1,
                 mtime: int = 0, devmajor: int = 0, devminor: int = 0,
                 rdevmajor: int = 0, rdevminor: int = 0, check: int = 0):
        self.name = name
        self.data = data
        self.mode = mode
        self.ino = ino
        self.uid = uid
        self.gid = gid
        self.nlink = nlink
        self.mtime = mtime
        self.devmajor = devmajor
        self.devminor = devminor
        self.rdevmajor = rdevmajor
        self.rdevminor = rdevminor
        self.check = check


def read_cpio_archive(path: Path) -> list[CpioEntry]:
    entries: list[CpioEntry] = []
    with open(path, "rb") as f:
        while True:
            header = f.read(110)
            if len(header) < 110:
                break
            magic = header[:6]
            if magic != b"070701":
                break
            ino = int(header[6:14], 16)
            mode = int(header[14:22], 16)
            uid = int(header[22:30], 16)
            gid = int(header[30:38], 16)
            nlink = int(header[38:46], 16)
            mtime = int(header[46:54], 16)
            filesize = int(header[54:62], 16)
            devmajor = int(header[62:70], 16)
            devminor = int(header[70:78], 16)
            rdevmajor = int(header[78:86], 16)
            rdevminor = int(header[86:94], 16)
            namesize = int(header[94:102], 16)
            check = int(header[102:110], 16)

            name_bytes = f.read(namesize)
            name = name_bytes.rstrip(b"\x00").decode("utf-8", errors="ignore")
            pad_name = (4 - ((110 + namesize) % 4)) % 4
            f.read(pad_name)

            data = f.read(filesize)
            pad_file = (4 - (filesize % 4)) % 4
            f.read(pad_file)

            entries.append(CpioEntry(
                name=name, data=data, mode=mode, ino=ino, uid=uid, gid=gid,
                nlink=nlink, mtime=mtime, devmajor=devmajor, devminor=devminor,
                rdevmajor=rdevmajor, rdevminor=rdevminor, check=check
            ))
            if name == "TRAILER!!!":
                break
    return entries


def write_cpio_archive(path: Path, entries: list[CpioEntry]) -> None:
    content_entries = [e for e in entries if e.name != "TRAILER!!!"]
    trailer = CpioEntry(name="TRAILER!!!", data=b"", mode=0, ino=0, uid=0, gid=0, nlink=1)
    content_entries.append(trailer)

    with open(path, "wb") as f:
        for e in content_entries:
            name_bytes = e.name.encode("utf-8") + b"\x00"
            namesize = len(name_bytes)
            filesize = len(e.data)

            header_str = (
                f"070701"
                f"{e.ino:08x}"
                f"{e.mode:08x}"
                f"{e.uid:08x}"
                f"{e.gid:08x}"
                f"{e.nlink:08x}"
                f"{e.mtime:08x}"
                f"{filesize:08x}"
                f"{e.devmajor:08x}"
                f"{e.devminor:08x}"
                f"{e.rdevmajor:08x}"
                f"{e.rdevminor:08x}"
                f"{namesize:08x}"
                f"{e.check:08x}"
            ).encode("ascii")

            f.write(header_str)
            f.write(name_bytes)
            pad_name = (4 - ((110 + namesize) % 4)) % 4
            if pad_name:
                f.write(b"\x00" * pad_name)

            if filesize > 0:
                f.write(e.data)
                pad_file = (4 - (filesize % 4)) % 4
                if pad_file:
                    f.write(b"\x00" * pad_file)


def compress_xz(data: bytes) -> bytes:
    return lzma.compress(data, format=lzma.FORMAT_XZ, preset=6)


def patch_initrd(initrd_path: Path, magisk_zip_path: Path, gapps_img_path: Path,
                 gapps_rc_path: Path, cust_img_path: Path, lspinit_path: Path,
                 post_fs_path: Path, init_lsp_rc_path: Path) -> None:
    print(f"[*] Reading stock initrd from {initrd_path} ...")
    entries = read_cpio_archive(initrd_path)
    print(f"    Loaded {len(entries)} CPIO entries from stock initrd.")

    with zipfile.ZipFile(magisk_zip_path, "r") as mz:
        stub_data = mz.read("stub.apk") if "stub.apk" in mz.namelist() else magisk_zip_path.read_bytes()
        magisk_data = mz.read("lib/x86_64/libmagisk.so") if "lib/x86_64/libmagisk.so" in mz.namelist() else b""
        magisk32_data = mz.read("lib/x86/libmagisk.so") if "lib/x86/libmagisk.so" in mz.namelist() else b""
        magiskinit_data = mz.read("lib/x86_64/libmagiskinit.so") if "lib/x86_64/libmagiskinit.so" in mz.namelist() else b""

    lspinit_data = lspinit_path.read_bytes()
    gapps_img_data = gapps_img_path.read_bytes()
    gapps_rc_data = gapps_rc_path.read_bytes()
    cust_img_data = cust_img_path.read_bytes()
    post_fs_data = post_fs_path.read_bytes()
    init_lsp_rc_data = init_lsp_rc_path.read_bytes()

    new_entries: list[CpioEntry] = []
    for e in entries:
        if e.name == "init":
            e.name = "wsainit"
            new_entries.append(e)
        elif e.name == "/init":
            e.name = "init"
            e.data = b"lspinit"
            e.mode = 0o120777
            new_entries.append(e)
        elif e.name in ("/lspinit", "lspinit"):
            e.name = "lspinit"
            e.data = lspinit_data
            e.mode = 0o100750
            new_entries.append(e)
        elif e.name in ("/magiskinit", "magiskinit"):
            e.name = "magiskinit"
            e.data = magiskinit_data
            e.mode = 0o100750
            new_entries.append(e)
        elif e.name.startswith("overlay.d/") or e.name == "overlay.d":
            continue
        else:
            new_entries.append(e)

    if not any(e.name == "init" for e in new_entries):
        new_entries.append(CpioEntry(name="init", data=b"lspinit", mode=0o120777))
    if not any(e.name == "lspinit" for e in new_entries):
        new_entries.append(CpioEntry(name="lspinit", data=lspinit_data, mode=0o100750))
    if not any(e.name == "magiskinit" for e in new_entries):
        new_entries.append(CpioEntry(name="magiskinit", data=magiskinit_data, mode=0o100750))

    new_entries.append(CpioEntry(name="overlay.d", mode=0o040750))
    new_entries.append(CpioEntry(name="overlay.d/sbin", mode=0o040750))
    new_entries.append(CpioEntry(name="overlay.d/init.lsp.magisk.rc", data=init_lsp_rc_data, mode=0o100644))
    new_entries.append(CpioEntry(name="overlay.d/gapps.rc", data=gapps_rc_data, mode=0o100644))
    new_entries.append(CpioEntry(name="overlay.d/sbin/post-fs-data.sh", data=post_fs_data, mode=0o100750))
    new_entries.append(CpioEntry(name="overlay.d/sbin/lsp_cust.img", data=cust_img_data, mode=0o100644))
    new_entries.append(CpioEntry(name="overlay.d/sbin/lsp_gapps.img", data=gapps_img_data, mode=0o100644))

    print("    Compressing Magisk payload binaries with XZ ...")
    if magisk_data:
        mag_xz = compress_xz(magisk_data)
        new_entries.append(CpioEntry(name="overlay.d/sbin/magisk.xz", data=mag_xz, mode=0o100644))
        new_entries.append(CpioEntry(name="overlay.d/sbin/magisk64.xz", data=mag_xz, mode=0o100644))
    if magisk32_data:
        new_entries.append(CpioEntry(name="overlay.d/sbin/magisk32.xz", data=compress_xz(magisk32_data), mode=0o100644))
    if stub_data:
        new_entries.append(CpioEntry(name="overlay.d/sbin/stub.xz", data=compress_xz(stub_data), mode=0o100644))

    bak_path = initrd_path.with_suffix(".img.bak")
    if not bak_path.exists():
        shutil.copy2(initrd_path, bak_path)

    print(f"[*] Writing patched initrd ({len(new_entries)} entries) to {initrd_path} ...")
    write_cpio_archive(initrd_path, new_entries)
    print("    Successfully wrote patched initrd.img!")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    magisk_on_wsa = script_dir.parent

    download_dir = magisk_on_wsa / "download"
    output_base = magisk_on_wsa / "output"
    bin_dir = magisk_on_wsa / "bin" / "x64"
    installer_dir = magisk_on_wsa / "installer"
    xml_dir = magisk_on_wsa / "xml"

    print("====================================================")
    print(" WSABuilds Native Local Builder (Windows / Pure Python)")
    print("====================================================")

    wsa_zip = download_dir / "wsa-retail.zip"
    magisk_zip = download_dir / "magisk-stable.zip"
    gapps_img = download_dir / "gapps-13.0-x86_64.img"
    gapps_rc = download_dir / "gapps-13.0.rc"
    cust_img = download_dir / "cust.img"
    lspinit = bin_dir / "lspinit"
    post_fs = script_dir / "post-fs-data.sh"
    init_lsp_rc = script_dir / "init.lsp.magisk.rc"

    for path, label in [
        (wsa_zip, "WSA Retail Archive"),
        (magisk_zip, "Magisk Stable Archive"),
        (gapps_img, "GApps Image"),
        (gapps_rc, "GApps RC"),
        (cust_img, "Cust Image"),
        (lspinit, "lspinit binary"),
    ]:
        if not path.exists():
            print(f"[-] ERROR: Required file not found: {label} ({path})")
            return 1

    print(f"[*] Inspecting {wsa_zip.name} ...")
    wsa_msix_name = ""
    wsa_ver = "2407.40000.4.0"
    with zipfile.ZipFile(wsa_zip, "r") as z:
        for name in z.namelist():
            if "x64" in name.lower() and name.endswith(".msix"):
                wsa_msix_name = name
                m = re.search(r'WsaPackage_([0-9.]+)_', name)
                if m:
                    wsa_ver = m.group(1)
                break

    if not wsa_msix_name:
        print("[-] ERROR: Could not locate x64 MSIX package inside wsa-retail.zip")
        return 1

    print(f"    Target x64 package: {wsa_msix_name}")
    print(f"    Detected WSA version: {wsa_ver}")

    output_dir = output_base / f"WSA_{wsa_ver}_x64"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_initrd = output_dir / "Tools" / "initrd.img"
    # If the output directory was already extracted, we can patch initrd directly from bak
    bak_path = target_initrd.with_suffix(".img.bak")
    if not target_initrd.exists() or not bak_path.exists():
        print(f"[*] Extracting {wsa_msix_name} directly to {output_dir} ...")
        with zipfile.ZipFile(wsa_zip, "r") as z:
            msix_bytes = z.read(wsa_msix_name)
            with zipfile.ZipFile(io.BytesIO(msix_bytes)) as msix:
                msix.extractall(output_dir)

    print("[*] Stripping Microsoft AppX signature metadata ...")
    for sig in ["[Content_Types].xml", "AppxBlockMap.xml", "AppxSignature.p7x", "AppxMetadata"]:
        p = output_dir / sig
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()

    # If bak exists, restore from bak first to patch from pristine stock
    if bak_path.exists():
        shutil.copy2(bak_path, target_initrd)

    patch_initrd(
        initrd_path=target_initrd,
        magisk_zip_path=magisk_zip,
        gapps_img_path=gapps_img,
        gapps_rc_path=gapps_rc,
        cust_img_path=cust_img,
        lspinit_path=lspinit,
        post_fs_path=post_fs,
        init_lsp_rc_path=init_lsp_rc,
    )

    print("[*] Staging Windows runtime dependencies and installer scripts ...")
    for appx in download_dir.glob("*.appx"):
        shutil.copy2(appx, output_dir / appx.name)

    if (bin_dir / "makepri.exe").exists():
        shutil.copy2(bin_dir / "makepri.exe", output_dir / "makepri.exe")

    (output_dir / "xml").mkdir(exist_ok=True)
    if (xml_dir / "priconfig.xml").exists():
        shutil.copy2(xml_dir / "priconfig.xml", output_dir / "xml" / "priconfig.xml")

    for f in ["MakePri.ps1", "Install.ps1", "Run.bat"]:
        src = installer_dir / f
        if src.exists():
            shutil.copy2(src, output_dir / f)

    filelist_path = output_dir / "filelist.txt"
    with open(filelist_path, "w", encoding="utf-8") as fl:
        for entry in sorted(output_dir.iterdir()):
            fl.write(f"{entry.name}\n")
    print("    Generated filelist.txt.")

    print("\n====================================================")
    print(f" Build completed successfully at: {output_dir}")
    print("====================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
