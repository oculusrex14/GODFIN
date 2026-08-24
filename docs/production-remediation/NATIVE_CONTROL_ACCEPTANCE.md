# Native and destructive control acceptance

This is the retained manual-evidence target for controls that cannot be exercised safely by an unattended browser run. It covers destructive actions, native file pickers, OS permission prompts, external-browser handoffs, backup restore, Gmail/Ollama installers, signing prompts, and Electron-only behavior.

The exact checklist is generated from the candidate source and production build:

```bash
cd /path/to/GODFIN_PRODUCTION/frontend
npm run verify:controls
```

Open `frontend/build/interactive-action-manifest.json`, filter `coverage.mode` to `manual-native`, and execute every item on the immutable candidate. For each control retain:

- control ID and accessible name;
- candidate SHA, artifact checksum, OS, architecture, app version, and channel;
- normal mouse/touch action and keyboard action;
- disabled/loading/empty/validation/offline behavior where listed;
- repeated/double-action protection;
- dialog focus return and Escape behavior where listed;
- 100%, 200%, and 400% zoom plus reduced-motion behavior;
- screenshot or trace filename and pass/fail result;
- tester name/date and defect reference if failed.

Do not place PINs, license keys, OAuth tokens, real statements, personal email, or financial data in evidence. A mapping is not a pass: the candidate remains NO-GO until every generated entry has exact-SHA evidence.
