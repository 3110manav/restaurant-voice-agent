from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # add_messages appends new messages instead of overwriting the list,
    # which is what lets LangGraph carry conversation history across turns.
    messages: Annotated[list, add_messages]
