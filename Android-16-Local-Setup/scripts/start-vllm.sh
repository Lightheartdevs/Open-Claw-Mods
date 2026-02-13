#!/bin/bash
# Start vLLM serving Qwen3-Coder-Next-FP8 (80B MoE)
# Run on the GPU server (192.168.0.122)
#
# Model: Qwen/Qwen3-Coder-Next-FP8
#   - 80B total params, 3B active (sparse MoE + hybrid DeltaNet)
#   - FP8 weights (~75GB), fits on single 96GB GPU
#   - 128K context window (256K native, limited for VRAM headroom)
#   - Native tool calling via qwen3_coder parser
#
# CRITICAL FLAGS:
#   --tool-call-parser qwen3_coder  (NOT hermes)
#   --compilation_config.cudagraph_mode=PIECEWISE  (prevents CUDA errors with DeltaNet)
#   Do NOT use --kv-cache-dtype fp8 (causes assertion errors with this architecture)

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

echo "Waiting for vLLM to start (model loading + CUDA graph compilation ~90s)..."
until curl -s http://localhost:8000/v1/models > /dev/null 2>&1; do
  sleep 5
  echo "  Still waiting..."
done
echo "vLLM is ready!"
curl -s http://localhost:8000/v1/models | python3 -m json.tool
