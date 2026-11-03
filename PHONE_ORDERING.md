# Phone ordering prototype

A customer calls a store, the agent takes the order, and WhatsApp gets the rest: the owner receives the
order with buttons, and the customer receives the bill with a UPI QR and pay link.

```
Caller → Exotel → LiveKit SIP → worker (app/voice/livekit_phone.py)
                                  Saaras hears, the agent acts, Bulbul speaks
                                  ↓ customer says yes to the read-back
                       Supabase: order + queued messages, saved together
                                  ↓
                       WhatsApp queue (app/phone/outbox.py), with retries
                         ├─ owner: order + Accept / Out of stock / Paid
                         └─ customer: bill + QR + pay link
                                  ↓ owner taps
                       POST /whatsapp/webhook → order updated, customer told
```

## 1. Database

Run `supabase/migrations/002_phone_ordering.sql` once in the Supabase SQL editor.

## 2. Environment

Add the new values from `.env.example` to the API and the worker (`deploy/worker/secrets.env`), as its
comment describes. Then redeploy both, since each has new dependencies.

Groq's free tier allows 8,000 tokens a minute, and one call can use that up. The agent then waits up to
a minute or asks the caller to repeat themselves. Use a paid Groq plan for real calls.

## 3. Stores

```bash
python -m app.phone.setup_store add --slug kirana-demo --name "Sharma Kirana" --type kirana --agent Veer --owner 9198XXXXXXXX --upi yourid@bank --payee "Sharma Kirana" --catalog app/data/kirana_demo.json
```

```bash
python -m app.phone.setup_store add --slug slice-station --name "Slice Station" --type restaurant --agent Kabir --owner 9198XXXXXXXX --upi yourid@bank --payee "Slice Station" --restaurant slice-station
```

Point the test number at a store. Run this again to switch to the other one:

```bash
python -m app.phone.setup_store use kirana-demo +91XXXXXXXXXX
```

The kirana catalog's prices are made up for the demo. It includes a ₹1 "Test Toffee" for trying a real
UPI payment. To use a real store's items, edit a copy of the file and run `add` again.

## 4. Try it without a phone

This uses the real agent, LLM and database, so an order placed here is real, and its WhatsApp messages
go out if WhatsApp is configured:

```bash
python -m app.phone.simulate kirana-demo +919XXXXXXXXX
```

See the result on the web app at `/admin/calls`, using your `ADMIN_API_KEY`.

## 5. WhatsApp

1. Create a Meta developer app with the WhatsApp product. Its free test number can message up to 5
   approved numbers, so add the customer's and the owner's.
2. Set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. The app's temporary token lasts about a day; a
   system user token doesn't expire.
3. Point the webhook at `https://<your API>/whatsapp/webhook`, with `WHATSAPP_VERIFY_TOKEN` as its verify
   token, set `WHATSAPP_APP_SECRET`, and subscribe to `messages`.
4. **Send any message to the test number from both phones.** The prototype uses free-form messages and
   buttons, which only reach someone who has messaged within the last 24 hours. Otherwise Meta refuses
   with error 131047, which shows up on `/admin/calls`. Reaching new customers needs approved templates.

## 6. Exotel and LiveKit

1. Fill in the number in `deploy/sip/inbound-trunk.json`, then create the trunk and rule:
   ```bash
   lk sip inbound create deploy/sip/inbound-trunk.json
   ```
   ```bash
   lk sip dispatch create deploy/sip/dispatch-rule.json
   ```
   The trunk must list only your Exotel number, and `agentName` must match the worker's
   (`LIVEKIT_AGENT_NAME`, by default `sarthi-voice`).
2. Copy the SIP address from the LiveKit console (Telephony → Configuration) and give it to Exotel, who
   map the number to it on their side: [Exotel's guide](https://support.exotel.com/support/solutions/articles/3000134145-livekit-and-exotel-sip-trunking-integration-guide).
3. Ring the number. The agent should greet you as the store.

If nobody answers, check the worker's logs. "no store answers on the dialled number" shows the number
LiveKit received, which is what `setup_store use` must be given.

## Test script

| Test | Do | Passes if |
|---|---|---|
| Kirana order | Order 3 items in Hindi | Items, total and both WhatsApp messages are right |
| Restaurant order | Order a dish with a size, in Hinglish | The right size and price |
| Change of mind | "Do nahi, teen kar do", then remove an item | The read-back and bill match the final order |
| Real payment | Order the Test Toffee, and pay from another person's UPI app | The amount is pre-filled and the money arrives |
| Pay link | Tap the link on the phone that received the bill | Your UPI app opens with the amount |
| Out of stock | Owner taps `Out of stock` | You're told not to pay, and the pay page shows it's cancelled |
| Hard call | Noisy room, interrupting, asking for a person | It recovers, or the owner gets a callback alert |

## Known limits

- **Payment isn't detected.** A plain UPI QR doesn't tell us who paid, so the owner taps `Paid`. Never
  treat a screenshot as proof.
- **Personal UPI IDs** can be refused or limited by UPI apps. Use `--merchant` with a merchant ID.
- **Landlines** that look like mobile numbers pass the first check, then fail at WhatsApp. The owner is
  told to call that customer.
