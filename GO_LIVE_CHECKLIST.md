# Phone ordering on Samvaad: go-live checklist

Restaurant phone orders through one Samvaad agent (Kabir) and our tool API (`app/samvaad/`).
Setup steps: [SARVAM_SETUP.md](SARVAM_SETUP.md). Earlier pilot plan: [SARVAM_PILOT_CHECKLIST.md](SARVAM_PILOT_CHECKLIST.md).

## Where we are (19 Nov 2026)

- [x] Kabir agent with 11 tools, working through an ngrok tunnel
- [x] Stores for `slice-station`, `saffron-table`, `sarson-da-khet` (owner WhatsApp 8976448886, no UPI: pay on delivery)
- [x] **First real phone order placed end to end**: YFUAQK, 2 Margherita Pizza + 2 Garlic Breadsticks, ₹1,300,
      delivery; bill and owner alert sent on WhatsApp; call log "ordered"
- [x] Dish names said in Hindi script match the English menu (`app/menu/translit.py`)
- [x] Remove from cart works with Hindi or other spellings
- [x] Read-back always carries the real items and total, even when the WhatsApp number is still missing
- [x] Tool replies put the exact words to say inside `result` ("Say exactly this to the guest: …")
- [x] Search results tell the agent to add a dish the guest already asked for
- [x] Tool calls without an interaction ID (Samvaad's Send button) and IDs containing "/" both work
- [ ] Today's code changes committed (503 tests pass)

**Seen in testing:** Samvaad's LLM repeated tool calls, picked the wrong dish ("Paneer Tikka" for Paneer Tikka
Pizza), skipped a dish it had just found, ignored "say exactly", and twice told the guest an order was placed
with a made-up total when checkout had refused it. The backend rules held every time. Watch this in the
complex-order tests below.

---

## 1. User journeys

### Customer (phone)

```
Dials the restaurant's number → Kabir greets (by name if known)
→ asks about the menu / orders dishes (sizes, add-ons, "no onion")
→ changes their mind (add / reduce / remove)
→ delivery or pickup → address (or the saved one)
→ read-back with the exact total → "haan"
→ order saved → WhatsApp bill
→ updates: accepted / out of stock / out for delivery
→ pays on delivery (UPI later)
```

Unhappy paths to handle: restaurant closed · dish out of stock · "manager se baat karao" · call drops mid-order ·
silence or a noisy line · wrong number or prank · "same as last time".

### Restaurant owner

```
Onboarding: menu, prices, hours, WhatsApp, phone number
→ gets each order on WhatsApp with Accept / Out of stock / Paid
→ the customer is told automatically
→ switches dishes off when they run out, sees calls and orders, sets upsells
```

### Us (operations)

See every call (transcript, outcome, cost) · alerts when WhatsApp or tools fail · onboard a restaurant in minutes.

---

## 2. Missing before go-live

### P0: before real customers

- [ ] **Stable hosting**: Render paid instance (Singapore or India region) instead of ngrok; update all tool URLs
- [ ] **Carts in the database** (Supabase) instead of API memory: a restart or reload loses live orders
- [ ] **Never drop an order for a missing WhatsApp number**: save it, alert the owner, skip only the bill
- [ ] **`quantity` = total wanted** in add_to_cart: a repeated "ek hi karo" removed a whole dish
- [ ] **WhatsApp business number + approved templates**: today it is Meta's test number (5 recipients), and
      customers who never messaged us are refused (error 131047)
- [ ] **One number per restaurant**, and confirm the dialled number reaches `start_call`
      (else: `store_slug` per deployment, or one agent copy per restaurant)
- [ ] **Opening hours**: closed means no orders, and say when it opens
- [ ] **Add-ons and notes** in the cart: "extra cheese", "no onion", half-and-half, combos; shown in the read-back,
      the owner's order and the bill
- [ ] **Transfer or callback to the restaurant**, tested on a real call
- [ ] **Owner buttons tested end to end**: Accept / Out of stock / Paid, and the customer is told
- [ ] **Samvaad plan with enough concurrent calls**: pay-as-you-go allows 4 at once across all restaurants;
      Pro 10, Growth 30
- [ ] **Security**: rotate `SAMVAAD_TOOL_TOKEN` (shared during testing), protect `/sarvam`, keep keys out of logs

### P1: during the pilot

- [ ] Returning customers: saved address and name from the `customers` table (backend, then the Samvaad
      variables `customer_name`, `saved_address`, `last_order`, which are already in the instructions)
- [ ] A guide for each restaurant (`@restaurant_guide` from `/samvaad/start`)
- [ ] Upsell settings for each restaurant (promoted dishes, pairings, combos)
- [ ] Order status messages to the customer
- [ ] Dashboard for owners and for us (calls, orders, cost per call)
- [ ] Alerts when tools or WhatsApp fail
- [ ] Faster `start` (0.9 s today, before the greeting): keep menus preloaded
- [ ] Load test: 10–30 calls at once
- [ ] Samvaad settings: try the strongest LLM on offer, and tune end-of-speech timing
- [ ] **Background noise cuts the read-back** (real call 20 Nov, order 6VE4F7): lower barge-in sensitivity or
      require a minimum speech length, turn on noise suppression, and shorten the read-back (skip the WhatsApp
      line when it's the caller's own number)
