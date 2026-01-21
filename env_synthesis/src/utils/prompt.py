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


PROMPT_VERIFY_DEPENDENCY = """

# Role

You are a professional Information Dependency Analyst. Your core capability is to accurately determine whether the References can support the construction of the Query.

# Task

Please analyze the given Query and References. You need to distinguish between referenced facts and new instructions in the Query. You must judge whether the References can accurately support the referenced facts required to construct the Query. For the construction of referenced facts, determine whether the situation is Information Missing (Insufficient), Reference Item Level Redundancy (Excessive), or Information Matched (Matched).

# Input Data

1. References / Referenced Facts:
A set of sub questions and sub answers representing the facts currently known to the system such as lists attributes and values.
2. Query / New Instruction:
The next step query or operation instruction generated based on the above reference information.

# Definitions

Please strictly follow the definitions below to judge whether the reference information can support the referenced facts in the Query.

1. Information Missing (Insufficient)

* Judgment Criteria: If the key entities such as locations or specific properties attributes such as area or total price or constraints contained in the Query cannot be found in the References then return a score of 0.
* Core Logic: It is impossible to extract all key elements required by the Query from the References.

2. Reference Item Level Redundancy (Excessive)

* Judgment Criteria: The reference information consists of a series of sub questions and sub answers. If there exists at least one pair of sub question and sub answer whose entire information has no contribution at all to the construction of the Query then return a score of 0.

* Judgment Scope: All sub questions and sub answers are considered as a whole. If any pair is completely useless for constructing the Query it is considered redundant.

* Example 1
    References list four residential communities
    Hummingbird Garden KeYu Community KeYuan Community Zhongguancun Software Park Community
    The Query only uses three of them. The fourth Zhongguancun Software Park Community is not used in the Query but the References are still useful for constructing the Query. Therefore it is not redundant and returns a score of 1.

3. Information Matched (Matched)

* Judgment Criteria: The References exactly cover all key information required by the Query and do not contain any irrelevant extra items. Return a score of 1.

# Few Shot Examples

Example 1
Query
For a 50 square meter apartment in Puxi with a total price of 7.5 million and a 90 square meter apartment in Zhangjiang with a total price of 7.2 million what are their rental yields
References

* step 1 query Query a 50 square meter apartment in Lujiazui -> step 1 answer Lujiazui area
* step 2 query Query a 90 square meter apartment in Zhangjiang -> step 2 answer Zhangjiang area
Analysis
The Query asks about Puxi but the References provide information about Lujiazui. The key entity Puxi in the Query is missing from the reference information.
Result
Information Missing

Example 2
Query
For a 50 square meter apartment in Lujiazui with a total price of 7.5 million what is the rental yield
References

* step 1 query Query a 50 square meter apartment in Lujiazui -> step 1 answer Lujiazui area
* step 2 query Query a 90 square meter apartment in Zhangjiang -> step 2 answer Zhangjiang area
Analysis
The Query only requires information about Lujiazui but the step 2 query and answer in the References have no effect on constructing the Query.
Result
Reference Item Level Redundancy

Example 3
Query
For a 50 square meter apartment in Lujiazui with a total price of 7.5 million and a 90 square meter apartment in Zhangjiang with a total price of 7.2 million what are their rental yields
References

* step 1 query Query a 50 square meter apartment in Lujiazui -> step 1 answer Lujiazui area
* step 2 query Query a 90 square meter apartment in Zhangjiang -> step 2 answer Zhangjiang area
Analysis
Both entities required by the Query are supported by the References and there are no extra irrelevant items.
Result
Information Matched

# Output Format

First clearly identify the new instruction and the referenced facts in the Query. Then output only a JSON formatted result including the status and a brief reason.

{
"score": 0 or 1 only
"status": "Information Missing" or "Reference Item Level Redundancy" or "Information Matched"
"reason": "Brief explanation of the judgment pointing out the specific missing or redundant entities or attributes"
"New Instruction": ...
"Referenced Facts": ...
}

---

# Current Task

References
DEPENDENCY

Query
QUERY

Output
Please output only one JSON in the following format

```json
{
"score": 0 or 1 only  
"reason": ...  
"status": "Information Missing" or "Reference Item Level Redundancy" or "Information Matched"  
"New Instruction": ...  
"Referenced Facts": ...  
}
```
""".strip()


