"""Talk to a store's phone agent by typing, with no phone, LiveKit or speech involved. Uses the real
agent, LLM and database, so an order placed here is a real order and its WhatsApp messages go out.

    python -m app.phone.simulate kirana-demo +919876543210
"""
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from app.phone import repository  # noqa: E402
from app.phone.call import PhoneCall  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    store = repository.get_store_by_slug(sys.argv[1])
    if store is None:
        sys.exit(f"No store '{sys.argv[1]}'. Add it with: python -m app.phone.setup_store")
    call = PhoneCall(f"simulated-{uuid.uuid4().hex[:8]}", store, sys.argv[2])
    print(f"Agent: {call.greeting}")
    try:
        while True:
            text = input("You: ").strip()
            if text:
                print(f"Agent: {call.take_turn(text)}")
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        call.close()
        print(f"Call ended: {call.outcome}")


if __name__ == "__main__":
    main()
