# Copyright 2025-2026 Beike Language and Intelligence (BLI).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


PROMPT_REWARD_CONCISE = """# I. Task Overview

You will act as an evaluator and read a complete trajectory of an Agent interacting with tools. Your goal is to assess the **cost efficiency** of each tool call, focusing on whether the call is concise, whether it could be optimized to reduce the number of calls or cost, and to identify redundant, repetitive, or inefficient calling paths.


# II. Input Format

1. The trajectory includes: the user’s original request, the Agent’s reasoning, each tool call (with parameters), tool responses, and the Agent’s final reply.
2. The trajectory is provided as a JSON object with the following structure:

```json
{
"tools": [...],
"messages": [
    {
    "role": "system" | "user" | "assistant" | "tool",
    "content": "...",
    "tool_calls": [...]
    }
]
}
````

The complete `trajectory` will be provided at the end of the prompt via the `{trajectory}` placeholder.

# III. Evaluation Criteria

## 3.1 Core Metric

Each tool call is scored as 0 or 1:

* **1.0 (Necessary)**: Without this call, the user’s goal cannot be achieved or would be very difficult to achieve; the call follows the context, parameters match the requirement, and it obtains new information or advances the process at minimal cost.
* **0.0 (Redundant)**: The call is disconnected from the goal (including task substitution), repeatedly retrieves already available information, has incorrect parameters (including format errors), involves **parameter hallucination** (the model fabricates parameters not provided by the user or uses default/example parameters), or represents invalid retries.

## 3.2 General Rules

1. **Necessity Principle**: Whether the call is an indispensable step toward the goal. If it is unrelated to the goal, or the goal has already been achieved earlier (overengineering), it is considered redundant.
2. **Information Gain Principle**: The call is expected to provide **critical missing information** needed to solve the task. If the information already exists or can be logically inferred from existing information, it is redundant.
3. **Reasonable Orchestration Principle**:

* **Batch Support**: If a tool supports batch queries (e.g., querying multiple IDs at once) but the model performs multiple serial calls, subsequent calls are considered redundant (non-concise).
* **Avoid Fragmentation**: Avoid splitting what should be a single atomic task into meaningless fragmented calls.
4. **Tool Trust Principle**: Tool definitions and responses are assumed to be reliable. Any call to a tool not defined in the `tools` list receives a score of 0 and is considered a model error. Retries caused by external system failures (e.g., timeouts, 500 errors) are considered necessary; however, repeated invalid verification with identical parameters is redundant.

## 3.3 Special Judgments (Common Failure Cases)

1. **Parameter Responsibility**

* **Parameter Errors / Hallucination**: If the model fabricates, omits, or hallucinates parameters (e.g., the user did not provide `user_id` but the model invents `user_id=12345`), or uses malformed parameters that cause failure or invalid results, score 0 and treat as a model error.

2. **Repeated Reads**

* After information has been clearly obtained (e.g., the tool has returned a result), continuing to call the tool again to fetch the same information.
* *Query retries allowed*: If a search tool returns no results, modifying the query and retrying to obtain different results is considered necessary.
* *Counterexample*: If the result of the current call can be inferred from existing information in the context, the call is redundant and should not be made.
* If historical results are needed, the model should directly reference prior responses. Only when an explicit “latest snapshot” is required and prior results may be stale is a re-call allowed and must be justified; otherwise, score 0.

3. **Invalid Retries**

* **Retries allowed**: Only when the previous step returned transient errors such as “timeout,” “network instability,” or “server busy.”
* **Retries forbidden**: If the previous step returned a clear business error (e.g., “no such record”), the model should check parameters or switch tools rather than retrying with identical inputs.

4. **Stochastic Interfaces**

* If the tool documentation or response indicates randomness or sampling, multiple calls are allowed to satisfy the user’s request, but the reasoning must explain why randomness necessitates repeated calls.

5. **Task Consistency**

* **Task substitution / goal degradation**: If a tool call is used to perform a simplified task that deviates from the user’s core requirement and does not meaningfully contribute to the real goal, score 0.

# IV. Evaluation Procedure

1. **Understand the Task**: Identify the user goal, available tools, and constraints.
2. **Parameter Source Check (Critical Step)**: Verify the origin of all parameters in every tool call, especially to identify **parameter hallucination**:

* **Parameter hallucination**: Parameter values cannot be derived from any source, are randomly invented by the model (e.g., random IDs, arbitrary numbers), or copied from example/default parameters in the `tools` definition.
3. **Step-by-Step Reconstruction**: Along the timeline, record the triggering context, existing information, and intent of each call.
4. **Per-Call Scoring**: Evaluate each call one by one according to the criteria above (including special judgments), and clearly state the reasoning. Pay special attention to cascading effects caused by parameter hallucination.
5. **Global Summary**: In the `thought` field, summarize the overall strategy, key decisions, existing issues, and possible improvements.

# V. Output Format

Strictly output **valid JSON** only. Do not add any extra text, comments, or explanations. `score` must be either `0.0` or `1.0`.

```json
{
"tool_call_num": <total number of tool calls>,
"tool_evaluations": [
    {
    "tool_index": 1,
    "tool_name": "<tool name>",
    "reasoning": "<concise justification: analyze necessity, parameter correctness, and conciseness in context>",
    "score": 0.0 | 1.0
    }
],
"thought": "<overall analysis>",
"tool_score_list": [score_1, score_2, ...]
}
```

# VI. Additional Notes

* Tool definitions must be strictly followed; do not infer unavailable capabilities.
* **Parameter source checking is the first step of evaluation**: before evaluating any tool call, you must verify whether all parameters originate from user input or tool outputs, and clearly determine whether parameter hallucination exists.
* Maintain consistent judgment standards across similar scenarios and do not overlook special rules.
* Strictly adhere to the output format and return valid JSON only; do not add any explanatory text.
* **Strict JSON formatting requirements**: The output must be valid and parsable JSON. Quotes inside string values must be escaped using `\"`. Nested unescaped quotes are forbidden (e.g., `"reasoning": "this is "necessary" call"` is invalid; use `"this is \"necessary\" call"` or avoid quotes).
* Respond in Chinese.

---

**Complete trajectory**:

```
{trajectory}
```

""".strip()


