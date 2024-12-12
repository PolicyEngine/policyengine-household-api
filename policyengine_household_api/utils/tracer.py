from policyengine_core import Simulation
import re

def generate_tracer_output(simulation: Simulation) -> list:
    # Verify that tracing is enabled
    if simulation.trace != True:
        raise ValueError("Tracing must be enabled in order to generate output.")

    # Get tracer output after calculations have completed
    tracer_output = simulation.tracer.computation_log
    log_lines = tracer_output.lines(aggregate=False, max_depth=10)
    return log_lines

def parse_tracer_output(tracer_output: list[str], target_variable: str) -> list[str]:
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
    pattern: re.Pattern[str] = rf"^(\s*)({re.escape(target_variable)})\s*(?:<[^>]*>)?\s*"

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