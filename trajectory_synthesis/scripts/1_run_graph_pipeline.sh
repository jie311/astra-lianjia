#!/bin/bash

# ============================================================
# Graph Pipeline Complete Workflow Script
# Includes: 1.Graph Building -> 2.Random Walk Sub-chain Extraction -> 3.Tool Chain Verification
# ============================================================

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SFT_ROOT="$SCRIPT_DIR/.."
PIPELINE_DIR="$SFT_ROOT/src/1_graph_build"

# Set PYTHONPATH to include src directory for utils module
export PYTHONPATH="$SFT_ROOT/src:$PYTHONPATH"

# ==================== Configuration Parameters ====================
# Input/Output files
INPUT_FILE="${INPUT_FILE:-$SFT_ROOT/data/test/mcp_servers.jsonl}"    ## Input file path for mcp_servers
WORKDIR="${WORKDIR:-$SFT_ROOT/data/test/workdir/graph_build}"       # Working directory for this task

# Model parameters
MODEL_NAME="${MODEL_NAME:-GLM-4.7-FP8}"     # Model for graph building
MAX_CONCURRENT="${MAX_CONCURRENT:-32}"       # Maximum concurrent async requests
NUM_PROCESSES="${NUM_PROCESSES:-8}"          # Number of processes

# Sub-chain parameters
MIN_LENGTH="${MIN_LENGTH:-2}"           # Minimum length of sub-chains from random walk
MAX_LENGTH="${MAX_LENGTH:-5}"           # Maximum length of sub-chains from random walk

# Verification parameters
VERIFY_PROCESSES="${VERIFY_PROCESSES:-128}"   # Concurrent processes for verification
OPERATORS="${OPERATORS:-vote_verify_chain1,vote_verify_chain1}"   # Operators for verification, comma-separated, configure in verify/operator_config.py

# ==================== Create Working Directory ====================
mkdir -p "$WORKDIR"

# Intermediate file paths
RAW_OUTPUT="$WORKDIR/1_raw_output.jsonl"        # Raw output from graph building
PARSED_OUTPUT="$WORKDIR/2_parsed_output.jsonl"   # Parsed output from graph building
SUB_CHAINS_OUTPUT="$WORKDIR/3_sub_chains.jsonl"   # Sub-chains from random walk
VERIFIED_OUTPUT="$WORKDIR/4_verified_output.jsonl"   # Verified output

echo "============================================================"
echo "Graph Pipeline Complete Workflow"
echo "============================================================"
echo "Input file: $INPUT_FILE"
echo "Working directory: $WORKDIR"
echo "Model: $MODEL_NAME"
echo "============================================================"
echo ""

# ==================== Step 1: Graph Building ====================
echo "============================================================"
echo "[Step 1/3] Graph Building: Call LLM to detect tool dependencies"
echo "============================================================"
if [ -f "$PARSED_OUTPUT" ]; then
    echo "Parsed output exists, skipping graph building step"
else
    cd "$PIPELINE_DIR/build"
    python3 1_gen_and_parse.py \
        --input_file "$INPUT_FILE" \
        --raw_output_file "$RAW_OUTPUT" \
        --parsed_output_file "$PARSED_OUTPUT" \
        --model_name "$MODEL_NAME" \
        --max_concurrent "$MAX_CONCURRENT" \
        --num_processes "$NUM_PROCESSES"
fi
echo ""

# ==================== Step 2: Random Walk Sub-chain Extraction ====================
echo "============================================================"
echo "[Step 2/3] Random Walk: Extract sub-chains from graph"
echo "============================================================"
if [ -f "$SUB_CHAINS_OUTPUT" ]; then
    echo "Sub-chains output exists, skipping random walk step"
else
    cd "$PIPELINE_DIR/build"
    python3 2_get_sub_chains.py \
        --input_file "$PARSED_OUTPUT" \
        --output_file "$SUB_CHAINS_OUTPUT" \
        --min_length "$MIN_LENGTH" \
        --max_length "$MAX_LENGTH"
fi
echo ""

# ==================== Step 3: Tool Chain Verification ====================
echo "============================================================"
echo "[Step 3/3] Tool Chain Verification: Validate sub-chains using operators"
echo "============================================================"
if [ -f "$VERIFIED_OUTPUT" ]; then
    echo "Verified output exists, skipping verification step"
else
    cd "$PIPELINE_DIR/verify"
    # Convert comma-separated operator names to space-separated
    OPERATOR_ARRAY=(${OPERATORS//,/ })
    python3 run_operators.py "$SUB_CHAINS_OUTPUT" "$VERIFIED_OUTPUT" \
        -p "$VERIFY_PROCESSES" \
        -o "${OPERATOR_ARRAY[@]}"
fi
echo ""

# ==================== Complete ====================
echo "============================================================"
echo "Pipeline execution complete!"
echo "============================================================"
echo "Output files:"
echo "  - Raw output: $RAW_OUTPUT"
echo "  - Parsed output: $PARSED_OUTPUT"
echo "  - Sub-chains: $SUB_CHAINS_OUTPUT"
echo "  - Verified output: $VERIFIED_OUTPUT"
echo "============================================================"

