# Owner environment checks — 25 August 2026

These checks used isolated synthetic package data and did not access or modify
the owner's existing GODFIN database, credentials, statements, or application
settings.

| Environment | Result | Evidence | Remaining limitation |
| --- | --- | --- | --- |
| Apple Silicon Mac | Passed unpacked package verification | Exact application candidate `5ee71fa`; first start 991 ms; restart 822 ms; idle memory 598.8 MB; database preserved; trust and maintenance boundaries enforced; request-only integrations loaded | Unsigned/unnotarized; no installer/update/uninstall claim |
| Windows host `narahari-strix` | Not executed | SSH connection timed out before authentication; no remote state changed | Bring the host online for the later signed-installer lifecycle matrix; exact-SHA Windows x64 native CI smoke already passes |
| Oracle Linux host | Not applicable to the x64 gate | Read-only system query reports Linux `aarch64` | This host cannot replace Linux x64 acceptance; exact-SHA Linux x64 native CI smoke already passes |
| macOS x64/Intel | Owner-deferred | Explicit owner instruction on 25 August 2026 | Reopen before Intel support is advertised or released |

The required-platform smoke decision relies on native GitHub Actions run
`32823401864` for macOS arm64, Windows x64, and Linux x64, plus the isolated
owner-Mac run above. Real signed-installer lifecycle checks remain release
gates and must not be inferred from smoke evidence.
