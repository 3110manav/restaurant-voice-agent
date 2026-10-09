# Voice Ordering Agent

A voice AI assistant for a multi-cuisine restaurant, built as two personas
sharing one engine:
- **Online** — a delivery-app ordering assistant (menu Q&A, cart, checkout).
- **Waiter** — an in-restaurant assistant that also handles ambient
  service requests (water, napkins, flagging a food issue, the bill,
  calling staff over) the way a real waiter would.

Both are voice-first (speech in, spoken reply out) and available through
a web UI, CLIs, and a JSON API.

## Why this project exists

Learning project covering the core building blocks of applied voice/LLM
systems: tool calling, RAG over structured data, stateful agent graphs,
speech-to-text, text-to-speech, and building two distinct agent personas
on one shared toolset/engine.

## Architecture

```
mic audio -> STT (Whisper via Groq) -> [ this repo: LangGraph agent ] -> TTS (Orpheus/Groq for English, Sarvam AI for Hindi) -> speaker
                                          |
                                          |-- search_menu / get_item_details  (RAG over menu.json via Chroma + Gemini embeddings)
                                          |-- add_to_cart / remove_from_cart / view_cart / checkout  (in-memory per-session cart)
                                          |-- [waiter only] request_item / flag_issue / request_bill / call_staff
                                          |
                                        Groq/Llama (tool-calling), LangGraph StateGraph + MemorySaver for conversation state
```

- `app/data/menu.json` — 105-item menu across Indian, South Indian, Chinese dim sum, Japanese sushi, Italian pasta and pizza, and sandwiches.
- `app/rag/menu_store.py` — embeds the menu into a **persisted** Chroma store (Gemini embeddings), exposes semantic `search()` and exact `find_by_name()`. Persisted and hash-checked against menu.json so a process restart doesn't re-embed everything — see the note in that file about Gemini's free-tier rate limit.
- `app/agent/tools.py` — ordering tools (both personas), closed over a per-session cart.
- `app/agent/service_tools.py` — waiter-only service tools (`request_item`, `flag_issue`, `request_bill`, `call_staff`), closed over a per-session service log.
- `app/agent/graph.py` — the LangGraph tool-calling loop, parameterized by `persona="online"|"waiter"` (different tools + system prompt, same engine).
- `app/voice/stt.py` — speech-to-text via Groq-hosted Whisper (auto-detects language, handles Hindi/English code-switching).
- `app/voice/tts.py` — text-to-speech, auto-routed by script: Groq's Orpheus for English, Sarvam AI's Bulbul for Hindi.
- `app/voice/recorder.py` — push-to-talk mic recording for the CLIs.
- `app/main.py` — FastAPI: `/chat` (text) and `/chat/voice` (audio in, text + audio out), both persona-aware. Serves the web frontend.
- `app/static/` — the web UI: persona toggle, chat transcript, mic button, cart and service-request panels.
- `cli.py` / `voice_cli.py` — text/voice REPLs for testing the agent directly, no frontend needed. `voice_cli.py waiter` runs the waiter persona.

## Setup

```bash
cd voice-ordering-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in:
#  GROQ_API_KEY   from console.groq.com/keys  (LLM tool-calling, STT, English TTS)
#  GOOGLE_API_KEY from aistudio.google.com/apikey  (embeddings only)
#  SARVAM_API_KEY sign up at indus.sarvam.ai, then get your key from their console  (Hindi TTS)
```

The English TTS model (`canopylabs/orpheus-v1-english`) requires a one-time
terms acceptance in the Groq console before it'll serve requests: open
https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english
and accept the terms there. Everything else, including Hindi TTS, works
without this.

The first run also builds the menu's embedding index, which takes
**~2-3 minutes** (throttled on purpose to stay under Gemini's free-tier
rate limit — see `app/rag/menu_store.py`). Every run after that reuses
the persisted index (`chroma_db/`) and starts almost instantly, unless
`menu.json` changed.

## Run it

**Web UI** (both personas, mic + text, cart and service-request panels):

```bash
uvicorn app.main:app --reload
# open http://localhost:8000
```

**CLIs** (no browser needed):

```bash
python cli.py               # text, online persona
python voice_cli.py         # voice, online persona
python voice_cli.py waiter  # voice, waiter persona
```

Try things like:
- Online: "What vegetarian mains do you have?" / "Add two margherita pizzas and a garlic naan" / "That's everything, check out"
- Waiter: "Can you bring me a glass of water?" / "This is cold, can you reheat it?" / "Can we get the bill?"

