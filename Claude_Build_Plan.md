# GODFIN - Claude Code (Opus 4.6) Build Plan

This document outlines the optimal strategy for executing the GODFIN build using Claude Code (powered by Opus 4.6) **running inside Antigravity**. It integrates the project's specification with your specifically installed tools and skills to ensure a clean, efficient, and high-quality build process.

## 0. Prerequisite: Deep Understanding & Vision Alignment

Before executing any construction or writing a single line of code, Claude Code **MUST read `GODFIN_Final_Build_Specification_v1 .md` in its entirety.**
- You must absorb the "Audit-First Financial Integrity Philosophy" completely.
- You must under NO CIRCUMSTANCES divert from the vision, architecture, or tech stack outlined in that document.
- The specification is the single source of truth. If a requirement seems complex, you must implement the complexity exactly as defined, rather than simplifying it on your own.

## 1. Negative Prompts for Deterministic Execution

To strike the right balance between deterministic execution for boilerplate/straightforward tasks, and high-level reasoning for complex planning, abide by these constraints:

*   **DO NOT** add new libraries, frameworks, or dependencies that are not explicitly specified in the `Tech Stack` section of the specification.
*   **DO NOT** write generic, boilerplate UI code or default "AI-looking" styles. Every component must look premium, minimalist, and adhere to the strict design language (deep navy backgrounds, Inter font, tabular nums).
*   **DO NOT** guess or hallucinate the classification logic. Always strictly implement the 5-Layer Classification Engine exactly as structured. 
*   **DO NOT** skip, reorder, or merge the 10 defined Build Phases. You must execute one phase at a time and verify it against the criteria before moving to the next.
*   **DO NOT** use mock data in production or leave hardcoded placeholders (except briefly in Phase 2/3 as designated).
*   **DO NOT** silently mutate financial history. The audit engine rules are absolute law and must be prioritized over short-term expediency.
*   **DO NOT** bypass test-driven development on core financial formulas. Do not proceed until tests are passing.
*   **DO** use high-level, deliberate planning (`brainstorming`, `writing-plans`) before tackling complex algorithmic tasks (e.g., finding the intersection of statement transactions during reconciliation, or resolving concurrent WAL locks).

## 2. Core Build Strategy & Skill Utilization

To maximize the efficiency of Opus 4.6 and ensure the audit-first integrity model is perfectly implemented, Claude Code should employ the following skills at different stages of the development lifecycle:

### Planning & Architecture
* **`brainstorming` & `writing-plans`**: Before starting each phase, Claude should take a moment to brainstorm potential edge cases (especially regarding the financial audit states) and write micro-plans for the session.
* **`executing-plans`**: Use this skill to rigorously stick to the 10 phases outlined in the GODFIN specification. Do not jump ahead.

### Parallel Development & Agents
* **`dispatching-parallel-agents` & `subagent-driven-development`**: For phases that require disjointed work (e.g., scaffolding the Vite frontend while simultaneously setting up the FastAPI routes), dispatch parallel subagents to handle these tasks to speed up development.

### UI / UX Design (Minimalist & Attractive)
* **`web-artifacts-builder`**: Before writing the final React components for complex UI parts (like the Audit Dashboard or the Review Queue), use this skill to generate and visually test isolated artifacts.
* UI Guidelines:
  * Emphasize a **minimalistic, premium financial aesthetic**.
  * Use Framer Motion for subtle, buttery-smooth interactions.
  * Deep navy (`#1a1f36`) backgrounds with stark white cards and precise typography (Inter font).
  * Focus on data-ink ratio: remove unnecessary borders, use spacing and typography for hierarchy.

### Testing & Verification
* **`test-driven-development` & `webapp-testing`**: Apply TDD strictly for the core financial formulas, the recurring detection algorithm, and the statement reconciliation logic. These cannot have bugs.
* **`verification-before-completion`**: Never close out a phase without verifying the Acceptance Criteria (e.g., making sure finalized months are truly immutable).
* **`systematic-debugging`**: Use this if the complex Regex parsers for Gmail or the SQLite WAL mode face lock issues.

### Tooling & Extension
* **`mcp-builder`**: If the LLM fallback or Gmail OAuth logic becomes complex to test locally, create a quick Model Context Protocol server to mock these external services during the build.
* **`skill-creator` & `writing-skills`**: Use these to codify specific repetitive tasks into reusable terminal commands for the workspace.

