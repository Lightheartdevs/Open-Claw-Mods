# Stress Test Results

## Test Environment
- **OpenClaw:** v2026.2.12 on 192.168.0.143 (Ubuntu 24.04, Node 22)
- **Model:** Qwen/Qwen2.5-Coder-32B-Instruct-AWQ via vLLM v0.14.0
- **Proxy:** vllm-tool-proxy.py v4 + SSE patch on 192.168.0.122:8003
- **Date:** 2026-02-13

## Test Command Format
```bash
VLLM_API_KEY=vllm-local openclaw agent --local --agent main -m '<prompt>'
```

---

## Test 1: File Write + Read
**Prompt:** `Create a file at /tmp/openclaw-test/hello.txt with the content "Hello from OpenClaw with local Qwen!"`
then: `Read the file /tmp/openclaw-test/hello.txt and show me its contents`

**Result: PASS**
- Agent used `write` tool to create the file
- Agent used `read` tool to read it back
- Content was correct

## Test 2: File Edit
**Prompt:** `Edit /tmp/openclaw-test/hello.txt and change the date from 2024 to 2025`

**Result: PARTIAL**
- Agent correctly used `edit` tool for the text replacement (worked)
- When asked to append text, agent incorrectly used `write` (overwrite) instead of `edit`
- This is a model reasoning issue, not a tool/infrastructure issue

## Test 3: Command Execution (Multiple)
**Prompt:** `Run these commands and show me the output: uname -a, df -h /, free -h, uptime`

**Result: PASS**
- Agent used `exec` tool
- All four commands returned correctly formatted output
- System information displayed properly

## Test 4: Multi-step Chain (6 steps)
**Prompt:** A complex 6-step task involving creating directory, writing file, reading it, modifying it, moving it, and verifying

**Result: FAIL**
- First tool call (mkdir) succeeded
- Model then got stuck in repetition loop
- `<|im_start|>` tokens leaked into output
- Same tool call JSON repeated continuously
- Proxy's MAX_TOOL_CALLS=20 safety net eventually stopped it
- **Root cause:** Known Qwen2.5 limitation with complex sequential tool chains

## Test 5: File Move
**Prompt:** `Move /tmp/openclaw-test/hello.txt to /tmp/openclaw-test/hello-moved.txt`

**Result: PASS** (confirmed by file existing at destination)

## Test 6: File Copy
**Prompt:** `Copy /tmp/openclaw-test/hello-moved.txt to /tmp/openclaw-test/hello-copy.txt`

**Result: PASS**
- Agent used `exec` tool with `cp` command
- File copied successfully, verified with `ls -la`

## Test 7: File Delete
**Prompt:** `Delete the file /tmp/openclaw-test/hello-copy.txt`

**Result: PASS**
- Agent used `exec` tool with `rm` command
- File deleted, confirmed absent

## Test 8: SSH to Remote Host
**Prompt:** `SSH to 192.168.0.122 as michael and run: hostname && uname -a`

**Result: HANG**
- Agent attempted `ssh michael@192.168.0.122`
- SSH prompted for password (`michael@192.168.0.122's password:`)
- Agent cannot provide interactive input
- Process hung indefinitely
- **Workaround:** Set up key-based SSH with `StrictHostKeyChecking=no`

---

## Summary Table

| # | Test | Tools Used | Result | Notes |
|---|------|-----------|--------|-------|
| 1 | File Write + Read | write, read | PASS | Clean execution |
| 2 | File Edit | edit, write | PARTIAL | Edit works, model picks wrong tool for append |
| 3 | Multiple Commands | exec | PASS | All commands returned correctly |
| 4 | Multi-step Chain | exec (repeated) | FAIL | Repetition loop, known Qwen2.5 issue |
| 5 | File Move | exec (mv) | PASS | File relocated correctly |
| 6 | File Copy | exec (cp) | PASS | File duplicated correctly |
| 7 | File Delete | exec (rm) | PASS | File removed correctly |
| 8 | SSH Remote | exec (ssh) | HANG | Password prompt blocks agent |

## Recommendations

1. **Keep prompts simple** — single-action prompts work reliably; multi-step chains may fail
2. **Use absolute paths** — the agent's working directory is `~/.openclaw/workspace`, not where you launched it
3. **Avoid interactive commands** — no password prompts, no sudo, no editors (vim/nano)
4. **For SSH** — configure key-based auth with `StrictHostKeyChecking=no` in `~/.ssh/config`
5. **Monitor proxy logs** — `tail -f /tmp/vllm-proxy.log` shows tool extraction and SSE re-wrapping activity
