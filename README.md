# GODFIN

GODFIN is a private, pre-launch, local-first personal-finance desktop app. The
React interface and FastAPI service run on the user's computer, and ordinary
financial data remains in that installation's SQLite database. The separate
Next.js website handles marketing, account authentication, one-time payments,
and license verification; it is not the application's data store.

## Start here

- Product requirements and non-negotiables: [`PLAN.md`](PLAN.md)
- Current technical source of truth: [`docs/ENGINEERING_GUIDE.md`](docs/ENGINEERING_GUIDE.md)
- Generated runtime and dependency facts: [`docs/generated/STACK_FACTS.md`](docs/generated/STACK_FACTS.md)
- Database lifecycle: [`docs/DATABASE_LIFECYCLE.md`](docs/DATABASE_LIFECYCLE.md)
- Architecture decisions: [`docs/architecture/README.md`](docs/architecture/README.md)
- Private release gates: [`docs/PRODUCTION_RELEASE.md`](docs/PRODUCTION_RELEASE.md)

Older build plans, historical change logs, and versioned specifications are
retained only as provenance. Their archive banners identify them as
non-authoritative.

## Local development

Use the repository-managed Python 3.12 environment and locked Node installs:

```bash
backend/venv/bin/python -m pip install --require-hashes -r backend/requirements-lock.txt
npm ci --prefix frontend
npm ci --prefix website
npm ci --prefix desktop
./start.sh
```

`./start.sh` uses `127.0.0.1:5100` for FastAPI and `127.0.0.1:5200` for Vite by
default. LAN binding is a deliberate, PIN-confirmed setting—not a development
default. The website runs separately on `127.0.0.1:5300`.

## Verification

```bash
backend/venv/bin/python scripts/verify_documentation_contracts.py
backend/venv/bin/python -m pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix website run verify:contracts
npm --prefix website run build
```

This repository is private and licensed under PolyForm Noncommercial 1.0.0.
Nothing in the repository authorizes a public release, production deployment,
or collection of desktop financial records.
