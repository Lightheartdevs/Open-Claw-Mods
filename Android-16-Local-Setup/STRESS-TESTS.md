# Stress Test Results

## Test Environment
- **OpenClaw:** v2026.2.12 on 192.168.0.143 (Ubuntu 24.04, Node 22)
- **Model:** Qwen/Qwen2.5-Coder-32B-Instruct-AWQ via vLLM v0.14.0
- **Proxy:** vllm-tool-proxy.py v4 + SSE patch on 192.168.0.122:8003
- **GPU:** NVIDIA RTX PRO 6000 Blackwell (96GB VRAM) on .122

## Test Command Format
```bash
VLLM_API_KEY=vllm-local openclaw agent --local --agent main --json -m '<prompt>'
```

---

## Round 1 — Initial Tests (2026-02-13 AM)

### Test 1: File Write + Read
**Prompt:** `Create a file at /tmp/openclaw-test/hello.txt with the content "Hello from OpenClaw with local Qwen!"`
then: `Read the file /tmp/openclaw-test/hello.txt and show me its contents`

**Result: PASS**
- Agent used `write` tool to create the file
- Agent used `read` tool to read it back
- Content was correct

### Test 2: File Edit
**Prompt:** `Edit /tmp/openclaw-test/hello.txt and change the date from 2024 to 2025`

**Result: PARTIAL**
- Agent correctly used `edit` tool for the text replacement (worked)
- When asked to append text, agent incorrectly used `write` (overwrite) instead of `edit`
- This is a model reasoning issue, not a tool/infrastructure issue

### Test 3: Command Execution (Multiple)
**Prompt:** `Run these commands and show me the output: uname -a, df -h /, free -h, uptime`

**Result: PASS**
- Agent used `exec` tool
- All four commands returned correctly formatted output
- System information displayed properly

### Test 4: Multi-step Chain (6 steps)
**Prompt:** A complex 6-step task involving creating directory, writing file, reading it, modifying it, moving it, and verifying

**Result: FAIL**
- First tool call (mkdir) succeeded
- Model then got stuck in repetition loop
- `<|im_start|>` tokens leaked into output
- Same tool call JSON repeated continuously
- Proxy's MAX_TOOL_CALLS=20 safety net eventually stopped it
- **Root cause:** Known Qwen2.5 limitation with complex sequential tool chains

### Test 5: File Move
**Prompt:** `Move /tmp/openclaw-test/hello.txt to /tmp/openclaw-test/hello-moved.txt`

**Result: PASS** (confirmed by file existing at destination)

### Test 6: File Copy
**Prompt:** `Copy /tmp/openclaw-test/hello-moved.txt to /tmp/openclaw-test/hello-copy.txt`

**Result: PASS**
- Agent used `exec` tool with `cp` command
- File copied successfully, verified with `ls -la`

### Test 7: File Delete
**Prompt:** `Delete the file /tmp/openclaw-test/hello-copy.txt`

**Result: PASS**
- Agent used `exec` tool with `rm` command
- File deleted, confirmed absent

### Test 8: SSH to Remote Host
**Prompt:** `SSH to 192.168.0.122 as michael and run: hostname && uname -a`

**Result: HANG**
- Agent attempted `ssh michael@192.168.0.122`
- SSH prompted for password (`michael@192.168.0.122's password:`)
- Agent cannot provide interactive input
- Process hung indefinitely
- **Workaround:** Set up key-based SSH with `StrictHostKeyChecking=no`

### Round 1 Summary

| # | Test | Tools Used | Result | Notes |
|---|------|-----------|--------|-------|
| 1 | File Write + Read | write, read | PASS | Clean execution |
| 2 | File Edit | edit, write | PARTIAL | Edit works, model picks wrong tool for append |
| 3 | Multiple Commands | exec | PASS | All commands returned correctly |
| 4 | Multi-step Chain (6) | exec (repeated) | FAIL | Repetition loop, known Qwen2.5 issue |
| 5 | File Move | exec (mv) | PASS | File relocated correctly |
| 6 | File Copy | exec (cp) | PASS | File duplicated correctly |
| 7 | File Delete | exec (rm) | PASS | File removed correctly |
| 8 | SSH Remote | exec (ssh) | HANG | Password prompt blocks agent |