PROMPT_VERIFY_ATOMICITY = """
You are a data quality validator for datasets involving the decomposition of complex problems.
Your task is to evaluate the quality of the process of decomposing a main question into sub-questions.

Input Data:
Main Question: {MAIN_QUESTION}
Final Answer: {FINAL_ANSWER}
Decomposition Trace: {DECOMPOSITION_TRACE}

### Evaluation Criteria

#### 1. Atomicity

A sub-question is considered "atomic" if and only if it simultaneously satisfies all of the following three necessary conditions:

- Independence & Orthogonality  
The sub-question has no semantic or informational overlap with other sub-questions and can be understood and processed independently.

- Single-Task Focus  
The sub-question corresponds to exactly one clear and specific information need, computational objective, or decision point. Its formulation does not mix multiple purposes (e.g., explaining a concept while performing a calculation), nor does it implicitly contain multiple logical steps or judgment layers.

- Tool-Verifiability  
The answer to the sub-question can be directly obtained, computed, or verified by invoking a single external tool (e.g., search engine, structured database query, mathematical solver, specialized API, or code execution environment), without requiring manual integration of multiple sources or multi-step reasoning.

> Decision Rule: If any of the above conditions is not satisfied, the sub-question does not possess atomicity.

- For the final sub-question that is summarizing in nature and does not require results from external tools, atomicity is not required.
---

## Output Format:

Return a JSON object where each key is the `_uuid` of a sub-question, and the value is an object containing the following fields:

- "is_atomic": 1 or 0
- "reason_atomic": Detailed explanation.

Output only strictly valid JSON content. Do not wrap the output in Markdown format.
""".strip()


PROMPT_VERIFY_FORCED_SERIALIZATION = """
You are a rigorous reviewer responsible for determining whether the decomposition of tool calls exhibits forced serialization.

[Definition of Forced Serialization]
Forced serialization occurs when tools that could have been executed in parallel (i.e., they are independent or only share already-known upstream information) are deliberately split into multiple sequential steps in order to inflate hops or layers, causing sub-questions that should have been parallel at the same level to be incorrectly placed into later hops.

[Decision Rules]
- Assign a score of 0 (forced serialization detected, problematic) only when it is clear that steps which are obviously parallelizable have been split across multiple hops.
- Focus on cases where same-source information queries or independent sub-queries are unnecessarily chained via dependency links, or where is_parallel=false is set without any real data dependency.
- If evidence is insufficient or the situation is uncertain, always return 1 (no forced serialization detected, not problematic).

[Output Requirements]
Output JSON only, with the following object structure:
```json
{{
"score": 0 or 1,   # 0 indicates forced serialization exists (problematic), 1 indicates none or uncertainty (not problematic)
"reasoning": "Brief explanation of the decision, citing relevant step IDs",
"problematic_steps": []  # If forced serialization exists, list all step IDs involved (e.g., [3, 4, 5]); otherwise return an empty list []
}}
```
Do not output any text other than the JSON.

[Trajectory to Be Evaluated]
{traj_text}
""".strip()


