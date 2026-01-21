<h4 align="center">
    <p>
        <b>简体中文</b> |
        <a href="README.md">English</a>
    </p>
</h4>


# 环境合成（Environment Synthesis）

<p align="center">
    <img src="../assets/env.png" alt="环境合成流程图" style="max-width: 100%;">
</p>

本模块用于从问答对（QA pairs）自动生成工具环境，包括工具文档生成、工具代码实现、调用语句生成等完整流程。通过 LLM 驱动的多步骤合成流程，将自然语言问题转化为可执行的工具环境，且中间过程完全可以通过规则校验，可以通过RLVR的形式对模型进行训练。

## 📁 项目结构

```
env_synthesis/
├── scripts/                             # 执行脚本
│   ├── step_01_gen_QA_for_pipeline.sh   # 步骤1：生成QA数据提示词并运行推理
│   ├── step_02_check_tool_necessity.sh  # 步骤2：检查工具必要性
│   ├── step_03_verify.sh                # 步骤3：验证（依赖关系、原子性等）
│   ├── step_04_env_synthesis.sh         # 步骤4：环境合成
│   └── step_05_merge_tools.sh           # 步骤5：合并工具
│
├── src/                                 # 源代码
│   ├── step_01_gen_QA_for_pipeline.py   # QA数据生成与推理
│   ├── step_02_check_tool_necessity.py  # 工具必要性检查
│   ├── step_03_verify.py                # 多维度验证（依赖、原子性、序列化、完整性）
│   ├── step_04_env_synthesis.py         # 环境合成核心逻辑
│   ├── step_05_merge_tools.py           # 工具合并
│   └── utils/                           # 工具函数
│       ├── api_client.py                # API客户端封装
│       ├── api_config.py                # API配置
│       ├── domain_config.py             # 领域配置
│       ├── get_prompt_batch.py          # 批量提示词生成
│       ├── logger.py                    # 日志工具
│       ├── multiprocess_inference.py    # 多进程推理
│       ├── prompt.py                    # 提示词模板
│       └── semaphore_config.py          # 信号量配置（并发控制）
│
└── data/                                # 数据文件
    ├── knowledge/                       # 知识库数据
    │   ├── en/                          # 英文知识库
    │   │   ├── context.jsonl
    │   │   ├── domains.jsonl
    │   │   └── questions.jsonl
    │   └── zh/                          # 中文知识库
    │       └── domains.jsonl
    └── taxonomy/                        # 分类体系数据
        └── finance.json
```

---

## 🚀 脚本说明与执行方法

本模块采用五步流水线，将问题分解为子问题，并为每个子问题生成对应的工具环境：

```
输入：domain/num_sample等参数配置
       ↓
[步骤1] 生成QA数据 → 调用LLM生成问题分解轨迹（decomposition_trace）
       ↓
[步骤2] 检查工具必要性 → 判断每个子问题是否需要工具
       ↓
[步骤3] 验证 → 验证依赖关系、原子性、强制序列化、子问题完整性
       ↓
[步骤4] 环境合成 → 为每个需要工具的子问题生成工具环境
       ↓
[步骤5] 合并工具 → 聚类相似意图的子问题，合并其工具代码（修改mock数据），验证后更新env_result
       ↓
输出：完整的工具环境（工具文档、代码、调用语句等）
```


### 步骤1：生成QA数据提示词 (`step_01_gen_QA_for_pipeline.py`)

**功能**：生成不同类型的问题分解提示词，并调用 LLM 生成问题分解轨迹。

**支持的模式**：
- `zh_kb`: 中文 + 知识库
- `zh_base`: 中文基础模式
- `en_base`: 英文基础模式
- `en_ctx`: 英文上下文模式（支持跳数范围）
- `en_q`: 英文按问题模式
- `tax`: 分类体系模式
- `all`: 运行所有模式

