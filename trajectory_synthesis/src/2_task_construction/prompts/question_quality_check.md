## Assignment
Perform a **Query Quality Evaluation** of a tool usage query across four fundamental dimensions to verify it satisfies rigorous standards for authentic tool utilization scenarios.

## Goal
Examine the supplied tool usage query and evaluate its quality across four principal dimensions:
1. **Tool Selection Difficulty** - The challenge level in determining which tools to employ given all accessible tools
2. **Tool Selection Uniqueness** - The distinctiveness and necessity of the chosen tools for this particular task given all accessible tools
3. **Query Quality** - Overall precision, specificity, and effectiveness
4. **Scenario Realism** - The authenticity and credibility of the described scenario

## Evaluation Standards

### 1. Tool Selection Difficulty
**Evaluation Focus**: The challenge level for a user to identify which particular tools are required to address this query.

**Rating Scale**:
- **very easy**: Query explicitly references tool names or renders tool selection self-evident
- **easy**: Tool selection is uncomplicated with evident indicators
- **medium**: Demands some deliberation but tool requirements are reasonably apparent
- **hard**: Demands meticulous analysis to identify suitable tools
- **very hard**: Demands substantial expertise and thorough reasoning to pinpoint the appropriate tools

### 2. Tool Selection Uniqueness
**Evaluation Focus**: The distinctiveness and necessity of the chosen tools for executing this particular task, and whether the task can exclusively be accomplished with these tools in the designated sequence.

**Rating Scale**:
- **not unique**: Numerous alternative tool combinations could execute the same task with equal effectiveness
- **somewhat unique**: Some alternative methods exist, but chosen tools provide certain benefits
- **moderately unique**: Chosen tools are aptly suited, with restricted alternative methods
- **quite unique**: Chosen tools are especially well-aligned with the task specifications
- **highly unique**: Task can exclusively be executed effectively with these particular tools in this sequence

### 3. Query Quality
**Evaluation Focus**: Overall caliber, precision, and effectiveness of the query as an authentic user request.

**Rating Scale**:
- **very poor**: Ambiguous, vague, or inadequately constructed query
- **poor**: Some precision deficiencies, lacking crucial context
- **average**: Precise and comprehensible, but could benefit from greater specificity or engagement
- **good**: Well-structured, precise, specific, and authentic
- **excellent**: Exceptionally precise, thorough, compelling, and expertly composed

### 4. Scenario Realism
**Evaluation Focus**: The authenticity, credibility, and true-to-life nature of the described scenario.

**Rating Scale**:
- **unrealistic**: Synthetic, contrived, or implausible scenario
- **somewhat unrealistic**: Contains some authentic elements but appears forced or improbable
- **moderately realistic**: Credible scenario with minor authenticity shortcomings
- **realistic**: Authentic scenario representing genuine use cases
- **highly realistic**: Completely organic, authentic scenario indistinguishable from actual user requirements

## Query Examination

### All Available Tools```
{ALL_SERVER_AND_TOOL_INFORMATION}
```

### Query Content
```
{QUESTION_CONTENT}
```

### Designated Tool for This Query
```
{INTENDED_TOOL}
```

## Deliverable Specifications

Deliver analysis with comprehensive reasoning PRECEDING scores for each of the four metrics.

## Response
Deliver your response using the following XML structure:

<response>
  <tool_selection_difficulty>
    <reasoning>
      <!-- Comprehensive explanation encompassing ambiguity level, domain expertise required, and alternative solutions given all accessible tools -->
    </reasoning>
    <rating><!-- Rating: very easy, easy, medium, hard, very hard --></rating>
  </tool_selection_difficulty>
  
  <tool_selection_uniqueness>
    <reasoning>
      <!-- Comprehensive explanation of tool necessity, sequential dependencies, and alternative tool feasibility given all accessible tools -->
    </reasoning>
    <rating><!-- Rating: not unique, somewhat unique, moderately unique, quite unique, highly unique --></rating>
  </tool_selection_uniqueness>
  
  <question_quality>
    <reasoning>
      <!-- Comprehensive explanation addressing linguistic caliber, information architecture, and actionability -->
    </reasoning>
    <rating><!-- Rating: very poor, poor, average, good, excellent --></rating>
  </question_quality>
  
  <scenario_realism>
    <reasoning>
      <!-- Comprehensive explanation of industry authenticity, workflow precision, and stakeholder conduct -->
    </reasoning>
    <rating><!-- Rating: unrealistic, somewhat unrealistic, moderately realistic, realistic, highly realistic --></rating>
  </scenario_realism>
</response> 
</output>