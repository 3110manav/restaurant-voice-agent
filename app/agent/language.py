"""The conversation's language: an explicit setting, not a guess.

The web app's English / हिन्दी toggle sends the language with every message and call. From it:
  - the agent gets a one-line LANGUAGE instruction at the end of every model call (agent/graph.py),
  - speech-to-text is told which language to expect (voice/stt.py, the LiveKit worker),
  - the reply is checked to be in that language's script (agent/guardrails.py),
  - text-to-speech uses that language's voice instead of guessing from the script (voice/tts.py).
So one stray Hindi word, or one mis-heard clip, can no longer flip the whole conversation.

Hindi is written in Devanagari (so the Hindi voice reads it properly), with prices as digits
followed by रुपये and dish names kept as they are on the menu.
"""

import re

DEFAULT = "en"
LANGUAGES = {"en": "English", "hi": "Hindi"}


def normalize(value: str | None) -> str:
    return value if value in LANGUAGES else DEFAULT


def _is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


def has_devanagari(text: str) -> bool:
    return any(_is_devanagari(ch) for ch in text)


def devanagari_share(text: str) -> float:
    """Fraction of the letters in `text` that are Devanagari (0.0 when it has no letters)."""
    letters = [ch for ch in text if ch.isalpha()]
    return sum(_is_devanagari(ch) for ch in letters) / len(letters) if letters else 0.0


def reply_in_language(reply: str, language: str) -> bool:
    """Is `reply` written in `language`? English means no Devanagari at all; Hindi means mostly
    Devanagari (dish names stay in English letters, so not entirely)."""
    if language == "hi":
        return devanagari_share(reply) >= 0.25 or not any(ch.isalpha() for ch in reply)
    return not has_devanagari(reply)


def use_hindi_voice(text: str, language: str | None) -> bool:
    """Which text-to-speech voice reads `text`. The conversation's language decides; only when
    none was given (the legacy CLIs) does it fall back to looking at the script."""
    if language in LANGUAGES:
        return language == "hi"
    return has_devanagari(text)


_DIRECTIVES = {
    "en": (
        "LANGUAGE: English. Reply only in English, in Latin letters, even if the guest writes Hindi "
        "words or Devanagari. Say prices in words followed by 'rupees'."
    ),
    "hi": (
        "LANGUAGE: Hindi. Reply only in simple, everyday spoken Hindi written in Devanagari, the way a "
        "waiter in India would speak, even if the guest writes English. Keep dish names exactly as on the "
        "menu. Write prices as digits followed by रुपये, for example 560 रुपये."
    ),
}


def directive(language: str) -> str:
    return _DIRECTIVES[normalize(language)]


AGENT_NAMES_HI = {"Meera": "मीरा", "Veer": "वीर", "Kabir": "कबीर", "Ira": "इरा"}


def greeting(language: str, agent_name: str, restaurant_name: str | None = None) -> str:
    if normalize(language) == "hi":
        name = AGENT_NAMES_HI.get(agent_name, agent_name)
        place = f"{restaurant_name} में आपका स्वागत है। " if restaurant_name else ""
        return f"नमस्ते, {place}मैं {name} हूँ।"
    place = f"welcome to {restaurant_name}. " if restaurant_name else ""
    return f"Namaste, {place}I'm {agent_name}." if place else f"Namaste, I'm {agent_name}."


# Fixed lines for when the model isn't asked (or its reply was rejected twice). Gender-neutral Hindi.
LINES = {
    "en": {
        "injection": "I can only help with your order and anything you need at the table. What would you like to have?",
        "empty": "Sorry, I didn't catch that. Could you say it once more?",
        "busy": "Sorry, I'm a little busy right now. Could you say that again in a moment?",
        "order": "I haven't placed that order yet. Shall I go ahead and place it?",
        "cart": "Let me make sure I get that right. What would you like me to add or change?",
        "service": "Let me get someone to help with that. One moment please.",
        "amount": "Let me double check that price for you. Which dish did you mean?",
        "dump": "What are you in the mood for? Something light, or something filling?",
        "default": "Sorry, could you say that once more?",
    },
    "hi": {
        "injection": "ऑर्डर और टेबल से जुड़ी बातों में ही मदद हो पाएगी। आप क्या लेना चाहेंगे?",
        "empty": "माफ़ कीजिए, ठीक से सुनाई नहीं दिया। क्या आप फिर से कह सकते हैं?",
        "busy": "माफ़ कीजिए, अभी थोड़ी भीड़ है। कृपया थोड़ी देर बाद फिर से कहिए।",
        "order": "अभी ऑर्डर दिया नहीं गया है। क्या मैं ऑर्डर दे दूँ?",
        "cart": "ज़रा ठीक से समझ लेते हैं। आप क्या जोड़ना या बदलना चाहेंगे?",
        "service": "अभी किसी को बुला देते हैं। एक पल रुकिए।",
        "amount": "ज़रा क़ीमत दोबारा देख लेते हैं। आप किस डिश की बात कर रहे हैं?",
        "dump": "आज क्या खाने का मन है? कुछ हल्का, या भरपेट?",
        "default": "माफ़ कीजिए, क्या आप फिर से कह सकते हैं?",
    },
}


def line(language: str, key: str) -> str:
    return LINES[normalize(language)][key]


# A short spoken acknowledgement, said the moment the guest stops talking while the model works,
# so a 2-3 second wait does not feel like silence. Fixed phrases: their audio is cached, so they
# play with no speech-generation delay.
ACKS = {
    "en": {"action": ["Sure.", "Okay.", "Got it."], "question": ["Let me check.", "One moment."]},
    "hi": {"action": ["ठीक है।", "जी।", "बिल्कुल।"], "question": ["ज़रा देखते हैं।", "एक पल।"]},
}
_SMALL_TALK = re.compile(
    r"^\s*((ok(ay)?|alright|great|good|nice|cool|perfect)[\s,]+)?"
    r"(hi|hello|hey|namaste|namaskar|thanks?( a lot| so much| very much)?|thank you( so much| very much)?|bye|goodbye|"
    r"okay|ok|yes|yeah|yep|no|nope|sure|fine|नमस्ते|धन्यवाद|शुक्रिया|हाँ|हां|नहीं|ठीक है)"
    r"([\s,]+(please|thanks|thank you))?[\s.!?।]*$",
    re.I,
)
_QUESTION = re.compile(r"^\s*(what|which|how|is|are|do|does|can|could|tell|क्या|कौन|कैसे|कितना)\b|\?\s*$", re.I)


def all_acks(language: str) -> list[str]:
    pools = ACKS[normalize(language)]
    return [phrase for pool in pools.values() for phrase in pool]


def pick_ack(text: str, language: str, count: int = 0) -> str | None:
    """The acknowledgement to say while the model works on `text`, or None for small talk and
    one-word answers (they get their reply fast enough on their own). `count` rotates the phrases."""
    if len(text.split()) < 3 or _SMALL_TALK.match(text):
        return None
    pool = ACKS[normalize(language)]["question" if _QUESTION.search(text) else "action"]
    return pool[count % len(pool)]
