import anthropic

household_explainer_template = f"""{anthropic.HUMAN_PROMPT} You are an AI assistant explaining US policy calculations. 
  The user has run a simulation for the variable '{{variable}}'.
  The below is a computation tree segment for the variable '{{variable}}' 
  describing the variable and all its sub-variables, as well as each 
  variable's entity group.
  {{computation_tree_segment}}
  Here's an ordered list of the entity groups in the simulation and their
  individual entities:
  {{entity_description}}
  Note that the user is interested in the value of '{{variable}}' associated 
  with entity '{{entity}}'.
      
  Please explain this result in simple terms. Your explanation should:
  1. Briefly describe what {{variable}} is.
  2. Explain the main factors that led to this result.
  3. Mention any key thresholds or rules that affected the calculation.
  4. If relevant, suggest how changes in input might affect this result.
      
  Keep your explanation concise but informative, suitable for a general audience. Do not start with phrases like "Certainly!" or "Here's an explanation. It will be rendered as markdown, so preface $ with \.
  
  {anthropic.AI_PROMPT}"""
