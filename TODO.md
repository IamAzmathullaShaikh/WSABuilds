# WSABuilds — Code Audit & Roadmap TODO (status: fully implemented & verified)

All items below have been implemented and verified.
✅ = implemented & verified live, ⚠️ = implemented (CI / external dependency verification).

Legend: 🔴 high / 🟠 medium / 🟢 feature.

---

## 🔴 Critical Architectural & Boot Fixes

### 1. `initrd.img` relative CPIO entry paths for Magisk & GApps ✅
- **Issue**: Stock Microsoft WSA `initrd.img` stores the init binary under `init` (relative path). `build.sh` originally called `mv /init /wsainit` which `magiskboot cpio` ignored due to absolute path prefixing. As a result, `init` was never replaced with the `lspinit` trampoline, and Magisk/GApps overlays (`overlay.d/`) failed to mount.
- **Fix**: Changed CPIO commands to `mv init wsainit`, `add 0750 lspinit ...`, `ln lspinit init`, `add 0750 magiskinit ...`. Migrated to dynamic bash array command construction and added post-pack assertion `magiskboot cpio ... exists wsainit`.
- **Live Verification**: Tested in live Android 13 runtime; `com.android.vending`, `com.google.android.gms`, `com.google.android.gsf`, and `com.topjohnwu.magisk` are fully operational.

### 2. GApps & Magisk SELinux Access Rules ✅
- **Issue**: Missing SELinux policies caused crashes and permission blocks on Google Play Services and system services communicating over vsock.
- **Fix**: Added explicit allow rules in `MagiskOnWSA/scripts/sepolicy.rule` for `gmscore`, `system_server tmpfs`, and vsock endpoints.

### 3. Invalid GitHub Action Versions in CI Workflows ✅
- **Issue**: `buildtester.yml`, `buildarm64.yml`, `build_old.yml`, `build_arm64_old.yml`, and `lint.yml` referenced non-existent `actions/checkout@v7`, `actions/setup-python@v6`, and `softprops/action-gh-release@v3`, preventing GitHub Actions from executing.
- **Fix**: Standardized all workflows on `actions/checkout@v4`, `actions/setup-python@v5`, and `softprops/action-gh-release@v2`.

---

## 🟠 Stability & Reliability Hardening

### 4. Native Windows Standalone Builder (`build_local.py`) ✅
- **Feature**: Developed a standalone, pure-Python Windows builder (`MagiskOnWSA/scripts/build_local.py`) that unpacks the WSA retail package, patches `initrd.img` with SVR4 CPIO binary parsing/repacking, injects Magisk/GApps payloads, and stages Windows runtime dependencies without requiring WSL or a Linux VM.

### 5. `WSAUninstaller.py` Restore Point Fault-Tolerance ✅
- **Issue**: `create_restore_point` crashed when Windows System Restore was disabled, aborting the uninstallation process.
- **Fix**: Wrapped registry configuration and PowerShell `Checkpoint-Computer` invocation in graceful exception handlers with fallback logging.

### 6. `WSAUpdater.py` Dynamic Repository Targeting ✅
- **Fix**: Added support for environment variable `WSABUILDS_REPO` and repository fallback (`IamAzmathullaShaikh/WSABuilds` -> `MustardChef/WSABuilds`), ensuring updates resolve properly regardless of upstream configuration.

### 7. Duplicate Nested Download Cleanup ✅
- **Fix**: Removed accidental redundant 287MB download folder inside `MagiskOnWSA/scripts/MagiskOnWSA/download`.

### 8. `Install.ps1` Typo Fix ✅
- **Fix**: Fixed spelling error in resource merge warning (`WSA Seetings` -> `WSA Settings`).

---

## 🟢 Documentation & Sync Status

### 9. README.md & Guide Modernization ✅
- Replaced outdated caution banners and obsolete 2025 bug notices with current verified status: Windows 11 / 10, Android 13 API 33, Magisk Stable, OpenGApps Pico.
- Updated `Documentation/Fix Guides/Post-Install Issues/Google Play Issues.md` with notes on the permanent initrd/SELinux resolution.

---

## Verification Matrix
- ✅ CPIO archive byte-level verification (`init` symlink -> `lspinit`, `wsainit` original init, `overlay.d/` tree).
- ✅ Real-time ADB Runtime Diagnostics (`test_runtime.py`): GApps (Store, GMS, GSF) PASS, Magisk App PASS, Network 0% packet loss.
- ✅ Workflow linting (`lint.yml` action versions validated).
- ✅ Python compilation (`compileall` & `py_compile` pass on all scripts).
