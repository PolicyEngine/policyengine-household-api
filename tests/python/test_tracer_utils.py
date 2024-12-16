from policyengine_household_api.utils.tracer import parse_tracer_output

# Add tests for generate_tracer_output: would require mock Simulation


# Tests for parse_tracer_output
class TestParseTracerOutput:
    tracer_output = [
        "only_government_benefit <1500>",
        "    market_income <1000>",
        "        employment_income <1000>",
        "            main_employment_income <1000 >",
        "    non_market_income <500>",
        "        pension_income <500>",
    ]

    def test_parse_tracer_output_entire_tree(self):

        result = parse_tracer_output(
            self.tracer_output, "only_government_benefit"
        )
        assert result == self.tracer_output

    def test_parse_tracer_output_subset_1(self):

        result = parse_tracer_output(self.tracer_output, "market_income")
        assert result == self.tracer_output[1:4]

    def test_parse_tracer_output_subset_2(self):
        result = parse_tracer_output(self.tracer_output, "non_market_income")
        assert result == self.tracer_output[4:]

    def test_parse_tracer_output_no_match(self):
        result = parse_tracer_output(self.tracer_output, "income")
        assert result == []


# Tests for trigger_ai_analysis
