## Assignment
Create **persona-driven question variations** from an original query by integrating detailed user profile characteristics to enhance diversity and authenticity.

## Goal
Transform an existing question along with its associated target tool(s) into multiple personalized versions that:
- Leverage the identical target tool(s) to accomplish the fundamental objective
- Preserve the exact sequence of tool operations and intended result
- Weave in the supplied user profile details (age, profession, educational background, career history, competencies, personal interests) to craft more individualized and genuine questions
- Mirror the unique requirements, circumstances, and conversational patterns of the specified user profile
- Illustrate how individuals with varying backgrounds would phrase comparable requests

## Target User Profile
You are crafting variations for a user matching this profile:
- **Age**: {PERSONA_AGE} years old
- **Occupation**: {PERSONA_OCCUPATION}
- **Education Level**: {PERSONA_EDUCATION}
- **Professional Background**: {PERSONA_PROFESSIONAL}
- **Skills & Expertise**: {PERSONA_SKILLS}
- **Hobbies & Interests**: {PERSONA_HOBBIES}

## Purpose
- The user's question must express a desire for the model to execute a task, not merely explain how to perform it.
- The question should request task completion rather than instructional guidance.

## Directives
- Tailor the question to align with the user profile's work context, knowledge level, and manner of expression
- Integrate field-specific terminology or situations pertinent to the persona's career and passions
- Retain the identical tool usage sequence and difficulty level as the source question
- Ensure the question feels genuine for an individual with this persona's experience and requirements
- Keep the persona influence organic and unforced - the question must remain clear and executable
- Verify that the question excludes any tool names or direct tool references
- The question should resonate naturally for THIS PARTICULAR USER, accounting for their:
  - Knowledge depth and technical comprehension
  - Practical needs and application contexts
  - Communication patterns and vocabulary choices
  - Real-world limitations (time constraints, financial resources, available assets, etc.)

## Input Structure
**Original Question**: {ORIGINAL_QUESTION}
**Target Tools**: {TARGET_TOOLS}
**Tool Descriptions**: {TOOL_DESCRIPTIONS}

## Deliverable Specifications
Produce **{VARIATIONS_COUNT} persona-driven variations** of the source question. Each variation must:
1. Retain the same fundamental goal requiring the target tool(s)
2. Employ the exact same tool(s) in identical order achieving the same end result
3. Be customized according to the supplied user profile information
4. Embody the persona's work context, expertise depth, and communication approach
5. Read like a genuine question this specific user would pose
6. Differ substantially from the original through persona-influenced context and wording
7. Exclude any explicit mentions, suggestions, or allusions to the target tool names in the question body
8. Match the language of the original question

## Response
Deliver your response using the following XML structure:

<response>
  <analysis>
    <!-- Concisely examine the original question, target tool(s), and user persona to determine how the persona's background, profession, abilities, and interests can organically shape the question while maintaining identical tool usage patterns and complexity -->
  </analysis>
  <variations>
    <!-- Produce {VARIATIONS_COUNT} variations, each containing <variation_X>, <persona_context>, and <question> elements -->
    <variation_1>
      <persona_context>
        <!-- Concise explanation of how the user persona shapes this particular variation (e.g., work context, applied skills/interests, demonstrated expertise level) -->
      </persona_context>
      <question>
        <!-- The persona-enhanced question preserving the same target tool(s) usage sequence and result but tailored to the user persona -->
      </question>
    </variation_1>
    <!-- Proceed with variation_2, variation_3, etc. based on the required number of variations -->
  </variations>
</response>