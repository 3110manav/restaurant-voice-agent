# Restaurants on Sarvam Samvaad: setup, step by step

One Samvaad agent answers for every restaurant, in the browser and on the phone. Samvaad hears, thinks and
speaks. The menu, cart, order rules and WhatsApp stay in this backend, which Samvaad calls as API tools.

```
Browser (/sarvam page, Sarvam web SDK)  ─┐
                                         ├─ Samvaad agent "Sarthi Restaurants"
Phone (Exotel number → Samvaad inbound) ─┘      │  store_slug says which restaurant
                                                │
                     API tools (Bearer SAMVAAD_TOOL_TOKEN)
                                                ▼
FastAPI  /samvaad/start   /samvaad/tools/{tool}   /samvaad/end        (app/samvaad/)
   │  menu search, cart, sizes, upsell hints, read-back rule, totals, order save
   ▼
Supabase (restaurants, dishes, phone_stores, orders, phone_calls)  →  WhatsApp bill + owner alert
```

Each step ends with a check. Don't move on until it passes.

---

## Step 1. Onboard each restaurant (backend)

A restaurant needs its menu in Supabase (it already has one if it shows at `/r/<slug>`) **and** a phone-store
row with the owner's WhatsApp and UPI. That row is what Samvaad looks up.

```bash
python -m app.phone.setup_store add --slug slice-station --name "Slice Station" --type restaurant --agent Kabir --owner 9198XXXXXXXX --upi yourid@bank --payee "Slice Station" --restaurant slice-station
```

Repeat for each restaurant (`saffron-table`, `sarson-da-khet`, …). The phone-store slug and the restaurant slug
can be the same.

**Check:** `GET /samvaad/browser/config` lists the restaurant under `stores` (it lists them once Step 2's
Sarvam IDs are set).

## Step 2. Environment variables

On the API (Render) and in your local `.env`:

| Variable | Value |
|---|---|
| `SAMVAAD_TOOL_TOKEN` | A long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SARVAM_API_KEY` | Already set |
| `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `SARVAM_APP_ID` | From the Samvaad console, once the agent exists (Step 4) |
| `SARVAM_APP_VERSION` | Optional: pin a committed agent version for the demo |
| `SAMVAAD_DEFAULT_STORE` | Optional: the slug that answers a phone call when no store can be found from the call |
| `PUBLIC_BASE_URL` | Already used for pay links: the API's public https address |

Samvaad has to reach the API over the internet. Use the Render URL. For local testing, run a tunnel
(for example `cloudflared tunnel --url http://localhost:8000`) and use its https address.

**Check:**

```bash
curl -s -X POST "$API/samvaad/tools/search_menu" -H "Authorization: Bearer $SAMVAAD_TOOL_TOKEN" -H "content-type: application/json" -d '{"interaction_id":"test-1","store_slug":"slice-station","query":"spicy pizza"}'
```

This returns `result` with real dishes. (This curl starts a call log row; nothing is ordered.)

## Step 3. Create the agent in Samvaad

New agent, single state, named **Sarthi Restaurants**. Languages: Hindi and English. Use a Bulbul voice.

### Variables (Variables tab)

| Name | Default | Filled by |
|---|---|---|
| `store_slug` | empty | browser (`agent_variables`) or the start tool |
| `store_name` | `our restaurant` | start tool |
| `agent_name` | `Kabir` | start tool |
| `channel` | `phone` | browser sends `browser` |
| `language` | `Hindi` | browser |
| `cart_summary` | `empty` | every cart tool (Save reply into variables) |

On inbound phone calls, map the caller's number into a variable `caller` (telephony metadata). If your
telephony connection exposes the **dialled** number, map it into `called_number`. That is how one agent knows
which restaurant was called. If it doesn't, see Step 6.

### Greeting

> Namaste! @store_name mein aapka swagat hai, main @agent_name. Aaj kya order karenge?

### Instructions (paste as is)

