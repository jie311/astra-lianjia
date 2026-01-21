<h4 align="center">
    <p>
        <b>简体中文</b> |
        <a href="README.md">English</a>
    </p>
</h4>

# SFT 数据合成与 Reward 打分系统

<p align="center">
    <img src="../assets/sft-pipeline.png" alt=" SFT 数据合成流程图" style="max-width: 100%;">
</p>
本代码库提供从工具图构建、任务生成、轨迹采集到质量评估的完整流水线。

## 📁 项目结构

```
trajectory_synthesis/
├── scripts/                                # 执行脚本
│   ├── 1_run_graph_pipeline.sh             # 图构建流水线：构建工具依赖图 → 随机游走提取子链 → 链验证
│   ├── 2_run_task_construction_pipeline.sh # 任务构建流水线：Prompt生成 → Query生成 → Query增强 → 质量评分
│   ├── 3_run_interaction_pipeline.sh       # 交互流水线：LLM与工具环境交互，生成执行轨迹
│   └── 4_run_reward.sh                     # Reward流水线：对轨迹进行多维度质量评估打分
│
├── src/                                    # 源代码
│   ├── 1_graph_build/                      # 工具图构建与验证模块
│   │   ├── build/                          # 图构建：LLM检测工具依赖、随机游走提取子链
│   │   └── verify/                         # 链验证：投票验证、回译验证等算子
│   ├── 2_task_construction/                # 任务（Query）生成与评分模块
│   │   ├── gen/                            # Query生成与增强
│   │   ├── verify/                         # Query质量评分
│   │   └── prompts/                        # 提示词模板
│   ├── 3_interaction/                      # LLM与环境交互模块
│   │   └── qwen_agent/                     # 基于Qwen-Agent的交互框架
│   ├── 4_reward/                           # 轨迹质量评估模块
│   └── utils/                              # 公共工具函数（API客户端、日志等）
│
└── data/                                   # 输入数据
    ├── mcp_servers.jsonl                   # MCP服务器配置：包含工具列表、服务器信息（图构建输入）
    ├── tasks.jsonl                         # 任务数据：Query、目标工具、评分信息（交互流水线输入）
    └── trajectories.jsonl                  # 轨迹数据：对话历史、工具调用记录（Reward流水线输入）
```

---

## 🚀 脚本说明与执行方法


### 🔄 完整工作流

```
mcp_servers.jsonl
       ↓
[1. 图构建流水线] → 构建工具依赖图，提取有效工具链
       ↓
[2. 任务构建流水线] → 生成并增强 Query，质量评分
       ↓
[3. 交互流水线] → LLM 与环境交互，生成轨迹
       ↓
[4. Reward 流水线] → 多维度质量评估
       ↓
  最终 SFT 数据
```

### 1. 图构建流水线 (`1_run_graph_pipeline.sh`)

**功能**：构建工具依赖图，提取工具链并验证其有效性。

**包含步骤**：
1. **图构建**：调用 LLM 检测工具间的依赖关系
2. **随机游走**：从图中提取指定长度的子链
3. **链验证**：使用验证算子过滤无效工具链

**执行方法**：
```bash
bash scripts/1_run_graph_pipeline.sh \
    --input_file <INPUT_FILE> \
    --model_name <MODEL_NAME> \
    --min_length <MIN_LENGTH> \
    --max_length <MAX_LENGTH> \
    --operators <OPERATORS>

# 示例：
bash scripts/1_run_graph_pipeline.sh \
    --input_file data/mcp_servers.jsonl \
    --model_name qwen-plus \
    --min_length 2 \
    --max_length 5 \
    --operators "vote,backtranslate"
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `INPUT_FILE` | Tool Document 文件 |
| `MODEL_NAME` | 模型名称 |
| `MIN_LENGTH` / `MAX_LENGTH` | 子链最大长度 |
| `OPERATORS` | 验证算子（逗号分隔） |

---

### 2. 任务构建流水线 (`2_run_task_construction_pipeline.sh`)

**功能**：生成task，并进行增强和质量评分。

**包含步骤**：
1. **Prompt 构建**：构建不同模式的prompt
2. **Task 生成**：调用 LLM 生成初始task
3. **Task 增强**：对task进行多样化/复杂化/用户画像增强
4. **质量评分**：对生成的 task 进行质量打分

**执行方法**：
```bash
bash scripts/2_run_task_construction_pipeline.sh \
    --input_file <INPUT_FILE> \
    --aug_mode <AUG_MODE> \
    --n_sample <N_SAMPLE> \
    --persona_dataset_path <PERSONA_DATASET_PATH>

