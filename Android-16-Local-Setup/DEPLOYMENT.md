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
- GPU with >= 24GB VRAM (for AWQ 4-bit, 32B model)
- Ports 8000 (vLLM) and 8003 (proxy) accessible from .143

## Step 1: Start vLLM (on .122)

Using Docker (recommended):
```bash
docker run -d \
  --name vllm-coder \
  --runtime nvidia \
  --gpus all \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:v0.14.0 \
  --model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ \
  --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --tensor-parallel-size 1
```

Verify it's running:
```bash
curl http://localhost:8000/v1/models
```

You should see the model listed.

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

Copy `configs/openclaw.json` to `~/.openclaw/openclaw.json`.

Or create it manually:
```json
{
  "models": {
    "mode": "merge",
    "providers": {
      "vllm": {
        "baseUrl": "http://192.168.0.122:8003/v1",
        "apiKey": "vllm-local",
        "api": "openai-completions",
        "models": [
          {
            "id": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
            "name": "Qwen 2.5 Coder 32B",
            "reasoning": false,
            "input": ["text"],
            "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
            "contextWindow": 32768,
            "maxTokens": 8192,
            "compat": {
              "supportsDeveloperRole": false,
              "supportsStore": false,
              "maxTokensField": "max_tokens",
              "supportsReasoningEffort": false
            }
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "vllm/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
      }
    }
  }
}
```

**Critical:** The `baseUrl` points to the **proxy** on port 8003, NOT directly to vLLM on port 8000.

Delete the auto-generated models cache:
```bash
rm -f ~/.openclaw/agents/main/agent/models.json
```

Set the API key in your environment:
```bash
echo 'export VLLM_API_KEY=vllm-local' >> ~/.bashrc
source ~/.bashrc
```

## Step 5: Verify the Setup

Check agent configuration:
```bash
openclaw agents list
# Should show: Model: vllm/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
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
- **Check:** `curl -X POST http://192.168.0.122:8003/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"Qwen/Qwen2.5-Coder-32B-Instruct-AWQ","messages":[{"role":"user","content":"hi"}],"stream":true}'`
- **Expected:** You should see `data: {...}\n\n` SSE chunks, ending with `data: [DONE]`

### Config validation errors on startup
- **Cause:** Using unsupported compat fields like `supportsStrictMode`, `supportedParameters`, `streaming`, `fallback`
- **Fix:** Only use validated fields: `supportsDeveloperRole`, `supportsStore`, `maxTokensField`, `supportsReasoningEffort`

### Tool calls returned as plain text
- **Cause:** Proxy not extracting tool calls, or OpenClaw pointing directly to vLLM instead of proxy
- **Check:** Verify `baseUrl` in openclaw.json points to port 8003 (proxy), not 8000 (vLLM)

### Agent gets stuck in repetition loop
- **Cause:** Qwen2.5 limitation with complex multi-step tool chains
- **Mitigation:** The proxy's MAX_TOOL_CALLS=20 eventually stops it. Keep prompts simple and single-action when possible.

### vLLM rejects `store` parameter
- **Cause:** Missing `"supportsStore": false` in compat
- **Fix:** Add it to the compat section of openclaw.json

### vLLM rejects `max_completion_tokens`
- **Cause:** Missing `"maxTokensField": "max_tokens"` in compat
- **Fix:** Add it to the compat section

### SSH/interactive commands hang
- **Cause:** The agent's exec tool cannot provide interactive input (passwords, confirmations)
- **Workaround:** Use key-based SSH with `StrictHostKeyChecking=no`, or avoid interactive commands entirely
