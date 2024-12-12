from policyengine_core import Simulation
from typing import Generator
import json
import os
import anthropic
import re


def generate_tracer_output(simulation: Simulation) -> list:
    # Verify that tracing is enabled
    if simulation.trace != True:
        raise ValueError(
            "Tracing must be enabled in order to generate output."
        )

    # Get tracer output after calculations have completed
    tracer_output = simulation.tracer.computation_log
    log_lines = tracer_output.lines(aggregate=False, max_depth=10)
    return log_lines


def parse_tracer_output(
    tracer_output: list[str], target_variable: str
) -> list[str]:
    """
    Given a household tracer output, parse its contents to find
    the calculation tree for a specific variable.

    Args:
        tracer_output (list[str]): The tracer output to parse.
        target_variable (str): The variable to find in the tracer output.

    Returns:
        list[str]: The calculation tree excerpt for the target variable.
    """
    result: list[str] = []
    target_indent: int | None = None
    capturing: bool = False

    # Create a regex pattern to match the exact variable name
    # This will match the variable name followed by optional whitespace,
    # then optional angle brackets with any content, then optional whitespace
    pattern: re.Pattern[str] = (
        rf"^(\s*)({re.escape(target_variable)})\s*(?:<[^>]*>)?\s*"
    )

    for line in tracer_output:
        # Count leading spaces to determine indentation level
        indent = len(line) - len(line.strip())

        # Check if this line matches our target variable
        match: bool = re.match(pattern, line)
        if match and not capturing:
            target_indent = indent
            capturing = True
            result.append(line)
        elif capturing:
            # Stop capturing if we encounter a line with less indentation than the target
            if indent <= target_indent:
                break
            # Capture dependencies (lines with greater indentation)
            result.append(line)

    return result


prompt_template = f"""{anthropic.HUMAN_PROMPT} You are an AI assistant explaining US policy calculations. 
  The user has run a simulation for the variable '{{variable}}'.
  Here's the tracer output:
  {{tracer_segment}}
      
  Please explain this result in simple terms. Your explanation should:
  1. Briefly describe what {{variable}} is.
  2. Explain the main factors that led to this result.
  3. Mention any key thresholds or rules that affected the calculation.
  4. If relevant, suggest how changes in input might affect this result.
      
  Keep your explanation concise but informative, suitable for a general audience. Do not start with phrases like "Certainly!" or "Here's an explanation. It will be rendered as markdown, so preface $ with \.
  
  {anthropic.AI_PROMPT}"""


def trigger_ai_analysis(prompt: str) -> Generator[str, None, None]:
    """
    Pass a prompt to Claude for analysis and return the response in streaming-
    formatted chunks.

    Args:
        prompt (str): The prompt to pass to Claude for analysis.

    Returns:
        Generator[str, None, None]: A generator that yields response chunks.
    """

    # Configure a Claude client
    claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def generate():
        """
        Generate response chunks from Claude.
        """
        chunk_size: int = 5
        buffer: str = ""

        with claude_client.messages.stream(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1500,
            temperature=0.0,
            system="Respond with a historical quote",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for item in stream.text_stream:
                buffer += item
                while len(buffer) >= chunk_size:
                    chunk = buffer[:chunk_size]
                    buffer = buffer[chunk_size:]
                    yield json.dumps({"response": chunk}) + "\n"

        if buffer:
            yield json.dumps({"response": buffer}) + "\n"

    return generate()
