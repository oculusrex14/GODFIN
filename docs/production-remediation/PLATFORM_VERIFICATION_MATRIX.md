# GODFIN platform verification matrix

Status vocabulary is restricted to `Passed`, `Failed`, `Partially verified`, `Not executed`, and `Not applicable`. Source/config review is not presented as native execution.

| Requirement | macOS arm64 | macOS x64 | Windows x64 | Linux x64 | Evidence | Status | External blocker | Owner action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Source build | Passed | Partially verified | Partially verified | Partially verified | Python/Node builds plus native-runner CI definitions | Partially verified | Non-arm64 native runners | Retain green native CI artifacts |
| Package build | Passed | Not executed | Not executed | Not executed | Private DMG/ZIP evidence at commit `25fd5f7` | Partially verified | Native machines/signing | Build exact final commit on each native runner |
| Launch | Passed | Not executed | Not executed | Not executed | Private arm64 app first start 3.0 s | Partially verified | Clean native systems | Run clean-install smoke |
| Backend startup | Passed | Not executed | Not executed | Not executed | Packaged PyInstaller backend, loopback readiness, backend auto-launch | Partially verified | Native packages | Verify port ownership/readiness on each platform |
| Database creation | Passed | Not executed | Not executed | Not executed | Fresh-lifecycle tests and arm64 package | Partially verified | Native packages | Start with empty user-data directory |
| Database upgrade | Passed | Not executed | Not executed | Not executed | Revision-19 fixture and isolated owner-copy rehearsal | Partially verified | Prior signed binaries/native packages | Run each supported predecessor fixture |
| Database restore | Passed | Not executed | Not executed | Not executed | Restore/rollback tests and packaged maintenance contract | Partially verified | Native failure/interruption matrix | Run corruption, permission, and power-loss drills |
| Secure storage | Passed | Not executed | Not executed | Not executed | macOS Keychain plus private-file fallback tests | Partially verified | Windows Credential Manager/Linux keyring package evidence | Verify locked/unlocked and unavailable-keyring cases |
| Statement import | Passed | Not executed | Not executed | Not executed | Strict parser tests and packaged local backend | Partially verified | Lawful real-layout corpus/native throughput | Run approved redacted corpus |
| Reports | Passed | Not executed | Not executed | Not executed | Deterministic report/tax-pack tests | Partially verified | Native PDF/font/pixel evidence | Render and reconcile on each native package |
| Local AI | Partially verified | Not executed | Not executed | Not executed | Signed registry and durable lifecycle tests; no final Ollama package matrix | Partially verified | Official Ollama/native hardware | Run install/cancel/crash/digest/benchmark matrix |
| Gmail flow | Passed | Not executed | Not executed | Not executed | Live packaged owner OAuth and initial sync | Partially verified | Google publication and other native packages | Keep private test user; later verify public consent requirements |
| License activation | Partially verified | Not executed | Not executed | Not executed | Signed local entitlement/three-device tests; owner-test path | Partially verified | Deployed signer/Supabase final evidence | Apply migrations and run clean three/four-device test |
| Update | Partially verified | Not executed | Not executed | Not executed | Update/recovery contracts and local private package | Partially verified | Signed immutable release/R2 | Exercise previous-to-candidate signed update |
| Rollback | Partially verified | Not executed | Not executed | Not executed | Immediate-predecessor snapshot restore tests | Partially verified | Signed predecessor/candidate pair | Exercise interrupted and completed rollback |
| Uninstall | Partially verified | Not executed | Not executed | Not executed | Data-preservation policy/package test; no clean uninstall UI evidence | Partially verified | Native installers | Uninstall/reinstall and verify Application Support retention |
| Data preservation | Passed | Not executed | Not executed | Not executed | Arm64 package verification and update/restore tests | Partially verified | Native installer matrix | Compare database/key/license/Gmail state before/after |
| Signing | Partially verified | Not executed | Not executed | Not applicable | Ad-hoc hardened-runtime signature only | Partially verified | Apple Developer ID and Windows certificate | Acquire identities; sign exact artifacts |
| Notarization | Not executed | Not executed | Not applicable | Not applicable | No Apple notarization credentials | Not executed | Apple Developer account/identity | Notarize and staple both Mac architectures |
| Checksums | Passed | Not executed | Not executed | Not executed | DMG/ZIP SHA-256 plus release workflow contracts | Partially verified | Exact native artifacts | Generate and independently verify final checksums |
| Package privacy | Passed | Not executed | Not executed | Not executed | Seven package privacy/integrity tests; inspected arm64 package | Partially verified | Native artifacts | Prove no DB/backups/OAuth/real statements in each package |

## Supported release decision

Only macOS arm64 has native private-package execution evidence, and even that artifact is ad-hoc signed and not authorized for public distribution. No Windows, Linux, macOS x64, notarization, or signed-update claim may be upgraded to `Passed` without retaining exact immutable artifact evidence.
