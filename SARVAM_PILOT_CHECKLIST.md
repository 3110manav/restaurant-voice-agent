# Sarvam pilot: what's done, what's missing

Goal: 10–15 restaurants ordering by browser and phone through one Sarvam Samvaad agent, plus an investor demo.
How to do each setup step: [SARVAM_SETUP.md](SARVAM_SETUP.md). Tick items here as they're done.

## Done (branch `feature/sarvam-14nov`, not committed yet)

- [x] Samvaad tool API: `/samvaad/start`, `/samvaad/end`, 9 tools (`app/samvaad/`), behind `SAMVAAD_TOOL_TOKEN`
- [x] Order rules reused from phone orders: totals in code, sizes, suggestions, read-back then yes, WhatsApp bill
- [x] `/sarvam` browser call page with live transcript and live cart; Sarvam key kept on the server
- [x] 21 tests; checked against the real Slice Station menu (no writes)
- [x] Setup guide: agent instructions, variables, all 11 tool configs

---

## Phase A: Get one browser call working (you, about 1 day)

| # | Step | Who | Blocks |
|---|---|---|---|
| A1 | Commit the branch and push it | Claude, on your OK | everything after |
| A2 | ✅ `SAMVAAD_TOOL_TOKEN` in `.env` (still to add on Render) | You | A5 |
| A3 | ✅ Rows for `slice-station` and `kirana-demo` (owner 8976448886, no UPI: pay on delivery). Full test order KG2QE2 passed over HTTP. Add more restaurants the same way | Done | |
| A4 | Deploy the branch's API to Render (or run a tunnel to localhost), so Samvaad can reach it over https | You | A5 |
| A5 | Build the Samvaad agent: variables, greeting, instructions, 11 tools; test in its test chat; commit a version | You | A6 |
| A6 | Put `SARVAM_ORG_ID`, `SARVAM_WORKSPACE_ID`, `SARVAM_APP_ID` (and optional `SARVAM_APP_VERSION`) on the API | You | A7 |
| A7 | First real browser call at `/sarvam`, together | Both | |

**Three unknowns to settle during A5/A7.** Sarvam's docs don't answer these:
- [ ] Is the browser SDK's interaction ID the same one the tools receive? (The live cart panel needs this.)
- [ ] How does Samvaad's tool editor let the LLM fill tool inputs: declared parameters, or agent variables?
- [ ] Do inbound phone calls expose the **dialled** number to tools? (Picks the restaurant on the phone.)

## Phase B: Ready for investors (about 1 week)

| # | Step | Who | Why |
|---|---|---|---|
| B1 | WhatsApp: Meta business verification, approved templates, `WHATSAPP_*` env vars on the API (none are set today) | You | Without it the bill and owner alert only sit in the queue, so the demo's best moment is missing |
| B2 | Protect `/sarvam` with a demo passcode and a per-visitor call limit | Claude | Anyone with the link can start Sarvam calls and spend your credits |
| B3 | Render paid instance, plus a warm-up ping from the `/sarvam` page | You + Claude | No 50-second cold start on stage |
| B4 | Deploy the web branch to Vercel with `BACKEND_URL` set | You | The demo runs on a real https link (the mic needs https) |
| B5 | Phone line: connect Exotel in Samvaad, inbound deployment, webhook to `/samvaad/end`, number on the phone store | You | Phone half of the demo |
| B6 | Rehearse the demo script on the venue's network; record a fallback video | You | |

## Phase C: Pilot with 10–15 restaurants (weeks 2–6)

| # | Step | Who | Why |
|---|---|---|---|
| C1 | Move carts from API memory into Supabase | Claude | A restart or a second instance loses live carts today |
| C2 | Per-call cost and latency log (Sarvam minutes, tool timings) in `phone_calls` | Claude | Price the product |
| C3 | Per-restaurant upsell settings (promoted dishes, pairings, combos) + owner console tab | Claude | Restaurants ask for this; feeds Samvaad through tool replies |
| C4 | Petpooja: push placed orders (and ideally pull menus) | Claude, after you get partner API access | Orders land in the restaurant's POS |
| C5 | Onboard 10–15 restaurants: menu, photos, owner WhatsApp, UPI, phone number | You (Claude can script the menu import) | |
| C6 | Clean up migration numbering (two 002s, two 003s) and confirm what production has applied | Claude | Safe onboarding |
| C7 | Fix the owner-alert template text in `app/whatsapp/templates.md` (it doesn't match the code) | Claude | Templates submitted by hand would be rejected or fail |
| C8 | Kirana and pharmacy stores from the shop database on Samvaad | Claude | Only restaurants and catalog kiranas work today |