---

## Round 2 — Extended Agentic Tests (2026-02-13 PM)

**Changes since Round 1:**
- Set up SSH key-based auth from .143 → .122 (ed25519, StrictHostKeyChecking=no)
- Sessions cleared between tests for clean state
- Used `--json` output flag for structured result capture

### Test 9: File Write (fresh session)
**Prompt:** `Create directory /tmp/a16-stress then write a file /tmp/a16-stress/test1.txt with: Hello from Android-16 stress test`

**Result: PASS** — 5268ms, 3 tool calls (mkdir, write, read-verify)
- Agent created dir, wrote file, read it back to verify
- `<|im_start|>` token leaked in verification payload but task still completed
- File content verified: `Hello from Android-16 stress test`

### Test 10: File Read
**Prompt:** `Read the file /tmp/a16-stress/test1.txt and tell me exactly what it contains`

**Result: PASS** — 1024ms, clean single-turn response
- Correctly reported file contents
- No token leak, no issues

### Test 11: File Edit (text replacement)
**Prompt:** `Edit the file /tmp/a16-stress/test1.txt and replace the word Hello with Greetings`

**Result: PASS** — 2388ms
- Used edit tool correctly
- File verified: `Greetings from Android-16 stress test`

### Test 12: Multi-Command Execution
**Prompt:** `Run these commands and show me the output: uname -a, df -h /, free -h, uptime`

**Result: PASS** — 6893ms
- All 4 commands returned correctly
- Clean output formatting with headers

### Test 13: 2-Step Chain (mkdir + write)
**Prompt:** `Create directory /tmp/a16-stress/chain2, then write info.txt with version=1.0 and status=active on separate lines`

**Result: PASS** — 2297ms, tools-only (no text payload)
- Both steps executed correctly
- File verified with correct multiline content

### Test 14: Write Script + Execute (2-step tool chain)
**Prompt:** `Write a Python script at /tmp/a16-stress/hello.py that prints Hello World, then execute it with python3`

**Result: PASS** — 2066ms
- Wrote valid Python script
- Executed it, output: `Hello World`

### Test 15: 3-Step Chain (write, read, edit)
**Prompt:** `Write /tmp/a16-stress/config.ini with [server] section, read it back, edit debug=true to debug=false`

**Result: PASS** — 5873ms
- All 3 operations executed correctly
- File verified: `debug=false` (changed from `debug=true`)

### Test 16: 4-Step Chain (multi-numbered)
**Prompt:** `4 steps: mkdir, write count=0, read to confirm, edit to count=1`

**Result: PARTIAL** — 136437ms (timed out at max_tokens=8192)
- Steps 1-2 executed (mkdir + write verified)
- Model got stuck planning all 4 steps as JSON code blocks instead of executing sequentially
- Repetition loop triggered before steps 3-4 could execute
- **Root cause:** Numbered multi-step prompts trigger Qwen2.5's planning loop

### Test 17: 5-Step Chain (real project setup)
**Prompt:** `5 steps: mkdir project dir, write Flask app.py, write requirements.txt, ls to verify, read main.py to confirm`

**Result: PASS** — 11123ms
- All 5 steps completed correctly
- Flask app with `/hello` endpoint, proper `requirements.txt`, `Dockerfile`
- `<|im_start|>` token leaked in payload [1] but self-recovered
- Files verified: valid Python, valid Dockerfile

### Test 18: 6-Step Chain (previously FAIL)
**Prompt:** `6 steps: mkdir webapp, write app.py with /health endpoint, write test_app.py, write Dockerfile, ls to verify, read app.py`

