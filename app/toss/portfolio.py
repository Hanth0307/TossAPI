"""Portfolio Read Gateway: read-only account/asset/order-status access.

Confirmed official GET endpoints only: `/api/v1/accounts`,
`/api/v1/holdings`, `/api/v1/orders`, `/api/v1/orders/{orderId}`,
`/api/v1/buying-power`, `/api/v1/sellable-quantity`,
`/api/v1/commissions`. All of them are called with the
`X-Tossinvest-Account` header per the official "계좌·자산·주문 API"
rule.

None of these methods can place, modify, or cancel an order - there
is no such method on this class, and `TossRestClient` itself has no
verb other than `get()`. The official POST /api/v1/orders (and
modify/cancel) endpoints exist per the docs but are out of scope for
Phase 02 and are not called anywhere in this codebase.

No official response field schema was shown for any of these
endpoints, so every method returns an `UnparsedRecord` preserving the
raw `result` payload rather than a fabricated field-level model - see
`app/toss/models.py::UnparsedRecord` and ADR 0007.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.toss.client import TossResponseEnvelope, TossRestClient
from app.toss.dto import RawEnvelopeDto
from app.toss.models import TOSS_SOURCE_NAME, RecordMetadata, UnparsedRecord
from app.toss.rate_limit import RateLimitGroup


class PortfolioReadAdapter:
    def __init__(
        self,
        client: TossRestClient,
        *,
        capture_raw_payload: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._capture_raw_payload = capture_raw_payload
        self._clock = clock

    def get_accounts(self) -> UnparsedRecord:
        return self._get("/api/v1/accounts", params=None, group=RateLimitGroup.ACCOUNT)

    def get_holdings(self) -> UnparsedRecord:
        return self._get("/api/v1/holdings", params=None, group=RateLimitGroup.ASSET)

    def get_orders(self, **params: str) -> UnparsedRecord:
        return self._get("/api/v1/orders", params=params or None, group=RateLimitGroup.ACCOUNT)

    def get_order(self, order_id: str) -> UnparsedRecord:
        return self._get(f"/api/v1/orders/{order_id}", params=None, group=RateLimitGroup.ACCOUNT)

    def get_buying_power(self, **params: str) -> UnparsedRecord:
        return self._get(
            "/api/v1/buying-power", params=params or None, group=RateLimitGroup.ACCOUNT
        )

    def get_sellable_quantity(self, symbol: str) -> UnparsedRecord:
        return self._get(
            "/api/v1/sellable-quantity", params={"symbol": symbol}, group=RateLimitGroup.ACCOUNT
        )

    def get_commissions(self, **params: str) -> UnparsedRecord:
        return self._get("/api/v1/commissions", params=params or None, group=RateLimitGroup.ACCOUNT)

    def _get(
        self, path: str, *, params: dict[str, str] | None, group: RateLimitGroup
    ) -> UnparsedRecord:
        envelope = self._client.get(path, params=params, requires_account=True, group=group)
        dto = RawEnvelopeDto.model_validate(envelope.payload)
        return UnparsedRecord(metadata=self._metadata(envelope), result=dto.result)

    def _metadata(self, envelope: TossResponseEnvelope) -> RecordMetadata:
        return RecordMetadata(
            source=TOSS_SOURCE_NAME,
            event_time=None,
            available_at=envelope.received_at,
            ingested_at=envelope.received_at,
            raw_payload=envelope.payload if self._capture_raw_payload else None,
        )