PROMPT_REWARD_FINAL_ANSWER_SUMMARY = """

## 🚀 Trajectory Summary Quality Evaluation Prompt (Optimized Version)

### I. Task

Evaluate the given **trajectory** (the complete sequence of steps taken by the assistant to accomplish the user task, including reasoning, actions, observations, planning, summaries/reflections, etc.) together with the corresponding **final_answer** (the assistant’s final response).  
The goal is to determine whether the final_answer provides an accurate and comprehensive summary of the trajectory, **with particular emphasis on whether all valuable final deliverables are fully presented**.  
Output a standardized score (1.0 / 0.5 / 0.0) along with explainable evaluation reasoning.

-----

### II. Scoring Criteria

#### Score 1.0 (Excellent Summary)

All of the following requirements must be satisfied:

* **Accurate and comprehensive**: Key information is accurate and the summary is comprehensive, fully capturing the core steps, action logic, and final outcomes of the trajectory, **with no important omissions**.
* **Complete deliverables**: If the trajectory produces any valuable final artifacts (e.g., written content, code, data, addresses, phone numbers, URLs, etc.), the **final_answer must fully present these deliverables**, rather than merely stating that they were “completed.”
* **Failure handling**: When all tools in the trajectory return errors or failures, the final_answer includes an apology and an explanation of the cause, and provides feasible remediation steps or suggestions.  
If multiple retries or explorations all fail, it is sufficient to apologize and explain one representative failure; when remediation or suggestions are provided, detailed intermediate steps may be omitted.
* **Single-turn simplification**: For single-turn interactions containing only user and system messages, a score of 1.0 may be assigned directly.
* **Error tolerance**: If the final_answer already fully satisfies the user query, occasional failed attempts in the trajectory do not need to be explained or apologized for; a score of 1.0 can still be assigned.

#### Score 0.5 (Partial Summary)

Any of the following conditions applies:

* **Incomplete information**: Key information is accurate, but the summary lacks completeness or detail, such as omitting secondary yet valuable steps or background context, or presenting final deliverables incompletely (e.g., stating “the copy was generated” without including the actual copy).
* **Unclear logic**: The process is summarized, but key turning points (e.g., reasons for tool failures, strategy changes) are explained insufficiently or ambiguously.

#### Score 0.0 (Invalid / Incorrect Summary)

Any of the following conditions applies:

* **Incorrect or irrelevant content**: Key information is inaccurate, the summary is completely irrelevant, erroneous, or includes fabricated or unreasonable content.
* **Pure error output**: The final_answer consists solely of an error code or error message and provides no process summary of the trajectory.
* **Result repetition without process**: The final_answer merely repeats the final result without reflecting the process logic or key transitions.
* **URL mismatch**: The tool returns valuable content, but the URL mentioned in the final_answer does not exist in the trajectory (duplicate cases should be judged accordingly; fundamentally, this reflects a lack of alignment between the summary and the trajectory).


## III. Assessment Objects

### 3.1 Trajectory Content
<trajectory_start>TRAJECTORY</trajectory_start>

### 3.2 Final Answer Content
<final_answer_start>FINAL_ANSWER</final_answer_start>

## IV. Output Requirements

You must strictly output the following JSON format and include no other content:
```json
{
    "thought": "A detailed analysis combining the trajectory and the final_answer, matching each scoring criterion step by step and explaining the reasoning that leads to the final score",
    "score": float,
    "reason": "Based on the trajectory and the final_answer, explain the core basis for the score, clearly mapping to the corresponding scoring tier"
}
```
""".strip()