**Result: PASS** — 14103ms
- All 6 steps completed correctly
- Generated: proper Flask app, unittest file with test_client, valid Dockerfile
- This was previously a FAIL in Round 1 — **now passing**

### Test 19: 8-Step Chain
**Prompt:** `8 steps: mkdir, write 3 files (step1-3.txt), ls, cat each of the 3 files`

**Result: PASS** — 10732ms
- All 8 steps completed correctly
- All files created with correct content
- All reads verified

### Test 20: 10-Step Chain (new frontier)
**Prompt:** `10 steps: mkdir, write 3 files, ls, read 2 files, edit 1 file (cc→CC), read to verify edit, echo confirmation`

**Result: PASS** — 11274ms
- All 10 steps completed correctly
- Edit operation (cc→CC) verified
- Files: a.txt=aa, b.txt=bb, c.txt=CC (edited from cc)

### Test 21: SSH to Remote Host (previously HANG)
**Prompt:** `SSH to 192.168.0.122 and run: hostname && uname -a && docker ps`

**Result: PASS** — 39102ms
- SSH with key-based auth worked perfectly
- Returned hostname, kernel info, and full Docker container list
- **This was previously HANG — now fixed with key-based auth**

### Test 22: Cross-Server GPU + Disk Check
**Prompt:** `SSH to 192.168.0.122 and check GPU status with nvidia-smi, then check disk space with df -h /`

**Result: PASS** — 5637ms
- nvidia-smi: RTX PRO 6000 Blackwell, 67°C, 305W/600W, 89375/97887 MiB, 100% util
- df: 1.8T total, 887G used, 52%
- Clean formatted output

### Test 23: Git Operations (init, write, commit)
**Prompt:** `Init git repo at /tmp/a16-stress/git-test, create README.md, stage and commit with "initial commit"`

**Result: PASS** — 7703ms
- Self-corrected when git commit failed due to missing user.name/email
- Configured git identity and retried — **genuine agentic problem-solving**
- Commit verified: `defba01 initial commit`

### Test 24: Multi-File Edit (modify 2 existing files)
**Prompt:** `Edit app.py to add /version endpoint, edit Dockerfile to expose port 5000`

**Result: FAIL** — 120030ms (timeout, aborted)
- Correctly planned both edits
- Struggled with edit tool semantics (add vs replace)
- Overwrote app.py with only the new endpoint (lost original code)
- Dockerfile not modified
- **Root cause:** Model uses `write` (overwrite) instead of `edit` for adding new content

### Test 25: Bug Finding + Fixing
**Prompt:** `Read calculator.py, run it, find the bug (divide does a*b instead of a/b), fix it with edit, re-run to verify`

**Result: PARTIAL** — 120034ms (timeout, aborted)
- Correctly identified the bug: `return a * b` should be `return a / b`
- Generated correct edit instruction but `<|im_start|>` token leaked mid-output
- Tool call JSON emitted as content text instead of structured tool_call
- Edit was never executed
- **Root cause:** Token leak corrupts tool call emission on complex reasoning chains

### Test 26: System Diagnostics (top command)
**Prompt:** `Check what processes are using the most CPU by running top -bn1 and summarize top 5`

**Result: PASS** — 7369ms
- Ran `top -bn1`, parsed output, summarized top 5 processes
- Clean formatted output with PID, command, user, CPU%

---

## Round 2 Summary

