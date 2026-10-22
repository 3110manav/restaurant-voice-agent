"""Quick REPL for testing the ordering agent without the API or voice layer.

Usage:
    python cli.py                  # online persona (Meera)
    python cli.py quick_commerce   # quick-commerce persona (Veer)
    python cli.py waiter           # waiter persona (Kabir)
    python cli.py hotel            # hotel persona (Ira)
"""
import sys

from dotenv import load_dotenv

load_dotenv()

from app.agent.graph import _PERSONAS, RestaurantOrderingAgent  # noqa: E402
from app.rag.menu_store import MenuStore  # noqa: E402


def main():
    persona = sys.argv[1] if len(sys.argv) > 1 else "online"
    if persona not in _PERSONAS:
        print(f"Unknown persona {persona!r}. Choose one of: {', '.join(_PERSONAS)}")
        return

    print(f"Loading menu and building the {persona} agent...")
    menu_store = MenuStore()
    agent = RestaurantOrderingAgent(session_id=f"cli-{persona}", menu_store=menu_store, persona=persona)

    print(f"Ready ({agent.agent_name}, {persona} persona). Type your order like you'd speak it. Ctrl+C to quit.\n")
    try:
        while True:
            user_text = input("you> ").strip()
            if not user_text:
                continue
            reply = agent.send(user_text)
            print(f"agent> {reply}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nbye")


if __name__ == "__main__":
    main()