PROMPT_REWARD_FINAL_ANSWER_CORRELATION = """

1. Task
    Evaluate the relevance and quality alignment between a user query and its corresponding answer. The core focus is to determine whether the answer truly, completely, and accurately addresses the user’s question, and to assign a standardized score (1.0 / 0.5 / 0.0) strictly based on predefined criteria.

2. Objective
    Conduct an in-depth analysis of the alignment between the user query and the answer. Ensure that the scoring is objective, consistent, and explainable, strictly adhering to the detailed standards of each score level. The evaluation must not involve subjective bias and should rely solely on the actual content of the query and the answer.

3. Assessment Criteria (with Detailed Scoring Guidelines)

    0. If the final_answer and the query are in different languages, directly assign a score of 0.0 and skip all further evaluation.

    1. If the intent of the query is “how to do something” (solution-oriented), but the final_answer does not provide a solution, directly assign a score of 0.0 and skip all further evaluation.

    2. If the query lacks critical information (e.g., missing necessary personal or contextual details), and the final_answer does not ask follow-up questions or seek clarification but instead responds directly, assign a score of 0.0 and skip all further evaluation.

    a. Score 1.0 (Fully Solves the Query)
        * Core principle: The answer fully, accurately, effectively, and directly resolves all core user requirements with high usability.
        * Assign a score of 1.0 only if **all** of the following conditions are met:
            * All core questions are resolved: The answer completely, clearly, and accurately addresses every key point in the user query.
            * No missing core information: All essential elements required by the query are covered, with no critical omissions.
            * High usability: The answer can be directly used as guidance for the user’s next actions or as a reliable source of information.
            * The answer must directly solve the user’s problem and must not be a substitute or alternative solution.

    b. Score 0.5 (Partially Solved / Missing / Incorrect)
        * Core principle: The answer is related to the query but fails to fully solve it due to functional issues, incomplete information, errors, or low content quality.
        * Assign a score of 0.5 if **any** of the following conditions are met:
            * Functional obstacles block the core objective: The content is relevant, but due to systemic or environmental issues (e.g., access restrictions, inaccessible URLs, missing information, query failure, unauthenticated state), the user cannot obtain or use the core information.
            * Partial solution / missing core information: Some aspects of the query are addressed, but critical information is missing or key constraints are not satisfied.
            * Ambiguity or errors: The answer contains relevant information but includes inaccuracies, unclear logic, or incorrect content.
            * Barely solves the problem: The answer attempts to address the query but lacks necessary supporting guidance or justification, resulting in low-quality output.

    c. Score 0.0 (Not Solved / Irrelevant)
        * Core principle: The answer is irrelevant, unreadable, or provides no effective information tailored to the user’s specific needs.
        * Assign a score of 0.0 if **any** of the following conditions are met:
            * The final_answer and the query are in different languages (e.g., the query is in Chinese and the final_answer is in English).
            * Irrelevant / off-topic: The content has no meaningful connection to the user’s intent or completely deviates from the query.
            * Functional errors: The structure or content is unparsable, unreadable, or directly returns an error message or empty content (excluding the external/environment-dependent cases specified under the 0.5 score).
            * Failure to provide a valid solution: No effective, relevant, or domain-appropriate information is provided to address the user’s query.

    d. Key Assessment Notes
        * Mandatory deep analysis: Judgments must be based on the specific content of both the query and the answer, not on summaries or assumptions.
        * Distinguish between 0.5 and 0.0 functional issues: A 0.5 score involves external or environmental dependency issues (e.g., permissions, network), while a 0.0 score involves inherent structural or content errors (e.g., unparsable output, empty answer).
        * Focus on core intent: Prioritize whether the answer resolves the user’s primary intent rather than secondary or non-essential details.

5. Output Requirements
    * The "thought" field must contain a detailed analytical process: explain the core intent and key elements of the query [explicit interpretation]; then evaluate how the answer matches the criteria for each score level—especially its alignment with the evaluation points for 1.0 / 0.5 / 0.0; finally, confirm the assigned score and explain the reasoning.
    * The "reason" field must concisely summarize the core basis for the score, directly referencing the predefined assessment criteria.
    * The "score" field must be exactly one of: 1.0, 0.5, or 0.0. No other values are allowed.
    * Output **only** the specified JSON format. No additional text, comments, or formatting changes are permitted.

    You must strictly output the following JSON structure and nothing else. Failure to do so will result in severe penalties.
    ```json
    {
        "thought": "... detailed analysis here ...",
        "reason": "... concise justification here ...",
        "score": float
    }
    ```

query: <query_start>QUERY</query_end>\n\n
answer: <answer_start>ANSWER</answer_end>
""".strip()

PROMPT_REWARD_URL = """
Determine whether the URL appears in the answer. If it appears, give a score of 1; otherwise, give a score of 0.
URL: <url_start>URL</url_end>
answer: <answer_start>ANSWER</answer_end>
```json
{
    "thought": "A detailed analysis combining the URL and the answer, matching the scoring criteria step by step and explaining the reasoning that leads to the final score",
    "score": float,
    "reason": "Based on the URL and the answer content, explain the core basis for the score, clearly stating the judgment conditions corresponding to the assigned score"
}
```
""".strip()


