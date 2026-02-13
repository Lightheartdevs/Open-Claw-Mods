# Deployment Guide

## Prerequisites

### Server 1: OpenClaw Host (192.168.0.143)
- Ubuntu 24.04 LTS
- Node.js >= 22 (`node --version` → v22.22.0)
- SSH key-based access to vLLM host
- Network access to vLLM host on port 8003

### Server 2: vLLM + Proxy Host (192.168.0.122)
- Ubuntu 24.04 LTS
- Python 3.12+ with Flask 3.1+
- Docker with NVIDIA GPU runtime
- GPU with >= 96GB VRAM (for Qwen3-Coder-Next-FP8, ~75GB model weights)
- Ports 8000 (vLLM) and 8003 (proxy) accessible from .143

## Step 1: Start vLLM (on .122)

Using Docker (recommended):
```bash
docker run -d \
  --name vllm-coder \
  --gpus all \
  --shm-size 16g \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-Coder-Next-FP8 \
  --port 8000 \
  --gpu-memory-utilization 0.92 \
  --max-model-len 131072 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --tensor-parallel-size 1 \
  --compilation_config.cudagraph_mode=PIECEWISE
```

**Important flags:**
- `--tool-call-parser qwen3_coder` — native tool calling parser for this model (NOT hermes)
- `--compilation_config.cudagraph_mode=PIECEWISE` — prevents CUDA memory access errors with hybrid DeltaNet
- `--gpu-memory-utilization 0.92` — 0.95 can cause crashes, 0.92 is safe
- `--max-model-len 131072` — 128K context; can try 262144 (256K) if needed
- Do **NOT** use `--kv-cache-dtype fp8` — causes assertion errors with Qwen3-Next architecture

Verify it's running (model takes ~60-90 seconds to load):
```bash
until curl -s http://localhost:8000/v1/models > /dev/null 2>&1; do sleep 5; echo "waiting..."; done
curl http://localhost:8000/v1/models
```

You should see `Qwen/Qwen3-Coder-Next-FP8` in the model list.

## Step 2: Deploy the Proxy (on .122)

Copy `proxy/vllm-tool-proxy.py` to `/home/michael/vllm-tool-proxy.py`.

Install dependencies:
```bash
pip3 install flask requests
```

Start the proxy:
```bash
nohup python3 /home/michael/vllm-tool-proxy.py \
  --port 8003 \
  --vllm-url http://192.168.0.122:8000 \
  > /tmp/vllm-proxy.log 2>&1 &
```

Verify:
```bash
curl http://localhost:8003/health
# Expected: {"status":"ok","version":"v4","vllm_url":"http://192.168.0.122:8000"}
```

## Step 3: Install OpenClaw (on .143)

```bash
sudo npm install -g openclaw@latest
openclaw --version  # Should show 2026.2.12 or later
```

Run initial setup if first install:
```bash
openclaw setup
```

## Step 4: Configure OpenClaw (on .143)

Copy `configs/openclaw.json` to `~/.openclaw/openclaw.json`:
```bash
# From your local machine:
scp configs/openclaw.json michael@192.168.0.143:~/.openclaw/openclaw.json
```

