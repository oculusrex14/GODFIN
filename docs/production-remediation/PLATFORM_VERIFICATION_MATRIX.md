# GODFIN platform verification matrix

Recorded: 25 August 2026 (Asia/Kolkata)

Status vocabulary is restricted to `Passed`, `Failed`, `Partially verified`,
`Not executed`, and `Not applicable`. Source/config review is not presented as
native execution. The owner has explicitly deferred macOS x64/Intel acceptance;
it is not a required gate for this private candidate pass.

The exact application candidate is
`5ee71fabfe8c7f28726bf625b75801cb254b23a1`. Native GitHub Actions run
`32823401864` built and launched unpacked packages on hosted native runners.
Evidence JSON is retained under `docs/production-remediation/evidence/`.

| Requirement | macOS arm64 | macOS x64 | Windows x64 | Linux x64 | Evidence / limitation |
| --- | --- | --- | --- | --- | --- |
| Source build | Passed | Not executed (owner-deferred) | Passed | Passed | Exact-SHA native run plus seven-job `main` run `32827447450` |
| Unpacked package build | Passed | Not executed (owner-deferred) | Passed | Passed | Native run `32823401864`; no installer was uploaded or published |
| Unpacked launch | Passed: 2.098 s CI; 0.991 s owner Mac | Not executed (owner-deferred) | Passed: 3.886 s | Passed: 3.224 s | All are below the 8 s cold-start budget |
| Restart | Passed: 2.440 s CI; 0.822 s owner Mac | Not executed (owner-deferred) | Passed: 2.390 s | Passed: 2.360 s | Exact-SHA package verifier |
| Idle memory | Passed: 529.2 MB | Not executed (owner-deferred) | Passed: 488.1 MB | Passed: 498.5 MB | All are below the 700 MB budget |
| Backend startup | Passed | Not executed (owner-deferred) | Passed | Passed | Bundled backend reached loopback readiness on every required platform |
| Database creation and relaunch preservation | Passed | Not executed (owner-deferred) | Passed | Passed | Isolated synthetic user-data directory; preservation flag is true |
| Local trust / maintenance boundary | Passed | Not executed (owner-deferred) | Passed | Passed | Package verifier exercised trusted and rejected paths |
| Lazy request-only integrations | Passed | Not executed (owner-deferred) | Passed | Passed | Parser/account/Gmail request boundaries loaded after startup |
| Package executable hashes | Passed | Not executed (owner-deferred) | Passed | Passed | Desktop/backend SHA-256 values are retained in the evidence JSON |
| Database upgrade / restore | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Automated migration/restore suites pass; native interruption drills remain |
| Secure OS storage | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Unit/contracts pass; locked/unavailable OS-keyring cases remain manual-native |
| Statement import and reports | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Backend paths are packaged and regression-tested; native picker/font/real-layout acceptance remains |
| Local AI / Ollama | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Signed registry and lifecycle tests pass; native hardware/download lifecycle remains |
| Gmail OAuth | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Packaged callback code is present; fresh owner authorization and seven-day soak remain |
| License activation | Partially verified | Not executed (owner-deferred) | Partially verified | Partially verified | Signed entitlement/three-device contracts pass; clean three/four-device owner acceptance remains |
| Installer install/uninstall | Not executed | Not executed (owner-deferred) | Not executed | Not executed | Smoke workflow intentionally retained no installer artifact |
| Signed update/rollback | Not executed | Not executed (owner-deferred) | Not executed | Not executed | Requires signing identities, R2, immutable predecessor/candidate pair, and owner approval |
| Signing | Partially verified | Not executed (owner-deferred) | Not executed | Not applicable | macOS smoke package is ad-hoc only; Windows Authenticode identity is absent |
| Notarization | Not executed | Not executed (owner-deferred) | Not applicable | Not applicable | Apple Developer ID/notarization credentials are absent |

## Evidence files

- `native-smoke-macos-arm64-5ee71fa.json`
- `native-smoke-windows-x64-5ee71fa.json`
- `native-smoke-linux-x64-5ee71fa.json`
- `owner-macos-arm64-smoke-5ee71fa.json`

Each file records the exact commit, Actions run/job, runner OS/architecture,
launch and restart timing, idle memory, privacy-boundary results, executable
hashes, and the explicit facts that the package was unsigned, unpublished, and
not uploaded as an installer.

## Supported private-candidate decision

Apple Silicon, Windows x64, and Linux x64 now have exact-candidate native
unpacked-build and launch evidence. This closes the requested three-platform
smoke gate; it does not close signing, notarization, installer, update,
rollback, uninstall, real-provider, assistive-technology, or clean-owner-system
acceptance. macOS x64/Intel is explicitly deferred by the owner and must be
reopened before Intel support is advertised or released.
