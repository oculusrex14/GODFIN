> **ARCHIVED HISTORICAL DOCUMENT — DO NOT USE FOR CURRENT IMPLEMENTATION.**
> The tool schemas and agent workflow below are obsolete. Follow the active
> environment instructions and `docs/ENGINEERING_GUIDE.md`.

# GODFIN — Tools Used Log

This log documents every unique tool invocation pattern with exact formatting, purpose, and response handling. Intended for replicating Claude Code tool use with locally running models.

---

## 1. Read Tool — Read a file

**Purpose:** Read file contents from disk.

**Invocation:**
```json
{
  "tool": "Read",
  "input": {
    "file_path": "/absolute/path/to/file.py"
  }
}
```

**Optional params:** `offset` (line number to start), `limit` (number of lines)

**Response handling:** Returns file contents with line numbers in `cat -n` format:
```
     1→from __future__ import annotations
     2→
     3→import os
```

**Use when:** Need to inspect file contents before editing. MUST read before editing.

---

## 2. Write Tool — Create or overwrite a file

**Purpose:** Write full contents to a file (creates or overwrites).

**Invocation:**
```json
{
  "tool": "Write",
  "input": {
    "file_path": "/absolute/path/to/new_file.py",
    "content": "from __future__ import annotations\n\nimport os\n"
  }
}
```

**Response handling:** Returns confirmation that file was written.

**Use when:** Creating new files or completely rewriting existing ones. Must Read first if file exists.

---

## 3. Edit Tool — Replace specific text in a file

**Purpose:** Find and replace exact string matches in a file.

**Invocation:**
```json
{
  "tool": "Edit",
  "input": {
    "file_path": "/absolute/path/to/file.py",
    "old_string": "def old_function():\n    pass",
    "new_string": "def new_function():\n    return True"
  }
}
```

**Optional params:** `replace_all` (boolean, default false — replace all occurrences)

**Response handling:** Returns confirmation with line numbers affected.

**Key rules:**
- `old_string` must be UNIQUE in the file (or use `replace_all: true`)
- Must preserve exact indentation (spaces/tabs) from the file
- Must Read the file first in the same conversation

---

## 4. Glob Tool — Find files by pattern

**Purpose:** Find files matching glob patterns.

**Invocation:**
```json
{
  "tool": "Glob",
  "input": {
    "pattern": "**/*.py",
    "path": "/absolute/path/to/search/dir"
  }
}
```

**Response handling:** Returns list of matching file paths sorted by modification time.

**Use when:** Finding files by name/extension. Replaces `find` command.

---

## 5. Grep Tool — Search file contents

**Purpose:** Search for patterns in file contents using ripgrep regex.

**Invocation (files_with_matches mode — default):**
```json
{
  "tool": "Grep",
  "input": {
    "pattern": "def get_current_user",
    "path": "/absolute/path/to/search",
    "type": "py"
  }
}
```

**Invocation (content mode — see matching lines):**
```json
{
  "tool": "Grep",
  "input": {
    "pattern": "def get_current_user",
    "path": "/absolute/path/to/search",
    "output_mode": "content",
    "-n": true,
    "-A": 3
  }
}
```

**Optional params:**
- `output_mode`: "files_with_matches" (default), "content", "count"
- `-A`, `-B`, `-C`: Lines after/before/around match (content mode only)
- `-n`: Show line numbers (content mode, default true)
- `-i`: Case insensitive
- `glob`: Filter files by glob (e.g., "*.py")
- `type`: Filter by file type (e.g., "py", "js")
- `head_limit`: Limit output entries

**Use when:** Searching for code patterns, function definitions, imports. Replaces `grep`/`rg`.

---

## 6. Bash Tool — Execute shell commands

**Purpose:** Run terminal commands (git, npm, pytest, etc.).

**Invocation:**
```json
{
  "tool": "Bash",
  "input": {
    "command": "cd /project/backend && python -m pytest tests/ -v",
    "description": "Run all backend tests verbosely",
    "timeout": 120000
  }
}
```

**Optional params:**
- `timeout`: Max wait in ms (default 120000, max 600000)
- `run_in_background`: Boolean, runs async
- `description`: Human-readable description of command

**Response handling:** Returns stdout + stderr. Truncated if > 30000 chars.

