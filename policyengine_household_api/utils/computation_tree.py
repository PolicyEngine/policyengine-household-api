from policyengine_core import Simulation
from policyengine_household_api.models.computation_tree import (
    EntityDescription,
)
import anthropic
from anthropic.types import Message
import os
import json
from typing import Generator, Any
import re

from policyengine_household_api.utils.config_loader import get_config_value


def trigger_streaming_ai_analysis(prompt: str) -> Generator[str, None, None] | None:
    """
    Pass a prompt to Claude for analysis and return the response in streaming-
    formatted chunks.

    Args:
        prompt (str): The prompt to pass to Claude for analysis.

    Returns:
        Generator[str, None, None]: A generator that yields response chunks.
        None: If AI is not enabled.
    """
    if not get_config_value("ai.enabled"):
        return None

    # Configure a Claude client
    claude_client = anthropic.Anthropic(api_key=get_config_value("ai.anthropic.api_key"))

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


def trigger_buffered_ai_analysis(prompt: str) -> str | None:
    """
    Pass a prompt to Claude for analysis and return a buffered response.

    Args:
        prompt (str): The prompt to pass to Claude for analysis.

    Returns:
        str: The response from Claude.
        None: If AI is not enabled.
    """
    if not get_config_value("ai.enabled"):
        return None

    # Configure a Claude client
    claude_client = anthropic.Anthropic(api_key=get_config_value("ai.anthropic.api_key"))

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


def add_entity_groups_to_computation_tree(
    country_id: str, tree: list[str], entity_description: EntityDescription
) -> list[str]:
    """
    Given a computation tree and an entity description, add entity group
    information to the tree.

    Args:
        tree (list[str]): The computation tree.
        entity_description (EntityDescription): The entity description.

    Returns:
        list[str]: The computation tree with entity group information added.
    """
    from policyengine_household_api.country import COUNTRIES

    metadata: dict[str, Any] = COUNTRIES.get(country_id).metadata["result"]

    result_tree: list[str] = []
    pattern: re.Pattern[str] = r"^\s*([a-zA-Z][a-zA-Z_0-9]*)(?=<)"

    for line in tree:
        # Parse line for variable name
        var_match: str = re.search(pattern, line)
        if var_match is None:
            raise ValueError(
                f"Could not parse variable name from line: {line}"
            )
        var_name: str = var_match.group(1).strip()

        # Look up this variable's entity_group value
        var_data = metadata["variables"].get(var_name, None)
        if var_data is None:
            raise ValueError(
                f"Variable {var_name} from computation tree not found in metadata."
            )

        var_entity = var_data.get("entity")
        if var_entity is None:
            raise ValueError(
                f"Variable {var_name} from computation tree has no entity information."
            )

        # Convert to plural because entity_description uses plural form
        entity_group = metadata["entities"].get(var_entity)["plural"]

        # Non-mutatively append entity_group to the line and save
        result_tree.append(f"{line} entity_group: {entity_group}")

    return result_tree