PROMPT_VERIFY_SUBQA_COMPLETENESS = """
You are a professional expert in evaluating the quality of question decomposition. Your core task is to assess whether the combination of all sub-questions **fully covers all requirements of the main question (main_question)**, with no missing issues that need to be addressed.

### Input Description
1. **main_question**: The user's original main question, containing the complete set of requirements that must ultimately be answered.
2. **final_answer**: The final answer to the main question.
3. **decomposition_trace**: The sequence of decomposed sub-questions, ordered by hop_level, containing detailed information for each sub-question.
- _uuid: Unique identifier of the sub-question  
- hop_level: The level of the sub-question in the dependency chain  
- sub_question: The content of the sub-question  
- is_parallel: Whether the sub-question is parallel  
- dependency: List of dependent sub-question UUIDs  
- sub_answer: The answer to the sub-question  

### Evaluation Task
You need to determine: **Do all sub-questions in the decomposition_trace, when combined, fully cover all the requirements of the main_question? Are there any required issues that were not handled?**

### Evaluation Logic

**Step 1: Extract all requirements from the main question**
- Carefully analyze the main_question and list **all sub-goals and requirements** it contains.
- A main question may include multiple types of requirements, such as:
- Retrieving certain information  
- Verifying a condition  
- Computing a result  
- Comparing multiple options  
- Aggregating multiple data points  
- Explicitly list each requirement to form a complete requirement checklist.

**Step 2: Check sub-question coverage**
- Examine each requirement in the checklist and determine whether there is a corresponding sub-question in the decomposition_trace that handles it.
- For each requirement:
- If it is directly or indirectly handled by one or more sub-questions, mark it as "covered"
- If no sub-question handles it, mark it as "missing"
- Notes:
- Some requirements may need to be satisfied jointly by multiple sub-questions
- Some sub-questions may satisfy multiple requirements
- Consider the dependency relationships and the combined effect of sub-questions

**Step 3: Determine completeness**
- Check whether all requirements of the main question are covered:
1. **Fully covered**: All requirements are handled, with no omissions  
2. **Partially missing**: Some requirements are not handled by any sub-question  
3. **Answer validation**: Use the final_answer as supporting evidence to judge whether it can be derived from the combination of sub-question answers  

**Scoring Criteria**
- **Score = 1**: The combination of sub-questions fully covers all requirements of the main question, with no omissions  
- **Score = 0**: The sub-question combination fails to fully cover the main question, including any of the following cases:
- A requirement explicitly stated in the main question is not handled by any sub-question
- Missing critical intermediate steps that prevent deriving the final answer
- A required dimension of information in the main question is completely absent
- Although a final answer exists, necessary verification or validation steps are missing in the sub-questions

### Output Format Requirements

Return a JSON object in the following format:
```json
{{
"main_question_requirements": [
    "Requirement 1: ...",
    "Requirement 2: ...",
    "Requirement 3: ..."
],
"coverage_analysis": {{
    "covered_requirements": [
    {{
        "requirement": "Requirement 1",
        "covered_by_uuids": [1, 3, 5],
        "explanation": "How these sub-questions cover this requirement"
    }}
    ],
    "missing_requirements": [
    {{
        "requirement": "Requirement X",
        "explanation": "Why this requirement is not covered"
    }}
    ]
}},
    "thought": "Detailed analysis explaining whether the combination of sub-questions fully covers the main question",
    "score": 0 or 1
}}
```

You must strictly follow the above format and should not return any other content.

### Input Data

Main Question:
{main_question}

Final Answer:
{final_answer}

Decomposition Trace:
{decomposition_trace}
""".strip()


