# Release Runbook

**Last updated:** 2026-04-16 (Phase 4 shipped)
**Canonical repo:** Chertixd/LoL-Draft-Helper (private -- code only)
**CDN repo:** Chertixd/lol-draft-helper-cdn (public -- data + updater manifest)

This document covers the updater key ceremony, release process, rollback procedures, and manual acceptance gates for the LoL Draft Analyzer desktop application.

---

## 1. Updater Key Ceremony

The Tauri auto-updater uses Ed25519 signatures to verify that updates are authentic. A key pair must be generated once and stored securely before any release build.

### 1.1 Key Generation

Run on your local machine (never in CI):

```bash
pnpm tauri signer generate -w ~/.tauri/lol-draft-analyzer.key
```

This produces:
- `~/.tauri/lol-draft-analyzer.key` -- the private key file (never commit this)
- The public key is printed to stdout

### 1.2 Three-Copy Storage

Store the private key and its passphrase in exactly three locations:

1. **GitHub Actions secrets** (on the code repo, NOT the CDN repo):
   - Secret name: `TAURI_SIGNING_PRIVATE_KEY` -- paste the entire file contents
   - Secret name: `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` -- paste the passphrase
   - Set at: https://github.com/Chertixd/LoL-Draft-Helper/settings/secrets/actions

2. **Password manager** (e.g., Bitwarden, KeePass):
   - Store both the key file contents and the passphrase as a single entry
   - Tag it so you can find it: "LoL Draft Analyzer Tauri signing key"

3. **Offline backup**:
   - Encrypted USB drive or printed QR code
   - Store in a physically secure location

### 1.3 Public Key Configuration

Paste the public key into `tauri.conf.json`:

```json
{
  "plugins": {
    "updater": {
      "pubkey": "<PASTE_PUBLIC_KEY_CONTENT_HERE>",
      "endpoints": [
        "https://chertixd.github.io/lol-draft-helper-cdn/latest.json"
      ]
    }
  }
}
```

Commit the updated `tauri.conf.json`. The public key is safe to commit -- it is used by installed clients to verify signatures, not to create them.

### 1.4 Critical Warnings

- **Use the Tauri v2 secret names:** `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. The Tauri v1 names (`TAURI_PRIVATE_KEY` / `TAURI_KEY_PASSWORD`) are silently ignored by Tauri v2, producing unsigned builds with no error.
- **NEVER prefix these secrets with `VITE_`.** Vite bundles all `VITE_*` environment variables into frontend assets, which would leak the private key to every user who downloads the app (ref: GHSA-2rcp-jvr4-r259).

---

## 2. Key Recovery

### If the GitHub Actions secret is lost

Restore from your password manager or offline backup. Re-add the secret at https://github.com/Chertixd/LoL-Draft-Helper/settings/secrets/actions.

### If ALL three copies are lost

The installed user base is locked to the old public key. Recovery requires a transitional release:

1. Generate a new key pair: `pnpm tauri signer generate -w ~/.tauri/lol-draft-analyzer-v2.key`
2. Ship a **transitional build** signed with the OLD key (if you still have access to any signed build pipeline) that updates `plugins.updater.pubkey` in `tauri.conf.json` to the NEW public key.
3. Once all clients have auto-updated to the transitional build (which now trusts the new key), switch CI to use the new private key.
4. Store the new key in all three locations per Section 1.2.

If no signed build pipeline exists at all (complete key loss with no backup), users must manually download and reinstall from the GitHub Release page. Document the situation in a GitHub Issue and pin it.

---

## 3. Key Rotation

Rehearse this procedure in a staging environment before performing it on the production release:

1. Generate a new key pair.
2. Ship a release **signed with the OLD key** that updates `plugins.updater.pubkey` to the NEW public key in `tauri.conf.json`.
3. Wait for all clients to auto-update to this transitional release.
4. Switch the GitHub Actions secrets (`TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) to the new key.
5. Store the new key in all three locations per Section 1.2.
6. Archive (do not delete) the old key -- it may be needed to sign hotfixes for users who missed the transitional release.

