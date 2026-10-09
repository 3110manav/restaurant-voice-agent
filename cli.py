"""Quick REPL for testing the ordering agent without the API or voice layer.

Usage:
    python cli.py
"""
from dotenv import load_dotenv

load_dotenv()

from app.agent.graph import RestaurantOrderingAgent  # noqa: E402
from app.rag.menu_store import MenuStore  # noqa: E402


def main():
    print("Loading menu and building the agent...")
    menu_store = MenuStore()
    agent = RestaurantOrderingAgent(session_id="cli-session", menu_store=menu_store)

    print("Ready. Type your order like you'd speak it. Ctrl+C to quit.\n")
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
