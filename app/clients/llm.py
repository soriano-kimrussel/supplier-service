"""Supplier enrichment through the Claude API.

Structured outputs are used so the model's answer arrives as a validated
`SupplierProfile` instead of prose the service would have to parse.
"""

import logging
from typing import Any, Protocol

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from app.errors import EnrichmentFailed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You classify suppliers for a procurement platform.

Given a supplier record, return:
- categories: up to five short procurement categories, lowercase (e.g. "packaging").
- risk_summary: one sentence on supply risk, based only on the record given.

Never invent facts that are not in the record. If the record is too thin to
judge, say so in risk_summary and return the categories you can support.
"""


class SupplierProfile(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=5)
    risk_summary: str


class Enricher(Protocol):
    async def enrich(self, supplier: dict[str, Any]) -> SupplierProfile: ...


class ClaudeEnricher:
    def __init__(self, client: AsyncAnthropic, *, model: str = "claude-opus-5") -> None:
        self._client = client
        self._model = model

    async def enrich(self, supplier: dict[str, Any]) -> SupplierProfile:
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _render(supplier)}],
                output_format=SupplierProfile,
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            raise EnrichmentFailed(str(exc), retryable=True) from exc
        except anthropic.APIStatusError as exc:
            retryable = exc.status_code >= 500
            raise EnrichmentFailed(str(exc), retryable=retryable) from exc

        if response.stop_reason == "refusal":
            raise EnrichmentFailed("model declined to classify this supplier")

        profile = response.parsed_output
        if profile is None:
            raise EnrichmentFailed("model returned no structured output")

        return profile


def _render(supplier: dict[str, Any]) -> str:
    lines = [f"{key}: {value}" for key, value in supplier.items() if value not in (None, "")]
    return "Supplier record:\n" + "\n".join(lines)