Everything above also works in Hindi, or mixed Hindi/English, for both
text and voice — spoken replies too: the agent replies in whichever
language you used, and `app/voice/tts.py` routes Hindi text to Sarvam AI
and English text to Groq's Orpheus automatically.

**API directly:**

```bash
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"session_id": "demo", "persona": "waiter", "message": "bring me some napkins"}'
```

## Deploying (free demo link)

The web UI/API (not the local CLIs — those need your mic/speakers directly)
can be hosted for free on [Render](https://render.com) as a Docker web
service. A few things specific to this project's architecture, already
handled below:

- **Embeddings are baked into the image**, not rebuilt at startup. Free
  hosts wipe the filesystem on every restart/spin-down, and rebuilding
  105 items' embeddings live would immediately hit Gemini's free-tier
  rate limit (the same one `app/rag/menu_store.py` already works around).
  So `chroma_db/` is committed to the repo and copied into the image as-is
  — **whenever you change `menu.json`, rebuild locally first** (just run
  `python cli.py` once, or any script that constructs `MenuStore()`) and
  commit the updated `chroma_db/` before redeploying.
- **The server image doesn't need `sounddevice`/`soundfile`/`numpy`** —
  those are mic/speaker libraries only the local CLIs use, split out into
  `requirements-cli.txt` so the Dockerfile (`requirements.txt`) stays free
  of system audio dependencies most containers don't have.
- **Mic access actually works better once hosted**: browsers only allow
  microphone access on HTTPS or localhost. Render gives you HTTPS by
  default, so the web UI's mic button will work in any real browser once
  deployed — no more Claude Code preview-pane restriction.

Steps:

1. Push this repo to GitHub (a new repo, your account).
2. On Render: **New > Web Service**, connect that repo, set
   **Environment: Docker** (it'll find the `Dockerfile` automatically).
3. Add environment variables in Render's dashboard (Settings > Environment):
   `GROQ_API_KEY`, `GOOGLE_API_KEY`, `SARVAM_API_KEY` — copy the values
   from your local `.env`, never commit them.
4. Deploy. Free tier spins down after 15 minutes idle and takes about a
   minute to wake back up on the next request — fine for a demo link, not
   for production traffic.

**Known limitations of this setup** (fine for a demo, not for real
traffic): sessions/carts are stored in memory (`app/main.py`'s `sessions`
dict, and LangGraph's `MemorySaver`), so a restart or spin-down loses all
active conversations, and it can't run more than one instance. A
production version would swap `MemorySaver` for `PostgresSaver` or
`SqliteSaver` (same interface, different backing store) and move cart
state into a real database or that same persistence layer.

## Tests

```bash
pytest
```

Only the cart/service tools are unit tested (no API key needed). The
agent loop, RAG retrieval, and voice pipeline are exercised manually via
the CLIs and web UI, since those need live API calls.

## Roadmap

1. ✅ **Text-only agent** — tool calling, cart state, RAG over the menu.
2. ✅ **Speech-to-text** — mic input via Whisper (Groq).
3. ✅ **Text-to-speech** — Orpheus (Groq) speaks English replies; Sarvam AI's Bulbul speaks Hindi replies. Routed automatically by script in `app/voice/tts.py`.
4. ✅ **Two personas + web frontend + expanded menu** — waiter service tools, a shared web UI for both personas, 105-item multi-cuisine menu.
5. ✅ **Hindi voice output** — Sarvam AI TTS for Hindi replies, alongside the Hindi STT/understanding that already worked.
6. **Polish** — barge-in/interruption handling, misheard-order recovery, a staff-facing view of the service log, demo video.

## Known limitation: mic in the Claude Code browser preview

If you're viewing the web UI through Claude Code's in-app browser pane,
mic access is blocked by that sandboxed preview (a device-permission
policy, not a bug in this app). Open http://localhost:8000 in a real
browser (Chrome/Safari) to use the mic there — text input works fine in
either. `voice_cli.py` always has real mic access since it isn't
browser-based.

## Swapping components

- LLM: swap `ChatGroq` in `app/agent/graph.py` for any LangChain chat model (e.g. `ChatAnthropic`, `ChatGoogleGenerativeAI`, `ChatOpenAI`).
- Embeddings: swap `GoogleGenerativeAIEmbeddings` in `app/rag/menu_store.py` for `VoyageAIEmbeddings`, `OpenAIEmbeddings`, or a local `sentence-transformers` model.
- Vector store: swap `Chroma` for Pinecone/Weaviate/etc. once you need it hosted rather than in-process.