```
You are @agent_name, the ordering assistant for @store_name, a restaurant. You take food orders by voice
in Hindi, English or a mix, and you always answer in the language the guest is using. Keep every reply to one or
two short sentences: this is a phone call.

Everything about the menu, prices, the cart and the order comes from your tools. Never guess a dish, price or
total, and never add up money yourself.

- When the guest asks what there is, or describes what they want, call search_menu.
- Never suggest or promise a dish unless a tool result lists it.
- Write dish names in English letters, exactly as the menu or search_menu spells them, with every word
  ("Paneer Tikka Pizza", not "Paneer Tikka").
- Call add_to_cart only for the NEW dishes the guest asked for in their latest message, once per dish. Never call it
  again for a dish already in the cart, unless the guest asks for more of it. If a tool says a dish comes in sizes,
  ask which one, then call add_to_cart with the size.
- If a tool result starts with "NOT ADDED", that dish is not on the menu: never tell the guest it was added.
- If a tool result says "Ask the customer which one" (a size, or which of several dishes), ask the guest that
  question right away, in one short sentence, and wait for their answer. Never move on to the address, read-back
  or checkout while the cart is empty or a question is still open.
- To reduce or remove a dish ("ek hi karo", "hata do"), call remove_from_cart with how many to take away. Do not
  call add_to_cart for it.
- A tool result may contain a line starting "[HINT FOR YOU ONLY". Follow it, and never read it out.
- When they are done, ask whether it is delivery or pickup (and the address for delivery), then call
  set_order_details.
- If a tool result contains "Say exactly this to the guest:", say that sentence word for word and nothing else.
  It is the read-back, the order confirmation, or a question such as the WhatsApp number for the bill.
- When the guest gives a WhatsApp number, call set_order_details again with it in whatsapp_number.
- Ask for the guest's name when you take the address, and pass it as customer_name. If they would rather not say, leave it empty.
- A change to one dish ("biryani without beans", "extra spicy"): put it in the item's note, or call add_note for a dish already in the cart. A wish about the whole order ("deliver after 8", "no cutlery"): call add_special_request. Never promise either will definitely be done.
- Only after the guest clearly says yes to the read-back, call checkout. If they change anything, the tools will
  ask for a new read-back first.
- Never say the order is placed unless the checkout result starts with "Order placed". If it says "Order not
  placed", tell the guest what is still needed and do it.
- Never calculate or say a total yourself. Only say a total that a tool result gives you.
- If the guest wants a person, has a complaint, or you cannot understand them after two tries, call
  request_callback.
- Always speak the guest's language (Hindi, English or a mix). Never switch to English unless they do.
- Don't repeat what the guest just said, and don't read the order or the address back yourself: the tools do that
  once, at the right moment. Confirm new dishes in one short sentence.
- After the order is placed, say the order-placed sentence and end the call straight away.
```

## Step 4. The tools

Create each one as an **API tool → Real integration**. Common settings for all of them:

- **Method:** POST, **Auth:** Bearer token = `SAMVAAD_TOOL_TOKEN` (stored in Secrets)
- **Body:** JSON, always including
  `{"interaction_id": "@Interaction ID", "store_slug": "@store_slug", "caller": "@caller", "called_number": "@called_number", "channel": "@channel", "language": "@language"}`
- **Max wait:** 10 s. **If it fails:** "Sorry, one moment, let me check that again."
- **Save reply into variables:** `cart_summary` ← `cart_summary`
- **Response template:** `{{result}}`. For `set_order_details`, `read_back_order` and `checkout`, use
  `{{result}} {{say}}`.