| # | Test | Steps | Result | Time | Notes |
|---|------|-------|--------|------|-------|
| 9 | File Write | 1 | PASS | 5.3s | Clean, minor token leak in verify step |
| 10 | File Read | 1 | PASS | 1.0s | Clean |
| 11 | File Edit | 1 | PASS | 2.4s | Correct text replacement |
| 12 | Multi-Command | 1 | PASS | 6.9s | 4 commands, all correct |
| 13 | 2-Step Chain | 2 | PASS | 2.3s | mkdir + write |
| 14 | Write + Execute | 2 | PASS | 2.1s | Python script creation + run |
| 15 | 3-Step Chain | 3 | PASS | 5.9s | write, read, edit |
| 16 | 4-Step Chain (numbered) | 4 | PARTIAL | 136s | Steps 1-2 OK, planning loop on 3-4 |
| 17 | 5-Step Chain (project) | 5 | PASS | 11.1s | Flask app + requirements + Dockerfile |
| 18 | 6-Step Chain | 6 | PASS | 14.1s | **Previously FAIL — now PASS** |
| 19 | 8-Step Chain | 8 | PASS | 10.7s | All files created and verified |
| 20 | 10-Step Chain | 10 | PASS | 11.3s | Edit + verify included |
| 21 | SSH Remote | 2 | PASS | 39.1s | **Previously HANG — now PASS** |
| 22 | Cross-Server GPU Check | 2 | PASS | 5.6s | nvidia-smi + df via SSH |
| 23 | Git Operations | 4 | PASS | 7.7s | Self-corrected git config error |
| 24 | Multi-File Edit | 2 | FAIL | 120s | Overwrites instead of editing |
| 25 | Bug Find + Fix | 4 | PARTIAL | 120s | Found bug, token leak blocked fix |
| 26 | System Diagnostics | 1 | PASS | 7.4s | top -bn1 parsed correctly |

---

## Overall Score

**Round 1:** 6/8 pass (75%)
**Round 2:** 14/18 pass, 2 partial, 2 fail (78% pass, 89% functional)
**Combined:** 20/26 pass, 3 partial, 3 fail (77% pass, 88% functional)

## Key Improvements Since Round 1

1. **SSH now works** — key-based auth from .143→.122 with StrictHostKeyChecking=no
2. **Multi-step chains dramatically improved** — 6-step (previously FAIL) now passes; 8 and 10-step chains pass
3. **Cross-server workflows work** — SSH + nvidia-smi, docker ps, remote diagnostics
4. **Git operations work** — including self-correction on missing git config
5. **Session clearing between tests helps** — prevents context pollution from prior conversations

## Remaining Failure Modes

1. **Multi-file edit (adding content to existing files)** — model uses `write` (overwrite) instead of `edit` (modify). This loses existing code. Workaround: explicit prompt "use the edit tool with oldText and newText".
2. **Complex reasoning + tool execution** — when the agent needs to reason about a bug AND execute a fix, `<|im_start|>` tokens leak and corrupt the tool call JSON. The fix is identified correctly but never executed.
3. **Numbered step prompts with 4+ steps** — explicitly numbering "do step 1, step 2, ..." can trigger planning loops. Natural language descriptions of the same tasks succeed.
4. **Token leak (`<|im_start|>`)** — appears in ~30% of multi-step responses but is usually non-fatal. The model self-recovers in most cases. Fatal only when it occurs mid-tool-call emission.

## Recommendations

1. **Use natural language descriptions** over numbered step lists — "create a Flask project with an app, tests, and Dockerfile" works better than "step 1: mkdir, step 2: write..."
2. **Clear sessions between complex tasks** — `rm ~/.openclaw/agents/main/sessions/*.jsonl`
3. **Use absolute paths** — the agent's working directory is `~/.openclaw/workspace`
4. **Avoid interactive commands** — no password prompts, no sudo, no editors (vim/nano)
5. **For SSH** — key-based auth is now configured (.143→.122)
6. **For file edits** — explicitly tell the model to use the edit tool with oldText/newText
7. **Monitor proxy logs** — `tail -f /tmp/vllm-proxy.log` shows tool extraction and SSE re-wrapping
8. **Single-action prompts are most reliable** — 1-3 step tasks have ~100% success rate
9. **Multi-step chains up to 10 steps work** when the steps are concrete file operations (write, read, exec)
10. **Chains involving reasoning + editing are the weak point** — consider breaking these into separate prompts
