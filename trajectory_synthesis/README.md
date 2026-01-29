<h4 align="center">
    <p>
        <a href="README_zh.md">简体中文</a> |
        <b>English</b>
    </p>
</h4>

# SFT Data Synthesis and Reward Scoring System

<p align="center">
    <img src="../assets/sft-pipeline.png" alt=" SFT 数据合成流程图" style="max-width: 100%;">
</p>

This codebase providing a complete pipeline from tool graph construction, task generation, trajectory collection to quality assessment.

## 📁 Project Structure

```
trajectory_synthesis/
├── scripts/                                # Execution scripts
│   ├── 1_run_graph_pipeline.sh             # Graph construction pipeline: Build tool dependency graph → Random walk to extract sub-chains → Chain verification
│   ├── 2_run_task_construction_pipeline.sh # Task construction pipeline: Prompt generation → Query generation → Query augmentation → Quality scoring
│   ├── 3_run_interaction_pipeline.sh       # Interaction pipeline: LLM interacts with tool environment to generate execution trajectories
│   └── 4_run_reward.sh                     # Reward pipeline: Multi-dimensional quality assessment and scoring of trajectories
│
├── src/                                    # Source code
│   ├── 1_graph_build/                      # Tool graph construction and verification module
│   │   ├── build/                          # Graph construction: LLM detects tool dependencies, random walk to extract sub-chains
│   │   └── verify/                         # Chain verification: Voting verification, back-translation verification and other operators
│   ├── 2_task_construction/                # Task (Query) generation and scoring module
│   │   ├── gen/                            # Query generation and augmentation
│   │   ├── verify/                         # Query quality scoring
│   │   └── prompts/                        # Prompt templates
│   ├── 3_interaction/                      # LLM-environment interaction module
│   │   └── qwen_agent/                     # Interaction framework based on Qwen-Agent
│   ├── 4_reward/                           # Trajectory quality assessment module
│   └── utils/                              # Common utility functions (API client, logging, etc.)
│
└── data/                                   # Input data
    ├── mcp_servers.jsonl                   # MCP server configuration: Contains tool list, server information (input for graph construction)
    ├── tasks.jsonl                         # Task data: Query, target tools, scoring information (input for interaction pipeline)
    └── trajectories.jsonl                  # Trajectory data: Conversation history, tool call records (input for Reward pipeline)
```

---

## 🚀 Script Description and Execution Methods

### 🔄 Complete Workflow

```
mcp_servers.jsonl
       ↓
[1. Graph Construction Pipeline] → Build tool dependency graph, extract valid tool chains
       ↓
[2. Task Construction Pipeline] → Generate and augment Query, quality scoring
       ↓
[3. Interaction Pipeline] → LLM interacts with environment to generate trajectories
       ↓
[4. Reward Pipeline] → Multi-dimensional quality assessment
       ↓
   Final SFT Data
```

### 1. Graph Construction Pipeline (`1_run_graph_pipeline.sh`)

**Function**: Build tool dependency graph, extract tool chains and verify their validity.

**Steps**:
1. **Graph Construction**: Call LLM to detect dependencies between tools
2. **Random Walk**: Extract sub-chains of specified length from the graph
3. **Chain Verification**: Use verification operators to filter invalid tool chains

**Execution**:
```bash
# Please modify the internal parameters according to your own needs.
bash scripts/1_run_graph_pipeline.sh
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `INPUT_FILE` | Tool Document file |
| `MODEL_NAME` | Model name |
| `MIN_LENGTH` / `MAX_LENGTH` | Sub-chain length range |
| `OPERATORS` | Verification operators (comma-separated) |

---

### 2. Task Construction Pipeline (`2_run_task_construction_pipeline.sh`)

**Function**: Generate tasks and perform augmentation and quality scoring.

**Steps**:
1. **Prompt Construction**: Build prompts in different modes
2. **Task Generation**: Call LLM to generate initial tasks
3. **Task Augmentation**: Augment tasks with diversity/complexity/user persona
4. **Quality Scoring**: Score the generated tasks

**Execution**:
```bash
# Please modify the internal parameters according to your own needs.
bash scripts/2_run_task_construction_pipeline.sh 
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `INPUT_FILE` | Input file (output from graph pipeline) |
| `AUG_MODE` | Augmentation mode (options: diverse/complicate/add_ug/all) |
| `N_SAMPLE` | Number of samples per prompt |
| `PERSONA_DATASET_PATH` | User persona dataset path |

---

### 3. Interaction Pipeline (`3_run_interaction_pipeline.sh`)

**Function**: Enable LLM to interact with the environment and generate complete execution trajectories.

**Execution**:
```bash
# Please modify the internal parameters according to your own needs.
bash scripts/3_run_interaction_pipeline.sh 
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `INPUT_FILE` | Task input file |
| `OUTPUT_FILE` | Output trajectory file |
| `MODEL_NAME` | Model name |
| `MAX_WORKERS` | Maximum concurrency |
| `TIMEOUT` | Single interaction timeout (seconds) |

---

### 4. Reward Assessment Pipeline (`4_run_reward.sh`)

**Function**: Perform multi-dimensional quality assessment on generated trajectories.

**Execution**:
```bash
# Please modify the internal parameters according to your own needs.
bash scripts/4_run_reward.sh
```

**Main Parameters**:
| Parameter | Description |
|-----------|-------------|
| `INPUT_FILE` | Input trajectory file (JSON format) |
| `OUTPUT_DIR` | Output directory |
| `MAX_CONCURRENT` | Maximum concurrent requests |

---

## 📊 Input Data Description

All input data is located in the `data/` directory, in JSONL format (one JSON object per line).

### `mcp_servers.jsonl`

MCP server configuration information, used as input for the **Graph Construction Pipeline**.

**Data Structure**:
```json
{
  "base_info": {
    "group_info": {
      "server_title": "Server Title",
      "server_name": "Server Name",
      "server_description": "Server Description",
      "domain": "Domain"
    },
    "tool_list": [
      {
        "name": "Tool Name",
        "description": "Tool Description",
        "parameters": { ... }
      }
    ]
  },
  "features": { ... }
}
```

### `tasks.jsonl`

Task data, used as input for the **Interaction Pipeline**.

**Data Structure**:
```json
{
  "query_info": {
    "generated_question": "User Question",
    "target_tools": ["tool1", "tool2"],
    "augmented_query_info": { ... },
    "query_score_info": { ... }
  },
  "mcp_info": { ... },
  "graph": { ... }
}
```

### `trajectories.jsonl`

Interaction trajectory data, used as input for the **Reward Pipeline**.

**Data Structure**:
```json
{
  "tools": [...],
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "content": "..."}
  ]
}
```

---

