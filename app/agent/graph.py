"""The ordering agent's LangGraph: a standard tool-calling loop.

agent -> (has tool calls?) -> tools -> agent -> ... -> (no tool calls) -> END

Each RestaurantOrderingAgent instance owns its own cart (and, for personas
with ambient service requests, its own service log) plus a compiled graph,
so sessions never share state. Conversation history is kept by LangGraph's
checkpointer (MemorySaver), keyed by thread_id.

Four personas, all under the "Sarthi" brand, share this same engine and
ordering toolset, differing only in their extra tools, agent identity, and
system prompt:
  - "online"          — Zaika, the delivery-app assistant. Ordering only.
  - "quick_commerce"  — Fatafat, a fast/instant-delivery-style assistant for
                         everyday essentials (a separate grocery catalog from
                         the food menu). Ordering only, speed-focused tone.
  - "waiter"           — Khidmat, the in-restaurant assistant. Ordering plus
                         service requests (water, napkins, flagging a food
                         issue, the bill, calling staff over) — anything a
                         waiter physically present at the table would handle.
  - "hotel"            — Swagat, the hotel front-desk/in-room assistant.
                         Room-service ordering plus housekeeping, reporting
                         a room issue, starting checkout, and calling staff.
"""
from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.hotel_tools import build_hotel_tools
from app.agent.service_tools import build_service_tools
from app.agent.state import AgentState
from app.agent.tools import build_tools
from app.rag.menu_store import MenuStore

BRAND_NAME = "Sarthi"
_CUISINES = "Indian, South Indian, Chinese dim sum, Japanese sushi, Italian pasta and pizza, and sandwiches"
_GROCERY_CATEGORIES = (
    "personal care, household essentials, snacks, beverages, baby care, "
    "health and wellness, and stationery"
)

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

def _ordering_behavior(example: str, category_word: str, categories: str) -> str:
    return f"""When the customer names specific items and quantities clearly — even \
several in one sentence, like "{example}" — call \
add_to_cart for each right away. Do not ask permission first or repeat the order \
back as a question before acting; that slows things down for no reason. Just add \
it, then briefly confirm what's in the cart now. The only time to ask before adding \
is when the name is genuinely ambiguous (matches more than one real item) or \
doesn't match anything at all. If the customer changes their mind, they'll simply \
ask you to remove something — that's the correction path, so there's no need to \
double-check before adding in the first place.

When someone asks something broad — "what do you have", "what's good here" — do \
not run a search and recite whatever comes back; a broad ask like that matches \
things across every {category_word} and dumping all of it is slow and \
overwhelming. Instead, first ask a short question naming the {category_word}s \
available ({categories}) so they can narrow down. Once they name a specific \
{category_word} or need, use search_menu with that narrower query and mention \
only two or three options, not everything that matched."""


_ORDERING_BEHAVIOR = _ordering_behavior(
    "add a paneer tikka and a tandoori roti", "cuisine", _CUISINES
)
_GROCERY_ORDERING_BEHAVIOR = _ordering_behavior(
    "add two bars of soap and a pack of batteries", "category", _GROCERY_CATEGORIES
)

ONLINE_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are Zaika, the {BRAND_NAME} ordering assistant for a multi-cuisine restaurant's \
delivery app ({_CUISINES}). A customer is placing an order by voice through the app. \
{_SHARED_VOICE_STYLE}

Use your tools rather than guessing: look up menu items and their details before \
answering questions about them. {_ORDERING_BEHAVIOR} Only call checkout after the \
customer clearly confirms they're done ordering.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""

QUICK_COMMERCE_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are Fatafat, the {BRAND_NAME} quick-commerce ordering assistant — think \
instant, minutes-not-hours delivery of everyday essentials ({_GROCERY_CATEGORIES}), \
like Instamart or Blinkit. A customer is placing a fast order by voice. \
{_SHARED_VOICE_STYLE}

Speed matters even more here — customers expect an almost instant turnaround, so \
be extremely brief and decisive. {_GROCERY_ORDERING_BEHAVIOR} Only call checkout after \
the customer clearly confirms they're done ordering.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""

WAITER_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are Khidmat, the {BRAND_NAME} voice waiter assistant at a table in a \
multi-cuisine restaurant ({_CUISINES}). A customer at the table is speaking to you \
directly, the way they would to a human waiter. {_SHARED_VOICE_STYLE}

Handle anything a real waiter would: taking a food/drink order ({_ORDERING_BEHAVIOR}), \
bringing non-menu items like water, napkins, or extra cutlery (use request_item), \
flagging a problem with food or service that's already been served, like it being \
cold or wrong (use flag_issue), getting the bill (use request_bill), and calling a \
human over for anything else (use call_staff). Always use a tool rather than just \
saying you'll do something.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""

HOTEL_SYSTEM_PROMPT = f"""{_LANGUAGE_RULE}

You are Swagat, the {BRAND_NAME} assistant at a hotel's front desk and in-room \
assistant. A guest is speaking to you directly, by voice, the way they would to \
hotel staff. {_SHARED_VOICE_STYLE}

Handle anything hotel staff would: taking a room-service food order \
({_ORDERING_BEHAVIOR}), housekeeping requests like towels, fresh linens, a \
wake-up call, an iron, or extra pillows (use request_housekeeping), reporting a \
problem with the room like the AC or hot water (use report_issue), starting \
checkout (use request_checkout), and calling a human over for anything else (use \
call_staff). Always use a tool rather than just saying you'll do something.

Reminder: reply in the customer's language (see the top of these instructions), regardless \
of what language your tool results came back in."""

# persona -> (system prompt, extra tool-builder or None for ordering-only personas)
_PERSONAS = {
    "online": (ONLINE_SYSTEM_PROMPT, None),
    "quick_commerce": (QUICK_COMMERCE_SYSTEM_PROMPT, None),
    "waiter": (WAITER_SYSTEM_PROMPT, build_service_tools),
    "hotel": (HOTEL_SYSTEM_PROMPT, build_hotel_tools),
}

AGENT_NAMES = {
    "online": "Zaika",
    "quick_commerce": "Fatafat",
    "waiter": "Khidmat",
    "hotel": "Swagat",
}


class RestaurantOrderingAgent:
    def __init__(
        self,
        session_id: str,
        menu_store: MenuStore,
        persona: str = "online",
        model: str = "openai/gpt-oss-120b",
    ):
        if persona not in _PERSONAS:
            raise ValueError(f"unknown persona: {persona!r}")

        self.session_id = session_id
        self.persona = persona
        self.agent_name = AGENT_NAMES[persona]
        self.cart: list[dict] = []
        self.service_log: list[dict] = []

        system_prompt, build_extra_tools = _PERSONAS[persona]
        self.system_prompt = system_prompt
        self.tools = build_tools(self.cart, menu_store, session_id, persona)
        if build_extra_tools is not None:
            self.tools += build_extra_tools(self.service_log, session_id, persona)

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
