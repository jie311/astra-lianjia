<h4 align="center">
    <p>
        <a href="README_zh.md">简体中文</a> |
        <b>English</b>
    </p>
</h4>

# Environment Synthesis

<p align="center">
    <img src="../assets/env.png" alt="Environment Synthesis Flowchart" style="max-width: 100%;">
</p>

This module automatically generates tool environments from question-answer pairs (QA pairs), including tool documentation generation, tool code implementation, call statement generation, and other complete workflows. Through an LLM-driven multi-step synthesis process, natural language questions are transformed into executable tool environments, with all intermediate processes fully verifiable through rules, enabling model training in the RLVR format.

## 📁 Project Structure

```
env_synthesis/
├── scripts/                             # Execution scripts
│   ├── step_01_gen_QA_for_pipeline.sh   # Step 1: Generate QA data prompts and run inference
│   ├── step_02_check_tool_necessity.sh  # Step 2: Check tool necessity
│   ├── step_03_verify.sh                # Step 3: Verification (dependencies, atomicity, etc.)
│   ├── step_04_env_synthesis.sh         # Step 4: Environment synthesis
│   └── step_05_merge_tools.sh           # Step 5: Merge tools
│
├── src/                                 # Source code
│   ├── step_01_gen_QA_for_pipeline.py   # QA data generation and inference
│   ├── step_02_check_tool_necessity.py  # Tool necessity check
│   ├── step_03_verify.py                # Multi-dimensional verification (dependencies, atomicity, serialization, completeness)
│   ├── step_04_env_synthesis.py         # Core environment synthesis logic
│   ├── step_05_merge_tools.py           # Tool merging
│   └── utils/                           # Utility functions
│       ├── api_client.py                # API client wrapper
│       ├── api_config.py                # API configuration
│       ├── domain_config.py             # Domain configuration
│       ├── get_prompt_batch.py          # Batch prompt generation
│       ├── logger.py                    # Logging utilities
│       ├── multiprocess_inference.py    # Multi-process inference
│       ├── prompt.py                    # Prompt templates
│       └── semaphore_config.py          # Semaphore configuration (concurrency control)
│
└── data/                                # Data files
    ├── knowledge/                       # Knowledge base data
    │   ├── en/                          # English knowledge base
    │   │   ├── context.jsonl
    │   │   ├── domains.jsonl
    │   │   └── questions.jsonl
    │   └── zh/                          # Chinese knowledge base
    │       └── domains.jsonl
    └── taxonomy/                        # Taxonomy data
        └── finance.json
```

---

## 🚀 Script Instructions and Execution Methods

This module adopts a five-step pipeline that decomposes questions into sub-questions and generates corresponding tool environments for each sub-question:

```
Input: domain/num_sample and other parameter configurations
       ↓
[Step 1] Generate QA data → Call LLM to generate question decomposition traces (decomposition_trace)
       ↓
[Step 2] Check tool necessity → Determine if each sub-question requires tools
       ↓
[Step 3] Verification → Verify dependencies, atomicity, forced serialization, sub-question completeness
       ↓
[Step 4] Environment synthesis → Generate tool environment for each sub-question that requires tools
       ↓
[Step 5] Merge tools → Cluster sub-questions with similar intents, merge their tool code (modify mock data), update env_result after verification
       ↓
Output: Complete tool environment (tool documentation, code, call statements, etc.)
```


### Step 1: Generate QA Data Prompts (`step_01_gen_QA_for_pipeline.py`)

**Function**: Generates different types of question decomposition prompts and calls LLM to generate question decomposition traces.

**Supported Modes**:
- `zh_kb`: Chinese + Knowledge base
- `zh_base`: Chinese base mode
- `en_base`: English base mode
- `en_ctx`: English context mode (supports hop range)
- `en_q`: English question-based mode
- `tax`: Taxonomy mode
- `all`: Run all modes

