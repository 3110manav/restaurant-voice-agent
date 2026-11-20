"""Hindi script to rough Roman letters, so a dish said as "पनीर टिक्का पिज़्ज़ा" finds "Paneer Tikka Pizza".

Speech-to-text and voice LLMs often write dish names in Devanagari while menus are in English. This is
not a proper transliteration: it only has to land close enough for the fuzzy name match in
app/menu/snapshot.py. Long vowels are written the way Indian menus usually spell them ("ee", "oo"), and
the inherent "a" is dropped at the end of a word ("पनीर" -> "paneer", not "paneera"). ड़ and ढ़ become "d" and "dh", the way menus spell them ("kadai", "pakoda").
"""
from __future__ import annotations

import re

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f", "ळ": "l",
}
_NUKTA_BASE = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "ड": "ड़", "ढ": "ढ़", "फ": "फ़"}
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e",
}
_MATRAS = {
    "ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_MARKS = {"ं": "n", "ँ": "n", "ः": "h"}
_VIRAMA, _NUKTA = "्", "़"
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text or ""))


def to_roman(text: str) -> str:
    """Devanagari letters in `text` become Roman ones; everything else is kept as is."""
    if not has_devanagari(text):
        return text
    chars = list(text)
    out: list[str] = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if i + 1 < len(chars) and chars[i + 1] == _NUKTA and ch in _NUKTA_BASE:
            ch, i = _NUKTA_BASE[ch], i + 1  # a consonant written as letter + dot below
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            elif nxt in _CONSONANTS or nxt in _NUKTA_BASE or nxt in _MARKS:
                out.append("a")  # the inherent vowel between consonants
            # at the end of a word the inherent vowel is silent
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _MARKS:
            out.append(_MARKS[ch])
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
        elif ch in (_NUKTA, _VIRAMA) or ch in _MATRAS:
            pass  # a stray mark with no letter before it
        else:
            out.append(ch)
        i += 1
    return "".join(out)
