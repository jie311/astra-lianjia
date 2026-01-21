## Purpose
Create **context-shifted question variations** from an original query that preserve the same target tool(s) usage and difficulty level while applying them to entirely different situations and domains.

## Target
Transform an existing question along with its associated target tool(s) into multiple versions that:
- Employ the identical target tool(s) to achieve the fundamental objective
- Preserve the exact sequence of tool operations and intended result
- Transfer the question to completely distinct contexts, situations, or subject areas
- Maintain the same difficulty level and constraint requirements as the source
- Showcase how the identical tool usage pattern transfers across varied real-world situations

## Principles
- Transpose the question to markedly different domains, user types, or circumstantial contexts while maintaining its original difficulty level
- Keep the tool operation sequence and end result uniform across all variations
- Guarantee each variation presents a plausible situation in its new context and remains solvable through identical tool operations
- Verify that the question excludes any tool names or direct tool references

## Input Structure
**Original Question**: {ORIGINAL_QUESTION}
**Target Tools**: {TARGET_TOOLS}
**Tool Descriptions**: {TOOL_DESCRIPTIONS}

### Intention
- The user's question must express a desire for the model to execute a task, not merely explain how to perform it.
- The question should request task completion rather than instructional guidance.

## Deliverable Specifications
Produce **{VARIATIONS_COUNT} context-shifted variations** of the source question. Each variation must:
1. Retain the same fundamental goal requiring the target tool(s)
2. Employ the exact same tool(s) in identical order achieving the same end result
3. Apply to an entirely different context, situation, or subject area
4. Maintain identical difficulty level and constraint requirements as the original
5. Read like a genuine, real-world situation from an alternative setting
6. Differ substantially from the original and peer variations exclusively in context
7. Exclude any explicit mentions, suggestions, or allusions to the target tool names in the question body
8. Match the language of the original question

## Response
Deliver your response using the following XML structure:

<response>
  <analysis>
    <!-- Concisely examine the original question and target tool(s) to comprehend the fundamental goal, tool usage pattern, difficulty level, and anticipated result, then determine how this can transfer across different domains while preserving operational uniformity -->
  </analysis>
  <variations>
    <!-- Produce {VARIATIONS_COUNT} variations, each containing <variation_X>, <context>, and <question> elements -->
    <variation_1>
      <context>
        <!-- Concise description of the new domain/situation introduced -->
      </context>
      <question>
        <!-- The context-shifted question preserving the same target tool(s) usage sequence, difficulty, and result but in an alternative context -->
      </question>
    </variation_1>
    <!-- Proceed with variation_2, variation_3, etc. based on the required number of variations -->
  </variations>
</response>
</output>