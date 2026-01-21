# Role

You are an expert Data Architect specializing in building **Tool-Use** evaluation datasets for Large Language Models (LLMs). Your task is to generate high-quality Question-Answer (QA) pairs and their detailed reasoning decomposition paths based on the given scenarios and constraints.

# Input Data

Please generate data based on the following input variables:

1.  **Domain**: {{Domain}}
2.  **Knowledge Corpus**: {{Knowledge_Corpus}}
3.  **Min_Num_Hops**: {{min_num_hops}}
3.  **Max_Num_Hops**: {{max_num_hops}}
4.  **Count**: {{num_samples}}

# Scenario Definitions

You need to construct **{{num_samples}}** complex **User Queries** and decompose them into sub-questions. Based on the input constraints, the data must adhere to one of the following logical structures:

1.  **Single-Hop**: Contains exactly 1 sub-question.
2.  **Parallel Single-Hop**: The user query contains multiple independent sub-tasks that are mutually exclusive and can be executed in parallel.
3.  **Multi-Hop**: Contains serialized dependency relationships (sub-question $q_{i+1}$ depends on the answer $a_i$).
4.  **Parallel Multi-Hop**: A hybrid structure. It contains both independent parts that can be parallelized and parts that depend on previous results.

# Constraints & Guidelines

1.  **Quantity & Diversity**: You must strictly generate **{{num_samples}}** data entries. Each entry must involve different entities, attributes, or specific scenarios. Avoid using repetitive templates that merely swap names or locations.
2.  **Realism & Specificity**: Generated sub-questions and sub-answers must be **specific** (e.g., specific dates, specific amounts, real entity names) and not vague descriptions (e.g., do not use "a certain community," "a certain company," "someone," or "sometime").
3.  **Task Parallelism**: When processing a multi-step task, the system must automatically identify and split out mutually independent sub-questions (where `is_parallel` is true). These sub-questions must not have any dependencies and can be executed in parallel.
4.  **Tool-Oriented**: Each `sub_question` must be designed as a **natural question from a user's perspective** that can be solved by calling a single **atomic** API tool. Each sub-question should map to a single operation or tool call (e.g., querying a database, accessing an API, performing a calculation, etc.). The `sub_answer` must **not** contain reasoning or calculation processes; it must contain only the final result of that sub-question.
5.  **Clear Dependencies**: You must explicitly indicate in the JSON `dependency` field which step's output the current step **directly depends** on (use `null` for parallel steps; use a list of IDs for converging steps). `hop_level` indicates the "layer": steps in the same layer can be parallel, while the next layer can only depend on outputs from the previous layer or earlier.
6.  **Corpus Compliance**: If a `Knowledge_Corpus` is provided, answers must be derived from that corpus; otherwise, synthesize reasonable specific data based on common sense.
7.  **Hop Range**: The `hop_level` must be between `{{min_num_hops}}` and `{{max_num_hops}}`. Decide **Num_Hops** by **Domain** and **Knowledge_Corpus**.

# Output Format

Please output **only** a JSON object list containing **{{num_samples}}** objects. The format is as follows:

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