PROMPT_TOOL_JUDGE_NEED = """
I will provide you with a user query. Your task is to determine whether this query requires calling external tools to be completed.

You must make the judgment strictly according to the rules below.

【Rules】
- Analyze the relationship between the query content and tool usage;
- Determine whether the query necessarily depends on external tools (such as search, computation, API calls, code execution, file retrieval, etc.) to obtain an answer;
- If the query can be answered directly through common knowledge, language understanding, or logical reasoning, then no tool call is required;
- If the query requires obtaining data from an external environment or tools, executing operations, or verifying information, then a tool call is required.

【Explanation】
- Examples of cases that require tool calls:
    - Queries involving real-time information, calculations, external knowledge bases, or file contents;
    - User requests to perform concrete operations (e.g., “run this for me”, “calculate”, “retrieve”).
- Examples of cases that do not require tool calls:
    - General knowledge Q&A, explanatory questions, or logical reasoning;
    - Answers that can be generated directly from the model’s own knowledge.

【Output Format】
You must strictly follow the JSON format below and must not return any other content. Otherwise, you will be subject to severe penalties.
{
    "thought": "your reasoning process",
    "need_tool_call": boolean, only true or false is allowed
}

User query: QUERY
""".strip()


PROMPT_TOOL_STATUS = """
I will provide you with a tool invocation result. Your task is to determine whether the tool call was successful.

You must strictly follow the rules below when making the judgment.

【Rules】
- The judgment is a boolean value:
    - True: the tool call succeeded
    - False: the tool call failed
- The evaluation should focus on whether the tool execution itself succeeded.
    You do NOT need to evaluate the completeness or correctness of the returned result.

【Explanation】
- Successful cases include:
    - The tool returns a result, and the result does not contain any error or exception information
- Failed cases include:
    - The tool returns error information such as error_code, exception messages, traceback information, or other abnormal content

【Output Format】
- Your response must be a JSON object:
{
    "thought": "your reasoning process",
    "tool_status": boolean, only true or false is allowed
}
You must strictly follow the format above and must not return any other content,
otherwise an error will occur.

Tool invocation content: TOOL_CONTENT
""".strip()


