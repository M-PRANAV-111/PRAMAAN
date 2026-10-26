"""The always-safe provider: reports 'not available' and never touches the network."""
from __future__ import annotations

from .types import (ClassifyRequest, ClassifyResult, ExplainRequest, ExplainResult, ExtractRequest, ExtractResult)


class NoneProvider:
    name = "none"
    model = ""

    def extract(self, req: ExtractRequest) -> ExtractResult:
        return ExtractResult(available=False, provider=self.name)

    def classify(self, req: ClassifyRequest) -> ClassifyResult:
        return ClassifyResult(available=False, provider=self.name)

    def explain(self, req: ExplainRequest) -> ExplainResult:
        return ExplainResult(available=False, provider=self.name)
