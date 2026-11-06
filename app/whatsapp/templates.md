# WhatsApp message templates

The wording lives in `app/whatsapp/template_defs.py`. Easiest: `python -m app.whatsapp_templates --waba-id <id> --submit`
submits them all and `--status` shows which are approved. The text below is for submitting by hand in WhatsApp
Manager instead, and it matches the code.

Submit these in Meta's WhatsApp Manager (Message templates > Create). Category **Utility**, language
**English**. Use exactly these names and variable positions: the code fills `{{1}}`, `{{2}}`... in this
order. Approval usually takes minutes to a day. Until a template is approved Meta rejects that message
(the order itself is never affected, and a failed send is recorded in `whatsapp_messages`).

**Start with three** (`sarthi_order_alert`, `sarthi_rx_order`, `sarthi_rx_request`): they cover the owner's
alert, the pharmacist's alert and asking for the prescription photo. Submit the other three the same day so
they are ready: a confirmation to the caller, a status update after the owner replies, and the pharmacist's
"photo arrived" nudge. Alerts go to a DIFFERENT phone from the store's business number (a number can't
message itself): the owner's or pharmacist's own phone.

Sample values for Meta's review form are in brackets.

## For the shop owner

**sarthi_order_alert**
```
Order {{1}} from {{2}} needs a prescription check. Items: {{3}}. Status: {{4}} Reply with CONFIRM or REJECT followed by the order code once it is checked.
```
[K7M2P] [Ravi (+919876543210)] [2 x Moisturizing Soap Bar, 1 x AA Batteries] [Rs 225] [Deliver to: 15 Shanti Nagar, Vashi]

**sarthi_rx_order** (the pharmacist)
```
Prescription order {{1}} from {{2}}: {{3}}. The customer {{4}} Reply with CONFIRM or REJECT followed by the order code once it is checked.
```
[K7M2P] [Ravi (+919876543210)] [1 x Azithral 500 [Rx]] [the customer will send the prescription on WhatsApp, and the order waits for it.]

**sarthi_rx_received** (the pharmacist, when the photo arrives)
```
Prescription received for order {{1}} from {{2}}. Reply with SHOW followed by the order code to view it, then CONFIRM or REJECT.
```
[K7M2P] [Ravi (+919876543210)]

## For the customer

**sarthi_order_confirmation**
```
Hi {{1}}, thanks for ordering from {{3}}. Your order {{2}}: {{4}}. Total {{5}}. We will update you when the store confirms it.
```
[Ravi] [K7M2P] [Gupta General Store] [2 x Moisturizing Soap Bar] [Rs 225]

**sarthi_rx_request**
```
Hi {{1}}, your order {{2}} at {{3}} includes a prescription medicine. Please reply here with a clear photo of the prescription so our pharmacist can confirm it.
```
[Ravi] [K7M2P] [Care Plus Medicals]

**sarthi_order_update**
```
Hi {{1}}, an update on your order {{2}}: {{3}} Reply here if you need help.
```
[Ravi] [K7M2P] [Good news: your order K7M2P at Care Plus Medicals is confirmed.]

## Notes
- Template names can be changed with `WHATSAPP_TPL_*` environment variables (see `.env.example`).
- Replies to a customer who has just messaged the store, and an owner's replies to the alerts, are free-form
  and need no template.
- Do not put promotions in these: Meta re-classifies promotional wording as Marketing, which costs more.
