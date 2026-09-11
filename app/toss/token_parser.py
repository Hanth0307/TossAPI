"""Parses the Toss OAuth token response - an isolated, swappable boundary.

**This module's field assumptions are NOT a confirmed Toss response
schema.** The official docs confirm Toss uses OAuth 2.0 Client
Credentials Grant and confirm the *request* shape
(`POST /oauth2/token`, form-encoded `grant_type`/`client_id`/
`client_secret`) - they were never shown to include an example
*response* body. `ProvisionalTokenResponseDto` below assumes the
RFC 6749 §5.1 standard response fields (`access_token`, `expires_in`)
for this grant type, because that is the specification the docs say
this endpoint implements - but "implements the OAuth2 spec" and
"returns exactly these JSON field names" are different claims, and
only the first one is confirmed. Treat this as a provisional adapter
assumption, not fact, until a real response has actually been
observed (see `TOKEN_RESPONSE_SCHEMA_VERIFIED` below).

This parsing logic is deliberately isolated from
`app.toss.auth.TossOAuthClient` behind the `TokenResponseParser`
protocol: `TossOAuthClient` calls `parser.parse(raw_body)` and knows
nothing about JSON field names. Once a real response is observed
(e.g. via an opt-in run of `tests/toss/test_integration_live.py`
against real credentials), only this file needs to change - correct
`ProvisionalTokenResponseDto`, flip `TOKEN_RESPONSE_SCHEMA_VERIFIED`
to `True`, update its docstring - `TossOAuthClient` is untouched.

Fail-closed: any response that does not match the assumed shape
(missing/mistyped `access_token`/`expires_in`) raises
`DataValidationError` rather than falling back to a default or a
partially-parsed token. The raised message never includes the raw
response body or any field value, so a token/secret that happens to
appear in an unexpected field of a malformed response can never leak
through it - see `tests/toss/test_token_parser.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.exceptions import DataValidationError

TOKEN_RESPONSE_SCHEMA_VERIFIED = False
"""Whether `ProvisionalTokenResponseDto`'s shape has actually been
observed against a real Toss token response. Flip to `True` only
alongside evidence (a real response body, e.g. from an opt-in
integration test run) - and update this module's docstring and
docs/architecture/0007-toss-api-integration.md in the same change.
"""


@dataclass(frozen=True)
class ParsedToken:
    access_token: str
    expires_in: int


class TokenResponseParser(Protocol):
    def parse(self, raw_body: bytes) -> ParsedToken: ...


class ProvisionalTokenResponseDto(BaseModel):
    """Provisional adapter assumption - NOT a confirmed Toss schema.

    See this module's docstring. `extra="ignore"` so a real response
    carrying additional fields we don't assume doesn't itself cause a
    failure - only a genuinely missing/mistyped `access_token`/
    `expires_in` does.
    """

    model_config = ConfigDict(extra="ignore")

    access_token: str
    expires_in: int


class ProvisionalTokenResponseParser:
    """Default `TokenResponseParser` - swap this, not `TossOAuthClient`,
    once the real Toss token response schema is confirmed.
    """

    def parse(self, raw_body: bytes) -> ParsedToken:
        try:
            dto = ProvisionalTokenResponseDto.model_validate_json(raw_body)
        except ValidationError as exc:
            # Deliberately not including exc's repr, the raw body, or any
            # field value in this message: a malformed response could
            # coincidentally carry a token/secret-looking value in an
            # unexpected field, and none of that may ever leak into a log
            # or exception message - see tests/toss/test_token_parser.py.
            raise DataValidationError(
                "Toss token response did not match the PROVISIONAL "
                "(unverified) OAuth2 shape assumed by "
                "ProvisionalTokenResponseDto - see app/toss/token_parser.py "
                "and docs/architecture/0007-toss-api-integration.md. This "
                "may mean the assumed schema itself is wrong, not "
                "necessarily that the request failed."
            ) from exc

        return ParsedToken(access_token=dto.access_token, expires_in=dto.expires_in)
