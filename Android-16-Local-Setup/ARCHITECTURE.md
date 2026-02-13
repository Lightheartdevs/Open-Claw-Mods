# Architecture Deep Dive

## How OpenClaw Talks to LLMs

OpenClaw uses an internal package called `@mariozechner/pi-ai` for LLM communication. The key file is:

```
/usr/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai/dist/providers/openai-completions.js
```

This 716-line file handles ALL communication with OpenAI-compatible endpoints. Key functions:

### `buildParams()` (line ~310)
- **Always sets `stream: true`** — this is hardcoded, not configurable
- Sends tools via `convertTools()` when `context.tools` is present
- Sets `max_completion_tokens` or `max_tokens` based on compat flag

### `detectCompat()` (line ~659)
Auto-detects compatibility settings from provider URL. For unknown providers (like vLLM), it defaults to:
- `supportsStore: true` (WRONG for vLLM — sends `store: false` which vLLM rejects)
- `maxTokensField: "max_completion_tokens"` (WRONG for vLLM — should be `max_tokens`)

### `getCompat()` (line ~697)
Merges explicit `model.compat` settings over detected defaults. This is how we override the bad defaults.

### `convertTools()` (line ~623)
Converts internal tool format to OpenAI function-calling format. Includes `strict: false` unless `supportsStrictMode` is explicitly `false`.

## The Agent Loop

The main agent runner lives in a bundled file:
```
/usr/lib/node_modules/openclaw/dist/pi-embedded-DxwVpEx9.js  (67,531 lines)
```

Key entry points:
- `runEmbeddedPiAgent()` at line ~67585 — top-level agent runner
- `runEmbeddedAttempt()` at line ~66858 — single conversation turn
- `createOpenClawCodingTools()` at line ~66925 — produces 23 built-in tools

The loop:
1. Build system prompt (tools, skills, workspace files, identity)
2. Create agent session with `createAgentSession()`
3. Send message to LLM via `openai-completions` provider
4. Parse response — if tool calls, execute them and loop back to step 3
5. If text response, return to user

## The OpenAI SDK Streaming Problem

This is the **critical issue** that makes naive local model setups fail silently.

```
OpenClaw (pi-ai) → OpenAI SDK → stream: true → expects SSE chunks
                                                    ↓
Proxy forces stream: false for tool extraction → returns JSON blob
                                                    ↓
OpenAI SDK async iterator gets 0 SSE chunks → empty response
                                                    ↓
Agent sees 0 tokens → "No reply from agent"
```

The fix is the SSE re-wrapping layer in the proxy:
```
Client requests stream: true  →  Proxy forces stream: false
                                        ↓
                              vLLM returns JSON response
                                        ↓
                              Proxy extracts tool calls from text
                                        ↓
                              Proxy converts JSON → SSE chunks
                                        ↓
Client receives SSE stream  ←  Proxy sends SSE with proper format
```

## Tool Call Extraction Pipeline

Qwen2.5-Coder doesn't use OpenAI's native `tool_calls` format. Instead it outputs tool calls in the `content` field in various formats:

### Format 1: `<tools>` tags
```
<tools>
{"name": "read", "arguments": {"path": "/tmp/test.txt"}}
</tools>
```

### Format 2: Bare JSON
```
{"name": "exec", "arguments": {"command": "ls -la"}}
```

### Format 3: Multi-line JSON
```
{"name": "write", "arguments": {"path": "/tmp/a.txt", "content": "hello"}}
{"name": "write", "arguments": {"path": "/tmp/b.txt", "content": "world"}}
```

The proxy's `extract_tools_from_content()` handles all three formats:
1. Regex match `<tools>(.*?)</tools>` — parse each line as JSON
2. Try parsing entire content as single JSON object
3. Split content by newlines, try parsing each line as JSON
4. For each parsed object with a `name` field, create a proper `tool_calls` entry
5. Clean remaining non-JSON content back into the `content` field

## Session Storage

OpenClaw stores conversation sessions as JSONL files:
```
~/.openclaw/agents/main/sessions/*.jsonl
```

Each line is a JSON object with types:
- `session` — session metadata
- `model_change` — model switch events
- `message` — user/assistant messages with tool calls
- `tool_result` — tool execution results

## Config Resolution Order

1. `~/.openclaw/openclaw.json` — user config (source of truth)
2. `~/.openclaw/agents/main/agent/models.json` — auto-generated from above
3. Built-in defaults in `openai-completions.js detectCompat()`

**Important:** When changing `openclaw.json`, delete `models.json` to force regeneration:
```bash
rm ~/.openclaw/agents/main/agent/models.json
```
