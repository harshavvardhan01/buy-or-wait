"""Accumulates model usage for the mandatory evaluation/usage_report.md."""
from collections import defaultdict


class TokenCounter:
    def __init__(self):
        self.by_model = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0,
                                             "provider": ""})

    def record(self, provider, model, input_tokens, output_tokens):
        entry = self.by_model[model]
        entry["provider"] = provider
        entry["calls"] += 1
        entry["input"] += input_tokens
        entry["output"] += output_tokens

    def totals(self):
        calls = sum(e["calls"] for e in self.by_model.values())
        inp = sum(e["input"] for e in self.by_model.values())
        out = sum(e["output"] for e in self.by_model.values())
        return calls, inp, out