**执行方法**：
```bash
bash scripts/step_01_gen_QA_for_pipeline.sh
# 或直接运行 Python 脚本
python src/step_01_gen_QA_for_pipeline.py \
    --mode zh_kb \
    --model_name <你的模型名称> \
    --output_dir ./output \
    --num_workers 4 \
    --batch_size 4 \
    --min_hops 3 \
    --max_hops 5 \
    --num_repeats 1 \
    --domain general
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `--mode` | 生成模式（必需） |
| `--model_name` | 模型名称（必需） |
| `--output_dir` | 输出目录（必需） |
| `--num_workers` | 并发工作进程数（默认：4） |
| `--batch_size` | 批处理大小（默认：4） |
| `--min_hops` | 最小跳数（默认：3） |
| `--max_hops` | 最大跳数（默认：5） |
| `--num_repeats` | 重复次数（默认：1） |
| `--domain` | 领域(默认： 通用) |

**输出**：
- `{mode}_prompts.jsonl`: 生成的提示词文件
- `{mode}_results.jsonl`: LLM 推理结果（包含 `decomposition_trace`）

---

### 步骤2：检查工具必要性 (`step_02_check_tool_necessity.py`)

**功能**：检查分解轨迹中每个子问题是否需要工具来解决。对于非叶子节点（被其他节点依赖的节点），必须要求 `tool_necessity=True`。

**执行方法**：
```bash
bash scripts/step_02_check_tool_necessity.sh
# 或直接运行 Python 脚本
python src/step_02_check_tool_necessity.py \
    --input_file ./output/zh_kb_results.jsonl \
    --model_name <你的模型名称> \
    --output_file ./output/zh_kb_necessity.json
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `--input_file` | 输入文件（步骤1的输出，JSONL格式） |
| `--model_name` | 模型名称（必需） |
| `--output_file` | 输出文件（JSON格式） |

**输出字段**：
- 每个 `decomposition_trace` 项新增：
  - `tool_necessity`: 布尔值，表示是否需要工具
  - `reason`: 原因说明
- `tool_necessity_legitimacy`: 整体合法性标志（非叶子节点必须为 True）

---

### 步骤3：验证 (`step_03_verify.py`)

**功能**：对问题分解轨迹进行多维度验证，确保质量。

**验证维度**：
1. **依赖关系验证** (`verify_dependency`): 验证子问题声明的依赖关系是否正确
2. **原子性验证** (`verify_atomicity`): 验证子问题是否足够原子化
3. **强制序列化验证** (`verify_forced_serialization`): 验证依赖关系是否必须串行执行，避免出现为了拟合hop_num将原本可以并行执行的内容，强行串行执行
4. **子问题完整性验证** (`verify_subqa_completeness`): 验证所有子问题是否完整覆盖主问题

**执行方法**：
```bash
bash scripts/step_03_verify.sh
# 或直接运行 Python 脚本
python src/step_03_verify.py \
    --input_file ./output/zh_kb_necessity.json \
    --model_name <你的模型名称> \
    --output_file ./output/zh_kb_verified.json \
    --max_concurrent 10
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `--input_file` | 输入文件（步骤2的输出） |
| `--model_name` | 模型名称（必需） |
| `--output_file` | 输出文件 |
| `--max_concurrent` | 最大并发请求数（默认：10） |

**输出字段**：
- `verify_result`: 包含各维度验证结果
  - `dependency_score`: 依赖关系得分
  - `atomicity_score`: 原子性得分
  - `forced_serialization_score`: 强制序列化得分
  - `subqa_completeness_score`: 子问题完整性得分
  - `overall_score`: 综合得分

---

### 步骤4：环境合成 (`step_04_env_synthesis.py`)

**功能**：为每个需要工具的子问题生成完整的工具环境，包括工具文档、工具代码、调用语句等。

**数据过滤**：
在开始环境合成之前，会对输入数据进行过滤：
1. **工具必要性合法性检查**：如果 `tool_necessity_legitimacy` 为 `False`，跳过该数据
2. **验证分数阈值过滤**：如果 `verify_result['score']` 小于 `threshold`，跳过该数据
   - **阈值确定方法**：`threshold` 应该根据验证结果的分布来确定，通常使用 **90% 分位数**（P90）
   - **含义**：只对验证分数在前 10% 的高质量数据进行环境合成
   - **计算示例**：
     ```python
     import numpy as np
     import json
     
     # 读取步骤3的验证结果
     verify_scores = []
     with open("verify_output.jsonl", "r") as f:
         for line in f:
             data = json.loads(line)
             score = data['verify_result']['score']
             verify_scores.append(score)
     
     # 计算90%分位数作为阈值
     threshold = np.percentile(verify_scores, 90)
     print(f"推荐阈值（90%分位数）: {threshold}")
     ```

**合成流程**：
对每个通过过滤的数据，依次执行以下4个步骤（每个步骤都有重试机制）：

1. **工具文档生成** (`_tool_document_generation`): 
   - 根据子问题生成工具文档描述
   - 最大重试次数：`ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - 输出：`tool_document` 和 `analysis`

