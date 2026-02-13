# Disaster Recovery & Restore Guide

**Last verified working state:** 2026-02-13
**Model:** Qwen3-Coder-Next-FP8 (80B MoE, upgraded from Qwen2.5-Coder-32B)
**Discord:** Online as @Android-16 (Local), bot ID `1470898132668776509`

This guide restores Android-16 (OpenClaw + Qwen3-Coder-Next-FP8 via vLLM) from scratch. Follow in order.

---

## Prerequisites

Two Ubuntu 24.04 servers on the same LAN:
- **192.168.0.143** (Tower2) — OpenClaw host, SSH user: `michael`
- **192.168.0.122** (lightheartworker) — GPU server, SSH user: `michael`

Hardware on .122: NVIDIA RTX PRO 6000 Blackwell (96GB VRAM)

---

## Step 1: Restore vLLM on .122

```bash
ssh michael@192.168.0.122

# Pull the model (skip if already cached at ~/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-Next-FP8/)
# If not cached, vLLM will auto-download on first start (~80GB)
docker pull vllm/vllm-openai:v0.15.1

# Start vLLM
docker run -d \
  --name vllm-coder \
  --gpus all \
  --shm-size 16g \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --restart unless-stopped \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-Coder-Next-FP8 \
  --port 8000 \
  --gpu-memory-utilization 0.92 \
  --max-model-len 131072 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --tensor-parallel-size 1 \
  --compilation_config.cudagraph_mode=PIECEWISE

# Wait for startup (~60-90 seconds for model loading + CUDA graph compilation)
until curl -s http://localhost:8000/v1/models > /dev/null 2>&1; do sleep 5; echo "waiting..."; done
echo "vLLM ready"
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

**CRITICAL FLAGS:**
- `--tool-call-parser qwen3_coder` (NOT hermes — this model has its own native parser)
- `--compilation_config.cudagraph_mode=PIECEWISE` (prevents CUDA memory errors with DeltaNet layers)
- Do **NOT** use `--kv-cache-dtype fp8` (causes assertion errors with Qwen3-Next architecture)
- `--gpu-memory-utilization 0.92` (0.95 can crash; 0.90 wastes VRAM)

**Verify:** You should see `Qwen/Qwen3-Coder-Next-FP8` in the model list.

---

## Step 2: Restore the Proxy on .122

```bash
ssh michael@192.168.0.122

# Install dependencies
pip3 install flask requests

# Copy the proxy from this repo
# (from your local machine):
scp proxy/vllm-tool-proxy.py michael@192.168.0.122:/home/michael/vllm-tool-proxy.py

# Start the proxy
pkill -f vllm-tool-proxy.py 2>/dev/null
nohup python3 /home/michael/vllm-tool-proxy.py \
  --port 8003 \
  --vllm-url http://192.168.0.122:8000 \
  > /tmp/vllm-proxy.log 2>&1 &

# Verify
sleep 2
curl http://localhost:8003/health
# Expected: {"status":"ok","version":"v4","vllm_url":"http://192.168.0.122:8000"}
```

**Verify:** Health endpoint returns status ok. Check logs: `tail -f /tmp/vllm-proxy.log`

---

## Step 3: Install OpenClaw on .143

```bash
ssh michael@192.168.0.143

# Node.js 22 should already be installed system-wide
node --version  # Should be v22.22.0

# Install OpenClaw globally
sudo npm install -g openclaw@2026.2.12

# Verify
openclaw --version  # Should show 2026.2.12
```

---

## Step 4: Restore OpenClaw Config on .143

```bash
ssh michael@192.168.0.143

mkdir -p ~/.openclaw

# Copy config from this repo (includes model, Discord, gateway, plugins)
# (from your local machine):
scp configs/openclaw.json michael@192.168.0.143:~/.openclaw/openclaw.json

# Delete cached models to force regeneration
rm -f ~/.openclaw/agents/main/agent/models.json

# Set API key environment variable
grep -q VLLM_API_KEY ~/.bashrc || echo 'export VLLM_API_KEY=vllm-local' >> ~/.bashrc
source ~/.bashrc
```

**Verify config is correct:**
```bash
python3 -c "import json; c=json.load(open('/home/michael/.openclaw/openclaw.json')); print('baseUrl:', c['models']['providers']['vllm']['baseUrl']); print('model:', c['models']['providers']['vllm']['models'][0]['id']); print('discord:', 'token' in c.get('channels',{}).get('discord',{})); print('gateway port:', c.get('gateway',{}).get('port'))"
# Expected:
# baseUrl: http://192.168.0.122:8003/v1
# model: Qwen/Qwen3-Coder-Next-FP8
# discord: True
# gateway port: 18791
```

**Critical:** The baseUrl MUST point to port **8003** (proxy), NOT 8000 (vLLM direct).

The config now includes:
- `channels.discord` — Bot token, guild `1469753709272764445`, 9 channels
- `plugins.entries.discord.enabled: true` — Activates Discord plugin
- `gateway` — Port 18791, LAN binding, auth token
- `messages.ackReactionScope: "group-mentions"` — Reaction acknowledgment scope

---

## Step 5: Restore SSH Key-Based Auth (.143 → .122)

```bash
ssh michael@192.168.0.143

# Generate key if it doesn't exist
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -C 'android-16@tower2'

# Copy key to .122 (will prompt for password: ##Linux-8488##)
# Install sshpass first if needed: sudo apt-get install -y sshpass
sshpass -p '##Linux-8488##' ssh-copy-id -o StrictHostKeyChecking=no michael@192.168.0.122

# Add SSH config
cat >> ~/.ssh/config << 'EOF'

Host 192.168.0.122
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    User michael
EOF
chmod 600 ~/.ssh/config

