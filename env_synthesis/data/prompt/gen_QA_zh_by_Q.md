# Role
你是一名构建LLM工具使用（Tool-Use）评估数据集的专家数据架构师。你的任务是根据给定的问题、场景和约束，生成高质量的回答（Answer）及其详细的推理分解路径。

# Input Data
请基于以下输入变量生成数据：
1. **Domain (场景领域)**: {{Domain}}
2. **Knowledge Corpus (专业知识/语料)**: {{Knowledge_Corpus}}
3. **Question（用户问题）**：{{Question}}

# Scenario Definitions
你需要先根据给定的问题**Question**给出详细答案**final_answer**，并将作答过程分解为多个子问题和子答案（QA Pairs）。
判定给定的问题**Question**，属于以下哪种场景：

1.  **Single-Hop**: 包含 1 个子问题。
2.  **Parallel Single-Hop**: 用户问题包含多个独立的子任务，互不依赖，可并行执行。
3.  **Multi-Hop**: 包含序列化的依赖关系（子问题 $q_{i+1}$ 依赖于 $a_i$）。
4.  **Parallel Multi-Hop**: 混合结构。既包含独立可并行的部分，也包含依赖前序结果的部分。

# Constraints & Guidelines
1.  **真实性与具体性**: 生成的子问题与子问题的答案必须具体（如具体的日期、金额、实体名称），不能是模糊的描述（如“某小区”，“某公司”，“某人”，“某时间”）。
2.  **任务并行**: 当处理一个多步骤的任务时，系统必须自动识别和拆分出那些相互独立的子问题（`is_parallel`为true）。这些子问题不应该有任何依赖关系，可以并行执行。
3.  **工具导向**: 每个子问题`sub_question`都必须被设计为可以通过调用一个**原子性**的API工具解决的**用户视角的自然提问**。每个子问题应该映射到一个单独的操作或工具调用，例如查询数据库、访问API、执行计算等。`sub_answer`不能包含推理和计算过程，只包含子问题的最终答案。
4.  **依赖清晰**: 必须在 JSON 的 `dependency` 字段中明确指出当前步骤**直接依赖**哪一步的输出（并行步骤为 `null` 或同父，汇聚步骤为 ID 列表）。`hop_level` 表示“层级”：同一层的步骤可以并行，下一层只能依赖上一层及之前的输出。
5.  **符合语料**: 如果提供 Knowledge_Corpus，答案必须源自该语料；否则基于常识合成合理的具体数据。
6.  **合理的分解粒度**: 慎重的决定**Num_Hops (推理跳数/深度)**是多少，在保证子问题和子答案的原子性的基础上，追求合理的推理跳数/深度，避免过多或过少的分解。

# Output Format
请仅输出一个 JSON 对象列表，格式如下：

```json
[
  {
    "scenario_type": "Single-Hop" | "Multi-Hop" | "Parallel Single-Hop" | "Parallel Multi-Hop",
    "main_question": "...",
    "final_answer": "...",
    "decomposition_trace": [
      {
        "_uuid": 1,
        "hop_level": 1,
        "sub_question": "...",
        "is_parallel": true,
        "dependency": null, 
        "sub_answer": "..."
      },
      {
        "_uuid": 2,
        "hop_level": 1,
        "sub_question": "...",
        "is_parallel": true,
        "dependency": null, 
        "sub_answer": "..."
      },
      {
        "_uuid": 3,
        "hop_level": 2,
        "sub_question": "...",
        "is_parallel": false,
        "dependency": [1, 2],
        "sub_answer": "..."
      },
      ...
      {
        "_uuid": 8,
        "hop_level": 3,
        "sub_question": "...",
        "is_parallel": false,
        "dependency": [7],
        "sub_answer": "..."
      }
    ]
  },
  ...
]
```