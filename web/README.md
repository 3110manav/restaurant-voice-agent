# Sarthi — web

The Next.js frontend for [Sarthi](../README.md): a product grid + floating
chat/voice widget for Meera, Veer, and Kabir, and a direct full-page
chat for Ira. See the root README for the full architecture, the four
personas, and how this talks to the Python backend.

## Run it

```bash
npm install
cp .env.example .env.local   # BACKEND_URL defaults to http://localhost:8000
npm run dev
# open http://localhost:3000
```

The Python backend (`uvicorn app.main:app --reload` from the repo root)
needs to be running too — this app proxies every API call to it through
its own Route Handlers under `src/app/api/`.

## Deploying

Vercel, with the project's **Root Directory** set to `web/` (this is a
monorepo — the Python backend lives at the repo root). One environment
variable: `BACKEND_URL`, pointing at the deployed backend.
