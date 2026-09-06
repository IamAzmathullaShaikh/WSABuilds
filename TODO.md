# WSABuilds — Code Audit & Roadmap TODO (status: fully implemented & verified)

All items below have been implemented and verified.
✅ = implemented & verified live, ⚠️ = implemented (CI / external dependency verification).

Legend: 🔴 high / 🟠 medium / 🟢 feature.

---

## 🔴 Critical Architectural & Boot Fixes

### 1. `initrd.img` Relative CPIO Entry Paths & Magisk 26+ Trampoline Architecture ✅
- **Issue**: Stock Microsoft WSA `initrd.img` stores the init binary under `init` (relative path). In addition, Magisk 26+ dynamic linker requires `overlay.d/sbin/init-ld.xz` and a `.backup` directory entry in the ramdisk. Without `init-ld.xz`, early boot halted, causing `vmmemWSA` termination and an infinite splash screen.
- **Fix**: Re-engineered ramdisk injection to generate the verified 15-entry SVR4 CPIO structure with `.backup`, symlink `init` -> `lspinit`, `magiskinit`, `wsainit`, CRC32-compressed `magisk.xz`, `init-ld.xz`, and `stub.xz`.
- **Live Verification**: Tested in live Android 13 runtime; `com.android.vending`, `com.google.android.gms`, `com.google.android.gsf`, and `com.topjohnwu.magisk` are fully operational.

### 2. Zero-Click ADB Authorization & Magisk Root Policy Automation ✅
- **Issue**: Fresh installations required interactive UI authorization prompts for ADB debugging (`AdbPromptRedirector`) and Magisk superuser requests, hanging automated workflows.
- **Fix**: Enhanced `build_local.py` to automatically inject the host's `adbkey.pub` into `overlay.d/sbin/adbkey.pub`, and updated `post-fs-data.sh` to pre-seed `/data/misc/adb/adb_keys` and configure Magisk's database (`/data/adb/magisk.db`) granting ADB shell (UID 2000) immediate superuser root privileges.
- **Live Verification**: ADB connects on `127.0.0.1:58526` immediately in state `device` (no `unauthorized`), and `su -c id` outputs `uid=0(root) gid=0(root) context=u:r:magisk:s0`.

### 3. GApps & Magisk SELinux Access Rules ✅
- **Issue**: Missing SELinux policies caused crashes and permission blocks on Google Play Services and system services communicating over vsock.
- **Fix**: Added explicit allow rules in `MagiskOnWSA/scripts/sepolicy.rule` for `gmscore`, `system_server tmpfs`, and vsock endpoints.

### 4. Invalid GitHub Action Versions in CI Workflows ✅
- **Issue**: `buildtester.yml`, `buildarm64.yml`, `build_old.yml`, `build_arm64_old.yml`, and `lint.yml` referenced non-existent `actions/checkout@v7`, `actions/setup-python@v6`, and `softprops/action-gh-release@v3`, preventing GitHub Actions from executing.
- **Fix**: Standardized all workflows on `actions/checkout@v4`, `actions/setup-python@v5`, and `softprops/action-gh-release@v2`.

---

## 🟠 Stability & Reliability Hardening

### 5. Native Windows Standalone Builder (`build_local.py`) ✅
- **Feature**: Developed a standalone, pure-Python Windows builder (`MagiskOnWSA/scripts/build_local.py`) that unpacks the WSA retail package, patches `initrd.img` with SVR4 CPIO binary parsing/repacking, injects Magisk/GApps payloads, and stages Windows runtime dependencies without requiring WSL or a Linux VM.

### 6. `WSAUninstaller.py` Restore Point Fault-Tolerance ✅
- **Issue**: `create_restore_point` crashed when Windows System Restore was disabled, aborting the uninstallation process.
- **Fix**: Wrapped registry configuration and PowerShell `Checkpoint-Computer` invocation in graceful exception handlers with fallback logging.

### 7. `WSAUpdater.py` Dynamic Repository Targeting ✅
- **Fix**: Added support for environment variable `WSABUILDS_REPO` and repository fallback (`IamAzmathullaShaikh/WSABuilds` -> `MustardChef/WSABuilds`), ensuring updates resolve properly regardless of upstream configuration.

### 8. Duplicate Nested Download Cleanup ✅
- **Fix**: Removed accidental redundant 287MB download folder inside `MagiskOnWSA/scripts/MagiskOnWSA/download`.

### 9. `Install.ps1` Typo Fix ✅
- **Fix**: Fixed spelling error in resource merge warning (`WSA Seetings` -> `WSA Settings`).

---

## 🟢 Documentation & Sync Status

### 10. README.md & Guide Modernization ✅
- Replaced outdated caution banners and obsolete 2025 bug notices with current verified status: Windows 11 / 10, Android 13 API 33, Magisk Stable, OpenGApps Pico.
- Updated `Documentation/Fix Guides/Post-Install Issues/Google Play Issues.md` with notes on the permanent initrd/SELinux resolution.

---

## Verification Matrix
- ✅ CPIO archive byte-level verification (`init` symlink -> `lspinit`, `wsainit` original init, `init-ld.xz`, `overlay.d/` tree).
- ✅ Real-time ADB Runtime Diagnostics (`test_runtime.py`): GApps (Store, GMS, GSF) PASS, Magisk App PASS, Magisk Root UID 0 PASS, Network 0% packet loss.
- ✅ Full clean purge and local rebuild from scratch executed and verified.
- ✅ Workflow linting (`lint.yml` action versions validated).
- ✅ Python compilation (`compileall` & `py_compile` pass on all scripts).
