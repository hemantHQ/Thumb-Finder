# Public distribution roadmap

## Phase 1 — Project foundation
- [x] Organize source, docs, scripts, tests, and packaging directories.
- [x] Establish one application version source.
- [x] Add contribution and security guidance.
- [x] Select Option A: no backend; CI-injected desktop API key.

## Phase 2 — GitHub automation
- [x] Add initial tagged Windows/macOS build and release workflow.
- [ ] Validate workflow on a test tag/release (not yet run on GitHub).
- [ ] Add CI syntax checks, tests, checksums, and release verification.

## Phase 3 — Public installers
- [ ] Create polished Windows installer.
- [x] Add macOS DMG packaging to the release workflow.
- [ ] Configure Windows signing and Apple Developer ID signing/notarization.

## Phase 4 — Mandatory updater
- [ ] Define signed update manifest and minimum supported version.
- [ ] Implement platform-aware update checks and downloads.
- [ ] Verify signatures/hashes and add recovery behavior.

## Phase 5 — Public beta
- [ ] Publish privacy policy and support contact.
- [ ] Test clean install, upgrade, recovery, and uninstall.
- [ ] Monitor API key usage/quota and verify API policy compliance.
