from policyengine_core import Simulation


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
