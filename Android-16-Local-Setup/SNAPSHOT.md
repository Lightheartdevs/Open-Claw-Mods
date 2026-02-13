# Live Server Snapshot — 2026-02-13

Captured from the running system during stress testing. Use this to verify a restore matches the known-good state.

---

## Server: 192.168.0.143 (Tower2 — OpenClaw Host)

### System
- **OS:** Ubuntu 24.04 LTS
- **Kernel:** Linux Tower2 6.17.0-14-generic x86_64
- **RAM:** 124Gi total, ~17Gi used, ~107Gi available
- **Disk:** /dev/nvme0n1p2 1.8T, 961G used (56%), 778G avail
- **Uptime:** 15+ hours at time of snapshot

### Software Versions
| Component | Version |
|-----------|---------|
| Node.js | v22.22.0 (system-wide at `/usr/bin/node`) |
| OpenClaw | 2026.2.12 (at `/usr/bin/openclaw`) |
| npm | 10.9.4 |

### OpenClaw Config (`~/.openclaw/openclaw.json`)
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

### Workspace Files (`~/.openclaw/workspace/`)
```
AGENTS.md
BOOTSTRAP.md
HEARTBEAT.md
IDENTITY.md
SOUL.md
TOOLS.md
USER.md
```

### SSH Config (`~/.ssh/config`)
```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/android-collective
  IdentitiesOnly yes

Host github-collective
    HostName github.com
    User git
    IdentityFile ~/.ssh/android-collective
    IdentitiesOnly yes

Host 192.168.0.122
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    User michael
```

### SSH Public Key
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPoNSurTyWzlS4RyWQTQOzLy/hxcni6G4wohrShV8j3c android-16@tower2
```

---

## Server: 192.168.0.122 (lightheartworker — GPU + vLLM Host)

### System
- **OS:** Ubuntu 24.04 LTS
- **Kernel:** Linux lightheartworker 6.17.0-14-generic x86_64
- **Disk:** /dev/nvme0n1p2 1.8T, 887G used (52%), 852G avail

### GPU
- **Model:** NVIDIA RTX PRO 6000 Blackwell
- **VRAM:** 97887 MiB total, 89375 MiB used (~91%)
- **Temperature:** 67 C
- **Power:** 305W / 600W cap
- **Utilization:** 100% (model loaded and serving)

### Software Versions
| Component | Version |
|-----------|---------|
| Python | 3.12.3 |
| Flask | 3.1.2 |
| Docker | installed with nvidia runtime |

### vLLM Container
- **Name:** `vllm-coder`
- **Image:** `vllm/vllm-openai:v0.14.0`
- **Status:** running (started 2026-02-12T19:04:55Z)
- **Command args:**
  ```
  --model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
  --port 8000
  --gpu-memory-utilization 0.90
  --max-model-len 32768
  --enable-auto-tool-choice
  --tool-call-parser hermes
  --tensor-parallel-size 1
  ```
- **Port:** 8000 (internal, accessible from LAN)
- **Model weights:** `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-32B-Instruct-AWQ/`

### Proxy Process
- **Script:** `/home/michael/vllm-tool-proxy.py`
- **PID:** 1555004
- **Command:** `python3 /home/michael/vllm-tool-proxy.py --port 8003 --vllm-url http://192.168.0.122:8000`
- **Port:** 8003 (accessible from LAN)
- **Log:** `/tmp/vllm-proxy.log`
- **Health check:** `curl http://localhost:8003/health` returns `{"status":"ok","version":"v4","vllm_url":"http://192.168.0.122:8000"}`

### Other Running Containers (on .122 at time of snapshot)
```
token-spy-dashboard-1   Up 10 hours
token-spy-collector-1   Up 12 hours
token-spy-db            Up 23 hours (healthy)
dream-dashboard         Up 25 hours (healthy)
dream-dashboard-api     Up 25 hours (healthy)
dream-node-exporter     Up 25 hours
dream-grafana           Up 25 hours
dream-prometheus        Up 25 hours
dream-cadvisor          Up 25 hours (healthy)
```

---

## Network Connectivity (Verified)

| From | To | Port | Protocol | Status |
|------|----|------|----------|--------|
| .143 | .122:8003 | TCP | HTTP (proxy) | OK |
| .143 | .122:22 | TCP | SSH (key-based) | OK |
| .122 (proxy) | .122:8000 | TCP | HTTP (vLLM) | OK |
| .143 OpenClaw | .122:8003 | TCP | HTTP+SSE | OK |

---

## How to Verify This Snapshot Matches Your System

```bash
# On .143:
openclaw --version                                    # 2026.2.12
node --version                                        # v22.22.0
cat ~/.openclaw/openclaw.json | python3 -m json.tool  # Should match above
ssh -o BatchMode=yes michael@192.168.0.122 'echo OK'  # Should print OK

# On .122:
docker inspect vllm-coder --format '{{.Config.Image}}'   # vllm/vllm-openai:v0.14.0
curl -s http://localhost:8000/v1/models | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"][0]["id"])'  # Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
curl -s http://localhost:8003/health | python3 -m json.tool  # status: ok, version: v4
python3 --version   # 3.12.3
python3 -c 'import flask; print(flask.__version__)'  # 3.1.2
```
