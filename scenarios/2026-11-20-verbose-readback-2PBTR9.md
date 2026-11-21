# Verbose read-back: the order and address said twice (2PBTR9)

- **When:** 20 Nov 2026, 16:49:51–16:51:51 (≈ 2 min)
- **Where:** Samvaad test agent (browser), so the caller was an email and the WhatsApp number had to be asked
- **Store:** `saffron-table`
- **Order placed:** 2PBTR9, 1 Paneer Tikka ₹340 + 2 Garlic Naan ₹180 + 1 Masala Dosa ₹200 = **₹720**, delivery.
  Correct, and the bill and owner alert were sent.
- **Recording:** `~/Desktop/WhatsApp Ptt 2026-11-20 at 4.51.53 PM.ogg` (not in the repo)

**Problem:** the order was right, but about 30–35 s of the call was repetition. At Samvaad's ₹3.50/min that is
≈ ₹2 a call if billed per second (see question 7 for Sarvam in GO_LIVE_CHECKLIST.md).

## What was said (Whisper transcript, shortened)

| Time | Who | Said |
|---|---|---|
| 0–5 s | Kabir | Namaste, Saffron Table mein aapka swagat hai, main Kabir… aaj kya order karenge? |
| 5–10 s | Guest | Veg Kolhapuri, ek Paneer Tikka aur do Garlic Naan |
| 10–21 s | Kabir | Maaf kijiye, Veg Kolhapuri hamare menu mein nahi hai. Iski jagah Paneer Tikka Masala, Paneer Tikka Pizza, Bombay Sandwich le sakte hain. |
| 21–25 s | Kabir | Baaki Paneer Tikka aur Garlic Naan add kar diye hain. Kya aap kuch aur lena chahenge? |
| 25–28 s | Guest | Shahi Paneer de do aur ek Butter Naan bhi |
| 28–33 s | Kabir | Maaf kijiye, Shahi Paneer hamare menu mein nahi hai… *(Butter Naan the same)* |
| 33–48 s | | Dosa → "which one?" → Masala Dosa; delivery |
| 48–69 s | Guest | Address: 1902 A Wing, Modi Space, Ganges, opposite Bhagwati Hospital, Borivali West |
| **69–84 s** | Kabir | **Aapka order: 1 Paneer Tikka, 2 Garlic Naan, 1 Masala Dosa, kul 720 rupaye. 1902 A Wing… Borivali West par delivery.** Bill WhatsApp par bhejna hai, aapka WhatsApp number bata dijiye? |
| 84–88 s | Guest | 89764 48886 |
| 88–92 s | Kabir | *(in English)* Would you like to add Gulab Jamun for dessert? → Guest: no |
| **92–113 s** | Kabir | *(in English)* **Your order is 1 Paneer Tikka, 2 Garlic Naan and 1 Masala Dosa, total 720 rupees, for delivery to 1902 A Wing, Modi Space, Ganges, opposite Bhagwati Hospital, Borivali West. The bill will be sent to WhatsApp number ending 8886.** Shall I confirm? |
| 113–120 s | Kabir | *(in English)* Your order is placed, the bill is on WhatsApp, you can pay on delivery. Thank you. |

## Tool calls (ngrok)

| Time | Tool | Sent | Our reply (short) |
|---|---|---|---|
| 16:50:02 | add_to_cart ×3 in parallel | Paneer Tikka 1 · Veg Kolhapuri 1 · Garlic Naan 2 | Added · **NOT ADDED** + 3 alternatives · Added (+ drink and side hint) |
| 16:50:17 | add_to_cart ×2 in parallel | Shahi Paneer 1 · Butter Naan 1 | **NOT ADDED** ×2, 3 alternatives each (Butter Naan offered *Butter Chicken*) |
| 16:50:36 | add_to_cart | Dosa | could mean Masala / Plain / Rava / Mysore Masala Dosa |
| 16:50:45 | add_to_cart | Masala Dosa | Added, ₹720 |
| 16:50:55 | set_order_details | delivery, "1902 ए विंग" | WhatsApp missing → **full summary + address** + ask for number |
| 16:50:59 | set_order_details | delivery, full address | the same full summary again |
| 16:51:18 | set_order_details | + whatsapp 89764 48886 | dessert hint (Gulab Jamun) |
| 16:51:24 | read_back_order | | **full read-back again**, with address and "8 8 8 6 वाले नंबर पर" |
| 16:51:43 | checkout | | Order placed 2PBTR9, ₹720 |
| 16:51:51 | end | | transcript and call_length empty |

## What to fix

| # | Waste | ≈ Time | Who | Fix |
|---|---|---|---|---|
| 1 | Order, total and full address said when asking for WhatsApp, then all again in the read-back | 15 s | Backend (`app/phone/ordering.py` `prepare_read_back`) | Ask only "बिल के लिए अपना व्हाट्सएप नंबर बता दीजिए?"; the real read-back follows anyway |
| 2 | Full address in the read-back | 7 s | Backend (`_summary`) | Say only its first part ("1902 A Wing पर डिलीवरी") |
| 3 | "8 8 8 6 वाले नंबर पर" right after the guest said the number | 4 s | Backend (`prepare_read_back`) | Skip it when the number is the caller's own or was just given |
| 4 | 3 alternatives per missing dish; a non-veg one for a veg dish | 4 s each | Backend (`app/samvaad/session.py` `_not_on_menu`) | At most 2, matching veg / non-veg |
| 5 | Two upsells: a drink, then a dessert | 6–8 s | Backend (`app/agent/salesflow.py`, `_dessert_first`) | One per call, with a per-restaurant switch |
| 6 | Read-back and closing switched to English and were reworded | 5 s | Kabir | Instruction: never switch language unless the guest does |
| 7 | ~8 s between "order placed" and hang-up | 5 s | Samvaad | End the call right after the order-placed sentence |

On a real phone call #1 doesn't happen, because the caller's number is the WhatsApp number.

## Replay

Same script on `saffron-table`: "Veg Kolhapuri, ek Paneer Tikka aur do Garlic Naan" → "Shahi Paneer aur ek Butter
Naan" → "Ek dosa" → "Masala Dosa" → delivery + address → WhatsApp number → "nahi" to dessert → "haan".

**Pass:** same order (₹720); the order and address are said once; one upsell at most; the call stays in Hindi;
under 1:30.