**Execution Method**:
```bash
bash scripts/step_01_gen_QA_for_pipeline.sh
# Or run the Python script directly
python src/step_01_gen_QA_for_pipeline.py \
    --mode zh_kb \
    --model_name <Your_model_name> \
    --output_dir ./output \
    --num_workers 4 \
    --batch_size 4 \
    --min_hops 3 \
    --max_hops 5 \
    --num_repeats 1 \
    --domain general
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `--mode` | Generation mode (required) |
| `--model_name` | Model name (required) |
| `--output_dir` | Output directory (required) |
| `--num_workers` | Number of concurrent worker processes (default: 4) |
| `--batch_size` | Batch size (default: 4) |
| `--min_hops` | Minimum number of hops (default: 3) |
| `--max_hops` | Maximum number of hops (default: 5) |
| `--num_repeats` | Number of repetitions (default: 1) |
| `--domain` | Domain (default: general)|

**Output**:
- `{mode}_prompts.jsonl`: Generated prompt file
- `{mode}_results.jsonl`: LLM inference results (contains `decomposition_trace`)

---

### Step 2: Check Tool Necessity (`step_02_check_tool_necessity.py`)

**Function**: Checks whether each sub-question in the decomposition trace requires tools to solve. For non-leaf nodes (nodes that are depended upon by other nodes), `tool_necessity=True` is mandatory.

**Execution Method**:
```bash
bash scripts/step_02_check_tool_necessity.sh
# Or run the Python script directly
python src/step_02_check_tool_necessity.py \
    --input_file ./output/zh_kb_results.jsonl \
    --model_name <Your_model_name> \
    --output_file ./output/zh_kb_necessity.json
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `--input_file` | Input file (output from Step 1, JSONL format) |
| `--model_name` | Model name (required) |
| `--output_file` | Output file (JSON format) |

**Output Fields**:
- Each `decomposition_trace` item adds:
  - `tool_necessity`: Boolean value indicating whether tools are needed
  - `reason`: Reason explanation
- `tool_necessity_legitimacy`: Overall legitimacy flag (must be True for non-leaf nodes)

---

### Step 3: Verification (`step_03_verify.py`)

**Function**: Performs multi-dimensional verification on question decomposition traces to ensure quality.

**Verification Dimensions**:
1. **Dependency Verification** (`verify_dependency`): Verifies whether the dependency relationships declared by sub-questions are correct
2. **Atomicity Verification** (`verify_atomicity`): Verifies whether sub-questions are sufficiently atomic
3. **Forced Serialization Verification** (`verify_forced_serialization`): Verifies whether dependency relationships must be executed serially, avoiding forced serialization of content that could be executed in parallel just to fit hop_num
4. **Sub-question Completeness Verification** (`verify_subqa_completeness`): Verifies whether all sub-questions completely cover the main question

**Execution Method**:
```bash
bash scripts/step_03_verify.sh
# Or run the Python script directly
python src/step_03_verify.py \
    --input_file ./output/zh_kb_necessity.json \
    --model_name <Your_model_name> \
    --output_file ./output/zh_kb_verified.json \
    --max_concurrent 10
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `--input_file` | Input file (output from Step 2) |
| `--model_name` | Model name (required) |
| `--output_file` | Output file |
| `--max_concurrent` | Maximum number of concurrent requests (default: 10) |

**Output Fields**:
- `verify_result`: Contains verification results for each dimension
  - `dependency_score`: Dependency score
  - `atomicity_score`: Atomicity score
  - `forced_serialization_score`: Forced serialization score
  - `subqa_completeness_score`: Sub-question completeness score
  - `overall_score`: Overall score

---

### Step 4: Environment Synthesis (`step_04_env_synthesis.py`)

**Function**: Generates complete tool environments for each sub-question that requires tools, including tool documentation, tool code, call statements, etc.

**Data Filtering**:
Before starting environment synthesis, input data is filtered:
1. **Tool Necessity Legitimacy Check**: If `tool_necessity_legitimacy` is `False`, skip this data
2. **Verification Score Threshold Filtering**: If `verify_result['score']` is less than `threshold`, skip this data
   - **Threshold Determination Method**: `threshold` should be determined based on the distribution of verification results, typically using the **90th percentile** (P90)
   - **Meaning**: Only perform environment synthesis on high-quality data with verification scores in the top 10%
   - **Calculation Example**:
     ```python
     import numpy as np
     import json
     
     # Read verification results from Step 3
     verify_scores = []
     with open("verify_output.jsonl", "r") as f:
         for line in f:
             data = json.loads(line)
             score = data['verify_result']['score']
             verify_scores.append(score)
     
     # Calculate 90th percentile as threshold
     threshold = np.percentile(verify_scores, 90)
     print(f"Recommended threshold (90th percentile): {threshold}")
     ```

**Synthesis Process**:
For each data item that passes filtering, the following 4 steps are executed sequentially (each step has retry mechanism):

1. **Tool Document Generation** (`_tool_document_generation`): 
   - Generate tool document description based on sub-question
   - Maximum retry attempts: `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - Output: `tool_document` and `analysis`

