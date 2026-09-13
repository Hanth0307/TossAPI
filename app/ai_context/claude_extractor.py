"""Real LLM-backed `ContextExtractor`, isolated the same way
`app.research.tradingview_mcp` isolates TradingView MCP: any failure
(network, auth, rate limit, a response that doesn't validate against
`LLMContextOutput`) is caught here and turned into an explicit
`unknown` `AIContextResult` - it is never allowed to raise into a
caller, and no field is ever guessed to paper over the failure.

Uses `client.messages.parse(output_format=LLMContextOutput)` (Claude
API structured outputs) so the response is schema-validated by the SDK
itself before this module ever sees it - see ADR 0011.
"""

from __future__ import annotations

from typing import Any

from app.ai_context.extractor import ContextExtractionRequest, ok_result, unknown_result
from app.ai_context.schema import AIContextResult, LLMContextOutput
from app.core.logging import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You analyze one news article or regulatory disclosure about a public \
company for a quantitative research pipeline. Extract only the \
structured classification requested by the output schema - do not \
invent a sentiment or trading recommendation, and do not assume this \
event is tradable.

Entity linking: you are given a list of known instruments (symbol, \
exchange, name). Only set match_status="matched" and fill in \
ticker/exchange when you are confident the text refers to one of \
these specific instruments. If the text refers to a company not in \
the list, or you are not sure which listed instrument it means, use \
match_status="unmatched" or "ambiguous" and leave ticker/exchange \
unset - never guess a plausible-looking ticker.

For every field with an "unknown" option, use it whenever the text \
does not give you enough information to decide - do not default to a \
neutral-sounding guess instead.
"""


def _build_prompt(request: ContextExtractionRequest) -> str:
    instruments_block = "\n".join(
        f"- {i.symbol} ({i.exchange}){f', {i.name}' if i.name else ''}"
        for i in request.known_instruments
    ) or "(none provided)"
    body = request.body or "(no body text)"
    return (
        f"Known instruments:\n{instruments_block}\n\n"
        f"Event kind: {request.event_kind.value}\n"
        f"Event time: {request.event_time.isoformat()}\n"
        f"Headline/title: {request.headline_or_title}\n\n"
        f"Body:\n{body}"
    )


class ClaudeContextExtractor:
    model_name = "claude"

    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self.model_version = model
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key)

    def extract(self, request: ContextExtractionRequest) -> AIContextResult:
        try:
            response = self._client.messages.parse(
                model=self.model_version,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_prompt(request)}],
                output_format=LLMContextOutput,
            )
            output = response.parsed_output
        except Exception as exc:  # intentionally broad: this is the isolation boundary
            logger.warning(
                "ai_context.claude_extractor.extraction_failed",
                extra={
                    "extra_fields": {
                        "source": request.source,
                        "external_id": request.external_id,
                        "error": str(exc),
                    }
                },
            )
            return unknown_result(
                request=request,
                model_name=self.model_name,
                model_version=self.model_version,
                parse_error=str(exc),
            )

        return ok_result(
            request=request,
            model_name=self.model_name,
            model_version=self.model_version,
            output=output,
        )