2. **工具文档复杂度扩展** (`_tool_document_complexity_scaling`): 
   - 扩展和优化工具文档的复杂度
   - 最大重试次数：`ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - 输出：`refined_version` 和 `analysis`

3. **调用语句生成** (`_call_statement_generation`): 
   - 根据问题和工具文档生成工具调用语句
   - 最大重试次数：`ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - 输出：`call_statement` 和 `analysis`

4. **工具部署** (`_tool_deployment`): 
   - 生成工具代码（Python函数）并在沙箱中验证
   - 验证逻辑：执行代码并检查 `tool_call_ans` 是否包含期望的答案
   - 最大重试次数：`ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`
   - 外层重试：如果整个流程失败，会进行外层重试（`ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES` 次）
   - 输出：`function`（代码）和 `analysis`

**执行方法**：
```bash
bash scripts/step_04_env_synthesis.sh
# 或直接运行 Python 脚本
python src/step_04_env_synthesis.py \
    --input_file ./output/zh_kb_verified.jsonl \
    --model_name <你的模型名称> \
    --output_file ./output/zh_kb_synthesized.jsonl \
    --threshold 0.85
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `--input_file` | 输入文件（步骤3的输出，JSONL格式） |
| `--model_name` | 模型名称（必需） |
| `--output_file` | 输出文件（JSONL格式） |
| `--threshold` | 验证分数阈值（必需），建议使用90%分位数 |

**输出字段**：
- `env_result`: 字典，key 为子问题的 `_uuid`，value 包含：
  - `question`: 子问题
  - `answer`: 子答案
  - `env_synthesis_result`: 环境合成结果
    - `data`: 
      - `tool_document`: 工具文档（JSON格式）
      - `tool_call_statement`: 工具调用语句
      - `code`: 工具代码（Python函数）
      - `tool_call_ans`: 工具调用结果（沙箱执行输出）
    - `extra_info`: 各步骤的详细信息
      - `tool_document_generation_result`: 步骤1的结果
      - `tool_document_complexity_scaling_result`: 步骤2的结果
      - `tool_call_statement_result`: 步骤3的结果
      - `tool_deployment_result`: 步骤4的结果

**注意**：
- 仅对 `tool_necessity=True` 的子问题进行环境合成
- `tool_necessity=False` 的子问题对应的 `env_result[_uuid]` 为 `None`
- 如果某个子问题的环境合成失败（所有重试都失败），对应的 `env_result[_uuid]` 为 `None`
- 每个步骤失败时会记录日志，便于排查问题

---

### 步骤5：合并工具 (`step_05_merge_tools.py`)

**功能**：将相似意图的子问题对应的工具代码合并，减少工具数量，提高代码复用性。

**合并流程**：
1. **过滤筛选**：仅保留 `tool_necessity=True` 的子问题
2. **意图聚合** (`intent_aggregation`): 使用 LLM 将相似意图的子问题聚类，生成意图聚类结果
3. **代码合并** (`merge_single_cluster_code`): 对每个包含多个子问题的聚类：
   - 提取聚类中所有子问题的 QA 对和工具代码
   - 以第一个子问题的代码为基础代码
   - 使用 LLM 修改代码中的 mock 数据部分，确保合并后的代码能处理所有 QA 对
   - 为每个 QA 对生成新的工具调用语句
   - 在代码沙箱中验证合并后的代码是否能通过所有测试用例（答案需出现在输出中）
   - 如果验证失败，最多重试 20 次
4. **后处理** (`post_process_merge_tools`): 将合并后的代码、工具文档、调用语句更新回 `env_result`，替换原有的独立工具代码

**执行方法**：
```bash
bash scripts/step_05_merge_tools.sh
# 或直接运行 Python 脚本
python src/step_05_merge_tools.py \
    --input_file ./output/zh_kb_synthesized.json \
    --model_name <你的模型名称> \
    --output_file ./output/zh_kb_merged.json
