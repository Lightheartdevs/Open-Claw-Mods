#!/bin/bash
# Start the vLLM tool call proxy
# Run on the same server as vLLM (192.168.0.122)
#
# Prerequisites: pip3 install flask requests

PROXY_SCRIPT="/home/michael/vllm-tool-proxy.py"
PROXY_PORT=8003
VLLM_URL="http://192.168.0.122:8000"
LOG_FILE="/tmp/vllm-proxy.log"

# Kill existing proxy if running
pkill -f "vllm-tool-proxy.py" 2>/dev/null
sleep 1

# Start proxy
nohup python3 "$PROXY_SCRIPT" \
  --port "$PROXY_PORT" \
  --vllm-url "$VLLM_URL" \
  > "$LOG_FILE" 2>&1 &

echo "Proxy starting (PID: $!)..."
sleep 2

# Verify
if curl -s "http://localhost:${PROXY_PORT}/health" | grep -q '"status":"ok"'; then
  echo "Proxy is healthy!"
  curl -s "http://localhost:${PROXY_PORT}/health" | python3 -m json.tool
else
  echo "ERROR: Proxy failed to start. Check $LOG_FILE"
  tail -20 "$LOG_FILE"
fi
