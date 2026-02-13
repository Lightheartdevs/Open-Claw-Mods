# Live Server Snapshot — 2026-02-13 (Updated: Qwen3-Coder-Next Brain Upgrade)

Captured from the running system. Use this to verify a restore matches the known-good state.
**Status:** Model upgraded to Qwen3-Coder-Next-FP8 (80B MoE), Discord online as @Android-16 (Local).

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
Full config now includes model, Discord, gateway, and plugins. See `configs/openclaw.json` in this repo for the exact file.

Key sections:
- `models.providers.vllm.baseUrl` → `http://192.168.0.122:8003/v1` (proxy, NOT direct)
- `channels.discord.token` → Android-16 bot token
- `channels.discord.guilds.1469753709272764445` → 9 channels configured
- `gateway.port` → 18791
- `plugins.entries.discord.enabled` → true

### Gateway Service
- **Service:** `openclaw-gateway.service` (systemd user service)
- **Status:** active (running), enabled (starts on boot)
- **Port:** 18791 (ws://0.0.0.0:18791)
- **Agent model:** `vllm/Qwen/Qwen3-Coder-Next-FP8`
- **Discord:** logged in as `1470898132668776509` (@Android-16 (Local))
- **Service file:** `~/.config/systemd/user/openclaw-gateway.service`

Startup log output:
```
[gateway] agent model: vllm/Qwen/Qwen3-Coder-Next-FP8
[gateway] listening on ws://0.0.0.0:18791
[discord] starting provider (@Android-16 (Local))
[discord] logged in to discord as 1470898132668776509
```

### Workspace Files (`~/.openclaw/workspace/`)
```
AGENTS.md
BOOTSTRAP.md
HEARTBEAT.md
IDENTITY.md
MEMORY.md
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
- **VRAM:** 97887 MiB total, 91105 MiB used (~93%)
- **Temperature:** 35 C (idle)
- **Power:** 15W idle / 600W cap
- **Utilization:** 0% idle (spikes during inference)

### Software Versions
| Component | Version |
|-----------|---------|
| Python | 3.12.3 |
| Flask | 3.1.2 |
| Docker | installed with nvidia runtime |

### vLLM Container
- **Name:** `vllm-coder`
- **Image:** `vllm/vllm-openai:v0.15.1`
- **Status:** running (started 2026-02-13)
- **Model memory:** 74.89 GiB for weights, loaded in ~28 seconds
- **Command args:**
  ```
  --model Qwen/Qwen3-Coder-Next-FP8
  --port 8000
  --gpu-memory-utilization 0.92
  --max-model-len 131072
  --enable-auto-tool-choice
  --tool-call-parser qwen3_coder
  --tensor-parallel-size 1
  --compilation_config.cudagraph_mode=PIECEWISE
  ```
- **Port:** 8000 (internal, accessible from LAN)
- **Model weights:** `~/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-Next-FP8/`
- **Architecture:** Qwen3NextForCausalLM (hybrid DeltaNet + MoE, 80B total / 3B active)
- **Backends:** TRITON Fp8 MoE, FLASHINFER attention
- **Known warning:** Missing optimized MoE config for RTX PRO 6000 Blackwell (uses defaults, functional)

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
python3 -c "import json; c=json.load(open('/home/michael/.openclaw/openclaw.json')); print('baseUrl:', c['models']['providers']['vllm']['baseUrl']); print('discord:', 'token' in c.get('channels',{}).get('discord',{})); print('gateway:', c.get('gateway',{}).get('port'))"
# Expected: baseUrl: http://192.168.0.122:8003/v1 | discord: True | gateway: 18791
ssh -o BatchMode=yes michael@192.168.0.122 'echo OK'  # Should print OK
systemctl --user status openclaw-gateway.service       # Should be active (running)
journalctl --user -u openclaw-gateway.service --since '1 hour ago' --no-pager | grep 'logged in to discord'
# Expected: [discord] logged in to discord as 1470898132668776509

# On .122:
docker inspect vllm-coder --format '{{.Config.Image}}'   # vllm/vllm-openai:v0.15.1
curl -s http://localhost:8000/v1/models | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"][0]["id"])'  # Qwen/Qwen3-Coder-Next-FP8
curl -s http://localhost:8003/health | python3 -m json.tool  # status: ok, version: v4
python3 --version   # 3.12.3
python3 -c 'import flask; print(flask.__version__)'  # 3.1.2
```