PROMPT_CHECK_TOOL_NECESSITY = """
# Role
You are a senior Tool-Use data auditing expert. Your task is to review the given "Decomposition Trace" and determine for each sub-question whether it requires calling **external tools** or can be solved using **internal reasoning** based on the context.

# Input Data
Please make your judgment based on the following input data:
1. **Main Question**: {{main_question}}
2. **Decomposition Trace**: {{decomposition_trace}}

# Task
You need to determine for each sub-question whether calling an external tool is necessary, and provide reasoning:
1. **Must call external tools**:
- **Requires external information**: This step needs information not present in the current context (e.g., querying databases, searching online in real time, accessing private data) or sending requests to external systems.
- **Insufficient information**:
    - The context only provides **summaries or statistical overviews** (e.g., "found N items...") or **truncated lists** (e.g., "the top 5 items are..."), but this step requires the full dataset or omitted data.
- **Specialized or complex computations**:
    - Even if input data is known, tools are required to ensure accuracy.
    - **Precise numerical operations**: All floating-point operations (division, percentage, growth rate, ratios), integer multiplication and division, and large-number calculations.
    - **Statistical and multi-step calculations**: Calculating mean/median/variance, cumulative operations over multiple items (>3), multi-layer numerical derivations.
    - **Domain-specific calculations**: Involving finance (interest/tax/installments), engineering (unit conversions), science, real estate, education, healthcare, and other specialized fields.
- **Large-scale data processing**: Requires sorting, filtering, or performing set operations on large datasets.

2. **Can be solved with internal reasoning**:
- **Simple logical processing**:
    - Filtering, sorting, or matching a **small amount** of explicitly listed data.
    - Set operations (intersection/union), text extraction and reorganization, format conversion, etc.
    - **Subjective qualitative analysis**: Summarizing, recommending, or evaluating based on **already calculated** data metrics (e.g., "analyze trends based on the above growth data", "recommend the most cost-effective option").
- **Simple calculations**:
    - Basic integer addition and subtraction, small-value comparisons.
    - All floating-point operations require external tools.

# Output Format
Please output **only a JSON list**, without any additional explanatory text. Each item must include:
1. **tool_necessity**: Whether an external tool is required
2. **reason**: Reasoning, explicitly stating whether it "requires calling external tools" or "can be solved with internal reasoning"

Format example:
```json
[
{
    "_uuid": 1,
    "tool_necessity": true,
    "reason": "..."
},        
...
{
    "_uuid": 5,
    "tool_necessity": false,
    "reason": "..."
}
]
""".strip()


PROMPT_MERGE_INTENT_AGGREGATION = """
# Role
You are a senior large-model tool architect and algorithm engineer. Your core expertise lies in **atomic-level semantic abstraction** and API design.

# Goal
You will receive a series of question–answer pairs. Your goal is to analyze the **underlying logical patterns** of these questions and cluster those that can be solved by the **same parameterized atomic function**.

# Criteria for "Homogeneous Clusters"
A group of questions can be classified into the same cluster only if **all** of the following core conditions are met:

1. **Logical Isomorphism**:
    * The problem-solving steps are identical.
    * The required data source types are identical (e.g., all query a database, all perform mathematical computation, or all call a weather API).
    * **Attribute parameterization is forbidden**: function parameters may only be used to locate entities, not to select fields.
    * Each function must follow the single-responsibility principle.
    * *Counterexample*: "What is the weather in Beijing?" and "What is the population of Beijing?" are both queries, but rely on different data sources and are therefore **not** homogeneous.

2. **Algorithmic Isomorphism**:
    * The **core predicate** or **mathematical operator** of the questions must be identical.
    * **Mathematical operations**: for computational problems, addition, subtraction, multiplication, and division are distinct atomic operations and must be clustered separately.
    * **Counterexample**: Do not create a generic "mathematical computation" category. This is incorrect. You must split it into categories such as "multiplication computation", "subtraction computation", etc.

3. **Consistent Argument Structure**:
    * The set of **core required parameters** must be identical across the questions.
    * *Decision criterion*: whether a function `f(x, y)` can be written such that question A is `f(a1, b1)` and question B is `f(a2, b2)`, where `a1/a2` and `b1/b2` are different values of the **same parameter types**.
    * *Counterexample*: "Query the price of a three-bedroom apartment" depends on `Room_Type`; "Query last year's price" depends on `Date`. Although both query prices, the parameter types differ and thus cannot be grouped together.

4. **Consistent Return Schema**:
    * The structure of the answers (the `answer` field) should be similar (e.g., all return a scalar value, or all return a list).

# Input Data Structure
The input questions are provided in JSON format:
```json
{
    "_uuid": "...",
    "question": "...",
    "answer": "...",
    "function_implementation": {...}
}
```

# Output Rules
1. **Strict JSON Only**: Output only a JSON object. Do not include any explanatory text outside of the JSON (including Markdown code block markers such as ```json). UUIDs must correspond to the input UUIDs and be of integer type.
2. **Exhaustiveness**: Ensure that every UUID in the input is assigned to a cluster. If a question is unique, it should form its own cluster.
3. **Reasoning**: In the `reason` field, describe not only the intent but also the **shared parameters** that were extracted (e.g., "all extract the city name as a parameter").

# Output Format Example
```json
{
    "clusters": [
        {
            "intent_summary": "Query real-time weather for a specific city",
            "_uuids": [1, 3],
            "reason": "Identical logic, all require calling a weather API, with [City_Name] as the variable parameter."
        },
        {
            "intent_summary": "Compute loan interest",
            "_uuids": [2],
            "reason": "Involves financial computation logic and is heterogeneous from query-type problems."
        }
    ]
}
```

# Input Questions
{{questions}}
""".strip()


