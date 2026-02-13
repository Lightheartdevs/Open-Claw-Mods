# Android-16 Local Setup: OpenClaw + Qwen2.5 via vLLM

**Instance:** Android-16
**OpenClaw Version:** 2026.2.12
**Model:** Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
**Inference Server:** vLLM v0.14.0 (Docker)
**Proxy:** vllm-tool-proxy.py v4 + SSE patch

## Overview

This setup runs OpenClaw with a **locally hosted** Qwen2.5-Coder-32B model served via vLLM, instead of cloud-based Anthropic/OpenAI models. This required solving five distinct compatibility issues between OpenClaw's internals and local model serving.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Server: 192.168.0.143 (OpenClaw Host)                         │
│                                                                 │
│  ┌───────────────────────────────────────────────┐              │
│  │  OpenClaw v2026.2.12                          │              │
│  │  ├── pi-ai (openai-completions provider)      │              │
│  │  │   └── OpenAI SDK (always stream: true)     │              │
│  │  ├── pi-agent-core (agent loop)               │              │
│  │  │   └── 23 built-in tools                    │              │
│  │  └── Config: ~/.openclaw/openclaw.json        │              │
│  └────────────────────┬──────────────────────────┘              │
│                       │ HTTPS (stream: true)                    │
└───────────────────────┼─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Server: 192.168.0.122 (vLLM + Proxy Host)                     │
│                                                                 │
│  ┌───────────────────────────────────────────────┐              │
│  │  vllm-tool-proxy.py (:8003)                   │              │
│  │  ├── Intercepts all /v1/chat/completions      │              │
│  │  ├── Forces stream:false when tools present   │              │
│  │  ├── Extracts tool calls from raw text        │              │
│  │  ├── Re-wraps response as SSE stream          │              │
│  │  └── Loop protection (MAX_TOOL_CALLS=20)      │              │
│  └────────────────────┬──────────────────────────┘              │
│                       │ HTTP (stream: false)                    │
│                       ▼                                         │
│  ┌───────────────────────────────────────────────┐              │
│  │  vLLM v0.14.0 (Docker: vllm-coder) (:8000)   │              │
│  │  ├── Model: Qwen2.5-Coder-32B-Instruct-AWQ   │              │
│  │  ├── --enable-auto-tool-choice                │              │
│  │  ├── --tool-call-parser hermes                │              │
│  │  ├── --gpu-memory-utilization 0.90            │              │
│  │  └── --max-model-len 32768                    │              │
│  └───────────────────────────────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## The Five Failure Points (and Fixes)

When OpenClaw tries to use a local model out-of-the-box, it fails at five distinct points. This setup fixes all of them:

### 1. SSE Streaming Mismatch (Critical)
**Problem:** OpenClaw's `pi-ai` library uses the OpenAI SDK with `stream: true` (always). When the proxy forces `stream: false` to extract tool calls from text, the SDK receives a non-streaming JSON response but expects SSE chunks. The async iterator produces 0 chunks → "No reply from agent" with 0 tokens.

**Fix:** The proxy's `convert_to_sse_stream()` function re-wraps the non-streaming response back into proper SSE chunks (`data: {json}\n\n` format with `[DONE]` sentinel).

### 2. Tool Calls Returned as Raw Text
**Problem:** Qwen2.5-Coder outputs tool calls in `<tools>JSON</tools>` format or as bare JSON in the `content` field. vLLM's hermes parser doesn't catch this format, so tool calls arrive as plain text instead of structured `tool_calls` array.

**Fix:** The proxy's `extract_tools_from_content()` parses `<tools>` tags, bare JSON objects, and multi-line JSON from the content field and converts them to proper `tool_calls` entries.

### 3. Unsupported API Parameters
**Problem:** OpenClaw's default compat settings send parameters that vLLM rejects:
- `store: false` (from `supportsStore: true` default)
- `max_completion_tokens` (from `maxTokensField: "max_completion_tokens"` default)
- `developer` role messages (from `supportsDeveloperRole: true` default)

**Fix:** Explicit compat flags in `openclaw.json`:
```json
"compat": {
  "supportsDeveloperRole": false,
  "supportsStore": false,
  "maxTokensField": "max_tokens",
  "supportsReasoningEffort": false
}
```

### 4. Tool Call Repetition Loops
**Problem:** Qwen2.5 can get stuck in repetitive loops when handling complex multi-step tool chains, repeatedly emitting the same tool call JSON with `<|im_start|>` tokens leaking into the output.

**Fix:** The proxy enforces `MAX_TOOL_CALLS = 20` — after 20 tool result messages in a conversation, it returns a stop message instead of forwarding to vLLM. This prevents runaway token consumption.

### 5. Config Schema Validation
**Problem:** Several community-suggested compat fields (`supportsStrictMode`, `supportedParameters`, `streaming`, `fallback`) are not in OpenClaw v2026.2.12's config schema and cause validation errors on startup.

**Fix:** Only use validated compat fields. See `configs/openclaw.json` for the exact working configuration.

## Files in This Setup

| File | Server | Purpose |
|------|--------|---------|
| `configs/openclaw.json` | .143: `~/.openclaw/openclaw.json` | OpenClaw configuration with vLLM provider |
| `proxy/vllm-tool-proxy.py` | .122: `/home/michael/vllm-tool-proxy.py` | Tool call extraction proxy with SSE re-wrapping |
| `proxy/proxy-patch.py` | .122: `/tmp/proxy-patch.py` | Script that adds SSE re-wrapping to the proxy |
| `scripts/start-proxy.sh` | .122 | Start the proxy as a background service |
| `scripts/start-vllm.sh` | .122 | Docker command to start vLLM |

## Stress Test Results

| Test | Result | Notes |
|------|--------|-------|
| File Create (write) | PASS | Created files with correct content |
| File Read (read) | PASS | Read back file content correctly |
| File Edit (edit) | PARTIAL | Edit tool works; model sometimes uses write instead of edit for appends |
| Command Execution (exec) | PASS | uname, df, free, uptime all returned correctly |
| Multiple Commands | PASS | Series of commands in one exec works |
| File Copy | PASS | Copied files with cp via exec |
| File Delete | PASS | Deleted files with rm via exec |
| File Move | PASS | Previous session moved file successfully |
| Multi-step Chain (6 steps) | FAIL | Model gets stuck in repetition loop with <\|im_start\|> token leaking |
| SSH to Remote Host | HANG | SSH prompts for password interactively; agent cannot provide it |

## Known Limitations

1. **Complex multi-step chains** (6+ sequential tool calls) can trigger repetition loops — this is a known Qwen2.5 limitation, not a proxy/OpenClaw issue
2. **Interactive commands** (ssh with password, sudo, anything requiring TTY input) will hang the agent
3. **Model sometimes picks wrong tool** — e.g. uses `write` (overwrite) when `edit` (modify) would be correct
4. **Context window fills up fast** — Qwen2.5-32B has 32K context; OpenClaw's 23 tools + system prompt consume ~8-10K tokens
5. **No vision/image support** — AWQ quantized model is text-only

## Quick Start

See `DEPLOYMENT.md` for step-by-step deployment instructions.