# 示例：
bash scripts/2_run_task_construction_pipeline.sh \
    --input_file output/graph_pipeline/chains.jsonl \
    --aug_mode all \
    --n_sample 5 \
    --persona_dataset_path data/personas.jsonl
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `INPUT_FILE` | 输入文件（图流水线输出） |
| `AUG_MODE` | 增强模式（可选：diverse/complicate/add_ug/all） |
| `N_SAMPLE` | 每个 prompt 采样数 |
| `PERSONA_DATASET_PATH` | 用户画像数据集路径 |

---

### 3. 交互流水线 (`3_run_interaction_pipeline.sh`)

**功能**：让 LLM 与环境进行交互，生成完整的执行轨迹。

**执行方法**：
```bash
bash scripts/3_run_interaction_pipeline.sh \
    --input_file <INPUT_FILE> \
    --output_file <OUTPUT_FILE> \
    --model_name <MODEL_NAME> \
    --max_workers <MAX_WORKERS> \
    --timeout <TIMEOUT>

# 示例：
bash scripts/3_run_interaction_pipeline.sh \
    --input_file data/tasks.jsonl \
    --output_file output/trajectories.jsonl \
    --model_name qwen-plus \
    --max_workers 10 \
    --timeout 300
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `INPUT_FILE` | task输入文件 |
| `OUTPUT_FILE` | 输出轨迹文件 |
| `MODEL_NAME` | 模型名称 |
| `MAX_WORKERS` | 最大并发数 |
| `TIMEOUT` | 单次交互超时时间（秒） |

---

### 4. Reward 评估流水线 (`4_run_reward.sh`)

**功能**：对生成的轨迹进行多维度质量评估。

**执行方法**：
```bash
bash scripts/4_run_reward.sh \
    --input_file <INPUT_FILE> \
    --output_dir <OUTPUT_DIR> \
    --max_concurrent <MAX_CONCURRENT>

# 示例：
bash scripts/4_run_reward.sh \
    --input_file data/trajectories.jsonl \
    --output_dir output/reward_results \
    --max_concurrent 20
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `INPUT_FILE` | 输入轨迹文件（JSON 格式） |
| `OUTPUT_DIR` | 输出目录 |
| `MAX_CONCURRENT` | 最大并发请求数 |

---

## 📊 输入数据说明

所有输入数据位于 `data/` 目录下，格式为 JSONL（每行一个 JSON 对象）。

### `mcp_servers.jsonl`

MCP 服务器配置信息，用于 **图构建流水线** 的输入。

**数据结构**：
```json
{
  "base_info": {
    "group_info": {
      "server_title": "服务器标题",
      "server_name": "服务器名称",
      "server_description": "服务器描述",
      "domain": "所属领域"
    },
    "tool_list": [
      {
        "name": "工具名称",
        "description": "工具描述",
        "parameters": { ... }
      }
    ]
  },
  "features": { ... }
}
```

### `tasks.jsonl`

任务数据，用于 **交互流水线** 的输入。

**数据结构**：
```json
{
  "query_info": {
    "generated_question": "用户问题",
    "target_tools": ["tool1", "tool2"],
    "augmented_query_info": { ... },
    "query_score_info": { ... }
  },
  "mcp_info": { ... },
  "graph": { ... }
}
```

### `trajectories.jsonl`

交互轨迹数据，用于 **Reward 流水线** 的输入。

**数据结构**：
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


