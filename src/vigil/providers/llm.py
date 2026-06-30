"""LLM client: a transparent mock by default, real Anthropic behind ``USE_LLM``.

The mock is used only for customer-facing reply *wording* — every decision the
agent makes is rule-grounded and cited, so the demo is fully deterministic and
truthful without a model. Setting ``USE_LLM=true`` (and installing the ``llm``
extra + ``ANTHROPIC_API_KEY``) swaps in Claude for nicer prose; the decisions,
citations, and routing are unchanged.
"""

from __future__ import annotations

from typing import Protocol

from vigil.config import get_settings


class LLMClient(Protocol):
    provider: str

    def complete(self, system: str, prompt: str) -> str: ...


class MockLLMClient:
    provider = "mock-heuristic-v1"

    def complete(self, system: str, prompt: str) -> str:  # pragma: no cover - trivial
        # The caller already composes a complete, citation-grounded reply; the
        # mock simply echoes it. Real prose generation is the USE_LLM path.
        return prompt.strip()


class AnthropicLLMClient:
    def __init__(self) -> None:
        import anthropic  # lazy import; only needed on the live path

        s = get_settings()
        self.provider = s.anthropic_model
        self._client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        self._model = s.anthropic_model

    def complete(self, system: str, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")


def get_llm_client() -> LLMClient:
    s = get_settings()
    if s.use_llm and s.anthropic_api_key and s.anthropic_api_key != "__PLACEHOLDER__":
        try:
            return AnthropicLLMClient()
        except Exception:  # pragma: no cover - fall back if SDK missing
            return MockLLMClient()
    return MockLLMClient()
