# Sarthi

A multi-persona voice/text AI ordering and service assistant, built as a
portfolio/learning project covering the full stack of an applied LLM
product: tool-calling agents, RAG, speech-to-text/text-to-speech, a
premium Next.js frontend, and (optionally) real persistence via Supabase.

One brand, one shared agent engine, four personas — each with its own name
and its own job:

| Agent | Persona key | Role |
|---|---|---|
| **Zaika** | `online` | Delivery-app ordering, like Swiggy or Zomato |
| **Fatafat** | `quick_commerce` | Instant grocery ordering, like Instamart or Blinkit — shampoo, snacks, batteries, not food |
| **Khidmat** | `waiter` | In-restaurant table-side assistant — ordering, plus water/napkins/bill/flagging an issue/calling staff |
| **Swagat** | `hotel` | Hotel front desk / in-room assistant — room-service ordering, housekeeping, reporting an issue, checkout |

All four speak Hindi and English (and code-switched mixes of both), by
voice or text, and reply in whichever language the customer used.

## Why this project exists

A from-scratch build covering the core building blocks of applied voice/LLM
systems: tool calling, RAG over structured catalogs, stateful agent graphs
(LangGraph), speech-to-text, text-to-speech, and a production-shaped
frontend (Next.js + a proxying API layer) talking to a Python agent
backend — deliberately kept as two services rather than one monolith.

## Architecture

```
Browser — web/ (Next.js, deployed on Vercel)
  shadcn/ui + Vengeance UI: product grids, floating chat/voice widget,
  persona pages under /chat/[slug]
        │
        │  server-side fetch, via Next.js Route Handlers under src/app/api/*
        ▼
FastAPI backend — app/ (deployed on Render)
  /chat   /chat/voice   /menu   /cart/add   /cart/remove   /health
        │
        ▼
RestaurantOrderingAgent — app/agent/graph.py
  LangGraph tool-calling loop + MemorySaver (per-session conversation state)
        │
        ├─ search_menu / get_item_details          RAG: Chroma + Gemini
        │                                           embeddings, over two
        ├─ add_to_cart / remove_from_cart /         separate catalogs (the
        │  view_cart / checkout                     restaurant menu, and a
        │                                           separate grocery catalog)
        ├─ [waiter] request_item / flag_issue /
        │  request_bill / call_staff
        │
        └─ [hotel] request_housekeeping /
           report_issue / request_checkout / call_staff
        │
        ▼  (checkout + service requests only, best-effort)
Supabase — orders, requests tables (app/erp.py, optional)

Voice path (orthogonal to the above): mic audio -> STT (Whisper via Groq)
-> agent -> TTS (Orpheus/Groq for English, Sarvam AI's Bulbul for Hindi)
-> spoken reply. Push-to-talk today; see Roadmap for realtime/barge-in.
```

Why the frontend proxies through its own API routes instead of calling the
Python backend directly from the browser: no CORS to configure, the
backend's URL/shape stays a server-side concern, and it's the idiomatic
Next.js "backend for frontend" pattern.

### Two separate catalogs

`online`, `waiter`, and `hotel` (room service) all share one 105-item
restaurant menu. `quick_commerce` has its own, completely separate
100-item grocery catalog — different items, different categories, no
food-specific fields. Both are backed by the same `MenuStore` class
(`app/rag/menu_store.py`) as two independent Chroma collections, so
adding a third catalog later is a one-line call, not a new class.

- `app/data/menu.json` — 105 items: Indian, South Indian, Chinese dim sum,
  Japanese sushi, Italian pasta and pizza, and sandwiches.
- `app/data/grocery.json` — 100 items: personal care, household
  essentials, snacks, beverages, baby care, health & wellness, stationery.

### Key files

**Backend (`app/`)**
- `app/agent/graph.py` — the LangGraph tool-calling loop and all four
  system prompts, parameterized by `persona`. One `RestaurantOrderingAgent`
  class; the persona only changes the prompt, the catalog, and which extra
  tools get bound.
- `app/agent/tools.py` — ordering tools, shared by every persona, closed
  over a per-session cart. Also exposes `add_item_to_cart` /
  `remove_item_from_cart_by_id`, the plain functions both the LLM tool and
  the direct `/cart/add` `/cart/remove` API routes call.
- `app/agent/service_tools.py` / `app/agent/hotel_tools.py` — the waiter's
  and hotel's extra ambient-request tools.