The config includes:
- **models** — vLLM provider pointing to proxy on :8003 with compat flags
- **channels.discord** — Bot token, guild, 9 channels (requireMention=false only for #android-16)
- **gateway** — Port 18791 with LAN binding
- **plugins** — Discord plugin enabled
- **messages** — ackReactionScope for group mentions

See `configs/openclaw.json` in this repo for the full file.

**Critical:** The `baseUrl` MUST point to port **8003** (proxy), NOT 8000 (vLLM direct).

Delete the auto-generated models cache:
```bash
rm -f ~/.openclaw/agents/main/agent/models.json
```

Set the API key in your environment:
```bash
echo 'export VLLM_API_KEY=vllm-local' >> ~/.bashrc
source ~/.bashrc
```

## Step 5: Deploy the Gateway Service (on .143)

Copy the systemd service file:
```bash
# From your local machine:
scp configs/openclaw-gateway.service michael@192.168.0.143:~/.config/systemd/user/openclaw-gateway.service
```

Enable and start:
```bash
ssh michael@192.168.0.143
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway.service
systemctl --user start openclaw-gateway.service
```

Verify it started:
```bash
systemctl --user status openclaw-gateway.service
```

You should see:
- `Active: active (running)`
- `[gateway] agent model: vllm/Qwen/Qwen3-Coder-Next-FP8`
- `[discord] starting provider (@Android-16 (Local))`
- `[discord] logged in to discord as 1470898132668776509`
- `[gateway] listening on ws://0.0.0.0:18791`

**Note:** "channels unresolved" at startup is normal — they resolve within 1-2 seconds after Discord login.

**Note:** "channels unresolved" at startup is normal — they resolve within 1-2 seconds after Discord login.

### Gateway Service Details
| Setting | Value |
|---------|-------|
| Service name | `openclaw-gateway.service` |
| Port | 18791 |
| Service file | `~/.config/systemd/user/openclaw-gateway.service` |
| Config read from | `~/.openclaw/openclaw.json` (via `HOME=/home/michael`) |
| Auto-restart | Yes (RestartSec=5) |
| Starts on boot | Yes (enabled, WantedBy=default.target) |
| Logs | `journalctl --user -u openclaw-gateway.service` |
| Detailed log | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |

## Step 6: Verify the Setup

Check agent configuration:
```bash
openclaw agents list
# Should show: Model: vllm/Qwen/Qwen3-Coder-Next-FP8
```

Run a simple test:
```bash
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m 'What is 2+2?'
```

Run a tool test:
```bash
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m 'List the files in /tmp'
```

If both return sensible output, the setup is working.

## Troubleshooting

### "No reply from agent" with 0 tokens
- **Cause:** SSE re-wrapping not working. The proxy is returning non-streaming JSON but OpenClaw expects SSE.
- **Check:** `curl -X POST http://192.168.0.122:8003/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"Qwen/Qwen3-Coder-Next-FP8","messages":[{"role":"user","content":"hi"}],"stream":true}'`
- **Expected:** You should see `data: {...}\n\n` SSE chunks, ending with `data: [DONE]`

### Config validation errors on startup
- **Cause:** Using unsupported compat fields like `supportsStrictMode`, `supportedParameters`, `streaming`, `fallback`
- **Fix:** Only use validated fields: `supportsDeveloperRole`, `supportsStore`, `maxTokensField`, `supportsReasoningEffort`

### Tool calls returned as plain text
- **Cause:** Proxy not extracting tool calls, or OpenClaw pointing directly to vLLM instead of proxy
- **Check:** Verify `baseUrl` in openclaw.json points to port 8003 (proxy), not 8000 (vLLM)

### Agent gets stuck in repetition loop
- **Cause:** Model limitation with complex multi-step tool chains (much less likely with Qwen3-Coder-Next)
- **Mitigation:** The proxy's MAX_TOOL_CALLS=20 eventually stops it. Keep prompts simple and single-action when possible.

### vLLM crashes with assertion error on startup
- **Cause:** Using `--kv-cache-dtype fp8` with Qwen3-Next architecture
- **Fix:** Do NOT use `--kv-cache-dtype fp8`. The FP8 model weights are fine, but FP8 KV cache is not supported for this architecture.

### vLLM crashes with CUDA illegal memory access
- **Cause:** Default cudagraph mode is incompatible with hybrid DeltaNet layers
- **Fix:** Add `--compilation_config.cudagraph_mode=PIECEWISE` to the docker run command

### vLLM rejects `store` parameter
- **Cause:** Missing `"supportsStore": false` in compat
- **Fix:** Add it to the compat section of openclaw.json

### vLLM rejects `max_completion_tokens`
- **Cause:** Missing `"maxTokensField": "max_tokens"` in compat
- **Fix:** Add it to the compat section

### SSH/interactive commands hang
- **Cause:** The agent's exec tool cannot provide interactive input (passwords, confirmations)
- **Workaround:** Use key-based SSH with `StrictHostKeyChecking=no`, or avoid interactive commands entirely
