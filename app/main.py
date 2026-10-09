"""API for both personas: text and voice in, text + spoken out.

POST /chat        {"session_id", "message", "persona"} -> reply + cart + service_log
POST /chat/voice   multipart: audio file + session_id + persona -> transcript,
                   reply, cart, service_log, and base64 WAV audio (English via
                   Orpheus/Groq, Hindi via Sarvam AI's Bulbul)

Serves the frontend (app/static/) at "/".
"""
import base64

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

from pathlib import Path  # noqa: E402

from app.agent.graph import RestaurantOrderingAgent  # noqa: E402
from app.rag.menu_store import MenuStore  # noqa: E402
from app.voice.stt import transcribe_bytes  # noqa: E402
from app.voice.tts import synthesize  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Voice Ordering Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

menu_store = MenuStore()
sessions: dict[str, RestaurantOrderingAgent] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str
    persona: str = "online"


class ChatResponse(BaseModel):
    reply: str
    cart: list[dict]
    service_log: list[dict]


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    cart: list[dict]
    service_log: list[dict]
    reply_audio_wav_base64: str | None = None


def get_or_create_session(session_id: str, persona: str) -> RestaurantOrderingAgent:
    key = f"{session_id}:{persona}"
    if key not in sessions:
        sessions[key] = RestaurantOrderingAgent(session_id=key, menu_store=menu_store, persona=persona)
    return sessions[key]


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_or_create_session(req.session_id, req.persona)
    reply = agent.send(req.message)
    return ChatResponse(reply=reply, cart=agent.cart, service_log=agent.service_log)


@app.post("/chat/voice", response_model=VoiceChatResponse)
async def chat_voice(session_id: str, persona: str, audio: UploadFile) -> VoiceChatResponse:
    agent = get_or_create_session(session_id, persona)

    audio_bytes = await audio.read()
    transcript = transcribe_bytes(audio_bytes, filename=audio.filename or "audio.webm")

    if not transcript:
        return VoiceChatResponse(transcript="", reply="", cart=agent.cart, service_log=agent.service_log)

    reply = agent.send(transcript)

    try:
        reply_audio_b64 = base64.b64encode(synthesize(reply)).decode("ascii")
    except Exception:
        reply_audio_b64 = None  # TTS unavailable/blocked — client falls back to text only

    return VoiceChatResponse(
        transcript=transcript,
        reply=reply,
        cart=agent.cart,
        service_log=agent.service_log,
        reply_audio_wav_base64=reply_audio_b64,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
