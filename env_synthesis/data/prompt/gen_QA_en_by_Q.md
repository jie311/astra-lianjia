# Role

You are an expert Data Architect specializing in building **LLM Tool-Use Evaluation Datasets**. Your task is to generate high-quality answers and detailed reasoning decomposition traces based on the given question, scenario, and constraints.

# Input Data

Please generate data based on the following input variables:

1.  **Domain**: {{Domain}}
2.  **Knowledge Corpus**: {{Knowledge_Corpus}}
3.  **Question**: {{Question}}

# Scenario Definitions

You must first provide a detailed **final_answer** based on the given **Question**, and decompose the answering process into multiple sub-questions and sub-answers (QA Pairs).
Classify the given **Question** into one of the following scenario types:

1.  **Single-Hop**: Contains exactly 1 sub-question.
2.  **Parallel Single-Hop**: The user question contains multiple independent sub-tasks that are mutually exclusive and can be executed in parallel.
3.  **Multi-Hop**: Contains serialized dependencies (sub-question $q_{i+1}$ depends on the answer $a_i$).
4.  **Parallel Multi-Hop**: A hybrid structure. It contains both independent parallel parts and parts that depend on previous results.

# Constraints & Guidelines

1.  **Realism & Specificity**: Generated sub-questions and sub-answers must be **specific** (e.g., specific dates, amounts, entity names) and must not be vague descriptions (e.g., "a certain community," "a company," "someone," "sometime").
2.  **Task Parallelism**: When processing a multi-step task, the system must automatically identify and split out mutually independent sub-questions (`is_parallel` set to `true`). These sub-questions must not have any dependencies and should be executable in parallel.
3.  **Tool Orientation**: Each `sub_question` must be designed as a **natural query from a user's perspective** that can be solved by invoking a single **atomic** API tool. Each sub-question should map to a discrete operation or tool call (e.g., querying a database, accessing an API, performing a calculation, etc.). The `sub_answer` must **not** contain reasoning or calculation processes; it must only contain the final result/value of that sub-question.
4.  **Clear Dependencies**: You must explicitly state in the JSON `dependency` field which step's output the current step **directly depends** on. Use `null` for parallel steps (or steps with the same parent) and a list of IDs for aggregation steps. `hop_level` indicates the "layer": steps in the same layer can be parallel; steps in the next layer can only depend on outputs from previous layers.
5.  **Corpus Compliance**: If `Knowledge_Corpus` is provided, the answer must be derived from that corpus; otherwise, synthesize reasonable, specific data based on common sense.
6.  **Reasonable Granularity**: Carefully determine the **Num_Hops (Reasoning Hops/Depth)**. While ensuring the atomicity of sub-questions and sub-answers, aim for a reasonable reasoning depth, avoiding excessive or insufficient decomposition.

# Output Format

Please output **ONLY** a list of JSON objects in the following format:

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