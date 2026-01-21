#!/bin/bash

# ============================================================
# Task Construction Pipeline Complete Workflow Script
# Includes: 1.Prompt Generation -> 2.Query Generation -> 3.Query Augmentation -> 4.Query Scoring
# ============================================================

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SFT_ROOT="$SCRIPT_DIR/.."
PIPELINE_DIR="$SFT_ROOT/src/2_task_construction"

# ==================== Configuration Parameters ====================
# Input/Output files
INPUT_FILE="${INPUT_FILE:-$SFT_ROOT/data/test/workdir/graph_build/4_verified_output.jsonl}"    # Input file (output from graph pipeline)
WORKDIR="${WORKDIR:-$SFT_ROOT/data/test/workdir/task_construction}"              # Working directory

# Model parameters
MODEL_NAME="${MODEL_NAME:-model_name}"     # Model name (must be configured in api_config.py)
POOL_SIZE="${POOL_SIZE:-32}"               # Concurrency pool size

# Prompt generation parameters
MAX_TOOL_USE="${MAX_TOOL_USE:-3}"           # Maximum number of tools in free scenario

# Query generation parameters
N_SAMPLE="${N_SAMPLE:-2}"                  # Number of samples per prompt

# Query augmentation parameters
AUG_MODE="${AUG_MODE:-all}"                 # Augmentation mode: diverse/complicate/add_ug/all
VARIATIONS_COUNT="${VARIATIONS_COUNT:-2}"   # Number of variations per augmentation
AUG_N_SAMPLE="${AUG_N_SAMPLE:-1}"           # Augmentation sampling count

# Persona configuration (required for add_ug mode)
PERSONA_DATASET_PATH="${PERSONA_DATASET_PATH:-persona_dataset_path}"   # Persona dataset path (Arrow format)
N_PERSONA_PER_QUERY="${N_PERSONA_PER_QUERY:-2}"    # Number of personas sampled per query

# Scoring parameters
SCORE_POOL_SIZE="${SCORE_POOL_SIZE:-32}"   # Scoring concurrency pool size

# ==================== Create Working Directory ====================
mkdir -p "$WORKDIR"

# Intermediate file paths
PROMPTS_DIR="$WORKDIR/1_prompts"
ALL_PROMPTS="$PROMPTS_DIR/all_prompts.jsonl"
QUERY_RAW="$WORKDIR/2_query_raw.jsonl"
QUERY_PARSED="$WORKDIR/2_query_parsed.jsonl"
AUGMENTED_RAW="$WORKDIR/3_augmented_raw.jsonl"
AUGMENTED_PARSED="$WORKDIR/3_augmented_parsed.jsonl"
SCORE_PREPARED="$WORKDIR/4_score_prepared.jsonl"
SCORE_RAW="$WORKDIR/4_score_raw.jsonl"
SCORE_PARSED="$WORKDIR/4_score_parsed.jsonl"

echo "============================================================"
echo "Task Construction Pipeline Complete Workflow"
echo "============================================================"
echo "Input file: $INPUT_FILE"
echo "Working directory: $WORKDIR"
echo "Model: $MODEL_NAME"
echo "Pool size: $POOL_SIZE"
echo "============================================================"
echo ""

# ==================== Step 1: Prompt Generation ====================
echo "============================================================"
echo "[Step 1/4] Prompt Generation: Generate prompts for different modes"
echo "============================================================"
if [ -f "$ALL_PROMPTS" ]; then
    echo "Prompts exist, skipping generation step"
else
    mkdir -p "$PROMPTS_DIR"
    cd "$PIPELINE_DIR/gen"
    
    # 1.1 Generate prompts with plan mode
    echo "[1.1] Generating prompts with plan mode..."
    python3 1_1_get_prompt.py \
        --have_plan \
        --mode single_server \
        --input_file "$INPUT_FILE" \
        --output_file "$PROMPTS_DIR/have_plan_query.jsonl"
    
    # 1.2 Generate prompts without plan for different num_tools
    for i in $(seq 1 $MAX_TOOL_USE); do
        echo "[1.2] Generating prompts with num_tools=${i}..."
        python3 1_1_get_prompt.py \
            --num_tools $i \
            --mode single_server \
            --input_file "$INPUT_FILE" \
            --output_file "$PROMPTS_DIR/noplan_query_tool_num_${i}.jsonl"
    done
    
    # 1.3 Merge all prompts
    echo "[1.3] Merging all prompts..."
    cat "$PROMPTS_DIR/have_plan_query.jsonl" > "$ALL_PROMPTS"
    for i in $(seq 2 $MAX_TOOL_USE); do
        cat "$PROMPTS_DIR/noplan_query_tool_num_${i}.jsonl" >> "$ALL_PROMPTS"
    done
    
    echo "Prompt generation complete, total $(wc -l < "$ALL_PROMPTS") entries"
fi
echo ""

# ==================== Step 2: Query Generation ====================
echo "============================================================"
echo "[Step 2/4] Query Generation: Call LLM to generate queries"
echo "============================================================"
if [ -f "$QUERY_PARSED" ]; then
    echo "Queries already generated, skipping generation step"
