import datetime as dt

from app.agents.extract_rfq import RFQFields
from app.agents.llm import LLMResponse, ScriptedLLM
from app.agents.orchestrator import RFQOrchestrator


class RecordingRegistry:
    def __init__(self):
        self.calls = []

    def declarations(self, names):
        return []

    def call(self, name, args, forced=False):
        self.calls.append((name, args))
        return {"error": "not allowed"}


def test_llm_tool_calls_are_bounded_independently_of_model_turns():
    registry = RecordingRegistry()
    llm = ScriptedLLM([
        LLMResponse(
            function_calls=[{"name": f"unknown_{i}", "args": {}} for i in range(20)],
            raw_parts=[],
        )
    ])
    orchestrator = RFQOrchestrator(registry, llm=llm, max_steps=1)
    fields = RFQFields(rfq_date=dt.date(2026, 11, 25))

    orchestrator._llm_plan(fields)

    assert len(registry.calls) == orchestrator.max_tool_calls == 4