---

## 4. Release Process

### 4.1 Tagging a Release

1. Ensure all changes are merged to `master`.
2. Update `CHANGELOG.md` with the release date and any last-minute notes.
3. Create and push a version tag:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

4. The `.github/workflows/release.yml` workflow triggers automatically on `v*` tags.

### 4.2 What CI Does

The release workflow (`.github/workflows/release.yml`) performs these steps:

1. Checkout code
2. Set up Python 3.12, install dependencies, build PyInstaller sidecar
3. Set up Node 20 LTS / pnpm 9.2.0, install JS dependencies
4. Run `pnpm tauri build` (produces `.msi` + NSIS `-setup.exe` + `.sig` files)
5. Compute SHA256 hashes of both installers
6. Create a GitHub Release with both artifacts and hashes in the release notes
7. Construct `latest.json` from the `.sig` files and publish it to `gh-pages` on the CDN repo

### 4.3 Post-Release Verification

After CI completes:

- [ ] GitHub Release exists with both `.msi` and `-setup.exe` artifacts
- [ ] Release notes contain SHA256 hashes for both files
- [ ] `latest.json` is accessible at https://chertixd.github.io/lol-draft-helper-cdn/latest.json
- [ ] `latest.json` contains the correct version number and a valid signature

Verify `latest.json`:

```bash
curl -s https://chertixd.github.io/lol-draft-helper-cdn/latest.json | python -c "import json,sys; d=json.load(sys.stdin); print('version=%s sig_len=%d' % (d['version'], len(d['platforms']['windows-x86_64']['signature'])))"
```

### 4.4 Microsoft AV Submission

Within 24 hours of each tagged release, submit the `.exe` for false-positive review:

- URL: https://www.microsoft.com/en-us/wdsi/filesubmission
- Upload the NSIS `-setup.exe` (the file most likely to trigger AV)
- Select "Incorrectly detected as malware/malicious"
- Whitelisting is by file hash and applies to that exact binary

---

## 5. latest.json Rollback

If a bad release needs to be rolled back, revert `latest.json` on the CDN repo so the auto-updater stops offering the bad version:

```bash
git clone https://github.com/Chertixd/lol-draft-helper-cdn.git /tmp/cdn-rollback
cd /tmp/cdn-rollback
git fetch origin gh-pages
git log origin/gh-pages --oneline -10    # find the previous-good SHA
git push --force origin <prev-good-sha>:gh-pages
```

Wait up to 10 minutes for the GitHub Pages edge cache to propagate (Fastly CDN).

Verify the rollback:

```bash
curl -s https://chertixd.github.io/lol-draft-helper-cdn/latest.json | python -c "import json,sys; print(json.load(sys.stdin)['version'])"
```

The version should match the previous-good release, not the bad one.

**Important:** This only prevents new auto-updates. Users who already downloaded the bad release will keep it until they manually reinstall. If the bad release is dangerous (not just buggy), create a GitHub Issue and pin it with manual reinstall instructions.

---

## 6. Manual Acceptance Gates

Complete this checklist before announcing each release. These tests are manual and not automated in CI.

### Clean Install

- [ ] Clean-install on Windows 10 VM: MSI installs per-user, Start Menu entry created, app opens
- [ ] Clean-install on Windows 11 VM: same as above

### Core Functionality

- [ ] App detects LoL client within 3 seconds
- [ ] Recommendations produced for all 5 roles across Normal Draft / Ranked Solo/Duo / Ranked Flex / Clash
- [ ] LoL client close -> waiting view -> reopen -> auto-reconnect

### Stability

- [ ] 2h idle with LoL open: RAM growth < 50 MB
- [ ] 20 consecutive drafts without restart: no functional degradation

### Auto-Update

- [ ] Install v1.0.0, tag v1.0.1, updater prompts, install, relaunch on new version

### Uninstall

- [ ] Uninstaller removes app and cache from %APPDATA%
