"""Milestone 3: voice in, voice out.

Push-to-talk over the mic -> Whisper (Groq) -> the ordering agent -> spoken
back through the speakers (Orpheus/Groq for English, Sarvam AI's Bulbul
for Hindi — see app/voice/tts.py).

Usage:
    python voice_cli.py            # online delivery-app persona
    python voice_cli.py waiter     # in-restaurant waiter persona
"""
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.agent.graph import RestaurantOrderingAgent  # noqa: E402
from app.rag.menu_store import MenuStore  # noqa: E402
from app.voice.recorder import record_until_enter  # noqa: E402
from app.voice.stt import transcribe  # noqa: E402
from app.voice.tts import speak  # noqa: E402


def main():
    persona = "waiter" if len(sys.argv) > 1 and sys.argv[1] == "waiter" else "online"

    print(f"Loading menu and building the {persona} agent...")
    menu_store = MenuStore()
    agent = RestaurantOrderingAgent(session_id=f"voice-cli-{persona}", menu_store=menu_store, persona=persona)

    print(f"Ready ({persona} persona). Speak naturally. Ctrl+C to quit.\n")
    tmp_dir = Path(tempfile.gettempdir())
    try:
        while True:
            audio_path = tmp_dir / "voice_ordering_turn.wav"
            try:
                record_until_enter(str(audio_path))
            except Exception as e:
                print(f"[recording error] {e!r}\n")
                continue

            print("Transcribing...", flush=True)
            try:
                heard = transcribe(str(audio_path))
            except Exception as e:
                print(f"[transcription error] {e!r}\n")
                continue
            if not heard:
                print("(didn't catch anything, try again)\n")
                continue
            print(f"you said> {heard}")

            print("Thinking...", flush=True)
            try:
                reply = agent.send(heard)
            except Exception as e:
                print(f"[agent error] {e!r}\n")
                continue
            print(f"agent> {reply}\n")

            try:
                speak(reply)
            except Exception as e:
                print(f"[speech playback error] {e!r}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nbye")


if __name__ == "__main__":
    main()
