"""The ordering agent's LangGraph: a standard tool-calling loop.

agent -> (has tool calls?) -> tools -> agent -> ... -> (no tool calls) -> END

Each RestaurantOrderingAgent instance owns its own cart (and, for the
waiter persona, its own service log) plus a compiled graph, so sessions
never share state. Conversation history is kept by LangGraph's
checkpointer (MemorySaver), keyed by thread_id.

Two personas share this same engine and ordering toolset, differing only
in their extra tools and system prompt:
  - "online"  — the delivery-app assistant. Ordering only.
  - "waiter"  — the in-restaurant assistant. Ordering plus service
                requests (water, napkins, flagging a food issue, the
                bill, calling staff over) — anything a waiter physically
                present at the table would handle.
"""
from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.service_tools import build_service_tools
from app.agent.state import AgentState
from app.agent.tools import build_tools
from app.rag.menu_store import MenuStore

_CUISINES = "Indian, South Indian, Chinese dim sum, Japanese sushi, Italian pasta and pizza, and sandwiches"

_LANGUAGE_RULE = """CRITICAL, above every other instruction: always reply in the same language \
the customer's most recent message was in. If they spoke Hindi, your reply must be in Hindi. If \
English, reply in English. If they mixed the two, mix naturally. Tool results in this \
conversation are written in English for the engineering team's benefit only — they are not part \
of the conversation's language and must never influence which language you answer in."""

_SHARED_VOICE_STYLE = """Your reply will be spoken aloud by a text-to-speech engine — so write \
ONLY plain spoken sentences. Never use markdown, bullet points, dashes, numbered \
lists, headers, or emoji. When listing multiple items, say them as a natural \
spoken sentence (e.g. "we've got the paneer tikka masala, the dal makhani, and \
the chana masala") rather than a list with line breaks.

Keep every reply as short as possible — one short sentence whenever it'll do. This \
is a fast ordering conversation, not a menu reading. Nobody wants to hear a long \
list read out loud; get to the point and let the customer ask for more if they want it."""

_ORDERING_BEHAVIOR = f"""When the customer names specific items and quantities clearly — even \
several in one sentence, like "add a paneer tikka and a tandoori roti" — call \
add_to_cart for each right away. Do not ask permission first or repeat the order \
back as a question before acting; that slows things down for no reason. Just add \
it, then briefly confirm what's in the cart now. The only time to ask before adding \
is when the name is genuinely ambiguous (matches more than one real menu item) or \
doesn't match anything at all. If the customer changes their mind, they'll simply \
ask you to remove something — that's the correction path, so there's no need to \
double-check before adding in the first place.

When someone asks something broad — "what do you have", "what starters do you \
have", "what's good here" — do not run a search and recite whatever comes back; a \
broad word like "starters" matches things across every cuisine and dumping all of \
it is slow and overwhelming. Instead, first ask a short question naming the \
cuisines available ({_CUISINES}) so they can narrow down. Once they name a \
specific cuisine or craving, use search_menu with that narrower query and mention \
only two or three options, not everything that matched."""

ONLINE_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are the ordering assistant for a multi-cuisine restaurant's \
delivery app ({_CUISINES}). A customer is placing an order by voice through the app. \
{_SHARED_VOICE_STYLE}

Use your tools rather than guessing: look up menu items and their details before \
answering questions about them. {_ORDERING_BEHAVIOR} Only call checkout after the \
customer clearly confirms they're done ordering.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""

WAITER_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are a voice waiter assistant at a table in a multi-cuisine \
restaurant ({_CUISINES}). A customer at the table is speaking to you directly, the way \
they would to a human waiter. {_SHARED_VOICE_STYLE}

Handle anything a real waiter would: taking a food/drink order ({_ORDERING_BEHAVIOR}), \
bringing non-menu items like water, napkins, or extra cutlery (use request_item), \
flagging a problem with food or service that's already been served, like it being \
cold or wrong (use flag_issue), getting the bill (use request_bill), and calling a \
human over for anything else (use call_staff). Always use a tool rather than just \
saying you'll do something.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""


class RestaurantOrderingAgent:
    def __init__(
        self,
        session_id: str,
        menu_store: MenuStore,
        persona: str = "online",
        model: str = "openai/gpt-oss-120b",
    ):
        if persona not in ("online", "waiter"):
            raise ValueError(f"unknown persona: {persona!r}")

        self.session_id = session_id
        self.persona = persona
        self.cart: list[dict] = []
        self.service_log: list[dict] = []

        self.tools = build_tools(self.cart, menu_store)
        if persona == "waiter":
            self.tools += build_service_tools(self.service_log)
            self.system_prompt = WAITER_SYSTEM_PROMPT
        else:
            self.system_prompt = ONLINE_SYSTEM_PROMPT

        llm = ChatGroq(model=model, temperature=0, timeout=30.0, max_retries=1)
        self.llm_with_tools = llm.bind_tools(self.tools)

        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _call_model(self, state: AgentState) -> dict:
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=self.system_prompt)] + messages
        response = self.llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("agent", self._call_model)
        graph.add_node("tools", ToolNode(self.tools))
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        return graph.compile(checkpointer=self.checkpointer)

    def send(self, user_text: str) -> str:
        config = {"configurable": {"thread_id": self.session_id}}
        result = self.graph.invoke({"messages": [("user", user_text)]}, config=config)
        return _extract_text(result["messages"][-1].content)


def _extract_text(content) -> str:
    """Gemini returns content as a list of typed blocks (text, thinking,
    signatures, ...) rather than a plain string — keep only the text parts."""
    if isinstance(content, str):
        return content
    parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
    return "\n".join(part for part in parts if part)
