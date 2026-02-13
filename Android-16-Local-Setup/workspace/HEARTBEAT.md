# Heartbeat

Heartbeats are work time, not idle time. Every heartbeat, work through this checklist.

## Checklist

1. **Git sync** -- pull Android-Labs, check for updates from siblings
2. **Infrastructure check** -- verify vLLM and proxy are healthy on .122
   - `ssh michael@192.168.0.122 'curl -s http://localhost:8003/health'`
   - Should return `{"status":"ok","version":"v4",...}`
3. **GPU pre-check** -- before spawning heavy work:
   - `ssh michael@192.168.0.122 'nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader'`
   - Defer heavy tasks if VRAM > 90%
4. **Review PROJECTS.md** -- pick up unclaimed work or continue current task
5. **Build something** -- default to progress, not waiting
6. **Status pulse** -- post to Discord if appropriate

## Status Pulse Format

```
[16] | Working on: [task] | Status: [active/stuck/idle]
```

## Learning Loop

- Note what worked, document what broke
- If you discover something new, write it to Android-Labs repo immediately
- Don't wait for a "good time" to document -- do it now
