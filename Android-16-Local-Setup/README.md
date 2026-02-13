# Android-16 Local Setup: OpenClaw + Qwen2.5 via vLLM

**Instance:** Android-16
**OpenClaw Version:** 2026.2.12
**Model:** Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
**Inference Server:** vLLM v0.14.0 (Docker)
**Proxy:** vllm-tool-proxy.py v4 + SSE patch
**Discord:** Online as @Android-16 (Local) — bot ID `1470898132668776509`
**Gateway:** Port 18791 on .143 (systemd: `openclaw-gateway.service`)
**Last Tested:** 2026-02-13 — **88% functional** (20/26 tests pass)

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
│                       │ HTTP (stream: true)                     │
│                       │                                         │
│  SSH key-based auth ──┼──────────────────────────── (.143→.122) │
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
│  GPU: NVIDIA RTX PRO 6000 Blackwell (96GB VRAM)                │
└─────────────────────────────────────────────────────────────────┘
```

## The Five Failure Points (and Fixes)

When OpenClaw tries to use a local model out-of-the-box, it fails at five distinct points. This setup fixes all of them:

### 1. SSE Streaming Mismatch (Critical)
**Problem:** OpenClaw's `pi-ai` library uses the OpenAI SDK with `stream: true` (always). When the proxy forces `stream: false` to extract tool calls from text, the SDK receives a non-streaming JSON response but expects SSE chunks. The async iterator produces 0 chunks -> "No reply from agent" with 0 tokens.

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

**Fix:** The proxy enforces `MAX_TOOL_CALLS = 20` -- after 20 tool result messages in a conversation, it returns a stop message instead of forwarding to vLLM. This prevents runaway token consumption.

### 5. Config Schema Validation
**Problem:** Several community-suggested compat fields (`supportsStrictMode`, `supportedParameters`, `streaming`, `fallback`) are not in OpenClaw v2026.2.12's config schema and cause validation errors on startup.

**Fix:** Only use validated compat fields. See `configs/openclaw.json` for the exact working configuration.

## Files in This Setup

| File | Server | Purpose |
|------|--------|---------|
| `configs/openclaw.json` | .143: `~/.openclaw/openclaw.json` | OpenClaw config (model, Discord, gateway, plugins) |
| `configs/openclaw-gateway.service` | .143: `~/.config/systemd/user/openclaw-gateway.service` | Systemd user service for Android-16 gateway |
| `proxy/vllm-tool-proxy.py` | .122: `/home/michael/vllm-tool-proxy.py` | Tool call extraction proxy with SSE re-wrapping |
| `proxy/proxy-patch.py` | .122: `/tmp/proxy-patch.py` | Script that adds SSE re-wrapping to the proxy |
| `scripts/start-proxy.sh` | .122 | Start the proxy as a background service |
| `scripts/start-vllm.sh` | .122 | Docker command to start vLLM |

## Documentation

| Document | Purpose |
|----------|---------|
| `ARCHITECTURE.md` | Deep dive into OpenClaw internals and the tool extraction pipeline |
| `DEPLOYMENT.md` | Step-by-step deployment from scratch |
| `PROXY-EXPLAINED.md` | How the proxy works, request flow, key functions |
| `STRESS-TESTS.md` | Full test results — 26 tests across 2 rounds |
| `RESTORE.md` | Disaster recovery — how to rebuild from scratch |
| `SNAPSHOT.md` | Live server state capture for verifying a restore |
| `SSH-SETUP.md` | How key-based SSH auth was configured |

## Stress Test Results (Latest: Round 2, 2026-02-13)

### What Works

| Category | Tests | Success Rate |
|----------|-------|-------------|
| File operations (write, read, edit) | 5/5 | 100% |
| Command execution | 3/3 | 100% |
| Multi-step chains (2-3 steps) | 3/3 | 100% |
| Multi-step chains (5-10 steps) | 4/4 | 100% |
| SSH / cross-server | 2/2 | 100% |
| Git operations | 1/1 | 100% |
| System diagnostics | 1/1 | 100% |

### What Partially Works

| Test | Issue |
|------|-------|
| 4-step numbered chain | Planning loop on numbered step lists |
| Bug finding + fixing | Correctly identifies bugs but token leak blocks the fix |

### What Fails

| Test | Issue |
|------|-------|
| Multi-file edit (add content) | Model uses `write` (overwrite) instead of `edit` |

### Key Improvements Over Initial Tests

1. **SSH now works** -- key-based auth from .143 to .122
2. **6-step chains now pass** -- previously failed with repetition loops
3. **8 and 10-step chains pass** -- significant multi-step reliability
4. **Cross-server workflows work** -- SSH + nvidia-smi, docker ps, remote diagnostics
5. **Git operations work** -- including self-correction on missing git config

## Known Limitations

1. **Multi-file editing** -- model uses `write` (overwrite) instead of `edit` (modify) when adding new content to existing files
2. **Complex reasoning + tool execution** -- `<|im_start|>` token leak can corrupt tool calls mid-thought
3. **Numbered step lists** -- "do step 1, step 2, ..." triggers planning loops; natural language descriptions work better
4. **Context window** -- 32K total, ~8-10K consumed by system prompt + 23 tools
5. **No vision/image support** -- AWQ quantized model is text-only
6. **Token leak (`<|im_start|>`)** -- appears in ~30% of multi-step responses, usually non-fatal

## Discord Integration

Android-16 has a live Discord presence via OpenClaw's built-in Discord plugin. He shows up as **@Android-16 (Local)** in the server.

### How It Works
- OpenClaw's `channels.discord` config section connects the bot to Discord using a bot token
- The `plugins.entries.discord.enabled: true` flag activates the Discord plugin
- The gateway runs as a systemd user service (`openclaw-gateway.service`) on port 18791
- When someone messages in a channel he's configured for, OpenClaw routes it to the Qwen model and posts the response back

### Channel Behavior
| Channel | Behavior |
|---------|----------|
| `#android-16` | Listens to ALL messages (no @mention needed) |
| All other channels | Only responds when `@Android-16` is mentioned |

### Key Discord IDs
| Entity | ID |
|--------|-----|
| Android-16 bot | `1470898132668776509` |
| Guild (server) | `1469753709272764445` |
| #android-16 | `1470931716041478147` |
| #general | `1469753710908276819` |

### Gotchas Learned During Setup
1. **`NO_REPLY` responses** — The model sometimes decides a message doesn't need a response, especially on first contact or vague pings. A direct question or @mention gets a response.
2. **"channels unresolved" at startup** — Normal. Channels resolve after the Discord gateway finishes caching (~1-2 seconds after login). Check the log for `logged in to discord as` to confirm success.
3. **Service file matters** — The systemd service must set `HOME=/home/michael` so OpenClaw reads `~/.openclaw/openclaw.json`. Without this, it won't find the config.
4. **Gateway port conflicts** — Todd uses 18790, Android-17 uses 18789. Android-16 uses **18791**. Never overlap.
5. **Token in config** — The Discord bot token lives in `openclaw.json` under `channels.discord.token`. If you regenerate the token in Discord Developer Portal, update both the live config on .143 AND this repo.

## Quick Start

See `DEPLOYMENT.md` for step-by-step deployment instructions.
If restoring from a failure, see `RESTORE.md` for disaster recovery.