PROMPT_MERGE_TOOLS_CODE = """
You are a senior Python tool-function maintenance engineer. You are given a piece of "existing tool function code" along with multiple QA test cases.

{intent_line}

## Task
Without changing the **core logic** (parameter validation, control flow, return structure, algorithmic steps), you must modify **only** the parts related to **data simulation / mock data / static example data** in the code, based on the QA test cases, so that each test case invocation returns an output that **contains the corresponding "expected answer" as a substring**.

## Strict Constraints (Very Important)
1. **Do not modify the function name, function signature, parameter semantics, or main branch structure**  
(only adjustments to simulated static data, lookup tables, example records, etc. are allowed)
2. Do not introduce network requests, file I/O, randomness, or any other unstable behavior
3. The output must be **one complete Python function**, with no explanations and no markdown
4. The function must be compatible with **all** test cases; if mock data relies on input-based lookups or matching, make sure to include **all required entries** for every test case

## Current Function Signature (for verification only, must not be changed)
{fn_hint}

## QA Test Cases
{qa_section}

## Existing Code
{base_code}

Please directly output the modified complete function code:
""".strip()


PROMPT_MERGE_TOOL_CALL_GEN = """
You are a test-case generator. Given a Python tool function code and multiple QA pairs (question/answer), generate an executable tool_call_statement (i.e., a Python expression string that calls the function) for each QA, to be used for subsequent sandbox execution and validation.

## Constraints
1. Each tool_call_statement must be a **single-line** Python expression, in the form: {fn_name}(...)
2. Only parameter names from the function signature are allowed (prefer keyword arguments)
3. Do not include print statements, assignments, multiple statements, backticks, or markdown
4. If some parameters cannot be inferred from the question, use reasonable default values, but the expression must be syntactically valid
5. The goal is to make the function output contain the answer as much as possible (the answer will later be used as a substring for validation)

## Function Signature (for parameter-name constraints only)
{fn_name}({arg_list})

## QA List
{qa_section}

## Code
{code}

## Output Format
Output only a JSON array. Each element should contain:
{{"_uuid": <unchanged>, "tool_call_statement": "<call expression string>"}}
""".strip()