### Workflow & Version Control
* **`using-git-worktrees`**: Isolate each of the 10 build phases into its own Git worktree. For instance, have one worktree for backend data-model, another for the frontend UI.
* **`requesting-code-review` & `receiving-code-review`**: Simulate a CTO review by having Claude self-critique the PRs across branches for compliance with the "Audit-First Financial Integrity Philosophy" before merging.
* **`finishing-a-development-branch`**: Cleanly merge and tear down worktrees when a phase is complete.

---

## 3. Step-by-Step Execution Plan

Claude Code should be instructed to execute the project sequentially. Open a terminal and use Claude Code to execute these phases:

### Phase 1: Foundation & Data Model
1. **Setup**: Use `dispatching-parallel-agents` to initialize the FastAPI backend and Vite+React+Tailwind frontend simultaneously.
2. **Execute**: Implement the SQLite schema (WAL mode) and Alembic migrations. 
3. **Verify**: Use `test-driven-development` to write a quick Pytest suite proving the tables interact correctly.

### Phase 2: Manual Transactions & UI Prototyping
1. **Design**: Use `web-artifacts-builder` to prototype the Minimalist Dashboard and Transaction List. Ensure it looks highly attractive before integrating into the Vite app.
2. **Execute**: Build the backend CRUD routes and connect the UI. Use React Query for fetching.

### Phase 3: Gmail Ingestion (Complex Logic)
1. **Execute**: Implement the Gmail OAuth and regex parsing.
2. **Debug**: Utilize `systematic-debugging` to perfect the `UPI_DEBIT_PATTERN` and `CC_DEBIT_PATTERN`.
3. **Verify**: Run `verification-before-completion` against mock HDFC email bodies.

### Phase 4: Five-Layer Classification Engine
1. **Plan**: This is the heart of GODFIN. Use `brainstorming` to ensure the exact, rule-based, fuzzy, embedding, and LLM fallback layers cascade efficiently without latency.
2. **Test**: Use `test-driven-development` extensively here.

### Phase 5 & 6: Review Queue, Dashboards, & Statements
1. **UI Polish**: Use `webapp-testing` to ensure the Review Queue is responsive and looks premium on mobile.
2. **Worktrees**: Use `using-git-worktrees` to separate the PDF parsing logic (Backend) from the complex UI state management of statement reconciliation (Frontend).
3. **Review**: Use `requesting-code-review` to ensure the CSV/PDF parsing doesn't introduce vulnerabilities or corrupt data.

### Phase 7: Embeddings & LLM
1. **Mocking**: Use `mcp-builder` to create a local testing mockup for the Sentence Transformers and LLM oauth fallback to avoid rate limits during development.

### Phase 8 & 9: Budgeting, Financial Formulas & Reporting
1. **TDD Core**: Use `test-driven-development` to implement the `calculate_required_monthly_saving` and `compute_impulse_index` functions exactly as mathematically specified.
2. **Reporting**: Produce the server-side PDF generation.

### Phase 10: Hardening, Polish, & The Audit Engine
1. **Security & State**: The Audit system (Draft -> Finalized -> Locked) is critical. Use `brainstorming` to visualize the state machine, then `executing-plans` to implement.
2. **Verification**: Enforce `verification-before-completion` to guarantee that hard deletes and edits are completely blocked on finalized months without explicit reopening. 
3. **Final Merge**: Use `finishing-a-development-branch` to wrap up all active code.

---

## 3. UI/UX Concrete Recommendations for Claude Code

When writing the frontend code, Claude Code should adhere to the following strict guidelines to achieve the requested Minimalist & Highly Attractive UI:

* **Colors**: 
  * Background: Slate-900 or deep navy (`bg-slate-900`) instead of generic black.
  * Cards/Surfaces: Deep glassmorphism or subtle borders (`bg-slate-800/50 border border-slate-700 backdrop-blur-md`).
  * Accents: Emerald green (`text-emerald-400`) for income/savings, Rose (`text-rose-400`) for excessive spend/alerts.
* **Typography**:
  * Use `font-sans` globally configured to `Inter`. 
  * Make numbers pop using tabular nums (`tabular-nums tracking-tight`) so dashboards look aligned and professional.
  * Large, thin variations for big totals (e.g., `text-5xl font-light tracking-tighter`).
* **Micro-interactions**:
  * Add hover lifts to transaction rows (`hover:-translate-y-0.5 transition-transform duration-200`).
  * Progress bars for budgets should have a smooth width animation.
* **Layout**:
  * Use plenty of empty space (`gap-8`, `p-8`). Don't cram data.
  * Hide scrollbars on lists, keep borders minimal. 

---

