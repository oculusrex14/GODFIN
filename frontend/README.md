# GODFIN desktop renderer

This React 19 + Vite application is the renderer for the local Electron app. It
talks only to the local FastAPI service and never owns credentials, filesystem
access, Node.js integration, or a remote financial-data connection.

Read [`../docs/ENGINEERING_GUIDE.md`](../docs/ENGINEERING_GUIDE.md) before
changing runtime boundaries or commands.

## Development

From the repository root:

```bash
npm ci --prefix frontend
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5200
```

Normally use `./start.sh` so the backend is ready before Vite starts. The safe
development default is `127.0.0.1`; private-LAN mode is an explicit app setting.

## Verification

```bash
npm --prefix frontend run test:auth
npm --prefix frontend run lint
npm --prefix frontend run build
```

The active bearer token is memory-only. A renderer reload or app relaunch must
return to the PIN screen. Do not add token persistence, remote scripts,
permissive navigation, or direct provider calls.