| Tool name | When | URL | Extra body fields the agent fills | Description for the agent |
|---|---|---|---|---|
| `start_call` | on_start | `/samvaad/start` | none | Loads the restaurant. Save reply into variables: `store_slug`, `store_name`, `agent_name` |
| `search_menu` | During conversation | `/samvaad/tools/search_menu` | `query` | Find dishes by name, ingredient, taste or diet |
| `get_item_details` | During conversation | `/samvaad/tools/get_item_details` | `name` | Price, sizes, spice level and ingredients of one dish |
| `add_to_cart` | During conversation | `/samvaad/tools/add_to_cart` | `item_name`, `quantity`, `variant`, `note` (or `items`: a list of `{name, quantity, variant, note}`) | Add dishes the guest asked for. `note` is a change to that dish in the guest's words ("without beans") |
| `add_note` | During conversation | `/samvaad/tools/add_note` | `item_name`, `note`, `variant` | A change to a dish already in the cart. The kitchen sees it on the WhatsApp ticket |
| `add_special_request` | During conversation | `/samvaad/tools/add_special_request` | `request` | A wish about the whole order, not one dish: "deliver after 8 pm", "no cutlery" |
| `remove_from_cart` | During conversation | `/samvaad/tools/remove_from_cart` | `item_name`, `quantity`, `variant` | Remove a dish or reduce its quantity |
| `view_cart` | During conversation | `/samvaad/tools/view_cart` | none | Read the cart and total |
| `set_order_details` | During conversation | `/samvaad/tools/set_order_details` | `order_type` (delivery/pickup), `address`, `whatsapp_number`, `customer_name` | Save delivery or pickup, the address, the guest's name if given, and a WhatsApp number for the bill |
| `read_back_order` | During conversation | `/samvaad/tools/read_back_order` | none | Read the full order back before placing it |
| `checkout` | During conversation | `/samvaad/tools/checkout` | none | Place the order, only after the guest said yes to the read-back |
| `request_callback` | During conversation | `/samvaad/tools/request_callback` | `reason` | Ask the restaurant to call the guest back |
| `end_call_log` | on_end | `/samvaad/end` | `"transcript": "@Call Transcript"`, `"end_reason"`, `"call_length"` | Closes the call log; a cart left without an order is marked abandoned |

How the agent's choices get into the body depends on Samvaad's tool editor. If it lets a tool declare
parameters, declare the extra fields above as parameters. Otherwise create them as agent variables and
reference them with `@`. The API accepts `item_name`/`quantity`/`variant` or an `items` list, and ignores
blank or unfilled values.

**Check:** use the agent's built-in test chat to order "do margherita medium" from `slice-station`
(set `store_slug` in the test's variables). The cart should update, and `read_back_order` should return
a `say` with the total.

Commit the agent version. Copy the org, workspace and app IDs into the API's environment (Step 2).

## Step 5. Browser calls

The web app's **/sarvam** page lists the restaurants, starts a Sarvam call with the chosen `store_slug`, shows
the live transcript and the live cart, and shows "Order placed" when it happens. The Sarvam key never reaches
the browser: the SDK's signed-URL request goes through `/api/sarvam/...` to the API, which adds it.

**Check:** open `/sarvam`, pick Slice Station, press Start call, order a pizza. The live order panel fills in.
Microphone access needs https (localhost is fine).

## Step 6. Phone calls

1. In Samvaad's telephony settings, connect Exotel (bring your own) or rent a number.
2. Create an **inbound deployment** for the agent and attach the restaurant numbers.
3. Set the deployment's webhook to `POST {API}/samvaad/end` with the same Bearer token.
4. Make sure each restaurant's number is on its phone-store row:
   `python -m app.phone.setup_store use slice-station +91XXXXXXXXXX`.

How the call finds its restaurant, in order: `store_slug` → the dialled number (`called_number`) →
`SAMVAAD_DEFAULT_STORE`. If Samvaad can't pass the dialled number, use one deployment per restaurant and set
that restaurant's `store_slug` as its default. Or, for the demo, use one number with `SAMVAAD_DEFAULT_STORE`.

**Check:** call the number, order, and confirm the order shows at `/admin/calls` and the WhatsApp bill arrives.

## Step 7. Investor demo checklist

- [ ] 2–3 restaurants onboarded with real-looking menus and photos
- [ ] Render on a paid instance (no 50 s cold start), `SARVAM_APP_VERSION` pinned
- [ ] WhatsApp templates approved, so the bill and owner alert actually arrive on stage
- [ ] Demo script: browser call in Hinglish → size question → drink suggestion → read-back → yes →
      WhatsApp bill on a phone → owner taps Accept → then the same order by phone call
- [ ] Rehearse on the venue's network. Have a recorded video as a fallback.

## Limits of this version

- Carts live in the API's memory for up to 3 hours, so run one API instance (moving them to Supabase is next).
- Kirana and pharmacy stores that live in the shop database aren't wired to Samvaad yet. Catalog kiranas and
  restaurants are.
- Tool names and rules match `app/phone/ordering.py`. Change the order rules there, not in the Samvaad prompt.
