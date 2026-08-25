# Local AI safety and lifecycle

This record covers repository work for `GF-AI-002` and `GF-AI-003`. GODFIN's deterministic imports, rules, balances, calculations, and exports never depend on an LLM.

## Device suitability

- macOS reads total memory from `sysctl` and currently reclaimable memory from `vm_stat`.
- Linux reads `MemTotal` and `MemAvailable` from `/proc/meminfo`.
- Windows reads total and available physical memory from `GlobalMemoryStatusEx`.
- A POSIX available-pages counter is a fallback; GODFIN does not invent a percentage of total memory when a live measurement is unavailable.
- A candidate must meet the signed registry's minimum RAM, retain the larger of 2 GB or 12.5% of total RAM for the OS, and leave the signed download estimate plus 15% and 2 GB free on disk.
- Ollama's installed tag and show APIs supply the exact installed size, digest, quantization metadata, and reported maximum context when available.
- GODFIN selects a 2,048, 4,096, or 8,192-token working context from current headroom and never exceeds the installed model's reported maximum.

Hardware detection is still a point-in-time estimate. The UI therefore calls an untested choice a candidate, not a guaranteed default.

## Download lifecycle

Every approved pull receives a random job ID. Its model, signed-registry evidence, expected digest, measured headroom, progress, PID, timestamps, terminal state, and retryability are stored in local SQLite. Only one pull may run at a time.

Normal application shutdown terminates the owned Ollama CLI process and records an interrupted, retryable job. On restart GODFIN:

1. checks whether the expected signed model actually completed;
2. accepts it only when the installed digest matches the current signed registry;
3. otherwise validates any persisted PID against the exact `ollama pull <model>` command before terminating an orphan; and
4. records an interrupted state that the user can safely retry.

Cancellation is propagated to the owned process. An exact digest mismatch removes the untrusted installed tag when possible. No raw CLI output, process path, or exception is returned to the UI.

## Benchmark and activation gate

A downloaded model is not ready merely because it fits the static matrix. GODFIN runs a fixed, non-authoritative finance-explanation prompt with the selected bounded context. The result records the exact model digest, context, live memory/disk snapshot, speed, and completion time.

Local activation fails closed unless:

- the model remains in the current signed registry;
- the installed digest still matches;
- current RAM and disk headroom still pass;
- the benchmark used the same digest;
- the benchmark is no more than 30 days old; and
- generation measured at least one token per second with a non-empty response.

Hosted providers do not use this local benchmark gate and retain their separate consent/redaction boundary.

## Untrusted transaction text

Imported merchant and payment-method values are Unicode-normalized, stripped of control characters, whitespace-normalized, length-bounded, JSON-serialized, and escaped so they cannot close their fixed prompt markers. The classification and review prompts explicitly state that these blocks are bank-statement data, never instructions, and that links, role changes, policy changes, output-format changes, or delimiter text inside them must be ignored.

Provider output remains untrusted: classification JSON is size-bounded, parsed, and validated against GODFIN's taxonomy before use. An LLM cannot create an authoritative financial total or silently finalize a classification.

## Remaining native evidence

Before release, repeat low-memory, low-disk, cancel, crash/restart, orphan-process, digest-change, slow-benchmark, and activation tests in signed packages on macOS arm64/x64, Windows x64, and Linux x64. Browser-visible interaction checks remain in the owner-requested final browser/computer-control tranche.
