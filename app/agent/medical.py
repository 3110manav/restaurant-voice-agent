"""Safety rules for the pharmacy agent. Plain code, like the rest of the guardrails.

The agent is a shop assistant, not a doctor or a pharmacist. It never diagnoses, never gives a
dose, and never says a medicine cures anything. These rules do not rely on the model behaving:

  screen_input  - what the customer says. A medical emergency, or a question about doses, side
                  effects, pregnancy or babies, is answered with a fixed line and never reaches
                  the model; the staff are told through a request row.
  reply_issues  - what the agent says. A reply that gives a dose or schedule, or names a
                  diagnosis or a cure, is rejected and regenerated (see guardrails.check_reply).

The patterns lean toward handing over to a person: a false alarm costs a short callback, a
miss costs far more. English, Hindi in Devanagari, and the common romanised Hindi are covered.
"""
import re

EMERGENCY = re.compile(
    r"chest pain|heart attack|can'?t breathe|cannot breathe|(trouble|difficulty|hard) (in )?breathing|"
    r"short(ness)? of breath|not breathing|unconscious|passed out|fainted|seizure|convulsion|having (a )?fit\b|"
    r"severe bleeding|bleeding (a lot|heavily|badly|won'?t stop)|overdose|too many (tablets|pills)|"
    r"swallowed (a lot|many|the whole|poison)|poison|snake ?bite|\bstroke\b|slurred speech|face (is )?drooping|"
    r"suicid|want to die|kill myself|swollen (face|lips|tongue|throat)|anaphyla|"
    r"सीने में दर्द|साँस नहीं|सांस नहीं|साँस लेने में|सांस लेने में|बेहोश|दौरा|ज़हर|जहर|ओवरडोज़?|ज़्यादा गोलियाँ|ज्यादा गोलियां|"
    r"seene mein dard|saans nahi|saans lene mein|behosh|zeher|jahar",
    re.I,
)

# Dose, schedule, safety and interaction questions: a pharmacist answers those, not us.
ADVICE = re.compile(
    r"\bdos(e|es|age)\b|how (many|much)\b[^.?!]{0,30}\b(should|can|do) (i|we|he|she|they)\b|"
    r"\b(should|can|could) (i|we) (take|give|have|use)\b|can (my |our )?(child|baby|kid|son|daughter|mother|father|wife|husband) "
    r"(take|have|use)\b|\b(twice|thrice|once) (a|per) day\b|times a day|every \d+ hours|before or after (food|meals)|"
    r"empty stomach|\bsafe (to|for|with)\b|side[- ]effects?|\binteract(s|ion|ions)?\b|with alcohol|mix(ing)? (it |them )?with|"
    r"खुराक|कितनी (गोली|गोलियाँ|गोलियां|मात्रा|बार)|कितने (बार|दिन)|साइड इफ़?ेक्ट|खाली पेट|खाने के (बाद|पहले)|"
    r"kitni goli|kitni baar|khurak|khaali pet",
    re.I,
)
SPECIAL_CASE = re.compile(
    r"pregnan|breast ?feed|nursing mother|newborn|new[- ]born|infant|\b\d+[- ]?(day|week|month)s?[- ]old\b|"
    r"गर्भ|प्रेग्नेंट|दूध पिला|नवजात|garbhwati|pregnant",
    re.I,
)

# Words that give instructions to take something, or name a diagnosis or a cure.
_DOSING = re.compile(
    r"\b(take|give|have)\s+(one|two|three|half|a|an|\d+)\b[^.?!]{0,40}\b(tablets?|capsules?|pills?|ml|spoons?|teaspoons?|drops?|sachets?)\b|"
    r"\b(once|twice|thrice|\d+\s*times)\s+(a|per|every)\s+(day|daily|hour|night)\b|\bevery\s+\d+\s+hours?\b|"
    r"\b(after|before) (food|meals?)\b|\bfor\s+\d+\s+days?\b|\bon an empty stomach\b|"
    r"दिन में \S+ बार|खाने के (बाद|पहले)|गोली (लें|खाएँ|खाएं)|\d+ दिन तक",
    re.I,
)
_DIAGNOSIS = re.compile(
    r"(?<!if )(?<!when )(?<!unless )(?<!in case )(?<!while )\byou (have|are suffering|probably have|might have|seem to have|must have)\b|"
    r"\bit(?:'s| is) (a|an|probably|likely|just)\b[^.?!]{0,30}\b(infection|flu|virus|viral|allergy|fever)\b|"
    r"\b(will|can|should|would) (cure|heal|treat|fix|clear)\b|\bcures?\b|\bI (can |will )?diagnose\b|\bthe diagnosis\b|"
    r"आपको .{0,20}(है|हुआ है)\b.{0,10}(इन्फेक्शन|बुखार|एलर्जी)|ठीक कर (देगा|देगी)|इलाज करेगा",
    re.I,
)


def screen_input(text: str) -> str | None:
    """"emergency", "advice", or None for an ordinary message (see the module docstring)."""
    if EMERGENCY.search(text):
        return "emergency"
    if ADVICE.search(text) or SPECIAL_CASE.search(text):
        return "advice"
    return None


def reply_issues(reply: str) -> list[str]:
    """What is wrong with a pharmacy reply, as violation kinds ("dosage_advice", "diagnosis")."""
    issues = []
    if _DOSING.search(reply):
        issues.append("dosage_advice")
    if _DIAGNOSIS.search(reply):
        issues.append("diagnosis")
    return issues


def has_dosing(text: str) -> bool:
    """Used offline to check that catalog text carries no dose or schedule."""
    return bool(_DOSING.search(text))
