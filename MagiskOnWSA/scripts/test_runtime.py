#!/usr/bin/python3
# =============================================================================
# test_runtime.py — Real-time WSA runtime tester and bug monitor
#
# Monitors WSA deployment, establishes ADB connection, and verifies:
#   1. Package deployment & version
#   2. Android VM boot state
#   3. Magisk root availability (`su -c id`)
#   4. OpenGApps / MindTheGapps components (Phonesky, GMSCore, GSF)
#   5. SELinux policy denials and runtime crashes
# =============================================================================

import os
import subprocess
import sys
import time

ADB = r"C:\Users\BangerSoul\bin\adb.exe"
WSA_PORT = "127.0.0.1:58526"

def run_cmd(cmd, shell=True):
    try:
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=15)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def wait_for_wsa_install(max_wait=600):
    print("[-] Checking WSA AppxPackage registration (waiting up to 10 minutes)...", flush=True)
    start = time.time()
    while time.time() - start < max_wait:
        code, out, _ = run_cmd('powershell.exe -Command "Get-AppxPackage -Name *WindowsSubsystemForAndroid* | Select-Object -ExpandProperty Version"')
        if code == 0 and out.strip():
            print(f"[+] WSA is installed! Version: {out.strip()}", flush=True)
            return True
        time.sleep(3)
    return False

def wait_for_adb_connection(max_wait=180):
    print(f"[-] Attempting to connect ADB to {WSA_PORT}...", flush=True)
    start = time.time()
    while time.time() - start < max_wait:
        code, out, _ = run_cmd(f'"{ADB}" connect {WSA_PORT}')
        if "connected to" in out.lower() or "already connected" in out.lower():
            print(f"[+] ADB connected successfully to {WSA_PORT}!", flush=True)
            return True
        # Also check `adb devices`
        _, dev_out, _ = run_cmd(f'"{ADB}" devices')
        if WSA_PORT in dev_out and "offline" not in dev_out:
            print(f"[+] ADB device detected: {dev_out}", flush=True)
            return True
        time.sleep(4)
    return False

def run_runtime_diagnostics():
    print("\n====================================================", flush=True)
    print(" Running Real-time Android Runtime Diagnostics", flush=True)
    print("====================================================\n", flush=True)

    # 1. Device and OS properties
    print("[*] Checking device & OS properties...", flush=True)
    _, model, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell getprop ro.product.model')
    _, android_ver, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell getprop ro.build.version.release')
    _, api_level, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell getprop ro.build.version.sdk')
    _, fingerprint, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell getprop ro.build.fingerprint')
    print(f"    Model        : {model}")
    print(f"    Android Ver  : {android_ver} (API {api_level})")
    print(f"    Fingerprint  : {fingerprint}")

    # 2. Magisk root check
    print("\n[*] Checking Magisk root availability...", flush=True)
    code, root_id, err = run_cmd(f'"{ADB}" -s {WSA_PORT} shell su -c "id"')
    if code == 0 and "uid=0(root)" in root_id:
        print(f"    [PASS] Root granted via Magisk! ({root_id})", flush=True)
    else:
        print(f"    [FAIL] Magisk root check failed: code={code}, out='{root_id}', err='{err}'", flush=True)

    # 3. Check Magisk daemon & files
    print("\n[*] Checking Magisk daemon & paths...", flush=True)
    _, magisk_ver, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell su -c "magisk -v"')
    _, magisk_code, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell su -c "magisk -V"')
    print(f"    Magisk binary version: {magisk_ver} ({magisk_code})")

    # 4. GApps package checks
    print("\n[*] Checking Google Play & GMS packages...", flush=True)
    _, packages, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} shell pm list packages -f')
    checks = {
        "Google Play Store (Phonesky)": "com.android.vending",
        "Google Play Services (GMS)": "com.google.android.gms",
        "Google Services Framework": "com.google.android.gsf",
        "Magisk Manager App": "com.topjohnwu.magisk"
    }
    for name, pkg in checks.items():
        if pkg in packages:
            print(f"    [PASS] {name} ({pkg}) is installed.")
        else:
            print(f"    [FAIL] {name} ({pkg}) is NOT found!")

    # 5. Check for SELinux / crashing errors in logcat
    print("\n[*] Checking logcat for fatal errors and SELinux denials...", flush=True)
    _, log_errors, _ = run_cmd(f'"{ADB}" -s {WSA_PORT} logcat -d -b main -b crash *:E')
    lines = [l for l in log_errors.splitlines() if any(k in l.lower() for k in ('fatal', 'crash', 'gmscore', 'magisk', 'denied'))]
    if lines:
        print(f"    Found {len(lines)} notable error lines in logcat (showing first 10):")
        for l in lines[:10]:
            print(f"      {l}")
    else:
        print("    [PASS] No fatal crashes or SELinux denials found in logcat!")

    print("\n====================================================", flush=True)
    print(" Diagnostics completed!", flush=True)
    print("====================================================\n", flush=True)

def main():
    if not wait_for_wsa_install(max_wait=60):
        print("[-] WSA is not registered yet.", flush=True)
        print("[-] Please run 'Run.bat' as Administrator from the output folder.", flush=True)
        return

    if not wait_for_adb_connection(max_wait=120):
        print("[-] Could not connect to WSA via ADB on 127.0.0.1:58526.", flush=True)
        print("[-] Please ensure WSA Settings has 'Developer Mode' enabled in Settings.", flush=True)
        return

    run_runtime_diagnostics()

if __name__ == "__main__":
    main()
