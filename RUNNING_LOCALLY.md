# Sarthi - Local Run & Setup Guide

A quick reference guide with ready-to-copy commands for running the Sarthi voice ordering agent locally.

---

## 📋 Quick Status Check

Make sure you are in the project root directory:
```bash
cd /Users/work/Desktop/projects/voice-ordering-agent
```

Check that your `.env` file exists:
```bash
ls -la .env
```
*(Your API keys for Groq, Google Gemini, Sarvam AI, Supabase, and LiveKit are already pre-configured in `.env`)*

---

## 🚀 Running the Full Web App

To run the web app, you will need **2 terminal tabs** (or 3 if you want LiveKit real-time voice calls).

### Terminal 1: Backend API (FastAPI)

```bash
cd /Users/work/Desktop/projects/voice-ordering-agent
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- **Health check URL**: [http://localhost:8000/health](http://localhost:8000/health) (should return `{"status":"ok"}`)
- **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Terminal 2: Web Frontend (Next.js)

```bash
cd /Users/work/Desktop/projects/voice-ordering-agent/web
npm run dev
```

- **Web App URL**: [http://localhost:3000](http://localhost:3000)
- **Staff Admin View**: [http://localhost:3000/admin](http://localhost:3000/admin)

Once both are running, open **[http://localhost:3000](http://localhost:3000)** in Chrome/Safari to test:
- 🍕 **Meera** (`/chat/online`): Food delivery ordering
- 🛒 **Veer** (`/chat/quick_commerce`): Instant grocery shopping
- 🍽️ **Kabir** (`/chat/waiter`): Dine-in restaurant table service & bill
- 🛎️ **Ira** (`/chat/hotel`): Hotel room service, housekeeping & front desk

---

### Terminal 3 (Optional): Real-time Voice Worker (LiveKit)

If you want to use the **phone icon** in the chat for full duplex, interruptible real-time voice calls:

```bash
cd /Users/work/Desktop/projects/voice-ordering-agent
source .venv/bin/activate
python -m app.voice.livekit_worker dev
```

*(Note: Push-to-talk mic inside the web chat works directly through Terminal 1 without needing this worker).*

---

## 💻 Running Terminal CLIs (No Browser Needed)

If you want to test the LLM agent and tools directly inside your terminal:

### 1. Interactive Text Chat

```bash
cd /Users/work/Desktop/projects/voice-ordering-agent
source .venv/bin/activate

# Choose any persona:
python cli.py                  # Meera (Food Delivery)
python cli.py quick_commerce   # Veer (Grocery)
python cli.py waiter           # Kabir (Restaurant Waiter)
python cli.py hotel            # Ira (Hotel Assistant)
```

### 2. Push-to-Talk Voice in Terminal

*Uses your computer's microphone and speakers directly:*

```bash
cd /Users/work/Desktop/projects/voice-ordering-agent
source .venv/bin/activate

python voice_cli.py            # Meera (Food Delivery)
python voice_cli.py waiter     # Kabir (Restaurant Waiter)
python voice_cli.py hotel      # Ira (Hotel Assistant)
```

---

## 🗣️ Things to Try (English & Hindi)

| Persona | Sample Test Prompts |
|---|---|
| **Meera** (Food) | *"What vegetarian pizzas do you have?"*<br>*"2 Margherita pizza aur ek garlic bread add kar do"*<br>*"What's in my cart?"* / *"Checkout"* |
| **Veer** (Grocery) | *"Add a Dove shampoo and AA batteries to my cart"*<br>*"Mujhe sar dard ke liye kuch chahiye"*<br>*"View cart"* |
| **Kabir** (Waiter) | *"Can you bring a glass of cold water to table 4?"*<br>*"Bhaiya bill le aao please"*<br>*"This soup is cold, please reheat it"* |
| **Ira** (Hotel) | *"Can I get fresh towels for room 302?"*<br>*"AC thik se kaam nahi kar raha hai"*<br>*"I'd like to request checkout"* |

---

## 🛠️ Troubleshooting & Helpers

### Kill any running servers / free ports 8000 and 3000
If you get `Address already in use` error:
```bash
kill -9 $(lsof -ti :8000) 2>/dev/null
kill -9 $(lsof -ti :3000) 2>/dev/null
```

### Test Backend Directly with cURL
```bash
curl -s http://localhost:8000/health
```

### Test Chat API with cURL
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test1", "persona": "online", "message": "What pastas do you have?"}'
```