**Use when:** Running tests, git operations, installing packages, starting servers, any shell command. Do NOT use for file read/write/search — use dedicated tools.

---

## 7. WebSearch Tool — Search the web

**Purpose:** Search the internet for current information.

**Invocation:**
```json
{
  "tool": "WebSearch",
  "input": {
    "query": "FastAPI TestClient lifespan override 2026"
  }
}
```

**Optional params:**
- `allowed_domains`: Array of domains to include
- `blocked_domains`: Array of domains to block

**Response handling:** Returns search results with titles, snippets, and URLs. MUST include Sources section in response.

---

## 8. WebFetch Tool — Fetch and analyze web content

**Purpose:** Fetch a URL and process content with AI.

**Invocation:**
```json
{
  "tool": "WebFetch",
  "input": {
    "url": "https://example.com/docs/page",
    "prompt": "Extract the configuration options for SQLAlchemy session management"
  }
}
```

**Response handling:** Returns AI-processed summary of the page content.

**Use when:** Need to read specific web pages (docs, Stack Overflow answers, etc.).

---

## 9. Task Tool — Launch subagent for complex tasks

**Purpose:** Spawn specialized agents for parallel or complex work.

**Invocation:**
```json
{
  "tool": "Task",
  "input": {
    "subagent_type": "Explore",
    "description": "Find auth patterns",
    "prompt": "Search the codebase at /project for all authentication-related files and patterns. Report file paths and key functions.",
    "model": "haiku"
  }
}
```

**Key subagent_types:**
- `Explore` — Fast codebase exploration (read-only)
- `Bash` — Command execution
- `general-purpose` — Multi-step research tasks
- `Plan` — Architecture/implementation planning

**Optional params:**
- `model`: "sonnet", "opus", "haiku" (default inherits parent)
- `run_in_background`: Boolean
- `resume`: Agent ID to continue previous work
- `max_turns`: Limit API round-trips

**Response handling:** Returns agent's final output message + agent ID for resuming.

---

## 10. TodoWrite Tool — Manage task list

**Purpose:** Track progress on multi-step tasks.

**Invocation:**
```json
{
  "tool": "TodoWrite",
  "input": {
    "todos": [
      {
        "content": "Fix auth test failures",
        "status": "in_progress",
        "activeForm": "Fixing auth test failures"
      },
      {
        "content": "Build frontend auth flow",
        "status": "pending",
        "activeForm": "Building frontend auth flow"
      }
    ]
  }
}
```

**Status values:** "pending", "in_progress", "completed"

**Rules:**
- Only ONE task should be "in_progress" at a time
- `content`: Imperative form ("Fix X")
- `activeForm`: Present continuous ("Fixing X")
- Mark complete immediately when done

---

## 11. AskUserQuestion Tool — Ask user for input

**Purpose:** Get clarification or choices from the user.

**Invocation:**
```json
{
  "tool": "AskUserQuestion",
  "input": {
    "questions": [
      {
        "question": "Which database should we use for caching?",
        "header": "Cache DB",
        "options": [
          {"label": "Redis (Recommended)", "description": "Fast in-memory store"},
          {"label": "SQLite", "description": "File-based, no extra deps"}
        ],
        "multiSelect": false
      }
    ]
  }
}
```

---

## 12. TaskOutput Tool — Check background task results

**Purpose:** Read output from background tasks.

**Invocation:**
```json
{
  "tool": "TaskOutput",
  "input": {
    "task_id": "task_abc123",
    "block": true,
    "timeout": 30000
  }
}
```

**Use when:** Checking on tasks launched with `run_in_background: true`.

---

## Tool Call Response Loop Pattern

When Claude Code calls a tool, the cycle is:

1. **Claude generates text** (optional) explaining what it will do
2. **Claude emits tool_use block** with tool name + input JSON
3. **System returns tool_result** with the output
4. **Claude processes result** and either:
   - Calls another tool (continues loop)
   - Generates final text response to user

**Parallel calls:** Multiple independent tool_use blocks can be emitted in a single response. The system executes all of them and returns all results together.

**Example — Read then Edit flow:**
```
Assistant: Let me read the file first.
[tool_use: Read {file_path: "/path/to/file.py"}]

System: [tool_result: file contents...]