- `app/rag/menu_store.py` — embeds a catalog into a **persisted** Chroma
  store, exposes semantic `search()` and exact `find_by_name()`/`get()`.
  Persisted and hash-checked per catalog so a process restart doesn't
  re-embed everything — see the note in that file about Gemini's
  free-tier rate limit (100 req/min), which the throttled batch build
  works around.
- `app/erp.py` — optional, best-effort writes of finalized orders and
  service/front-desk requests to Supabase (see **Supabase (optional)**
  below). A no-op with no project configured.
- `app/voice/stt.py` / `app/voice/tts.py` — speech-to-text via Groq-hosted
  Whisper; text-to-speech auto-routed by script (Groq's Orpheus for
  English, Sarvam AI's Bulbul for Hindi).
- `app/voice/recorder.py` — push-to-talk mic recording, CLI only.
- `app/voice/livekit_worker.py` + `livekit_llm.py` + `livekit_tts.py` +
  `livekit_rooms.py` — the realtime/interruptible voice worker (see
  **Realtime voice (LiveKit)** below), a separate process from the rest
  of the backend.
- `app/voice/livekit_tokens.py` — mints tokens and dispatches that worker
  for the web app's "Call" button; lives in the main API process (uses the
  lightweight `livekit-api` package, not the full agents runtime).
- `app/main.py` — the FastAPI app; see **API** below.
- `app/static/` — a minimal legacy text/voice frontend (pre-dates `web/`),
  still served at the backend's own `/` for a quick sanity check without
  running the Next.js app.
- `cli.py` / `voice_cli.py` — text/voice REPLs for testing the agent
  directly, no frontend needed.

**Frontend (`web/`, Next.js 16 App Router)**
- `src/lib/personas.ts` — the four personas' identity, tone, and
  `layout: "grid" | "direct-chat"`.
- `src/app/chat/[slug]/page.tsx` — one dynamic route for all four
  personas; branches on `layout`.
- `src/components/ordering-page.tsx` + `src/components/menu/product-grid.tsx`
  — the `"grid"` layout (Zaika, Fatafat, Khidmat): a browsable, filterable
  product grid with instant add/remove, plus a persistent cart/service-log
  panel.
- `src/components/chat/floating-chat-widget.tsx` — the floating chat/voice
  bubble used by the `"grid"` personas.
- `src/components/chat/chat-widget.tsx` — the `"direct-chat"` layout
  (Swagat): chat is the whole page.
- `src/components/chat/chat-panel.tsx` — the actual message list + text
  input + mic button, shared by both layouts above.
- `src/hooks/use-chat-session.ts` — one hook owning session id, messages,
  cart, service log, mic recording (`MediaRecorder` → `/api/chat/voice`),
  and the direct (non-agentic) cart calls. Both layouts are built on it.
- `src/app/api/*/route.ts` — the proxy layer to the Python backend (see
  **Architecture** above).
- `src/app/admin/page.tsx` — the staff view (see **Staff view** below):
  polls `/admin/orders` and `/admin/requests` every 8s, with a one-click
  resolve action.
- `src/components/voice/realtime-call.tsx` + `realtime-call-panel.tsx` —
  the realtime voice call UI (see **Realtime voice (LiveKit)** below),
  built on `@livekit/components-react`.

## Setup

**Backend:**

```bash
cd voice-ordering-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in:
#  GROQ_API_KEY      from console.groq.com/keys  (LLM tool-calling, STT, English TTS)
#  GOOGLE_API_KEY    from aistudio.google.com/apikey  (embeddings only)
#  SARVAM_API_KEY    sign up at indus.sarvam.ai, then get your key from their console  (Hindi TTS)
#  SUPABASE_URL / SUPABASE_SERVICE_KEY  optional — see "Supabase (optional)" below
```

The English TTS model (`canopylabs/orpheus-v1-english`) requires a one-time
terms acceptance in the Groq console before it'll serve requests: open
https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english
and accept the terms there. Everything else, including Hindi TTS, works
without this.

The first run also builds both catalogs' embedding indexes, which together
take **~3-4 minutes** (throttled on purpose to stay under Gemini's
free-tier rate limit — see `app/rag/menu_store.py`). Every run after that
reuses the persisted index (`chroma_db/`) and starts almost instantly,
unless `menu.json` or `grocery.json` changed.

**Frontend:**

```bash
cd web
npm install
cp .env.example .env.local   # BACKEND_URL defaults to http://localhost:8000
npm run dev
# open http://localhost:3000
```

## Run it

**Web app** (all four personas, product grids, floating chat/voice,
cart/service panels):

