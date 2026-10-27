"""Wraps a RestaurantOrderingAgent as a LiveKit Agents `llm.LLM`, so the
realtime voice pipeline (STT -> [this] -> TTS) runs through the exact same
LangGraph tool-calling agent as the text and push-to-talk paths — one
"brain", not a second one to keep in sync.

The agent's own LangGraph MemorySaver already tracks conversation history
per session_id, so this doesn't replay LiveKit's ChatContext into it — it
only needs the customer's latest utterance, which `_last_user_text` pulls
off the end of that context.

RestaurantOrderingAgent.send() is a blocking call that may itself make
several Groq requests internally (the tool-calling loop), so each realtime
turn is emitted as a single ChatChunk rather than real token-by-token
streaming — the agent "thinks" before TTS starts "speaking", the same
latency shape as the text/push-to-talk UI today.
"""
from __future__ import annotations

import asyncio

from livekit.agents import APIConnectOptions
from livekit.agents.llm import LLM, ChatChunk, ChatContext, ChatMessage, ChoiceDelta, LLMStream, Tool
from livekit.agents.llm.tool_context import ToolChoice
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr
from livekit.agents.utils import shortuuid

from app.agent import language as lang
from app.agent.graph import AgentBusyError, RestaurantOrderingAgent
from app.voice import cart_sync


def _last_user_text(chat_ctx: ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if isinstance(item, ChatMessage) and item.role == "user":
            return item.text_content or ""
    return ""


class SarthiLLM(LLM):
    """Adapts one already-constructed RestaurantOrderingAgent to `llm.LLM`.

    `session_id`/`persona` are the plain (unprefixed) values the web app
    uses too — passed through so each turn can mirror this process's cart
    back to the main API via cart_sync.sync_cart, see that module.
    """

    def __init__(
        self,
        agent: RestaurantOrderingAgent,
        session_id: str,
        persona: str,
        restaurant: str | None = None,
        table_no: str | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._session_id = session_id
        self._persona = persona
        self._restaurant = restaurant
        self._table_no = table_no
        self._acks = 0  # how many acknowledgements said so far (rotates the phrases)

    @property
    def model(self) -> str:
        return self._agent.agent_name

    @property
    def provider(self) -> str:
        return "sarthi"

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict] = NOT_GIVEN,
    ) -> SarthiLLMStream:
        return SarthiLLMStream(
            self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options
        )


class SarthiLLMStream(LLMStream):
    async def _run(self) -> None:
        user_text = _last_user_text(self._chat_ctx)
        if not user_text:
            return

        llm: SarthiLLM = self._llm  # type: ignore[assignment]
        agent = llm._agent
        loop = asyncio.get_running_loop()

        # Say "Sure." (audio is cached) straight away, while the model works on the real answer.
        ack = lang.pick_ack(user_text, agent.language, llm._acks)
        if ack:
            llm._acks += 1
            self._event_ch.send_nowait(
                ChatChunk(id=shortuuid(), delta=ChoiceDelta(role="assistant", content=f"{ack} "))
            )
        try:
            reply = await loop.run_in_executor(None, agent.send, user_text)
        except AgentBusyError:
            reply = lang.line(agent.language, "busy")

        asyncio.create_task(
            cart_sync.sync_cart(
                llm._session_id, llm._persona, agent.cart, agent.service_log, llm._restaurant, llm._table_no
            )
        )

        self._event_ch.send_nowait(
            ChatChunk(
                id=shortuuid(),
                delta=ChoiceDelta(role="assistant", content=reply),
            )
        )