PROMPT_TOOL_CONTENT_PLAN = """
# I. Task Overview

You will act as a rigorous evaluator. Your task is to assess the quality of a specific intermediate-round **tool-calling plan** generated by an Agent, based on the provided **tool list** and the Agent–environment interaction **full trajectory**.

You must take a **global perspective**—including the prior context before this round, the most recent tool return results, and the actual execution outcomes after this plan—to judge whether the plan:
- correctly understands the current state,
- proposes reasonable and necessary actions,
- and uses correct tools with correct parameters.

# II. Input Description

The input will be provided in JSON format and contains three parts:
1. **`tools` (Tool List)**: All tool definitions available for the task (name, description, parameter schema).
2. **`trajectory` (Full Trajectory)**: The complete message history from the beginning to the end of the task, including user requests, system instructions, assistant reasoning and calls, and tool responses.
**Note:** This is a “god’s-eye view” dataset that includes events occurring *after* the evaluated round and is used to assess the plan’s ultimate validity.
3. **`plan` (Plan to Be Evaluated)**: The target object to be scored. It corresponds to a specific `assistant` message in the trajectory and contains the generated `tool_calls`.

Note: The `assistant_index` in the full trajectory is consistent with the `assistant_index` in the plan and can be used to directly locate the evaluated plan within the trajectory.

**Placeholders:**
- `{tools}`: tool list data
- `{trajectory}`: full trajectory data
- `{plan}`: the specific plan to be evaluated

# III. Evaluation Criteria

## 1. Correctness Dimensions
A “correct” tool call must satisfy **all** of the following:
- **Intent Correctness**: Aligns with the current task goal and makes correct logical inferences based on the previous tool results.
- **Parameter Correctness**: Parameters must **strictly** conform to the tool schema, with accurate values and correct formats.
- **Necessity**: From a global perspective, the tool is necessary to achieve the current task objective.

## 2. Scoring Rules

### Case A: Single Tool Call (Plan contains exactly 1 tool)
In this case, **0.5 is strictly forbidden**.
- **1.0 (Fully Correct)**: All correctness criteria are satisfied.
- **0.0 (Incorrect)**: Any issue such as parameter hallucination, invalid retry, redundant retrieval, or incorrect intent.

### Case B: Multiple Tool Calls (Plan contains more than 1 tool)
- **1.0 (Fully Correct)**: **All** tool calls are correct and necessary.
- **0.5 (Partially Correct)**: **Some** tool calls are correct, while **others** contain issues.
- **0.0 (Completely Incorrect)**: **All** tool calls contain issues.

## 3. Common Failure Patterns

0. **Parameter Errors**: Any parameter error immediately counts as a failed tool call. This includes invalid parameters causing permanent errors, nearly-correct parameters with invalid values, correct intent but invalid parameter values, or incorrect formats leading to execution failure.
- *Counterexample*: `conversationHistory` in `result_coverage` is not properly escaped, causing JSON parsing failure.
1. **Parameter Hallucination**: Calling a tool not listed in `tools`, using parameters not defined in the schema, fabricating parameter values, or inventing values not mentioned previously (e.g., city codes or ID numbers).
- *Counterexample*: `customToken` should not be a placeholder string like `"your_token_here"` but a concrete value such as `1234567890`.
2. **Redundant Retrieval**: Repeatedly calling the same tool to fetch the same information after it has already been clearly returned earlier.
3. **Invalid Retry**: Retrying unchanged calls after **non-recoverable errors** (e.g., parameter validation failure, permission denied, 404, permanent server errors).
- **Allowed retries**: Timeouts, transient network issues, or temporary server overload.
- **Disallowed retries**: Explicit business logic errors (e.g., “record not found”).
4. **Dependency Race**: In the same planning round, a tool call’s parameters depend on the results of another tool call from the same round.
- *Counterexample*: Calling `add(2,3)` and `add(5,4)` simultaneously while assuming the first result is 5.
- *Counterexample*: Calling `add` and `multiply` together where one depends on the result of the other—these must be split into separate rounds.
5. **Fabricated Parameters**: Using the model’s internal reasoning to compute intermediate values instead of obtaining them from tools.
- *Counterexample*: The assistant computes `(16 * tan(30°))²` internally without using a tool.
6. **Unreasonable Planning**: Illogical tool usage, invalid parameters, incorrect operation order, or ignoring tool prerequisites, leading to failure.
- *Example*: Computing a full distance matrix for all points and then directly calling a route tool from the first to the last point—this plan is unreasonable.
7. **Empty Tool Name**: Tool name cannot be empty. An empty tool name is considered a failed call.
8. **Execution Parameter Errors**: Tool execution failures caused by parameter parsing errors (e.g., JSON errors such as `"Unterminated string starting at: line 1 column 542"`).

# IV. Evaluation Procedure

1. **Context Analysis**:
- Read the `trajectory` and locate the plan round.
- **Inventory existing information** to avoid redundant retrieval.
- **Previous state check**: Analyze the immediately preceding tool result and classify errors as transient or permanent.

2. **Legality Check**:
- **Schema validation**: Verify that all parameter names and values strictly match the tool definitions.

3. **Per-Call Validation**:
- **Retry rationality**: Determine whether retries are justified or improved (e.g., better formatting, clearer focus, structured input).
- **Information gain**: Does the call provide new critical information?
- **Dependency validity**: Check for invalid concurrent dependencies among multiple tool calls.
- Use subsequent execution results (god’s-eye view) to distinguish planning errors from external uncontrollable failures.

4. **Score Determination**:
- Assign a score according to Section III.

5. **Thought Writing**:
- **Format**: Extremely concise, no verbosity, limited to 2–3 sentences.
- **Structure**:
    1. **Situation**: The plan contains X tool calls.
    2. **Issues / Strengths**: Clearly identify issues such as parameter hallucination, invalid retry, or redundant retrieval.
    3. **Conclusion**: Assign score Y based on the rules.

# V. Output Format

Output **valid JSON only**, with **no explanatory text**.

```json
{
    "score": "0.0 | 0.5 | 1.0",
    "thought": "Concise analytical reasoning",
    "pre_assistant_calls": "List of tools called by the assistant before the current assistant_index"
}
````

""".strip()