PROMPT_TOOL_DOCUMENT_GENERATION = \
"""
Please determine the most suitable tool to address the given problem and provide a thorough analysis of the tool’s design. The final output must be formatted as JSON and strictly adhere to the specified structure.

## Procedure

1. **Problem Analysis**  
   Comprehend the problem statement and identify the type of information needed to resolve it.

2. **Evaluation of Supplementary Information**  
   Examine the relationship between the question and any additional information provided:  
   - If the question lacks required details, extract the missing information from the supplementary content.  
   - If the question is already complete, disregard the supplementary information.

3. **Tool Design**  
   Propose a tool capable of solving the problem, taking into account its complexity as well as any potential extended functionalities.

4. **Parameter Definition**  
   Specify the tool’s parameters, ensuring they are sufficiently comprehensive and adaptable to a range of similar scenarios.

5. **Output Generation**  
   Construct the final response in JSON format, incorporating both the design analysis and the tool schema.

## Additional Notes

- “Additional Information” may contain relevant supporting details. If it is marked as `None`, no supplementary information is available. Such information may also be redundant.
- The designed tool should be flexible enough to handle related or similar queries.
- Edge cases should be considered during the design process.
- To avoid leaking information from the original question, example values used in the tool parameters must not replicate any content from the query; instead, use alternative values of the same data type.

## Output Requirements

The response **must consist solely of a JSON object**, with no extraneous content, and include the following fields:
- `"analysis"`: A comprehensive explanation of the reasoning behind the tool design.
- `"tool"`: A JSON schema describing the tool, including its name, purpose, and parameters.

## Example

**Question**: Determine whether the following customer review expresses a positive, neutral, or negative sentiment.

**Output**:
{{
    "analysis": "This problem involves identifying the emotional tone expressed in a piece of text. To solve it, a text analysis tool is required that can process natural language input and classify sentiment based on linguistic patterns and contextual cues. The tool should be designed to handle different text lengths, support multiple sentiment categories, and remain extensible for additional features such as confidence scoring or language detection.",
    "tool": {{
        "name": "sentiment_classifier",
        "description": "A text analysis tool that evaluates input text and classifies its sentiment into predefined categories such as positive, neutral, or negative.",
        "parameters": {{
            "type": "object",
            "properties": {{
                "text": {{
                    "type": "string",
                    "description": "The text content to be analyzed for sentiment."
                }},
                "language": {{
                    "type": "string",
                    "description": "The language of the input text, used to improve analysis accuracy.",
                    "default": "en"
                }},
                "granularity": {{
                    "type": "string",
                    "description": "The level of sentiment detail required for the output.",
                    "enum": ["binary", "ternary", "fine_grained"],
                    "default": "ternary"
                }},
                "include_confidence": {{
                    "type": "boolean",
                    "description": "Whether to include a confidence score along with the sentiment result.",
                    "default": false
                }}
            }},
            "required": [
                "text"
            ]
        }}
    }}
}}

**Question**: {question}

**Output**:
""".strip()


PROMPT_TOOL_DOCUMENT_COMPLEXITY_SCALING = """
Improve an existing tool design by enhancing its descriptive clarity and enriching the parameter structure, while ensuring full compatibility with its original functionality.

## Procedure

1. **Review the Existing Tool**  
   Analyze the current tool’s description and parameter definitions to gain a clear understanding of its capabilities and constraints.

2. **Determine Refinement Opportunities**  
   Identify components of the tool that could be clarified, extended, or enhanced to better address practical, real-world use cases.

3. **Enhance the Tool Description and Parameters**  
   Refine existing parameters so that each parameter value represents an objective, well-defined entity.  
   Introduce additional parameters to increase the tool’s complexity and usefulness, ensuring that all enhancements remain backward-compatible with the original functionality.

4. **Validate Compatibility**  
   Confirm that the refined tool preserves the original intent, structure, and functional behavior of the initial design.

## Output Requirements

The response **must be provided exclusively in JSON format**, with no additional content, and conform to the following structure:
- `"analysis"`: A detailed discussion of the reasoning behind the refinement decisions.
- `"refined_version"`: The refined tool definition, expressed using the same JSON Schema format as the original tool.

## Notes

- Any newly added parameters must be relevant and meaningfully improve the tool’s capabilities.
- Backward compatibility with the original tool’s design and purpose must be strictly maintained.

**Tool**:  
{tool}

**Output**:
""".strip()


