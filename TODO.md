# WSABuilds — Code Audit TODO (status: implemented)

All items below were implemented in this pass. ✅ = done, ⚠️ = done but needs a live
run/verification that cannot happen in this environment (GitHub Actions runs, Windows-only
runtime, live Microsoft FE3 queries).

Legend: 🔴 high / 🟠 medium / 🟢 feature.

---

## 🔴 Bugs

### 1. `update-downloadlinks.py` fails against the current README ✅
`MagiskOnWSA/Update Check/update-downloadlinks.py` now targets the 2-column table
(`Operating System` / `Download Page`); the header-count check uses `len(headers)`.
Functionally tested against the real README for both `WIF` and `retail` (correct cells updated).

### 2. Duplicate-tag guard in `update.yml` never fires ✅
"Stop workflow if tag exists" steps now reference the correct step ids
(`checkTag1`, `checkTag2`, `checkTag3`).

### 3. `buildtester.yml` broken against the new `build.sh` ✅
The tester now uses the `MagiskOnWSAOld` build system (which natively supports
`--gapps-brand`, `--custom-model`, `--after-compress`, `--release-type latest`, delta/alpha),
plus the missing deps (`patchelf`, `jq`, `p7zip-full`).

### 4. `generateKernelSULink.py` hardcodes `v2.1.2` ✅
Now fetches `releases/latest` (matches `KernelSUUpdateCheck.py`). Also fixed the invalid
`\d` escape / unescaped-dot regex in the kernel-version parse.

### 5. "Redfin"/custom device model dead in the new build path ✅
New `MagiskOnWSA/scripts/apply_custom_model.sh` mounts the system/vendor images, runs
`fixGappsProp.py` (Pixel prop spoofing), and repacks to vhdx. Wired into `build.yml` /
`buildarm64.yml` behind `devicemodel != none`. ⚠️ needs a live build to confirm image round-trip.

### 6. Old `build.sh` patches the wrong installer file ✅
All `sed` patches in `MagiskOnWSAOld/scripts/build.sh` now target `../installer/$ARCH/Install.ps1`
(the file actually shipped).

### 7. `windows10patch.ps1` undefined `$outputDir` ✅
Script now takes `-OutputDir` (default `.`), verifies the manifest exists, and downloads the
WSAPatch DLLs into `WsaClient/`. Used by `build.yml`, `build_old.yml` and `buildtester.yml`.

### 8. WSA checkers hardcode runner paths ✅
`WSAInsiderUpdateCheck.py` / `WSARetailUpdateCheck.py` read the FE3 XML templates from
`WSA_XML_DIR` (set by `update.yml` to the cloned MagiskOnWSALocal dirs) with a repo-local
fallback. Both scripts are now wired into `update.yml`'s check job and no longer `exit(1)`
on FE3 network failures.

### 9. `buildtester.yml` uses undefined `artifact_folder` output ✅
`buildtester.yml` build job now exports `artifact_folder`; make-pri folder paths use it and
archive names use `artifact`. The "Set date" step now writes `GITHUB_OUTPUT` (the cache key
used to be `artifact-`).

---

## 🟠 Issues

### 10. TLS verification disabled ✅
`session.verify = True` in `generateWSALinks.py`, `WSAUpdateChecker.py`, `WSAInsiderUpdateCheck.py`,
`WSARetailUpdateCheck.py`.

### 11. Massive duplication ✅ (mostly)
- `MagiskOnWSAOld/Update Check/` deleted (byte-identical to `MagiskOnWSA/Update Check/`).
- `MagiskOnWSA/DLL/` deleted (stale WSAPatch snapshot: its `lspinit` copies differ from the live
  `bin/` ones used by `build.sh`, `WsaPatch.dll` is downloaded fresh by `windows10patch.ps1`, and
  its docs duplicate the main `Documentation/`). Recoverable from git history if ever needed.
- `update.yml` build matrix: 26 copy-pasted jobs → 4 matrix jobs (`build_wif_x64`,
  `build_wif_arm64`, `build_retail_x64`, `build_retail_arm64`).

### 12. GApps source mismatch (checker vs downloader) ✅ (documented)
The build consumes `LSPosed/WSA-Addon` `.img/.rc` artifacts (mechanism requirement) while release
notes track upstream `MustardChef/MindTheGappsArchived`. `generateGappsLink.py` now records the
resolved `GAPPS_ADDON_TAG` into the build env; the split is documented in `MTGUpdateCheck.py`.
True unification would require changing the build mechanism, so it is documented rather than forced.

### 13. GitHub API callers crash on unexpected responses ✅
`generateMagiskLink.py` / `generateGappsLink.py` use `headers.get()`, handle non-200/non-403 with
a clear error + `exit(1)`, and reject unsupported Magisk release types early.

