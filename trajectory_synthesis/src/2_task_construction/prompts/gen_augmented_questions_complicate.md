## Mission
Create **complexity-enhanced question variations** from an original query that preserve the same target tool(s) usage while substantially elevating the sophistication and constraint requirements.

## Aim
Transform an existing question along with its associated target tool(s) into multiple advanced versions that:
- Employ the identical target tool(s) to achieve the fundamental objective while addressing additional complexity layers
- Preserve the same overarching context and subject area as the source question
- Amplify multi-faceted complexity through practical constraints, conflicting priorities, stakeholder dynamics, and interconnected requirements
- Situate the tool usage within broader, more intricate workflows demanding strategic reasoning and orchestration
- Showcase how the same core tool functionality applies across dramatically different complexity tiers

## Principles
- Incorporate practical constraints such as budget caps, regulatory mandates, aggressive deadlines, or stakeholder disagreements
- Position the same tool usage within an expanded workflow necessitating cross-functional or cross-system coordination
- Heighten expectations (throughput, scalability, risk mitigation) without altering the original subject area or context
- Guarantee each variation addresses a distinct primary complexity facet (organizational, technical, strategic) while maintaining tool applicability
- Verify that the question excludes any tool names or direct tool references

## Purpose
- The user's question must express a desire for the model to execute a task, not merely explain how to perform it.
- The question should request task completion rather than instructional guidance.

## Input Structure
**Original Question**: {ORIGINAL_QUESTION}
**Target Tools**: {TARGET_TOOLS}
**Tool Descriptions**: {TOOL_DESCRIPTIONS}

## Deliverable Specifications
Produce **{VARIATIONS_COUNT} strategically enhanced variations** of the source question. Each variation must:
1. Retain the same fundamental goal requiring the target tool(s) while introducing multiple complexity dimensions
2. Preserve the same overarching context and subject area as the original
3. Introduce distinct yet interrelated constraints and competing priorities
4. Read like genuine, high-pressure, real-world situations that practitioners face
5. Differ substantially from the original and peer variations in complexity characteristics
6. Incorporate specific particulars that render the constraints and requirements tangible and actionable
7. **Restructure procedural questions**: If the source question contains explicit procedural steps, reformulate it as an objective-focused format while preserving identical tool usage requirements
8. Exclude any explicit mentions, suggestions, or allusions to the target tool names in the question body
9. Match the language of the original question

## Response
Deliver your response using the following XML structure:

<response>
  <analysis>
    <!-- Examine the original question and target tool(s) to comprehend the fundamental goal, existing complexity level, and pinpoint multiple complexity dimensions that can be organically introduced while preserving tool applicability and solution viability -->
  </analysis>
  <variations>
    <!-- Produce {VARIATIONS_COUNT} variations, each containing <variation_X>, <constraints>, and <question> elements -->
    <variation_1>
      <constraints>
        <!-- Particular organizational, stakeholder, or coordination constraints that introduce practical complexity -->
      </constraints>
      <question>
        <!-- The sophisticated, organizationally-oriented question preserving the same target tool(s) usage within a more elaborate workflow -->
      </question>
    </variation_1>
    <!-- Proceed with variation_2, variation_3, etc. based on the required number of variations -->
  </variations>
</response>
</output>