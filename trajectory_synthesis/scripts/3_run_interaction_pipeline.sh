#!/bin/bash

# ============================================================
# Interaction Pipeline Complete Workflow Script
# Generate trajectory through LLM and environment interaction
# ============================================================

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SFT_ROOT="$SCRIPT_DIR/.."
PIPELINE_DIR="$SFT_ROOT/src/3_interaction"

# ==================== Configuration Parameters ====================
# Input/Output files
INPUT_FILE="${INPUT_FILE:-$SFT_ROOT/data/test/workdir/interaction/input.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-$SFT_ROOT/data/test/workdir/interaction/trajectory_output.jsonl}"

# Model parameters
MODEL_NAME="${MODEL_NAME:-GLM-4.7-FP8-think}"
MAX_WORKERS="${MAX_WORKERS:-10}"
TIMEOUT="${TIMEOUT:-240}"

# Smithery parameters (optional)
SMITHERY_API_KEY="${SMITHERY_API_KEY:-your_SMITHERY_API_KEY}"
SMITHERY_PROFILE="${SMITHERY_PROFILE:-your_SMITHERY_PROFILE}"

# System prompt
DEFAULT_SYSTEM_PROMPT='Planning and thinking about the task before function calling in every single turn. The language must be consistent with user'"'"'s language.'
SYSTEM_PROMPT="${SYSTEM_PROMPT:-$DEFAULT_SYSTEM_PROMPT}"

echo "============================================================"
echo "Interaction Pipeline Workflow"
echo "============================================================"
echo "Input file: $INPUT_FILE"
echo "Output file: $OUTPUT_FILE"
echo "Model: $MODEL_NAME"
echo "Workers: $MAX_WORKERS"
echo "Timeout: $TIMEOUT"
echo "============================================================"
echo ""

# ==================== Execute Interaction ====================
echo "============================================================"
echo "[Executing] LLM environment interaction to generate trajectory"
echo "============================================================"

cd "$PIPELINE_DIR"
python3 interact_qwen_agent.py \
    --input_file "$INPUT_FILE" \
    --output_file "$OUTPUT_FILE" \
    --model_name "$MODEL_NAME" \
    --smithery_api_key "$SMITHERY_API_KEY" \
    --smithery_profile "$SMITHERY_PROFILE" \
    --max_workers "$MAX_WORKERS" \
    --timeout "$TIMEOUT" \
    --system_prompt "$SYSTEM_PROMPT"

echo ""

# ==================== Complete ====================
echo "============================================================"
echo "Pipeline execution complete!"
echo "============================================================"
echo "Output file: $OUTPUT_FILE"
echo "============================================================"