- [ ] `end_call_log` sends an empty transcript: set its `transcript` row to the built-in Call Transcript variable
- [ ] Not-on-the-menu dishes: show the search hint only when the named dish is in the result, and add the
      instruction line "never add a different dish in its place without the guest agreeing" (Maggiano's Pizza)
- [ ] Kabir swapped Paneer Tikka Pizza for Paneer Tikka on its own (20 Nov call): check it's fixed by the
      full-dish-name instruction

### P2: after the pilot

- [ ] Petpooja: push orders into the restaurant's POS, ideally pull menus
- [ ] UPI pay links and QR
- [ ] Pharmacy, on our own stack (LiveKit + Groq + Sarvam voice) for its stricter safety rules
- [ ] Analytics
- [ ] Fewer numbers via call forwarding, if Sarvam passes the original (diversion) number

### Questions for Sarvam

1. On inbound calls, do tools receive the **dialled number**?
2. On forwarded calls, do they receive the **original (diversion) number**?
3. Can an inbound deployment set **agent variables** (e.g. `store_slug`) per number?
4. Can an agent use a **custom LLM** endpoint (OpenAI-compatible)? Which LLMs can we pick?
5. Do unused prepaid minutes carry over? Pilot pricing or startup credits? Growth concurrency at Pro price?
6. Bulk pricing for 100+ numbers?

---

## 3. Complex-order test plan

**How:** 30–40 scripted calls, each with an expected final cart and total. Run them as Samvaad simulated tests
(₹2 each) or browser calls, and real phone calls for the final round. After each call, check the ngrok log
(http://localhost:4040), `orders`, `message_outbox` and `phone_calls`.

**Score each call:** final cart exactly right? Read-back before checkout? Any order placed without a "haan"?
Any total or confirmation the agent made up?

### Scenarios (The Saffron Table)

| # | Type | Guest says | Expected |
|---|---|---|---|
| 1 | Several in one breath | "Do Margherita, ek Paneer Tikka Pizza, ek Penne Arrabbiata aur teen breadsticks" | 4 lines, quantities exact |
| 2 | Reduce | "Margherita ek hi karo" | Margherita = 1 (not 0) |
| 3 | Remove | "Penne hata do" | Penne gone |
| 4 | Swap | "Penne ki jagah Fettuccine Alfredo kar do" | Penne out, Alfredo in |
| 5 | Correction mid-sentence | "Teen breadsticks… nahi nahi, do" | Breadsticks = 2 |
| 6 | Hindi names | "मार्गरीटा पिज़्ज़ा aur मिसो सूप" | Margherita + Miso Soup |
| 7 | Vague | "Ek dosa de do" | Kabir asks which dosa |
| 8 | Not on the menu | "Butter chicken milega?" | Says no, offers alternatives |
| 9 | Description | "Kuch spicy veg starter batao" | Search, then a suggestion |
| 10 | Price question | "Paneer Tikka Pizza kitne ka hai?" | ₹590, from the tool |
| 11 | Total mid-order | "Abhi tak kitna hua?" | The exact cart total |
| 12 | Change after the read-back | Read-back, then "ek Miso Soup aur add karo", then "haan" | New read-back before checkout |
| 13 | Add-ons *(fails until add-ons are built)* | "Margherita extra cheese ke saath, onion nahi" | Add-on and note saved |
| 14 | Wants a human | "Manager se baat karni hai" | Callback alert to the owner |
| 15 | Rejects the read-back | "Nahi, galat hai" | Fixes the order, reads back again |
| 16 | Pickup | "Main khud le jaunga" | Pickup, no address asked |
| 17 | Silence | *(stay silent for 10 s)* | A polite prompt, then ends gracefully |
| 18 | Upsell | Orders a pizza only | One drink or dessert suggestion, said once |

The full reference order (scenarios 1–5 in one call): 1 Margherita Pizza ₹470 + 1 Paneer Tikka Pizza ₹590 +
1 Penne Arrabbiata ₹460 + 2 Garlic Breadsticks ₹360 + 1 Miso Soup ₹200 = **₹2,080**.

### Go-live bar

| Measure | Pass if |
|---|---|
| Final cart correct: simple / medium / complex | ≥ 98% / ≥ 93% / ≥ 85% |
| Orders placed without a "haan" | 0 |
| Totals or confirmations the agent made up | 0 |
| Read-back before checkout | 100% |

**Decision:** if Samvaad misses the bar after the P0 fixes (especially made-up totals), run the same scenarios
on our Groq stack and compare before going live.

---

## Testing notes

- Samvaad's **Test agent** (browser) sends the tester's **email** as the caller, so there is no WhatsApp number
  and checkout waits for one. Real phone calls send the caller's number automatically.
- Send "hi" from the test phone to the WhatsApp test number (+1 555-617-6465) within 24 hours before a test,
  or Meta refuses the messages.
- Every tool needs the token in its **Auth** tab; pasting a cURL doesn't fill it. Body rows must be variables,
  not text left over from the cURL (only `called_number` stays as empty text).
- ngrok adds about 0.1–0.35 s per tool call; phone calls are slower than browser mostly because of the phone
  network and 8 kHz audio.
