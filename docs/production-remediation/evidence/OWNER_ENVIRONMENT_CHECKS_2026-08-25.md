# Owner environment checks — 25 August 2026

These checks used isolated synthetic package data and did not access or modify
the owner's existing GODFIN database, credentials, statements, or application
settings.

| Environment | Result | Evidence | Remaining limitation |
| --- | --- | --- | --- |
| Apple Silicon Mac | Passed unpacked package verification | Exact application candidate `5ee71fa`; first start 991 ms; restart 822 ms; idle memory 598.8 MB; database preserved; trust and maintenance boundaries enforced; request-only integrations loaded | Unsigned/unnotarized; no installer/update/uninstall claim |
| Windows host `narahari-strix` | Passed unpacked package verification | Final repository HEAD `9a0fc3c` (same application tree as `5ee71fa`); repeatable first start 2.258 s; restart 1.955 s; idle memory 552.7 MB; database preserved; trust and maintenance boundaries enforced; request-only integrations loaded | Newly built unsigned binaries incurred a rejected one-time 19.230 s endpoint-security scan; Authenticode, installer/update/uninstall, SmartScreen, and clean-system acceptance remain open |
| Oracle Linux host | Not applicable to the x64 gate | Read-only system query reports Linux `aarch64` | This host cannot replace Linux x64 acceptance; exact-SHA Linux x64 native CI smoke already passes |
| macOS x64/Intel | Owner-deferred | Explicit owner instruction on 25 August 2026 | Reopen before Intel support is advertised or released |

The required-platform smoke decision relies on native GitHub Actions run
`32823401864` for macOS arm64, Windows x64, and Linux x64, plus the isolated
owner-Mac and owner-STRIX runs above. Real signed-installer lifecycle checks
remain release gates and must not be inferred from smoke evidence.