else
    cd "$PIPELINE_DIR/gen"
    python3 1_2_gen_query.py \
        --model "$MODEL_NAME" \
        --inp_file "$ALL_PROMPTS" \
        --out_file "${WORKDIR}/2_query" \
        --pool_size "$POOL_SIZE" \
        --n_sample "$N_SAMPLE"
    
    # Rename output files
    mv "${WORKDIR}/2_query_raw.jsonl" "$QUERY_RAW" 2>/dev/null || true
    mv "${WORKDIR}/2_query_parsed.jsonl" "$QUERY_PARSED" 2>/dev/null || true
    
    echo "Query generation complete, total $(wc -l < "$QUERY_PARSED") entries"
fi
echo ""

# ==================== Step 3: Query Augmentation ====================
echo "============================================================"
echo "[Step 3/4] Query Augmentation: Augment generated queries"
echo "============================================================"
if [ -f "$AUGMENTED_PARSED" ]; then
    echo "Query augmentation complete, skipping augmentation step"
else
    cd "$PIPELINE_DIR/gen"
    
    # Build base command
    CMD="python3 1_3_augment_query.py \
        --model $MODEL_NAME \
        --inp_file $QUERY_PARSED \
        --out_file ${WORKDIR}/3_augmented \
        --pool_size $POOL_SIZE \
        --n_sample $AUG_N_SAMPLE \
        --augmentation_mode $AUG_MODE \
        --variations_count $VARIATIONS_COUNT"
    
    # Add persona parameters for add_ug mode
    if [[ "$AUG_MODE" == "add_ug" || "$AUG_MODE" == "all" ]]; then
        if [[ -n "$PERSONA_DATASET_PATH" ]]; then
            echo "Enabling user profile feature, Persona dataset: $PERSONA_DATASET_PATH"
            CMD="$CMD --persona_dataset_path '$PERSONA_DATASET_PATH' --n_persona_per_query $N_PERSONA_PER_QUERY"
        else
            echo "Warning: add_ug mode requires PERSONA_DATASET_PATH, but not set, skipping add_ug augmentation"
            if [[ "$AUG_MODE" == "add_ug" ]]; then
                AUG_MODE="diverse"
                CMD="python3 1_3_augment_query.py \
                    --model $MODEL_NAME \
                    --inp_file $QUERY_PARSED \
                    --out_file ${WORKDIR}/3_augmented \
                    --pool_size $POOL_SIZE \
                    --n_sample $AUG_N_SAMPLE \
                    --augmentation_mode diverse \
                    --variations_count $VARIATIONS_COUNT"
            fi
        fi
    fi
    
    eval $CMD
    
    # Rename output files
    mv "${WORKDIR}/3_augmented_raw.jsonl" "$AUGMENTED_RAW" 2>/dev/null || true
    mv "${WORKDIR}/3_augmented_parsed.jsonl" "$AUGMENTED_PARSED" 2>/dev/null || true
    
    echo "Query augmentation complete, total $(wc -l < "$AUGMENTED_PARSED") entries"
fi
echo ""

# ==================== Step 4: Query Scoring ====================
echo "============================================================"
echo "[Step 4/4] Query Scoring: Score augmented queries for quality"
echo "============================================================"
cd "$PIPELINE_DIR/verify"

# 4.1 Prepare scoring data
if [ -f "$SCORE_PREPARED" ]; then
    echo "[4.1] Scoring preparation data exists, skipping"
else
    echo "[4.1] Preparing scoring data..."
    python3 1_1_score_template.py \
        --input_file "$AUGMENTED_PARSED" \
        --output_file "$SCORE_PREPARED"
fi

# 4.2 Generate scores
if [ -f "$SCORE_RAW" ]; then
    echo "[4.2] Scoring raw results exist, skipping"
else
    echo "[4.2] Generating scores..."
    python3 1_2_gen_score.py \
        --model "$MODEL_NAME" \
        --inp_file "$SCORE_PREPARED" \
        --out_file_raw "$SCORE_RAW" \
        --out_file_parsed "$SCORE_PARSED" \
        --pool_size "$SCORE_POOL_SIZE"
fi

# 4.3 Parse scoring results
if [ -f "$SCORE_PARSED" ]; then
    echo "[4.3] Scoring parsed results exist, skipping"
else
    echo "[4.3] Parsing scoring results..."
    python3 1_3_parse_score.py \
        --inp_file "$SCORE_RAW" \
        --out_file "$SCORE_PARSED"
fi

echo "Query scoring complete, total $(wc -l < "$SCORE_PARSED") entries"
echo ""

# ==================== Complete ====================
echo "============================================================"
echo "Pipeline execution complete!"
echo "============================================================"
echo "Output files:"
echo "  - Prompts directory: $PROMPTS_DIR"
echo "  - Query generation (raw): $QUERY_RAW"
echo "  - Query generation (parsed): $QUERY_PARSED"
echo "  - Query augmentation (raw): $AUGMENTED_RAW"
echo "  - Query augmentation (parsed): $AUGMENTED_PARSED"
echo "  - Score preparation: $SCORE_PREPARED"
echo "  - Score results (raw): $SCORE_RAW"
echo "  - Score results (parsed): $SCORE_PARSED"
echo "============================================================"

