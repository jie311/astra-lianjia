#!/bin/bash

# ============================================================
# Reward Pipeline Script
# Evaluate trajectory quality with multiple reward dimensions
# ============================================================

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SFT_ROOT="$SCRIPT_DIR/.."
PIPELINE_DIR="$SFT_ROOT/src/4_reward"

# ==================== Configuration ====================
# Input file (JSON format with tools and messages)
INPUT_FILE="${INPUT_FILE:-$SFT_ROOT/data/test/workdir/reward/input.json}"
OUTPUT_DIR="${OUTPUT_DIR:-$SFT_ROOT/data/test/workdir/reward}"

# Model parameters
MODEL_NAME="${MODEL_NAME:-model_name}"
MAX_CONCURRENT="${MAX_CONCURRENT:-5}"

echo "============================================================"
echo "Reward Pipeline"
echo "============================================================"
echo "Input file: $INPUT_FILE"
echo "Output dir: $OUTPUT_DIR"
echo "Model: $MODEL_NAME"
echo "Max concurrent: $MAX_CONCURRENT"
echo "============================================================"
echo ""

# ==================== Create output directory ====================
mkdir -p "$OUTPUT_DIR"

# ==================== Run reward evaluation ====================
echo "============================================================"
echo "[Running] Evaluating trajectory with reward functions"
echo "============================================================"

cd "$PIPELINE_DIR"
python3 reward.py \
    --inname "$INPUT_FILE" \
    --model_name "$MODEL_NAME" \
    --max_concurrent "$MAX_CONCURRENT"

echo ""

# ==================== Done ====================
echo "============================================================"
echo "Pipeline completed!"
echo "============================================================"
echo "Output saved to: $OUTPUT_DIR"
echo "============================================================"

