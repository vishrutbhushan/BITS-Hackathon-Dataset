#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime="$project_dir/.venv/bin/python"
server="$project_dir/local_mlx_server.py"
model_dir="$project_dir/models/Qwen3.5-9B-4bit"
port="${AGENTIC_LOCAL_PORT:-8080}"

if [ ! -x "$runtime" ] || [ ! -f "$server" ]; then
    echo "Missing local MLX server runtime" >&2
    exit 1
fi
if [ ! -f "$model_dir/config.json" ]; then
    echo "Missing Qwen model: $model_dir" >&2
    exit 1
fi

echo "Starting MLX-VLM on http://127.0.0.1:$port"
echo "The model is loaded lazily on the first request: $model_dir"
exec "$runtime" "$server" --host 127.0.0.1 --port "$port"