# Verify
ssh -o BatchMode=yes michael@192.168.0.122 'echo SSH_OK && hostname'
# Expected: SSH_OK \n lightheartworker
```

---

## Step 6: Restore the Gateway Service on .143

```bash
# Copy the systemd service file from this repo
# (from your local machine):
scp configs/openclaw-gateway.service michael@192.168.0.143:~/.config/systemd/user/openclaw-gateway.service

ssh michael@192.168.0.143

# Reload, enable, and start
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway.service
systemctl --user start openclaw-gateway.service

# Verify
sleep 3
systemctl --user status openclaw-gateway.service
```

**Verify:** You should see:
- `Active: active (running)`
- `[discord] starting provider (@Android-16 (Local))`
- `[discord] logged in to discord as 1470898132668776509`
- `[gateway] listening on ws://0.0.0.0:18791`

**Note:** "channels unresolved" at startup is normal — resolves within 1-2 seconds.

**Gateway port map (avoid conflicts):**
| Agent | Port |
|-------|------|
| Android-17 | 18789 |
| Todd | 18790 |
| Android-16 | 18791 |

---

## Step 7: Verify End-to-End

```bash
ssh michael@192.168.0.143

# Test 1: Simple text response
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m 'What is 2+2?'

# Test 2: Tool call (file write)
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m 'Create a file at /tmp/restore-test.txt with the content: restore successful'

# Test 3: Verify file was created
cat /tmp/restore-test.txt
# Expected: restore successful

# Test 4: SSH via agent
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m 'SSH to 192.168.0.122 and run hostname'
```

If all 4 tests pass, the core restore is complete.

**Test 5: Discord (verify bot is online)**
```bash
# Check gateway service is running and Discord logged in
journalctl --user -u openclaw-gateway.service --since '5 min ago' --no-pager | grep discord
# Expected: "logged in to discord as 1470898132668776509"

# Then go to Discord and @Android-16 in #android-16 channel — he should respond
```

---

## Troubleshooting

### "No reply from agent" with 0 tokens
The SSE re-wrapping isn't working. Check:
```bash
# Test proxy directly
curl -X POST http://192.168.0.122:8003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-Coder-Next-FP8","messages":[{"role":"user","content":"hi"}],"stream":true}'
# Should return: data: {...}\n\n chunks ending with data: [DONE]
```

### Config validation errors on OpenClaw startup
Only use validated compat fields. The working set is:
```json
"compat": {
  "supportsDeveloperRole": false,
  "supportsStore": false,
  "maxTokensField": "max_tokens",
  "supportsReasoningEffort": false
}
```
Do NOT add: `supportsStrictMode`, `supportedParameters`, `streaming`, `fallback`

### vLLM rejects `store` or `max_completion_tokens`
These mean the compat flags are missing. Re-copy `configs/openclaw.json` and delete models cache:
```bash
rm -f ~/.openclaw/agents/main/agent/models.json
```

### Proxy returns 502
vLLM isn't running or isn't reachable from the proxy:
```bash
ssh michael@192.168.0.122
curl http://localhost:8000/v1/models  # Should return model list
docker ps | grep vllm               # Should show running container
```

### SSH still prompts for password
Key auth isn't configured. Re-run Step 5. Check:
```bash
ssh -o BatchMode=yes -v michael@192.168.0.122 'echo ok' 2>&1 | grep -i 'auth'
```

### Agent gets stuck / repetition loop
Clear sessions and try a simpler prompt:
```bash
rm -rf ~/.openclaw/agents/main/sessions/*.jsonl
```

---

## Version Pins (Exact Known-Good State)

| Component | Version | Location |
|-----------|---------|----------|
| OpenClaw | 2026.2.12 | .143: `/usr/bin/openclaw` |
| Node.js | 22.22.0 | .143: system-wide |
| vLLM | 0.15.1 | .122: Docker `vllm/vllm-openai:v0.15.1` |
| Model | Qwen/Qwen3-Coder-Next-FP8 (80B MoE) | .122: `~/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-Next-FP8/` |
| Python | 3.12.3 | .122: system |
| Flask | 3.1.2 | .122: pip |
| Proxy | v4.0 + SSE patch | .122: `/home/michael/vllm-tool-proxy.py` |
| Gateway service | openclaw-gateway.service | .143: `~/.config/systemd/user/` |
| Gateway port | 18791 | .143 |
| Discord bot ID | 1470898132668776509 | Discord |
| Ubuntu | 24.04 LTS | Both servers |
| Kernel | 6.17.0-14-generic | Both servers |
| GPU | RTX PRO 6000 Blackwell (96GB) | .122 |

## File Locations

| File | Server | Path |
|------|--------|------|
| OpenClaw config | .143 | `~/.openclaw/openclaw.json` |
| OpenClaw binary | .143 | `/usr/bin/openclaw` |
| Workspace | .143 | `~/.openclaw/workspace/` |
| Sessions | .143 | `~/.openclaw/agents/main/sessions/*.jsonl` |
| Models cache | .143 | `~/.openclaw/agents/main/agent/models.json` |
| SSH key | .143 | `~/.ssh/id_ed25519` |
| SSH config | .143 | `~/.ssh/config` |
| Gateway service | .143 | `~/.config/systemd/user/openclaw-gateway.service` |
| Gateway logs | .143 | `journalctl --user -u openclaw-gateway.service` |
| Detailed log | .143 | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |
| vLLM Docker | .122 | Container: `vllm-coder` |
| Proxy script | .122 | `/home/michael/vllm-tool-proxy.py` |
| Proxy log | .122 | `/tmp/vllm-proxy.log` |
| Model weights | .122 | `~/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-Next-FP8/` |
