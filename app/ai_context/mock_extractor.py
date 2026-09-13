"""Deterministic `ContextExtractor` for tests and offline use - never
calls a network. Mirrors `ClaudeContextExtractor`'s exact unknown-
fallback behavior (via the shared `ok_result`/`unknown_result`
helpers) so a test written against the mock exercises the same
contract a caller sees against the real extractor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai_context.extractor import ContextExtractionRequest, ok_result, unknown_result
from app.ai_context.schema import AIContextResult, LLMContextOutput


@dataclass
class MockContextExtractor:
    """`responses` maps `external_id` -> either a canned
    `LLMContextOutput` (success) or an `Exception` instance (simulated
    failure). An `external_id` with no configured response also
    produces an explicit unknown result - this mock never guesses a
    default success.
    """

    model_name: str = "mock"
    model_version: str = "0.0.0"
    responses: dict[str, LLMContextOutput | Exception] = field(default_factory=dict)

    def extract(self, request: ContextExtractionRequest) -> AIContextResult:
        outcome = self.responses.get(request.external_id)
        if outcome is None:
            return unknown_result(
                request=request,
                model_name=self.model_name,
                model_version=self.model_version,
                parse_error=f"no mock response configured for external_id={request.external_id!r}",
            )
        if isinstance(outcome, Exception):
            return unknown_result(
                request=request,
                model_name=self.model_name,
                model_version=self.model_version,
                parse_error=str(outcome),
            )
        return ok_result(
            request=request,
            model_name=self.model_name,
            model_version=self.model_version,
            output=outcome,
        )
