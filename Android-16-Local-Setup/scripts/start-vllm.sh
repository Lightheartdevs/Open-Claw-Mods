#!/bin/bash
# Start vLLM serving Qwen2.5-Coder-32B-Instruct-AWQ
# Run on the GPU server (192.168.0.122)

docker run -d \
  --name vllm-coder \
  --runtime nvidia \
  --gpus all \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  --ipc=host \
  --restart unless-stopped \
  vllm/vllm-openai:v0.14.0 \
  --model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ \
  --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --tensor-parallel-size 1

echo "Waiting for vLLM to start..."
until curl -s http://localhost:8000/v1/models > /dev/null 2>&1; do
  sleep 5
  echo "  Still waiting..."
done
echo "vLLM is ready!"
curl -s http://localhost:8000/v1/models | python3 -m json.tool