2. **Tool Document Complexity Scaling** (`_tool_document_complexity_scaling`): 
   - Expand and optimize the complexity of tool documents
   - Maximum retry attempts: `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - Output: `refined_version` and `analysis`

3. **Call Statement Generation** (`_call_statement_generation`): 
   - Generate tool call statements based on question and tool document
   - Maximum retry attempts: `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - Output: `call_statement` and `analysis`

4. **Tool Deployment** (`_tool_deployment`): 
   - Generate tool code (Python function) and verify in sandbox
   - Verification logic: Execute code and check if `tool_call_ans` contains expected answer
   - Maximum retry attempts: `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - Outer retry: If the entire process fails, outer retry will be performed (`ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES` times)
   - Output: `function` (code) and `analysis`

**Execution Method**:
```bash
bash scripts/step_04_env_synthesis.sh
# Or run the Python script directly
python src/step_04_env_synthesis.py \
    --input_file ./output/zh_kb_verified.jsonl \
    --model_name <Your_model_name> \
    --output_file ./output/zh_kb_synthesized.jsonl \
    --threshold 0.85
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `--input_file` | Input file (output from Step 3, JSONL format) |
| `--model_name` | Model name (required) |
| `--output_file` | Output file (JSONL format) |
| `--threshold` | Verification score threshold (required), recommended to use 90th percentile |

**Output Fields**:
- `env_result`: Dictionary, key is sub-question's `_uuid`, value contains:
  - `question`: Sub-question
  - `answer`: Sub-answer
  - `env_synthesis_result`: Environment synthesis result
    - `data`: 
      - `tool_document`: Tool document (JSON format)
      - `tool_call_statement`: Tool call statement
      - `code`: Tool code (Python function)
      - `tool_call_ans`: Tool call result (sandbox execution output)
    - `extra_info`: Detailed information for each step
      - `tool_document_generation_result`: Result from step 1
      - `tool_document_complexity_scaling_result`: Result from step 2
      - `tool_call_statement_result`: Result from step 3
      - `tool_deployment_result`: Result from step 4

**Notes**:
- Environment synthesis is only performed on sub-questions with `tool_necessity=True`
- For sub-questions with `tool_necessity=False`, the corresponding `env_result[_uuid]` is `None`
- If environment synthesis for a sub-question fails (all retries fail), the corresponding `env_result[_uuid]` is `None`
- Logs are recorded when each step fails for troubleshooting

---

### Step 5: Merge Tools (`step_05_merge_tools.py`)

**Function**: Merges tool code corresponding to sub-questions with similar intents, reducing the number of tools and improving code reusability.

**Merging Process**:
1. **Filtering**: Only retain sub-questions with `tool_necessity=True`
2. **Intent Aggregation** (`intent_aggregation`): Use LLM to cluster sub-questions with similar intents, generating intent clustering results
3. **Code Merging** (`merge_single_cluster_code`): For each cluster containing multiple sub-questions:
   - Extract QA pairs and tool code for all sub-questions in the cluster
   - Use the code from the first sub-question as the base code
   - Use LLM to modify the mock data section in the code, ensuring the merged code can handle all QA pairs
   - Generate new tool call statements for each QA pair
   - Verify in code sandbox whether the merged code can pass all test cases (answers must appear in output)
   - If verification fails, retry up to 20 times
4. **Post-processing** (`post_process_merge_tools`): Update merged code, tool documents, and call statements back to `env_result`, replacing original independent tool code