PROMPT_TOOL_CONTENT_UNDERSTAND = """
I will provide you with a tool list, the complete interaction context between the Agent system and the environment (including all historical interactions), and the Agent’s returned dict. Your task is to evaluate how well the Agent understands the returned content of a specified batch of tool calls.

You must strictly follow the rules below.

【Important Notes – Read Carefully】
- **Scoring target: the returned results of this batch of tool calls (tool_call_id: {tool_call_ids}) + the Agent’s subsequent reaction**
- **Batch concept: tool calls are executed in batches. Each batch contains one or more tools called in parallel. The current batch includes the following tool_call_id(s): {tool_call_ids}**
- **Key focus: only the tool messages in the context whose tool_call_id is {tool_call_ids} (i.e., the return results of this batch)**
- **Indexing aid: the index positions of this batch in the context are {tool_batch_indices}, with index–call_id mapping: {tool_index_call_ids} (indices are only for locating; batching is determined strictly by tool_call_id)**
- **Important: score strictly according to the specified tool_call_id(s); do NOT extend or infer other tool messages**
- **Batch continuity: if the previous batch is call_1, the current batch should be call_2 or start from call_2 as a continuous sequence, not a discontinuous ID like call_6**
- **If the specified tool_call_id is immediately followed by an assistant message, treat it as a single independent batch and do not extend to subsequent tool messages**
- If this batch contains multiple consecutive tool messages (parallel calls), treat them as one unified batch

【Redundant Call Judgment – Critical Rule】
- **Core rule: if the Agent initiates redundant tool calls in later steps (repeating the same/similar tools without adjusting strategy based on the current batch results), then even if the Agent’s final summary mentions this batch, the understanding score for the current batch MUST be 0.0**
- **Criteria for redundant calls:**
1. The current batch has already returned clear results (success / failure / error)
2. The Agent subsequently initiates tool calls with the same or similar objectives
3. The subsequent calls do not involve substantive parameter adjustments or strategy changes based on the current batch
- **Key interpretation: redundancy itself indicates lack of understanding. Do NOT give a high score because “the Agent eventually summarized correctly” or “understood it from a global perspective.”**
- **Typical scenarios:**
- The current batch search returns “not found,” and the Agent later searches again with the same keywords
- The current batch fails and returns an error, and the Agent later repeats the same call without fixing parameters
- The current batch already provides the required information, yet the Agent repeatedly re-verifies or re-fetches it
- **Explicit rule: once redundant calls are detected, you MUST assign a score of 0.0**

【Scoring Focus – Core Logic】
- **Primary focus: the return results of the current batch + the Agent’s subsequent reaction (the content and tool_calls in the ans field)**
- **Judgment basis: determine whether the Agent understood the current batch results by examining its subsequent reaction**
- Did the Agent correctly identify key information in the tool return (success / failure / error reason, etc.)?
- Did the Agent take correct follow-up actions or provide correct explanations based on the tool results?
- Did the Agent correctly use the returned information in subsequent steps?
- **Role of historical context:**
- Historical context is mainly for understanding the current state and background and should not be overemphasized
- If the Agent implicitly understood the tool return in history and correctly used it later (even without explicit explanation), this step can be considered understood from a global perspective
- However, the primary scoring basis remains: the current batch results + the Agent’s immediate subsequent reaction

【Rules】
- Tool content understanding scores have three levels:
- 0.0: Completely incorrect understanding of the tool return
- 0.5: Incomplete understanding of the tool return
- 1.0: Completely correct understanding of the tool return

【Strict Consistency – Thought and Score Must Match】
- Write the thought first, then assign the score. If the thought states “not understood / issues exist / repeated mistakes / redundant calls,” the score must be lowered accordingly
- **[Redundant call rule] If redundant tool calls are found later (same/similar calls without substantive parameter adjustment), `understand_score` MUST be 0.0, regardless of any other performance**
- If the thought indicates complete lack of understanding (e.g., repeating the same error, ignoring feedback, contradiction with tool returns), `understand_score` MUST be 0.0
- If the thought indicates partial understanding or missing key information, `understand_score` MUST be 0.5
- Only when the thought explicitly states “fully understood, fully utilized results, actions consistent with feedback” is a score of 1.0 allowed
- Error types are not limited (permission, parameters, data, logic, etc.). Once repeated failure without strategy adjustment is observed, it is considered complete misunderstanding and scored 0.0

【Scoring Steps – Must Be Followed】
1. At the beginning of the thought, write one of:
“Judgment: fully understood / partially understood / completely not understood”
2. Strictly map judgment to score:
- “Completely not understood” → `"understand_score": "0.0"`
- “Partially understood”      → `"understand_score": "0.5"`
- “Fully understood”          → `"understand_score": "1.0"`
3. **Special check: if redundant tool calls are found later, you must override the judgment to “completely not understood” and assign 0.0**
4. Self-check before output: if judgment and score are inconsistent, you must correct them

【Explanation – Scoring Standards (Based on Tool Returns + Agent Reaction)】
- **Scoring is based on the Agent’s subsequent reaction (ans field)**
- Completely incorrect understanding – **must score 0.0**
- The Agent’s explanation of the current batch is entirely incorrect and contradicts the tool return
- The tool clearly returns an error/exception, but the Agent neither explains nor adjusts parameters and instead repeats the same operation
- The tool return is normal and reliable, yet the Agent doubts it without user request and repeatedly verifies or calls additional tools
- **Redundant calls exist: repeating the same/similar tools without substantive adjustment. Even if the Agent later summarizes correctly, the score must still be 0.0**
- Partially correct understanding
- The tool return does not meet requirements (e.g., irrelevant search results, missing fields), and the Agent merely states it will continue or change strategy without clearly explaining the issue
- The Agent’s summary covers only part of the key information, with omissions or incomplete abstraction
- The Agent identifies some errors but ignores other important error information
- Completely correct understanding
- The Agent fully and accurately understands the current batch results, with no issues in summary or explanation
- When the tool returns empty or “not found,” the Agent clearly states this and provides next-step suggestions
- When the tool returns errors or exceptions, the Agent accurately explains the cause and proposes feasible workarounds or alternatives, rather than repeating the same erroneous call
- When the tool returns structured data (lists, tables, fields), the Agent correctly extracts key information without omission or fabrication
- When the tool results already satisfy the task, the Agent completes the task or summarizes directly, without unnecessary doubt or repeated calls
- If the Agent’s summary is inconsistent with its actual actions, it should be considered only partially understood and scored 0.5

【Other Notes】
- The `thought` should be precise and concise, without redundancy

【Additional Notes – Parallel Tool Call Handling】
- In the interaction context, multiple consecutive `role: "tool"` messages may appear, indicating parallel tool calls in a single assistant response
- In such cases, treat all consecutive `role: "tool"` messages up to the next `role: "assistant"` message as a single batch
- You must consider all tool returns in this batch together when judging understanding and assign a single unified score
- Do not judge based only on the last tool message; consider all tool returns in the batch along with the Agent’s subsequent reply

【Output Format】
- Your output must be a JSON object:
```json
{
    "thought": "... detailed analysis here",
    "understand_score": "... final score here"
}
````

You must strictly follow this format and return no other content, otherwise you will receive a severe penalty.

【Additional Constraints】

* The `thought` must be precise but not verbose

【Additional Notes – Parallel Tool Call Handling (Reiterated)】

* **The current batch includes tool_call_id(s): {tool_call_ids} (primary identifier)**
* **Index positions in context: {tool_batch_indices} (for reference only)**
* **Strict restriction: analyze only tool messages with tool_call_id {tool_call_ids}; do not extend to others**
* **Batch identification rule: tool calls proceed sequentially. If the previous batch is call_1, the current batch should be call_2 or start from call_2. Do not confuse non-contiguous IDs (e.g., call_6)**
* **If the specified tool_call_id is a single ID (e.g., call_2) and is immediately followed by an assistant message, treat it as a single batch and score only that tool message**
* If the batch contains multiple consecutive tool messages (parallel calls), treat them as one unified batch
* **Scoring logic:**

* First analyze what the tool messages with tool_call_id {tool_call_ids} returned (success / failure / error / data)
* Then analyze the Agent’s subsequent reaction (ans field): what it said, what it did, and whether it made correct judgments based on the tool returns
* Determine understanding based on the Agent’s subsequent reaction
* Do not focus only on the last tool message; consider all tool returns in the batch together with the Agent’s reply

Tool list:
{tools}

Interaction context:
{trajectory}

Agent returned dict:
{ans}
""".strip()


