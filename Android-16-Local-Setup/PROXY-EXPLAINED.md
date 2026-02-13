# vllm-tool-proxy.py — How It Works

## Why a Proxy Is Needed

OpenClaw cannot talk directly to vLLM for tool-calling tasks because of three incompatibilities:

1. **OpenClaw always streams** (`stream: true`) but tool call extraction requires seeing the full response
2. **Qwen2.5 outputs tool calls as text** in `<tools>` tags instead of OpenAI's structured `tool_calls` format
3. **vLLM's hermes parser** doesn't catch Qwen2.5-AWQ's tool call output format

The proxy sits between OpenClaw and vLLM, fixing all three issues transparently.

## Request Flow

```
1. OpenClaw sends:     POST /v1/chat/completions
                        {stream: true, tools: [...], messages: [...]}

2. Proxy checks:       Has tools? Yes → force stream: false
                        (saves original was_streaming = true)

3. Proxy strips:       stream_options (vLLM rejects this when stream=false)

4. Proxy checks:       Tool call count in messages > 20? → return stop message

5. Proxy forwards:     POST to vLLM:8000/v1/chat/completions
                        {stream: false, tools: [...], messages: [...]}

6. vLLM responds:      {choices: [{message: {content: "<tools>{...}</tools>"}}]}

7. Proxy extracts:     Parses <tools> tags → structured tool_calls array
                        Cleans content field (removes extracted JSON)

8. Proxy cleans:       Strips vLLM-specific fields (prompt_logprobs, etc.)
                        Removes empty tool_calls arrays
                        Strips reasoning/refusal/annotations fields

9. Proxy re-wraps:     Converts JSON response → SSE chunks:
                        data: {"choices":[{"delta":{"role":"assistant"}}]}
                        data: {"choices":[{"delta":{"content":"..."}}]}
                        data: {"choices":[{"delta":{"tool_calls":[...]}}]}
                        data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}
                        data: {"choices":[],"usage":{...}}
                        data: [DONE]

10. OpenClaw receives: Proper SSE stream with structured tool calls
```

## Key Functions

### `convert_to_sse_stream(resp_json)`
Converts a complete non-streaming JSON response into a generator that yields SSE-formatted chunks. Produces:
- Role chunk (assistant)
- Content chunk (if any text content)
- Tool call chunks (one per tool call, with index)
- Finish chunk (with finish_reason)
- Usage chunk (token counts)
- `[DONE]` sentinel

### `forward_fix_and_rewrap_sse(url, headers, body)`
The main handler for streaming requests with tools:
1. Sends non-streaming request to vLLM
2. Extracts tool calls from content
3. Cleans response for OpenClaw compatibility
4. Returns SSE stream via `convert_to_sse_stream()`

### `extract_tools_from_content(response_json)`
Post-processes vLLM responses to find tool calls hidden in text content:
1. Tries `<tools>JSON</tools>` regex extraction
2. Tries parsing entire content as single JSON object
3. Tries parsing each line of content as separate JSON objects
4. For each valid tool call JSON (has `name` field), creates proper `tool_calls` entry
5. Cleans remaining non-JSON text back into content

### `clean_response_for_openclaw(resp_json)`
Strips fields that OpenClaw doesn't expect:
- Top-level: `prompt_logprobs`, `prompt_token_ids`, `kv_transfer_params`, `service_tier`, `system_fingerprint`
- Choice-level: `stop_reason`, `token_ids`
- Message-level: `reasoning`, `reasoning_content`, `refusal`, `annotations`, `audio`, `function_call`
- Empty `tool_calls` arrays (replaced with absence of field)
- Usage: `prompt_tokens_details`

### `check_tool_loop(body)`
Safety net: counts `tool` role messages in the conversation. If count >= 20, returns a synthetic stop message instead of forwarding to vLLM. Prevents runaway token consumption from repetition loops.

## Routing Logic

```python
if has_tools and client_wanted_streaming:
    → forward_fix_and_rewrap_sse()   # Non-stream → extract → SSE re-wrap
elif streaming:
    → stream_response()              # Pure passthrough streaming
else:
    → forward_with_body_and_fix()    # Non-streaming with tool extraction
```

## How the SSE Patch Was Applied

The original proxy (v4.0) already had tool extraction but lacked SSE re-wrapping. The patch script (`proxy-patch.py`) modified the proxy in-place:

1. Added `convert_to_sse_stream()` function
2. Added `was_streaming` tracking before forcing `stream: false`
3. Added `forward_fix_and_rewrap_sse()` function
4. Updated routing logic to use the new SSE path when client wanted streaming

The patch was applied via:
```bash
scp proxy-patch.py michael@192.168.0.122:/tmp/
ssh michael@192.168.0.122 "python3 /tmp/proxy-patch.py"
```