```

**主要参数**：
| 参数 | 说明 |
|------|------|
| `--input_file` | 输入文件（步骤4的输出） |
| `--model_name` | 模型名称（必需） |
| `--output_file` | 输出文件 |

**输出字段**：
- `clusters`: 意图聚类结果，每个聚类包含：
  - `_uuids`: 聚类中的子问题 UUID 列表
  - `intent_summary`: 意图摘要
  - `reason`: 聚类原因
- `aggregated_env`: 合并后的环境列表，每个元素包含：
  - `status`: 合并状态（"success"/"partial_success"/"failed"/"no_data"/"error"）
  - `merged_code`: 合并后的工具代码
  - `tool_call_statements`: 每个 QA 对应的工具调用语句列表
  - `verification`: 验证结果（测试用例通过情况、重试次数等）
- `env_result`: 更新后的环境结果，合并成功的子问题使用合并后的代码

**注意**：
- 仅对 `tool_necessity=True` 的子问题进行聚类和合并
- 仅对聚类中包含多个子问题（`len(_uuids) > 1`）的进行代码合并
- 如果合并后代码无法通过所有测试用例，整个数据会被标记为失败（返回 `None`）
- 合并的核心是修改 mock 数据，让一个函数能处理多个不同的 QA 对
- 合并后的代码需要在代码沙箱中验证，确保所有测试用例的答案都出现在输出中

---

## 📊 数据格式说明

### 输入数据格式（步骤1）

步骤1接受知识库文件作为输入，格式为 JSONL（每行一个 JSON 对象）。

**知识库文件示例** (`data/knowledge/zh/domains.jsonl`):
```json
{
  "domain": "weather",
  "description": "天气领域相关知识"
}
```

**问题文件示例** (`data/knowledge/en/questions.jsonl`):
```json
{
  "question": "如何计算复利？",
  "answer": "复利是根据本金和累计利息计算的。"
}
```

### 中间数据格式

**步骤1输出** (`decomposition_trace`):
```json
{
  "uuid": "主问题UUID",
  "main_question": "主问题",
  "decomposition_trace": [
    {
      "_uuid": "子问题UUID",
      "sub_question": "子问题",
      "sub_answer": "子问题答案",
      "dependency": [1, 2]  // 依赖的其他子问题索引
    }
  ]
}
```

**步骤2输出** (添加工具必要性):
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
      "reason": "需要调用工具获取实时数据"
    }
  ],
  "tool_necessity_legitimacy": true
}
```

**步骤3输出** (添加验证结果):
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

**步骤4输出** (添加环境合成结果):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [...],
  "env_result": {
    "uuid_1": {
      "question": "子问题",
      "answer": "子问题答案",
      "env_synthesis_result": {
        "data": {
          "tool_document": "工具文档描述",
          "tool_call_statement": "function_name(arg1, arg2)",
          "code": "def function_name(arg1, arg2):\n    ...",
          "tool_call_ans": "调用结果"
        },
        "extra_info": {
          "tool_document_generation_result": {...},
          "tool_document_complexity_scaling_result": {...},
          "tool_call_statement_result": {...},
          "tool_deployment_result": {...}
        }
      }
    },
    "uuid_2": null  // tool_necessity=False 的情况
  }
}
```

**步骤5输出** (添加合并结果):
```json
{
  "uuid": "...",
  "main_question": "...",
  "decomposition_trace": [...],
  "env_result": {
    // 合并成功的子问题使用合并后的代码
    "uuid_1": {
      "env_synthesis_result": {
        "data": {
          "code": "合并后的代码",
          "tool_document": {...},
          "tool_call_statement": "更新后的调用语句"
        }
      },
      "merge_flag": true  // 标记已合并
    }
  },
  "clusters": [
    {
      "_uuids": ["uuid_1", "uuid_2"],
      "intent_summary": "意图摘要",
      "reason": "聚类原因"
    }
  ],
  "aggregated_env": [
    {
      "intent_summary": "意图摘要",
      "_uuids": ["uuid_1", "uuid_2"],
      "status": "success",
      "merged_code": "合并后的工具代码",
      "tool_call_statements": [
        {
          "_uuid": "uuid_1",
          "tool_call_statement": "function_name(args1)",
          "question": "子问题1",
          "answer": "子问题答案1"
        },
        {
          "_uuid": "uuid_2",
          "tool_call_statement": "function_name(args2)",
          "question": "子问题2",
          "answer": "子问题答案2"
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

## 🔧 配置说明

### API 配置

API 配置位于 `src/utils/api_config.py`，包括：
- `API_CONFIGS`: 模型 API 配置字典
- `SANDBOX_URL`: 代码沙箱 URL（用于工具部署验证）
- `ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES`: 环境合成内部重试次数
- `ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES`: 环境合成外部重试次数

### 领域配置

领域配置位于 `src/utils/domain_config.py`，支持：
- `weather`: 天气

可在 `data/taxonomy/` 目录下添加新的领域分类文件。