```bash
# terminal 1
uvicorn app.main:app --reload
# terminal 2
cd web && npm run dev
# open http://localhost:3000
```

**CLIs** (no browser needed):

```bash
python cli.py                  # text, online persona (Zaika)
python cli.py quick_commerce   # text, quick-commerce persona (Fatafat)
python cli.py waiter           # text, waiter persona (Khidmat)
python cli.py hotel            # text, hotel persona (Swagat)

python voice_cli.py            # voice, online persona
python voice_cli.py waiter     # voice, waiter persona
# (quick_commerce / hotel work the same way)
```

Try things like:
- Zaika: "What vegetarian mains do you have?" / "Add two margherita pizzas and a garlic naan" / "That's everything, check out"
- Fatafat: "Add a shampoo and a pack of batteries" / "Do you have anything for a headache?"
- Khidmat: "Can you bring me a glass of water?" / "This is cold, can you reheat it?" / "Can we get the bill?"
- Swagat: "Can I get extra towels for room 204?" / "The AC isn't working" / "I'd like to check out"

Everything above also works in Hindi, or mixed Hindi/English, for both
text and voice — spoken replies too: the agent replies in whichever
language you used, and `app/voice/tts.py` routes Hindi text to Sarvam AI
and English text to Groq's Orpheus automatically.

In the web app, voice is push-to-talk: click the mic, speak, click again
(or the stop icon) to send. It needs HTTPS or `localhost` for mic access —
both the Next.js dev server and a real deployment satisfy that.

## API

All persona-aware endpoints take a `persona` value of `online`,
`quick_commerce`, `waiter`, or `hotel`.

```
POST /chat          {"session_id", "message", "persona"} -> reply + cart + service_log
POST /chat/voice     multipart: audio file + session_id + persona (query params) ->
                     transcript, reply, cart, service_log, and base64 WAV audio
GET  /menu?persona   -> that persona's catalog (food menu, or the separate
                        grocery catalog for quick_commerce)
POST /cart/add       {"session_id", "persona", "item_id", "quantity"} -> cart
POST /cart/remove    {"session_id", "persona", "item_id", "quantity"} -> cart
GET  /admin/orders   -> {"configured", "orders": [...]}  (requires Supabase)
GET  /admin/requests -> {"configured", "requests": [...]}  (requires Supabase)
POST /admin/requests/{id}/resolve -> the updated request row
POST /livekit/token -> {"session_id", "persona"} -> {"configured", "url",
                     "token", "room"} for the web app's realtime call button
                     (see "Realtime voice (LiveKit)"). configured=false with
                     no token when LiveKit isn't set up.
GET  /health
```

`/cart/add` and `/cart/remove` deliberately bypass the LLM — tapping "Add"
on a product card is a deterministic action with nothing to interpret, so
there's no reason to spend a Groq call (or ~1-3s of latency) on it. The
agent's own `add_to_cart`/`remove_from_cart` tools still handle it when the
customer asks by voice or text instead of clicking.

```bash
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"session_id": "demo", "persona": "waiter", "message": "bring me some napkins"}'
```

## Supabase (optional)

A lightweight "ERP" layer: finalized orders and every service/front-desk
request get written to Supabase, on top of the in-memory per-session cart
that already drives the conversation. It's entirely optional — without it,
everything above works exactly the same, just without that durability /
staff-visibility layer.

To enable it:
1. Create a free project at [supabase.com](https://supabase.com).
2. Run `supabase/schema.sql` in its SQL editor (creates `orders` and
   `requests` tables) — do this before setting the env vars below, or
   writes will fail with "Could not find the table 'public.orders'".
3. In `.env`, set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. For
   `SUPABASE_SERVICE_KEY`, go to Settings → API Keys → "Publishable and
   secret API keys" tab and copy the **secret** key (starts with
   `sb_secret_`) — not the publishable key (`sb_publishable_...`). The
   secret key is the one with `BYPASSRLS`; the publishable key is the
   client-safe one and can't write past Row Level Security. (Supabase is
   retiring the older `anon`/`service_role` naming for this same
   publishable/secret split — new projects only get the new names.)

`app/erp.py` picks this up automatically on the next restart; with it
unset, `app/erp.py`'s writes are no-ops.

### Staff view