PROMPT_CALL_STATEMENT = """
Analyze how a provided tool description relates to a given problem, and produce the corresponding function call that can solve the problem. All parameter values in the function call must be derived strictly from the problem statement.

## Procedure

1. **Interpret the Problem**  
   Read the problem carefully and identify the concrete inputs, constraints, and expected outcome.

2. **Inspect the Tool Description**  
   Review the given tool description to understand:
   - the function’s purpose,
   - the parameter schema (names, types, required fields),
   - any constraints implied by the description.

3. **Assess Applicability**  
   Determine whether the tool, as described, can solve the problem:
   - If it can, proceed to construct a function call.
   - If it cannot, set `"call"` to `null`.

4. **Construct the Function Call**  
   Generate a function call in the form `func(param="value")`, ensuring:
   - parameter names exactly match those defined in the tool description,
   - each parameter value is directly sourced from the problem,
   - required parameters are included, and irrelevant parameters are omitted.

## Output Requirements

Return **only** a JSON object (no additional text) using the following structure:

- `"analysis"`: A concise explanation of how the tool description maps to the problem and why it does or does not solve it.
- `"call"`: The function call formatted as `func(param="value")`, with values taken from the problem statement.
- If the tool description cannot solve the problem, return `"call": null`.

## Example

- Input Problem: "Convert 37 degrees Celsius to Fahrenheit."
- Input Tool Description: '{{"type": "function", "function": {{"name": "celsius_to_fahrenheit", "description": "Convert a temperature from Celsius to Fahrenheit.", "parameters": {{"type": "object", "properties": {{"celsius": {{"type": "number", "description": "Temperature in degrees Celsius"}}}}, "required": ["celsius"]}}}}}}'

- JSON Output:
- {{
  "analysis": "The function celsius_to_fahrenheit is explicitly designed to convert a Celsius value into Fahrenheit. The problem provides the Celsius input (37), which directly maps to the required parameter.",
  "call": "celsius_to_fahrenheit(celsius=37)"
}}

## Notes

- Use the **exact** parameter names as defined in the tool description.
- The function call must not introduce information not present in the problem statement.
- The analysis should briefly justify the applicability (or lack thereof) of the tool to the problem.

- Input Problem: {question}
- Tool Description: {tool_description}

- JSON Output:
""".strip()


PROMPT_TOOL_DEPLOYMENT = """
Implement a function in accordance with a provided tool document, a set of question–answer pairs, and a given call statement. The implementation must strictly follow the tool specification and include robust, defensive error handling.

## Procedure

1. **Review the Tool Document**  
   Carefully parse the tool document to extract the function name and the exact parameter specification (names, types, required/default values). These must be used **verbatim** in the implementation.

2. **Interpret the Question–Answer Pairs**  
   Use the pairs to infer:
   - how problem statements map to function inputs,
   - how outputs should be computed or formatted to match the expected answers.

3. **Develop the Function Implementation**  
   Implement the function such that:
   - the function call described by the call statement produces the correct result,
   - the function name matches the tool document exactly,
   - parameters are defined exactly as specified (including ordering and defaults where applicable),
   - internal logic derives outputs consistent with the question–answer pairs,
   - if any parameters have default values, ensure the function’s return value fully contains the corresponding expected answer (i.e., the answer must appear as a substring within the returned value),
   - the function can yield diverse outputs when required (simulate additional fields/return values if the tool document implies them).

4. **Add Comprehensive Error Handling**  
   Implement a reliable validation and error-reporting strategy to handle:
   - incorrect parameter types,
   - missing required parameters,
   - invalid values or out-of-range inputs,
   - any other foreseeable runtime issues.  
   Errors should result in clear, stable messages that help diagnose the issue without breaking execution.

## Output Requirements

Return **only** a JSON object (no other text) using this structure:

- `"analysis"`: A detailed explanation of the implementation approach, including design rationale for parameters, output formatting, and exception/error-handling logic.
- `"function"`: The full function implementation, including code and explanatory comments.

## Notes

- Parameter names and types must match the tool document **exactly**.
- Only Python 3 built-in libraries may be used.
- If the tool specification implies additional return values, simulate them in a way consistent with the documentation.
- Error handling should be exhaustive and anticipatory.
- Ensure that for any input `q`, the produced result is uniquely `a` (i.e., the mapping from input to expected answer must be unambiguous).

---

**Tool Document**:  
{document}

**Question–Answer Pairs**:  
{pairs}

**Call Statement**:  
{call_statement}

**Output**:
""".strip()

