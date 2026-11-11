"""The wording of every WhatsApp template Sarthi sends, with sample values for Meta's review.

Meta approves each template's text once; at send time only the {{1}}, {{2}}... values change. The names come from
notify.TEMPLATES (the order of the values there matches the numbers here). Rules Meta enforces, kept in mind
below: the text may not start or end with a variable, each variable is numbered once and in order, and a
variable's value cannot contain newlines. `python -m app.whatsapp_templates` submits these and checks their status.
"""
import re

DEFINITIONS: dict[str, dict] = {
    "order_alert": {
        "body": "New order {{1}} from {{2}}: {{3}}. Total {{4}}. {{5}}. Reply with CONFIRM or REJECT followed by the order code.",
        "samples": ["K7M2P", "Ravi (+919876543210)", "2 x Moisturizing Soap Bar, 1 x AA Batteries", "Rs 225", "Deliver to: 15 Shanti Nagar, Vashi"],
    },
    "rx_alert": {
        "body": "Order {{1}} from {{2}} needs a prescription check. Items: {{3}}. Status: {{4}} Reply with CONFIRM or REJECT followed by the order code once it is checked.",
        "samples": ["K7M2P", "Ravi (+919876543210)", "1 x Azithral 500 [Rx]", "the customer will send the prescription on WhatsApp, and the order waits for it."],
    },
    "rx_received": {
        "body": "Prescription received for order {{1}} from {{2}}. Reply with SHOW followed by the order code to view it, then CONFIRM or REJECT.",
        "samples": ["K7M2P", "Ravi (+919876543210)"],
    },
    "order_confirmation": {
        "body": "Hi {{1}}, thanks for ordering from {{3}}. Your order {{2}}: {{4}}. Total {{5}}. We will update you when the store confirms it.",
        "samples": ["Ravi", "K7M2P", "Gupta General Store", "2 x Moisturizing Soap Bar", "Rs 225"],
    },
    "rx_request": {
        "body": "Hi {{1}}, your order {{2}} at {{3}} includes a prescription medicine. Please reply here with a clear photo of the prescription so our pharmacist can confirm it.",
        "samples": ["Ravi", "K7M2P", "Care Plus Medicals"],
    },
    "order_update": {
        "body": "Hi {{1}}, an update on your order {{2}}: {{3}} Reply here if you need help.",
        "samples": ["Ravi", "K7M2P", "Good news: your order K7M2P at Care Plus Medicals is confirmed."],
    },
}

LANGUAGE = "en"
CATEGORY = "UTILITY"
VARIABLE = re.compile(r"\{\{(\d+)\}\}")


def variables(body: str) -> list[int]:
    return [int(n) for n in VARIABLE.findall(body)]


def components(key: str) -> list[dict]:
    """The `components` Meta wants for creating this template."""
    d = DEFINITIONS[key]
    return [{"type": "BODY", "text": d["body"], "example": {"body_text": [d["samples"]]}}]
