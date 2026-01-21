## Mission
Construct a **Tool Invocation Query** derived from the supplied MCP Server and its tool specifications.

## Aim
Examine the supplied MCP Server and its accessible tools, then formulate a plausible user query that would inherently necessitate utilizing **{NUM_TOOLS} tools** from this MCP Server for complete resolution.

## Instructions

### Query Authenticity
- Formulate queries representing practical situations where users would need to engage with the MCP Server's tools
- The query should appear natural and credible, resembling an actual request from someone genuinely requiring task completion
- Account for typical applications, challenges, or processes that would demand the capabilities offered by the MCP Server's tools

### Tool Selection
- Concentrate on **{NUM_TOOLS} tools** from the MCP Server that would collaborate to address the query
- The query should demand a progression or blend of tool invocations for complete resolution
- Select tools based on their complementary nature and logical workflow construction
- Consider each tool's specification and function when designing the query requiring multiple operations

### Query Sophistication
- Formulate queries with sufficient sophistication to justify employing {NUM_TOOLS} tools
- The query should encompass multiple facets or demand several operations for resolution
- Incorporate pertinent context or limitations that necessitate multi-tool engagement
- Exclude explicit tool names from the query
- Verify the query cannot be plausibly addressed using only a single tool

### Intention
- The user's query must express a desire for the model to execute a task, not merely explain how to perform it.
- The query should request task completion rather than instructional guidance.

### Response Structure
Your response should encompass:
1. **Tool Examination**: Concisely examine the MCP Server's accessible tools and their principal capabilities.
2. **Target Tools**: The particular tool names from the MCP Server that should collaborate to address this query, in their probable invocation sequence.
3. **Query**: A lucid, plausible user query demanding multiple tool engagement. The query should match the language of the MCP Server's description.

## MCP Server Description
{MCP_SERVER_NAME}: {MCP_SERVER_DESCRIPTION}

Available Tools:
{TOOL_LIST}

## Deliverable
Verify your query demands precisely {NUM_TOOLS} tools for complete resolution. Deliver your response using the following XML structure:

<response>
  <server_analysis>
    <!-- Concisely examine the MCP Server's accessible tools and their principal capabilities. -->
  </server_analysis>
  <target_tools>
    <!-- The particular tool names from the MCP Server that should collaborate to address this query, enumerated in sequence. e.g., <tool>create_twitter_post</tool> <tool>get_last_tweet</tool> -->
  </target_tools>
  <question>
    <!-- A lucid, plausible user query demanding multiple tool engagement. -->
  </question>
</response></output>