With Supabase configured, open `/admin` in the web app (there's a "Staff
view" link at the bottom of the landing page) for a live, auto-refreshing
(every 8s) view of open service/front-desk requests across all four
personas — with a one-click "Mark resolved" — plus recent orders. It's
unauthenticated for now (see **Known limitations** below); the `/admin/*`
backend routes it calls are read/update-only and report `configured: false`
with an empty list rather than erroring when Supabase isn't set up.

## Realtime voice (LiveKit)

Alongside push-to-talk (click the mic, speak, click again to send), every
persona's chat panel now has a phone icon: **realtime, interruptible
voice** — speak naturally, barge in on the agent mid-sentence — via
[LiveKit Agents](https://docs.livekit.io/agents/). Live and verified end
to end against a real LiveKit Cloud project, not just in isolation.

**Backend:**
- `app/voice/livekit_llm.py` — adapts a `RestaurantOrderingAgent` to
  LiveKit's `llm.LLM` interface. It doesn't replay LiveKit's chat history
  into the agent — the agent's own LangGraph `MemorySaver` already tracks
  that — it just forwards the latest utterance to `agent.send()`.
- `app/voice/livekit_tts.py` — adapts `app/voice/tts.py`'s existing
  English/Hindi routing (Groq Orpheus / Sarvam Bulbul) to LiveKit's
  `tts.TTS` interface, instead of a second TTS integration.
- `app/voice/livekit_worker.py` — the worker entrypoint: Groq Whisper for
  STT (same model the push-to-talk path uses), Silero VAD for turn
  detection/barge-in, the two adapters above for the brain and the voice.
  Reads which persona and session to resume from the room name
  (`sarthi__{persona}__{session_id}`, see `app/voice/livekit_rooms.py`,
  unit tested). Runs as its own long-lived process, separate from
  `uvicorn app.main:app`.
- `app/voice/livekit_tokens.py` + `POST /livekit/token` (see **API**) —
  mints a room token for the web app's "Call" button and dispatches the
  worker into that room, using the lightweight `livekit-api` package (not
  the full agents runtime) so the main API stays lean.

**Frontend (`web/`):**
- `src/components/voice/realtime-call.tsx` — fetches a token, then mounts
  `@livekit/components-react`'s `<LiveKitRoom>` with the mic auto-published.
- `src/components/voice/realtime-call-panel.tsx` — the in-call UI: a
  `BarVisualizer` that animates with the agent's actual speech (brand
  violet, driven by `useVoiceAssistant()`'s `listening`/`thinking`/
  `speaking` state), a live transcript via `useTranscriptions()`, and hang
  up. Themed through LiveKit's `--lk-*` CSS custom properties rather than
  its default styling.
- The call button lives in `ChatPanel` next to the push-to-talk mic, so
  it's available in both the floating widget (Zaika/Fatafat/Khidmat) and
  the full-page chat (Swagat).

**Verified live** (see git history for the session transcript): a test
client minted a real token, the worker was dispatched and correctly
resolved persona + session from the room name, Silero VAD and turn
detection initialized, `SarthiTTS` called the real Groq Orpheus endpoint
and streamed audio into the room, and a browser subscribed to and played
that track. The one leg not exercisable from this environment is a real
browser granting microphone permission — verify that yourself by opening
the web app in an actual browser (not a sandboxed preview) and clicking
the phone icon.

**Running the worker:**
```bash
pip install -r requirements-livekit.txt   # separate from requirements.txt —
                                           # pulls in onnxruntime for Silero VAD
python -m app.voice.livekit_worker dev    # connects to LiveKit Cloud, local dev
```
You can also test the worker directly with no frontend at all via LiveKit's
[Agents Playground](https://agents-playground.livekit.io).

**Known limitation**: the worker is a separate OS process from
`uvicorn app.main:app`, so a realtime voice session gets its own fresh
in-memory cart — it won't see a simultaneous text/push-to-talk session's
cart for "the same customer" until session state moves into Supabase (or
another shared store), the same caveat this README already notes for
`MemorySaver`.

## Deploying (free demo links)

Backend (FastAPI) on [Render](https://render.com), frontend (Next.js) on
[Vercel](https://vercel.com) — both have a genuinely free tier.

**Backend — Render:**
- **Embeddings are baked into the image**, not rebuilt at startup. Free
  hosts wipe the filesystem on every restart/spin-down, and rebuilding
  200+ items' embeddings live would immediately hit Gemini's free-tier
  rate limit. So `chroma_db/` (both the `restaurant_menu` and
  `grocery_catalog` collections) is committed to the repo and copied into
  the image as-is — **whenever you change `menu.json` or `grocery.json`,
  rebuild locally first** (start the backend once, which constructs both
  `MenuStore`s) and commit the updated `chroma_db/` before redeploying.
- The server image doesn't need `sounddevice`/`soundfile`/`numpy` — those
  are mic/speaker libraries only the local CLIs use, split into
  `requirements-cli.txt` so `requirements.txt` (what the Dockerfile
  installs) stays free of system audio dependencies.
- Steps: push to GitHub → Render **New → Web Service** → connect the repo
  → **Environment: Docker** (finds the root `Dockerfile` automatically) →
  add `GROQ_API_KEY`, `GOOGLE_API_KEY`, `SARVAM_API_KEY` (and the two
  `SUPABASE_*` vars if using it) → Deploy. Free tier spins down after 15
  minutes idle and takes about a minute to wake back up — fine for a demo
  link, not production traffic.

**Frontend — Vercel:**
- This is a monorepo: set the Vercel project's **Root Directory** to
  `web/`. Vercel only ever builds/deploys from there.
- Add one environment variable: `BACKEND_URL` = your Render backend's URL.
- Deploy. Mic access works out of the box — Vercel serves over HTTPS by
  default, which is all `getUserMedia` requires.

**Known limitations of this setup** (fine for a demo, not for real
traffic): sessions/carts live in memory (`app/main.py`'s `sessions` dict,
and LangGraph's `MemorySaver`), so a backend restart or spin-down loses
all active conversations, and it can't run more than one backend instance.
A production version would swap `MemorySaver` for `PostgresSaver` (same
interface, different backing store) and move the in-memory cart into
Supabase (or wherever `MemorySaver` lands) too. The `/admin` staff view is
also unauthenticated — fine for a local demo, but add real auth (Supabase
Auth, or at least a password gate) before deploying it somewhere public.

## Tests

```bash
pytest
```

Only the cart/service/hotel tools are unit tested (no API key needed) —
14 tests, pure logic, no network calls. The agent loop, RAG retrieval, and
voice pipeline are exercised manually via the CLIs and web app, since
those need live API calls.

## Roadmap

1. ✅ **Text-only agent** — tool calling, cart state, RAG over the menu.
2. ✅ **Speech-to-text** — mic input via Whisper (Groq).
3. ✅ **Text-to-speech** — Orpheus (Groq) for English, Sarvam AI's Bulbul
   for Hindi, routed automatically by script.
4. ✅ **Two personas → four personas** — Zaika, Fatafat, Khidmat, Swagat,
   all under the Sarthi brand, sharing one engine.
5. ✅ **Hindi voice output**, alongside the Hindi STT/understanding that
   already worked.
6. ✅ **Next.js frontend** — product grids with instant add/remove,
   floating chat/voice widget, and a separate 100-item grocery catalog for
   quick-commerce, distinct from the restaurant menu.
7. ✅ **Working push-to-talk voice in the web app** (`MediaRecorder` →
   `/chat/voice`), on top of the CLI voice path that already worked.
8. ✅ **Supabase ERP, verified live** — checkout and every service/
   front-desk request persist for real, confirmed through an actual agent
   conversation, not just a direct insert.
9. ✅ **Staff-facing admin view** — `/admin`: live orders and open
   requests across all four personas, with a one-click resolve action.
10. ✅ **Real-time, interruptible voice** — LiveKit Agents worker wrapping
    the existing agent (not rewriting it), verified live end to end against
    a real LiveKit Cloud project; a "Call" button with an animated,
    speech-reactive voice UI sits in every persona's chat panel alongside
    push-to-talk. Only the actual mic-permission-granted path is unverified
    from this environment (sandboxed browser can't grant mic access) —
    needs a real-browser check.
11. **A shared cart/session store** (Supabase or similar) so a realtime
    voice session and a text/push-to-talk session for the same customer
    see the same cart, instead of each process keeping its own.
12. **Admin auth, misheard-order recovery, a demo video.**

## Swapping components

- LLM: swap `ChatGroq` in `app/agent/graph.py` for any LangChain chat model (e.g. `ChatAnthropic`, `ChatGoogleGenerativeAI`, `ChatOpenAI`).
- Embeddings: swap `GoogleGenerativeAIEmbeddings` in `app/rag/menu_store.py` for `VoyageAIEmbeddings`, `OpenAIEmbeddings`, or a local `sentence-transformers` model.
- Vector store: swap `Chroma` for Pinecone/Weaviate/etc. once you need it hosted rather than in-process.
- Conversation persistence: swap LangGraph's `MemorySaver` for `PostgresSaver`/`SqliteSaver` (same interface) once sessions need to survive a restart.
