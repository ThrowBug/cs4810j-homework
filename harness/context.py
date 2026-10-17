"""What an agent receives (Context) and returns (Verdict)."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

import httpx
from browser_use import ChatOpenAI


@dataclass
class Meter:
	"""Token usage summed over every LLM call made through Context.llm()."""

	calls: int = 0
	prompt_tokens: int = 0
	completion_tokens: int = 0
	by_model: dict[str, int] = field(default_factory=dict)

	@property
	def total_tokens(self) -> int:
		return self.prompt_tokens + self.completion_tokens


@dataclass
class Verdict:
	passed: bool  # True if every expectation held; False if the app misbehaved
	reason: str = ''


@dataclass
class Context:
	cdp_url: str  # attach to the prepared browser: BrowserSession(cdp_url=ctx.cdp_url)
	app_url: str  # the app's base URL; the browser is already logged in on the start page
	out_dir: Path  # this run's folder: put logs, screenshots and GIFs here
	memory_dir: Path  # persists across runs and tasks: for memory, caches, RAG indexes
	meter: Meter
	mark: Callable[[str], Awaitable[None]] | None = None

	async def trace_step(self, title: str) -> None:
		"""Add a named step, with a snapshot of the current page, to this test's Playwright trace."""
		if self.mark:
			await self.mark(title)

	def llm(self, model: str | None = None) -> ChatOpenAI:
		"""An LLM on the course endpoint whose usage is counted. Use only LLMs made here.

		model defaults to LLM_MODEL from .env; pass another name (for example a cheaper
		model for easy steps) to mix models within one run.
		"""
		name = model or os.environ['LLM_MODEL']
		no_structured = os.getenv('LLM_NO_STRUCTURED_OUTPUT', 'false').lower() == 'true'
		meter = self.meter

		# Count usage from every API response, including replies the agent later rejects
		# as malformed: those tokens were spent too.
		async def count_usage(response: httpx.Response) -> None:
			if not response.request.url.path.endswith('/chat/completions') or response.status_code != 200:
				return
			await response.aread()
			usage = (response.json() or {}).get('usage') or {}
			meter.calls += 1
			meter.prompt_tokens += usage.get('prompt_tokens', 0)
			meter.completion_tokens += usage.get('completion_tokens', 0)
			meter.by_model[name] = meter.by_model.get(name, 0) + usage.get('total_tokens', 0)

		# Reasoning models spend hidden "thinking" tokens before answering; LLM_REASONING_EFFORT
		# (minimal / low / medium / high) caps that. Leave it empty to use the provider's default.
		effort = os.getenv('LLM_REASONING_EFFORT', 'low').strip()
		reasoning = {'reasoning_models': [name], 'reasoning_effort': effort} if effort else {}
		return ChatOpenAI(
			model=name,
			api_key=os.environ['OPENAI_API_KEY'],
			base_url=os.getenv('OPENAI_BASE_URL') or None,
			dont_force_structured_output=no_structured,
			add_schema_to_system_prompt=no_structured,
			max_completion_tokens=8192,
			http_client=httpx.AsyncClient(timeout=300, event_hooks={'response': [count_usage]}),
			**reasoning,
		)
