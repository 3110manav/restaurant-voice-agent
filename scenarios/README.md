# Call scenarios to debug

Real or test calls with something worth fixing, kept so they can be replayed later. Each file has what the guest
said, what the agent said, the tool calls our API got, and what to change.

| Date | File | Store | Order | Problem |
|---|---|---|---|---|
| 20 Nov 2026 | [verbose-readback-2PBTR9.md](2026-11-20-verbose-readback-2PBTR9.md) | saffron-table | 2PBTR9, ₹720 | Order right, but ~30–35 s of a 2 min call was repetition |

**Adding one:** copy the latest file, name it `YYYY-MM-DD-short-problem-ORDERREF.md`, and add a row above. Tool calls
come from the ngrok inspector (http://localhost:4040) or the API logs; the transcript from Samvaad's call log or a
recording (transcribe with Groq Whisper).
