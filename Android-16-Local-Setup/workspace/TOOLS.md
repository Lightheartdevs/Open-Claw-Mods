# Tools & Environment

## SSH Access

| Host | User | Auth | Purpose |
|------|------|------|---------|
| 192.168.0.122 | michael | Key-based (ed25519, no password) | GPU server, vLLM, Docker, Android-17's home |
| 192.168.0.143 | michael | Local (this machine) | OpenClaw host, my home |

## GitHub Repos

| Repo | Purpose |
|------|---------|
| `Lightheartdevs/Android-Labs` | Collective workspace, long-term memory |
| `Lightheartdevs/Open-Claw-Mods` | OpenClaw modifications and setup documentation |

## Key Ports

**On .122 (GPU server):**

| Port | Service |
|------|---------|
| 8000 | vLLM direct (DO NOT use for sub-agents) |
| 8003 | vLLM tool proxy (USE THIS) |
| 8001 | Faster-Whisper STT |
| 8080 | RAG research assistant |
| 8083 | Text embeddings (HuggingFace TEI) |
| 8880 | Kokoro TTS |
| 8888 | SearXNG search |
| 7860 | Flux image generation |
| 3000 | Open WebUI |
| 3001 | Dream Dashboard UI |
| 3002 | Dream Dashboard API |
| 5678 | n8n workflow automation |
| 6333 | Qdrant vector DB |

**Smart Proxy (load-balanced across both GPUs):**

| Port | Service |
|------|---------|
| 9100 | vLLM round-robin |
| 9101 | Whisper STT |
| 9102 | Kokoro TTS |
| 9103 | Embeddings |
| 9104 | Flux images |
| 9105 | SearXNG |
| 9106 | Qdrant |
| 9107 | Coder only (.122) |
| 9108 | Sage only (.143) |
| 9199 | Cluster health |

## Google Calendar

Read-only iCal: `michael@lightheartlabs.com` (URL in Android-Labs docs)
