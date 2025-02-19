from policyengine_core import Simulation
import anthropic
from anthropic.types import Message
import os
import json
from typing import Generator
import re

prompt_template = f"""{anthropic.HUMAN_PROMPT} You are an AI assistant explaining US policy calculations. 
  The user has run a simulation for the variable '{{variable}}'.
  Here's the tracer output:
  {{computation_tree_segment}}
  Here's an ordered list of the tax entities in the simulation:
  {{entity_description}}
  Note that the user is interested in the value associated with 
  entity '{{entity}}'.
      
  Please explain this result in simple terms. Your explanation should:
  1. Briefly describe what {{variable}} is.
  2. Explain the main factors that led to this result.
  3. Mention any key thresholds or rules that affected the calculation.
  4. If relevant, suggest how changes in input might affect this result.
      
  Keep your explanation concise but informative, suitable for a general audience. Do not start with phrases like "Certainly!" or "Here's an explanation. It will be rendered as markdown, so preface $ with \.
  
  {anthropic.AI_PROMPT}"""


def trigger_streaming_ai_analysis(prompt: str) -> Generator[str, None, None]:
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


def trigger_buffered_ai_analysis(prompt: str) -> str:
    """
    Pass a prompt to Claude for analysis and return a buffered response.

    Args:
        prompt (str): The prompt to pass to Claude for analysis.

    Returns:
        str: The response from Claude.
    """

    # Configure a Claude client
    claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Pass the prompt to Claude for analysis
    response: Message = claude_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1500,
        temperature=0.0,
        system="Respond with a historical quote",
        messages=[{"role": "user", "content": prompt}],
    )

    response_str: str = parse_string_from_claude_message(response)

    return response_str


def generate_computation_tree(simulation: Simulation) -> list[str]:
    # Verify that simulation tracing is enabled
    if simulation.trace != True:
        raise ValueError(
            "Tracing must be enabled in order to generate output."
        )

    # Get tracer output after calculations have completed
    tracer_output = simulation.tracer.computation_log
    log_lines = tracer_output.lines(aggregate=False, max_depth=10)
    return log_lines


def parse_string_from_claude_message(message: Message) -> str:
    """
    Parse a string from a Claude message.

    Args:
        message (Message): The message to parse.

    Returns:
        str: The parsed string.
    """

    # There appears to be no canonical method to do this natively
    # within Claude API; e.g., see
    # https://community.openai.com/t/message-id-for-assistant-replies/562558

    # Parse the message
    if getattr(message, "content", None) is None:
        raise ValueError("The message does not contain any content.")

    if len(message.content) == 0:
        raise ValueError("The message content is empty.")

    if getattr(message.content[0], "text", None) is None:
        raise ValueError("The message content does not contain any text.")

    return message.content[0].text


def parse_computation_tree_for_variable(
    variable: str, tree: list[str]
) -> list[str]:
    """
    Given a household computation_tree output, parse its contents to find
    the calculation tree for a specific variable.

    Args:
        variable (str): The variable to find in the computation_tree output.

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
        rf"^(\s*)({re.escape(variable)})\s*(?:<[^>]*>)?\s*"
    )

    for line in tree:
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
