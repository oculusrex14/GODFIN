# GODFIN desktop packaging

Repository architecture, supported versions, and shared verification commands
are defined in [`../docs/ENGINEERING_GUIDE.md`](../docs/ENGINEERING_GUIDE.md).
This file covers only the native desktop packaging surface.

Electron is a hardened shell around two bundled, local artifacts:

- `frontend/dist` is served through the privileged `godfin://app` protocol.
- `backend/dist/godfin-backend` is a native PyInstaller bundle listening only
  on `127.0.0.1:5100`.

The renderer has no Node.js integration or preload bridge. Context isolation,
Chromium sandboxing, navigation restrictions, denied permissions, CSP, a
single-instance lock, and Electron fuse hardening are enabled.

## Local packaging

Install the backend build dependency and desktop dependencies:

```bash
backend/venv/bin/python -m pip install --require-hashes -r backend/requirements-build-lock.txt
cd desktop
npm ci
npm run dist:mac
```

Build each operating system on that operating system. PyInstaller output is
native and must not be cross-compiled. The GitHub release workflow uses native
macOS x64/arm64, Windows x64, and Linux x64 runners.

Unsigned local builds are for smoke testing only. Production artifacts require:

- macOS: `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`,
  `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID`.
- Windows: `CSC_LINK` and `CSC_KEY_PASSWORD` for the Authenticode certificate.

Auto-update metadata points to `https://releases.godfin.dev`. The private
GitHub draft release is the review/staging record; public update assets must be
copied to the release bucket only after explicit owner authorization.