PROMPT_QUERY_UNDERSTAND = """
You are a professional AI model evaluation expert. Your core task is to assess whether the model correctly understood the user’s **Query** in its **first response**.

### Input Description
1. **Query**: The user’s question or instruction.
2. **First Response**: The model’s original first-turn reply (the object to be evaluated).
3. **Trajectory**: Subsequent multi-turn dialogue records (used only as auxiliary context).

### Evaluation Logic Flow
You must strictly follow the steps below when reasoning and making judgments:

**Step 1: Analyze the Query Requirements**

**1.1 Missing Parameters and Clarification Rules**
* If the query itself is unclear or missing key “slots” (slots can also be inferred from the parameters required by tools called in tool_calls), the model should first ask follow-up questions or request clarification instead of fabricating information.
    * If the first response contains clarification questions or requests for missing information, assign a score of **1**.
    * If the first response does not contain clarification questions or requests, assign a score of **0**.

**1.2 Tool-Call–Related Rules**
* If the understanding is correct but there are issues in tool_calls, assign **1 point** (correct understanding, incorrect execution).
* If key data required by the query is not provided, but the assistant directly calls a tool anyway, assign **0 points**.
* If critical parameters in the first-round tool_calls are not mentioned in the query and are strongly tied to personal information that must be provided by the user but was not provided, assign **0 points**. In all other cases, proceed to the next step.

**1.3 Query Type Judgment**
* If the query asks for advice on *how to do something* (e.g., “How to do…”, “What is the best way to do…”) rather than asking the model to solve a concrete problem, assign **0 points**.
* If the query’s goal is to request a solution and does not explicitly require tool usage, but the assistant still calls tools in the first round, assign **0 points**.

**1.4 Normal Case Handling**
* If the query does not fall into any of the above cases, analyze the Query and extract the **key information points required for correct understanding** (`query_understand_key_info`).

**Step 2: Check the First Response Status (Preliminary Risk Control)**
* **Empty response**: If the First Response is empty, contains only meaningless characters, or clearly triggers a safety refusal (considered compliant with safety policy), directly assign **Score = 1**.

**Step 3: Evaluate Understanding in the First Response (Core Judgment)**
* **Obvious misunderstanding**: If the First Response is not empty and is clearly off-topic, misses key information, or demonstrates misunderstanding, assign **Score = 0**.
    * *Note: Even if the model corrects itself in later turns of the Trajectory, the first-round score remains 0.*
* **Obvious correct understanding**: If the First Response clearly and accurately covers the intent of the Query, assign **Score = 1**.
    * *Note: Even if the model is later misled or hallucinates in subsequent turns, as long as the first response is correct, the score remains 1.*

**Step 4: Use Trajectory for Auxiliary Judgment (Only for Ambiguous Cases)**
* **Activation condition**: Only use the Trajectory when the First Response is short, vague, or ambiguous and cannot be judged independently.
* **Supplementary logic**:
    1. Extract explanations or subsequent behaviors from the Trajectory that clarify the intent of the first response.
    2. **Conflict resolution principle**: If there are contradictions within the Trajectory, prioritize the earlier (chronologically first) content.
    3. **Final judgment**: If, after incorporating supplementary information, the implicit intent of the first response is confirmed to be correct, assign **1 point**; otherwise, assign **0 points**.

### Output Format Requirements

- Your output must be a JSON object:
```json
{
    "query_understand_key_info": "... the key information required for correctly understanding the query",
    "thought": "... detailed reasoning process",
    "add_info_understand": "... the optimized interpretation of the first response after incorporating trajectory information",
    "score": "... final score, 0 or 1"
}
````

You must strictly follow this format and return no other content, otherwise you will receive a severe penalty.

【Additional Notes】

* Your `thought` should be precise and concise, without unnecessary verbosity.

Query:
{query}

First Response:
{query_understand}

Trajectory:
{trajectory}
""".strip()


