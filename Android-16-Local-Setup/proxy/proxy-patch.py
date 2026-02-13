import json
import re

with open("/home/michael/vllm-tool-proxy.py", "r") as f:
    content = f.read()

# Add a function to convert non-streaming response to SSE format
new_func = '''
def convert_to_sse_stream(resp_json):
    """Convert a non-streaming chat completion response to SSE format
    so the OpenAI SDK can parse it when it expects streaming."""
    import time

    def generate():
        model = resp_json.get("model", "unknown")
        resp_id = resp_json.get("id", "chatcmpl-converted")
        created = resp_json.get("created", int(time.time()))

        for choice in resp_json.get("choices", []):
            msg = choice.get("message", {})
            content_text = msg.get("content")
            tool_calls = msg.get("tool_calls")
            finish_reason = choice.get("finish_reason", "stop")

            # First chunk: role
            first_chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "logprobs": None,
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(first_chunk)}\\n\\n"

            # Content chunks
            if content_text:
                content_chunk = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": content_text},
                        "logprobs": None,
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(content_chunk)}\\n\\n"

            # Tool call chunks
            if tool_calls:
                for i, tc in enumerate(tool_calls):
                    tc_chunk = {
                        "id": resp_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "tool_calls": [{
                                    "index": i,
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": tc["function"]["name"],
                                        "arguments": tc["function"]["arguments"]
                                    }
                                }]
                            },
                            "logprobs": None,
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(tc_chunk)}\\n\\n"

            # Finish chunk
            finish_chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "logprobs": None,
                    "finish_reason": finish_reason
                }]
            }
            yield f"data: {json.dumps(finish_chunk)}\\n\\n"

        # Usage chunk
        usage = resp_json.get("usage")
        if usage:
            usage_chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [],
                "usage": usage
            }
            yield f"data: {json.dumps(usage_chunk)}\\n\\n"

        yield "data: [DONE]\\n\\n"

    return generate()

'''

# Insert the new function before the proxy route
content = content.replace(
    "@app.route('/v1/<path:path>',",
    new_func + "\n@app.route('/v1/<path:path>',",
    1
)

# Now update the proxy function to track if original request was streaming
# and re-wrap the response
old_forward = """    # Force non-streaming when tools are present so post-processor can extract tool calls from text
    if body and has_tools(body) and body.get("stream", False):
        logger.info("Forcing non-streaming for tool call post-processing")
        body["stream"] = False
        body.pop("stream_options", None)
    is_streaming = body.get("stream", False) if body else False"""

new_forward = """    # Track if client originally requested streaming
    was_streaming = body.get("stream", False) if body else False
    # Force non-streaming when tools are present so post-processor can extract tool calls from text
    if body and has_tools(body) and was_streaming:
        logger.info("Forcing non-streaming for tool call post-processing (will re-wrap as SSE)")
        body["stream"] = False
        body.pop("stream_options", None)
    is_streaming = body.get("stream", False) if body else False"""

content = content.replace(old_forward, new_forward)

# Update the non-streaming path to re-wrap as SSE when originally streaming
old_else = """    if is_streaming:
        return stream_response(url, headers, body)
    else:
        return forward_with_body_and_fix(url, headers, body)"""

new_else = """    if is_streaming:
        return stream_response(url, headers, body)
    elif was_streaming and body and has_tools(body):
        # Client wanted streaming but we forced non-streaming for tool extraction
        # Get the response, fix it, then re-wrap as SSE
        return forward_fix_and_rewrap_sse(url, headers, body)
    else:
        return forward_with_body_and_fix(url, headers, body)"""

content = content.replace(old_else, new_else)

# Add the new forward_fix_and_rewrap_sse function before forward_request
new_rewrap = '''
def forward_fix_and_rewrap_sse(url, headers, body):
    """Forward non-streaming, fix tool calls, then re-wrap as SSE for streaming clients."""
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=300)
        try:
            resp_json = resp.json()
            if body and has_tools(body):
                extract_tools_from_content(resp_json)
            clean_response_for_openclaw(resp_json)
            logger.info("SSE-REWRAP: " + json.dumps({"c": str((resp_json.get("choices") or [{}])[0].get("message",{}).get("content"))[:200], "tc": len((resp_json.get("choices") or [{}])[0].get("message",{}).get("tool_calls",[])), "f": (resp_json.get("choices") or [{}])[0].get("finish_reason"), "s": resp.status_code}))
            return Response(
                convert_to_sse_stream(resp_json),
                status=200,
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}
            )
        except Exception as e:
            logger.error(f'SSE rewrap parse error: {e}')
            return Response(resp.content, status=resp.status_code)
    except Exception as e:
        logger.error(f'SSE rewrap forward error: {e}')
        return Response(json.dumps({'error': str(e)}), status=502, mimetype='application/json')

'''

content = content.replace(
    "def forward_request(url):",
    new_rewrap + "def forward_request(url):",
    1
)

with open("/home/michael/vllm-tool-proxy.py", "w") as f:
    f.write(content)

print("Proxy patched successfully!")