**Execution Method**:
```bash
bash scripts/step_05_merge_tools.sh
# Or run the Python script directly
python src/step_05_merge_tools.py \
    --input_file ./output/zh_kb_synthesized.json \
    --model_name <Your_model_name> \
    --output_file ./output/zh_kb_merged.json
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `--input_file` | Input file (output from Step 4) |
| `--model_name` | Model name (required) |
| `--output_file` | Output file |

**Output Fields**:
- `clusters`: Intent clustering results, each cluster contains:
  - `_uuids`: List of sub-question UUIDs in the cluster
  - `intent_summary`: Intent summary
  - `reason`: Clustering reason
- `aggregated_env`: Merged environment list, each element contains:
  - `status`: Merge status ("success"/"partial_success"/"failed"/"no_data"/"error")
  - `merged_code`: Merged tool code
  - `tool_call_statements`: List of tool call statements for each QA pair
  - `verification`: Verification results (test case pass status, retry count, etc.)
- `env_result`: Updated environment results, merged sub-questions use merged code

**Notes**:
- Clustering and merging are only performed on sub-questions with `tool_necessity=True`
- Code merging is only performed on clusters containing multiple sub-questions (`len(_uuids) > 1`)
- If merged code cannot pass all test cases, the entire data will be marked as failed (returns `None`)
- The core of merging is modifying mock data so that one function can handle multiple different QA pairs
- Merged code needs to be verified in code sandbox to ensure answers for all test cases appear in output

---

## 📊 Data Format Specifications

### Input Data Format (Step 1)

Step 1 accepts knowledge base files as input, in JSONL format (one JSON object per line).

**Knowledge Base File Example** (`data/knowledge/zh/domains.jsonl`):
```json
{
  "domain": "Weather",
  "description": "Weather related knowledge"
}
```

**Question File Example** (`data/knowledge/en/questions.jsonl`):
```json
{
  "question": "How to calculate compound interest?",
  "answer": "Compound interest is calculated on the principal and the accumulated interest."
}
```

### Intermediate Data Formats

**Step 1 Output** (`decomposition_trace`):
```json
{
  "uuid": "Main question UUID",
  "main_question": "Main question",
  "decomposition_trace": [
    {
      "_uuid": "Sub-question UUID",
      "sub_question": "Sub-question",
      "sub_answer": "Sub-question answer",
      "dependency": [1, 2]  // Indices of other sub-questions this depends on
    }
  ]
}
```

**Step 2 Output** (Add tool necessity):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [
    {
      "_uuid": "...",
      "sub_question": "...",
      "sub_answer": "...",
      "dependency": [...],
      "tool_necessity": true,
      "reason": "Tool is necessary to get real-time data"
    }
  ],
  "tool_necessity_legitimacy": true
}
```

**Step 3 Output** (Add verification results):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [...],
  "verify_result": {
    "dependency_score": 0.95,
    "atomicity_score": 0.88,
    "forced_serialization_score": 0.92,
    "subqa_completeness_score": 0.90,
    "overall_score": 0.91
  }
}
```

**Step 4 Output** (Add environment synthesis results):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [...],
  "env_result": {
    "uuid_1": {
      "question": "Sub-question",
      "answer": "Sub-question answer",
      "env_synthesis_result": {
        "data": {
          "tool_document": "Tool document description",
          "tool_call_statement": "function_name(arg1, arg2)",
          "code": "def function_name(arg1, arg2):\n    ...",
          "tool_call_ans": "Call result"
        },
        "extra_info": {
          "tool_document_generation_result": {...},
          "tool_document_complexity_scaling_result": {...},
          "tool_call_statement_result": {...},
          "tool_deployment_result": {...}
        }
      }
    },
    "uuid_2": null  // Case where tool_necessity=False
  }
}
```

**Step 5 Output** (Add merging results):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [...],
  "env_result": {
    // Merged sub-questions use merged code
    "uuid_1": {
      "env_synthesis_result": {
        "data": {
          "code": "Merged code",
          "tool_document": {...},
          "tool_call_statement": "Updated call statement"
        }
      },
      "merge_flag": true  // Flag indicating merged
    }
  },
  "clusters": [
    {
      "_uuids": ["uuid_1", "uuid_2"],
      "intent_summary": "Intent summary",
      "reason": "Clustering reason"
    }
  ],
  "aggregated_env": [
    {
      "intent_summary": "Intent summary",
      "_uuids": ["uuid_1", "uuid_2"],
      "status": "success",
      "merged_code": "Merged tool code",
      "tool_call_statements": [
        {
          "_uuid": "uuid_1",
          "tool_call_statement": "function_name(args1)",
          "question": "Sub-question 1",
          "answer": "Sub-question answer 1"
        },
        {
          "_uuid": "uuid_2",
          "tool_call_statement": "function_name(args2)",
          "question": "Sub-question 2",
          "answer": "Sub-question answer 2"
        }
      ],
      "verification": {
        "all_tests_passed": true,
        "test_results": [...],
        "retry_count": 0
      }
    }
  ]
}
```

---

## 🔧 Configuration

### API Configuration

API configuration is located in `src/utils/api_config.py`, including:
- `API_CONFIGS`: Model API configuration dictionary
- `SANDBOX_URL`: Code sandbox URL (for tool deployment verification)
- `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`: Environment synthesis inner retry count
- `ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES`: Environment synthesis outer retry count

### Domain Configuration

Domain configuration is located in `src/utils/domain_config.py`, supporting:
- `weather`: Weather domain

New domain taxonomy files can be added in the `data/taxonomy/` directory.