PROMPT_QUERY_PLAN = """
You are a professional AI model evaluation expert, responsible for assessing the model's **Initial Global Planning** in its **first response**.

## Input
1. **Query**: The user’s question or instruction
2. **First Response**: The model’s first-turn reply (primary object of evaluation)
3. **Trajectory**: Subsequent multi-turn dialogue records (auxiliary validation information)

First, identify one of the two situations, then strictly follow the step-by-step evaluation:

**Situation A – Empty Response or Contains Only First-Step Plan:**
- In this case, evaluate the quality of the first-step plan by referencing the first-step tool_calls and their results in the Trajectory. Check the following dimensions in order; once a criterion is met, stop further checks and assign the corresponding score:

1. **Tool Legality Check**  
- If the first-step calls a **non-existent tool**, even if the logic is correct and the plan seems reasonable, it is considered a critical error. Ignore optional prefixes when comparing with the tool library.  
- **Score: 0**

2. **Core Intent Deviation Check**  
- Off-topic, missing key information, misunderstanding, or passing inaccurate tool parameters / wrong defaults.  
- If the first-step plan deviates from the user’s Query (e.g., mixing up time, location, task type, or calling irrelevant tools), even with correct tool existence and format, it is considered failing to meet basic intent.  
- **Score: 0**

3. **Preliminary Core Intent Satisfaction Check**  
- If the first-step correctly identifies the **core intent** of the user Query (e.g., querying a specific event, retrieving information for a particular place/time, performing a calculation) and the tool parameters (time, location, keywords, etc.) match the user’s request, even if a complete answer is not yet generated, the core intent is preliminarily satisfied.  
- If tool parameters are correct but the tool fails due to external reasons, the plan is still considered preliminarily satisfying the intent.  
- **Score: 1**

> **Additional Notes:**  
> - “Empty Response” refers to output being empty or a placeholder (e.g., “Processing…”).  
> - “Only first-step plan” means the model only outputs a tool call plan (e.g., JSON-formatted tool_call) without generating a natural language answer.  
> - Core intent should be extracted from the **main objective** of the user Query, ignoring secondary modifiers or examples.  
> - If key entities such as time/location are not explicitly provided, the model may reasonably default or clarify but must not fabricate conflicting information.

**Situation B – Contains Complete Plan:**
- Proceed to Step 2 for detailed evaluation.

---

### Step 2: Evaluate Complete Plan (Situation B)

Check the following in order; stop once a criterion is met:

- **Tool Validity**: If the plan calls a tool not defined or absent in the tool library, even if logical and reasonable, it is a critical error. **Score = 0**.
- **Execution Exception Exemption**: If the plan logic is reasonable, tool selection appropriate, and aligned with user Query, but tool calls in the trajectory fail due to **external uncontrollable factors** (e.g., API downtime, network timeout, auth failure, quota exceeded), and failure is clearly environmental rather than model error, **score still 1**.
- **Plan Completeness (Partially Satisfying)**: If the plan appears complete but trajectory execution exposes any of the following, assign **0.5**:
    -- Missing key steps required to fulfill the user Query (e.g., must get location first but only check weather).  
    -- Tool call sequence significantly differs from the plan description (e.g., plan says call A then B, but trajectory skips A or sequence error affecting result).  
    -- Tool parameter, dependency, or usage violations (e.g., missing required params, wrong input types).  
    -- Meaningless repetition, redundant operations, or no reasonable fallback after tool failure.  
- **Plan Completeness (Fully Satisfying)**: If the plan clearly and completely covers all core user Query requirements, and the trajectory tool calls strictly follow the plan (correct sequence, parameters, no redundancy or omission), even if tools fail due to external factors, assign **1**.

---

### Output Format
- Return a JSON object:

```json
{
    "add_info_plan": "The first-round plan description supplemented with Trajectory information",
    "thought": "Concise reasoning: 1)First Response completeness check 2)Applicable scoring condition 3)Reasoning for score",
    "score": "... final score 0 / 0.5 / 1"
}
````

* Your output must strictly follow this format; no extra content is allowed.
* The `thought` must be accurate and concise.

TOOLS:
{tools}

Query:
{query}

First Response:
{query_plan}

Trajectory:
{trajectory}
""".strip()