### 14. Large commented-out code blocks ✅
Removed the commented rclone/OneDrive blocks (both old workflows) and the commented make-pri block
(`build.yml`/`buildarm64.yml`) — the make-pri pipeline is restored as a real job (see #24).

### 15. `WSAUpdater.py` empty stub ✅
Implemented a functional updater: admin check, installed-WSA detection, latest matching release
lookup (OS/arch aware), download with progress, 7-Zip extraction, launches `Install.ps1`.
⚠️ Windows-only runtime, not executed here.

### 16. `WSAUninstaller.py` shortcut/dir cleanup flaws ✅
Shortcut deletion now resolves `.lnk` targets via `WScript.Shell` COM (realpath does not resolve
shortcuts); removed the bogus `%LocalAppData%\Local\Packages\...` path.
⚠️ Windows-only runtime, not executed here.

### 17. Destructive git patterns ✅
All `Update Check/*.py` + `update.yml` now use
`git checkout -f update 2>/dev/null || git checkout -b update` (no orphan-branch wipe).

### 18. Magisk min-version check can error on empty value ✅
`build.sh` guards with `[ -n "$MAGISK_VERSION_CODE" ]` before the `-lt 26000` comparison.

### 19. First-run bootstrapping of `.appversion` ✅
All four version checkers validate the stored version (`looks_like_version`) and bootstrap from
latest; both WSA checkers wrap `version.parse` and treat garbage as "none".

### 20. Hardcoded Windows Kit path ✅
`build_arm64_old.yml` / `buildarm64.yml` / `buildtester.yml` resolve the newest installed SDK's
arm64 `makepri.exe` instead of a fixed `10.0.22621.0` path.

### 21. Workflow inputs drift / dead code ✅
- `build_old.yml`/`build_arm64_old.yml` now declare + use `release_type` (the dead `RLS_TYPE`
  variable and hardcoded `--release-type latest` are gone); `update.yml` passes `release_type`
  to all four build workflows.
- Fixed the `artifact_folder }}}` stray-brace output typo in `build_arm64_old.yml`.
- Removed dead `steps.date.outputs.date` references in both old workflows.
- Deleted unreferenced `houdini.rc` + `init.windows.x64_64` (typo'd) from both libhoudini trees
  and the stray `MagiskOnWSA/arm64/makepri.exe`.

### 22. `extractWSA.py` unused variable ✅
Removed the unused `stat = Path(zip_path).stat()`.

---

## 🟢 Feature implementations

### 23. Wire device-model (Pixel) spoofing into the new build path ✅
See #5 — `apply_custom_model.sh` + workflow step.

### 24. Re-enable MakePri resource merging for new builds ✅
`build.yml` / `buildarm64.yml` now follow the proven `build_old.yml` pattern: ubuntu build →
upload artifact → windows-latest job (download, MakePri/x64 or newest-SDK makepri copy/arm64,
diskpart compact, compress, release upload). ⚠️ needs a live Actions run to confirm.

### 25. SHA-256 checksums on releases ✅
All four build workflows generate `sha256-checksum.txt` and attach it to the release uploads.

### 26. Parameterize KernelSU version ✅
See #4 — latest release instead of hardcoded tag.

### 27. Re-enable automated WSA version detection ✅
WSA insider/retail checkers run in `update.yml`'s check job; `wsa_ver` input is now optional and
falls back to the detected version per channel; builds/README/tags are gated on
`INSIDER_UPDATE`/`RETAIL_UPDATE`. ⚠️ live FE3 behavior unverified.

### 28. Single Windows 10 patch script ✅
`windows10patch.ps1` (parameterized) is now called by `build.yml`, `build_old.yml` and
`buildtester.yml` instead of three drifting inline copies.

### 29. CI linting ✅
New `.github/workflows/lint.yml`: actionlint (workflows), shellcheck (`-S warning`, all `.sh`),
`python3 -m compileall` (all `.py`). All three pass locally. The 8 shellcheck warnings in the
houdini installers were fixed (SC2155 x3, SC2024 documented).

### 30. Matrix-driven build configuration ✅
`update.yml` builds 26 job definitions → 4 `strategy.matrix` jobs (see #11).

### 31. OneDrive mirror publishing ✅ (removed)
Commented rclone steps and the now-unused `onedrivepath` env/outputs removed from both old
workflows; README mirrors were already gone.

---

## Verification performed
- ✅ `actionlint` (v1.7.12): 0 issues across all 7 workflows.
- ✅ `shellcheck` `-S warning`: 0 issues on all bash scripts.
- ✅ `bash -n` on all scripts.
- ✅ `python3 -m py_compile` on all Python sources (incl. the `\d` escape fix).
- ✅ `update-downloadlinks.py` functionally tested against the real README (WIF + retail).

## Remaining (cannot be verified here)
- Live GitHub Actions runs of the restructured release pipeline (#24, #27, new lint job).
- Windows-only runtime: `WSAUpdater.py`, `WSAUninstaller.py`, `windows10patch.ps1`, `MakePri.ps1`.
- Real image mount/repack round-trip in `apply_custom_model.sh`.
- Live FE3 queries (WSA version checkers) and the bubbles-wow MS account token availability.
- Live FE3/MS account token behavior and the `DLL/` snapshot was removed (stale/unreferenced;
  recoverable from git history).
