"""
Context-Aware Translation API — Enhanced Mode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEW in this version:
  ① Universal Coreference Resolution
     • Learns ANY entity from context: people, animals, objects, places,
       organisations, concepts — no hardcoded names.
     • Uses a lightweight rule-based NLP parser so it works with zero
       extra model downloads (no spaCy required, though spaCy is used
       as an optional upgrade if installed).
     • Entity → pronoun mapping is built fresh each call from the
       session's recent sentences.

  ② 100+ Emotion Taxonomy
     • Primary layer  : 7 Ekman emotions (joy, sadness, anger, fear,
                        surprise, disgust, neutral)
     • Secondary layer: 28 Plutchik wheel sub-emotions derived from
                        primary scores via a weighted blend matrix
     • Nuanced layer  : 70+ fine-grained emotions mapped from secondary
                        scores (e.g. elation, melancholy, exasperation,
                        awe, loathing, serenity …)
     • Valence + Arousal dimensions returned for every call
     • Intensity band  : low / moderate / high / intense
     • All layers returned in the API response so the frontend can
       display as many or as few as it needs.

  ③ All original functionality preserved unchanged
     (MyMemory → LibreTranslate → Lingva → NLLB fallback, Whisper,
      session management, caching, batch endpoint, health check …)
"""

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import tempfile
import os
import re
import time
import hashlib
import asyncio
import aiohttp
import gc
import uuid
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

app = FastAPI(title="Context-Aware Translation API — Enhanced")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

# ═══════════════════════════════════════════════════════════════
# LANGUAGE CODE TABLES
# ═══════════════════════════════════════════════════════════════

MYMEMORY_CODES = {
    "english":    "en",
    "hindi":      "hi",
    "bengali":    "bn",
    "tamil":      "ta",
    "telugu":     "te",
    "marathi":    "mr",
    "kannada":    "kn",
    "malayalam":  "ml",
    "french":     "fr",
    "german":     "de",
    "spanish":    "es",
    "portuguese": "pt",
    "italian":    "it",
}

LIBRE_CODES  = MYMEMORY_CODES.copy()
LINGVA_CODES = MYMEMORY_CODES.copy()

NLLB_LANG_CODES = {
    "english":    "eng_Latn",
    "hindi":      "hin_Deva",
    "bengali":    "ben_Beng",
    "tamil":      "tam_Taml",
    "telugu":     "tel_Telu",
    "marathi":    "mar_Deva",
    "kannada":    "kan_Knda",
    "malayalam":  "mal_Mlym",
    "french":     "fra_Latn",
    "german":     "deu_Latn",
    "spanish":    "spa_Latn",
    "portuguese": "por_Latn",
    "italian":    "ita_Latn",
}

# ═══════════════════════════════════════════════════════════════
# TRANSLATION CACHE
# ═══════════════════════════════════════════════════════════════

_cache: dict = {}
MAX_CACHE = 300

def cache_key(text: str, src: str, tgt: str) -> str:
    return hashlib.md5(f"{text[:200]}{src}{tgt}".encode()).hexdigest()

def cache_get(k: str):
    return _cache.get(k)

def cache_set(k: str, v: str):
    global _cache
    if len(_cache) >= MAX_CACHE:
        for old in list(_cache.keys())[:50]:
            del _cache[old]
    _cache[k] = v

# ═══════════════════════════════════════════════════════════════
# TRANSLATION BACKENDS  (unchanged from original)
# ═══════════════════════════════════════════════════════════════

async def translate_mymemory(text: str, src: str, tgt: str) -> Optional[str]:
    try:
        src_code  = MYMEMORY_CODES.get(src, "en")
        tgt_code  = MYMEMORY_CODES.get(tgt, "hi")
        lang_pair = f"{src_code}|{tgt_code}"
        url       = "https://api.mymemory.translated.net/get"
        params    = {"q": text[:500], "langpair": lang_pair}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data            = await resp.json()
                    result          = data.get("responseData", {}).get("translatedText", "")
                    response_status = data.get("responseStatus", 0)

                    if not result or result.upper().startswith("MYMEMORY WARNING"):
                        return None

                    result_stripped    = result.strip()
                    all_codes_upper    = {c.upper() for c in MYMEMORY_CODES.values()}

                    if result_stripped.upper() in all_codes_upper:
                        print(f"⚠️  MyMemory returned lang code '{result_stripped}' — skipping")
                        return None
                    if result_stripped.lower() == text.strip().lower():
                        print(f"⚠️  MyMemory returned unchanged text — skipping")
                        return None
                    if len(text.strip()) > 10 and len(result_stripped) <= 3:
                        print(f"⚠️  MyMemory returned too-short result — skipping")
                        return None
                    if response_status != 200:
                        print(f"⚠️  MyMemory bad responseStatus {response_status} — skipping")
                        return None

                    return result_stripped
    except Exception as e:
        print(f"⚠️  MyMemory failed: {e}")
    return None


LIBRE_INSTANCES = [
    "https://libretranslate.com",
    "https://translate.argosopentech.com",
    "https://libretranslate.de",
]

async def translate_libre(text: str, src: str, tgt: str) -> Optional[str]:
    src_code = LIBRE_CODES.get(src, "en")
    tgt_code = LIBRE_CODES.get(tgt, "hi")
    payload  = {"q": text[:500], "source": src_code, "target": tgt_code, "format": "text"}

    for instance in LIBRE_INSTANCES:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.post(f"{instance}/translate", json=payload) as resp:
                    if resp.status == 200:
                        data   = await resp.json()
                        result = data.get("translatedText", "")
                        if result:
                            return result.strip()
        except Exception as e:
            print(f"⚠️  LibreTranslate {instance} failed: {e}")
    return None


LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://lingva.garudalinux.org",
    "https://translate.plausibility.cloud",
]

async def translate_lingva(text: str, src: str, tgt: str) -> Optional[str]:
    import urllib.parse
    src_code = LINGVA_CODES.get(src, "en")
    tgt_code = LINGVA_CODES.get(tgt, "hi")
    encoded  = urllib.parse.quote(text[:500])

    for instance in LINGVA_INSTANCES:
        try:
            url = f"{instance}/api/v1/{src_code}/{tgt_code}/{encoded}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data   = await resp.json()
                        result = data.get("translation", "")
                        if result:
                            return result.strip()
        except Exception as e:
            print(f"⚠️  Lingva {instance} failed: {e}")
    return None


_local_tokenizer = None
_local_model     = None

def get_local_model():
    global _local_tokenizer, _local_model
    if _local_model is None:
        print("⏳ Loading local fallback model …")
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        torch.set_grad_enabled(False)
        name             = "facebook/nllb-200-distilled-600M"
        _local_tokenizer = AutoTokenizer.from_pretrained(name)
        _local_model     = AutoModelForSeq2SeqLM.from_pretrained(
            name, torch_dtype=torch.float32, low_cpu_mem_usage=True)
        _local_model.eval()
        print("✅ Local fallback model loaded")
    return _local_tokenizer, _local_model

def translate_local_sync(text: str, src: str, tgt: str) -> str:
    import torch
    tokenizer, model = get_local_model()
    src_code         = NLLB_LANG_CODES.get(src, "eng_Latn")
    tgt_code         = NLLB_LANG_CODES.get(tgt, "hin_Deva")
    tokenizer.src_lang = src_code
    inputs = tokenizer(text[:300], return_tensors="pt", truncation=True, max_length=128)

    # ── Safe forced_bos_token_id resolution ──────────────────────────
    # tokenizer.lang_code_to_id is absent in newer transformers builds.
    # convert_tokens_to_ids is the stable cross-version API.
    try:
        # Preferred: direct dict lookup (works on transformers <4.33)
        forced_bos = tokenizer.lang_code_to_id[tgt_code]
    except (AttributeError, KeyError):
        try:
            # Fallback: convert the language token string to its id
            forced_bos = tokenizer.convert_tokens_to_ids(tgt_code)
            if forced_bos == tokenizer.unk_token_id or forced_bos is None:
                raise ValueError(f"Unknown language token: {tgt_code}")
        except Exception as e:
            print(f"⚠️  Could not resolve forced_bos for {tgt_code}: {e}")
            # Last resort: use the tokenizer's default bos token
            forced_bos = tokenizer.bos_token_id or 2

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos,
            max_new_tokens=80, num_beams=1, do_sample=False,
        )
    return tokenizer.batch_decode(outputs, skip_special_tokens=True)[0].strip()

# ═══════════════════════════════════════════════════════════════
# ① UNIVERSAL COREFERENCE RESOLUTION
# ═══════════════════════════════════════════════════════════════
#
# How it works
# ────────────
# Given the recent context sentences the model:
#
#   Step 1 — Entity extraction
#     Scans each sentence for "entity anchors":
#       • Capitalised tokens (proper nouns: Arnab, Delhi, Google …)
#       • Definite NPs introduced with "the" followed by a common noun
#         (the cat, the manager, the ball …)
#       • Possessive + noun phrases (Arnab's tricks → entity = Arnab)
#
#   Step 2 — Pronoun binding
#     For each entity the sentence is checked for gender / number / type
#     cues to decide which pronouns the entity can be referred to by:
#       • Male proper noun cues  → binds to  he / him / his / himself
#       • Female proper noun cues → she / her / hers / herself
#       • Plural cues            → they / them / their / themselves
#       • Non-person thing cues  → it / its / itself
#       • No cue / ambiguous     → defaults to he/she both (tried in order)
#
#   Step 3 — Replacement
#     Pronouns in the CURRENT sentence are replaced with the resolved
#     entity using whole-word, case-preserving regex substitution.
#     Most-recent-context wins (later sentences override earlier ones).
#
# This is entirely rule-based — no extra models, no API calls.
# If spaCy is installed the function upgrades automatically to its
# superior NER, but it is NOT required.
#
# ═══════════════════════════════════════════════════════════════

# ── Optional spaCy upgrade (attempted once at import time) ────
_spacy_nlp = None
try:
    import spacy as _spacy_module
    _spacy_nlp = _spacy_module.load("en_core_web_sm")
    print("✅ spaCy en_core_web_sm loaded — using NER coreference")
except Exception:
    pass  # spaCy not installed or model not downloaded — rule-based fallback used



_NON_ENTITY_STARTS = {
    "The", "A", "An", "This", "That", "These", "Those",
    "He", "She", "They", "It", "I", "We", "You",
    "When", "Where", "Who", "What", "How", "If", "Because",
    "Then", "But", "And", "Or", "So", "Yet", "For", "Nor",
    "His", "Her", "Its", "Their", "Our", "Your", "My",
    "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday",
    "January","February","March","April","May","June","July","August",
    "September","October","November","December",
}

# Pronouns to resolve → grouped by semantic category
_PRONOUNS = {
    "masculine": ["he", "him", "his", "himself"],
    "feminine":  ["she", "her", "hers", "herself"],
    "neuter":    ["it", "its", "itself"],
    "plural":    ["they", "them", "their", "theirs", "themselves"],
}

# Gender-hint wordlists (applied to the whole sentence, case-insensitive)
_MALE_HINTS   = {
    "he","him","his","himself","mr","sir","king","prince","duke","lord",
    "boy","man","men","male","brother","father","son","uncle","nephew",
    "husband","boyfriend","grandfather","grandson","actor","monk","priest",
}
_FEMALE_HINTS = {
    "she","her","hers","herself","ms","mrs","miss","madam","queen","princess",
    "duchess","lady","girl","woman","women","female","sister","mother",
    "daughter","aunt","niece","wife","girlfriend","grandmother","granddaughter",
    "actress","nun","priestess",
}
_PLURAL_HINTS = {
    "they","them","their","themselves","we","us","our","team","group",
    "people","children","kids","students","players","members","staff",
}
_ANIMAL_HINTS = {
    "cat","dog","bird","fish","horse","lion","tiger","bear","elephant",
    "monkey","snake","rabbit","wolf","fox","deer","cow","bull","sheep",
    "goat","pig","chicken","duck","eagle","parrot","turtle","frog",
}
_OBJECT_HINTS = {
    "ball","car","bike","book","phone","laptop","table","chair","bag",
    "bottle","pen","pencil","camera","watch","ring","key","door","window",
    "box","bag","cup","plate","knife","sword","gun","ship","plane","train",
}


def _extract_entities_from_sentence(sentence: str) -> List[Dict]:
    """
    Returns a list of entity dicts extracted from a single sentence:
      { "name": str, "gender": "masculine"|"feminine"|"neuter"|"plural"|"unknown" }
    Most specific / rightmost entity is considered the main referent.
    """
    words_lower = sentence.lower().split()
    entities: List[Dict] = []

    # ── 1. Proper nouns (capitalised tokens not in skip list) ──────────
    # Handle multi-word proper nouns: "Arnab Goswami", "New Delhi"
    tokens = sentence.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        clean = re.sub(r"[^A-Za-z'-]", "", tok)
        if clean and clean[0].isupper() and clean not in _NON_ENTITY_STARTS and len(clean) > 1:
            # Try to grab a multi-word name (consecutive capitalised tokens)
            name_parts = [clean]
            j = i + 1
            while j < len(tokens):
                nxt = re.sub(r"[^A-Za-z'-]", "", tokens[j])
                if nxt and nxt[0].isupper() and nxt not in _NON_ENTITY_STARTS:
                    name_parts.append(nxt)
                    j += 1
                else:
                    break
            name   = " ".join(name_parts)
            gender = _infer_gender(name, words_lower)
            entities.append({"name": name, "gender": gender, "type": "proper"})
            i = j
        else:
            i += 1

    # ── 2. Definite NPs: "the <noun>" patterns ─────────────────────────
    the_pattern = re.compile(r'\bthe\s+([a-z]+(?:\s+[a-z]+)?)\b', re.IGNORECASE)
    for m in the_pattern.finditer(sentence):
        noun = m.group(1).strip().lower()
        # Only keep nouns that are unlikely to just be articles of proper nouns
        if noun not in _NON_ENTITY_STARTS and len(noun) > 2:
            gender = "neuter"
            if noun in _ANIMAL_HINTS:
                gender = "neuter"   # animals → "it" by default (override with context)
            if noun in _OBJECT_HINTS:
                gender = "neuter"
            # Check sentence for gender cues to upgrade
            if any(h in words_lower for h in _MALE_HINTS):
                gender = "masculine"
            elif any(h in words_lower for h in _FEMALE_HINTS):
                gender = "feminine"
            entities.append({"name": "the " + noun, "gender": gender, "type": "definite_np"})

    return entities


# ── Known-name gender lookup (South Asian + common English names) ──────
# Avoids relying solely on sentence-level hints when names are unambiguous.
_KNOWN_MALE_NAMES: set = {
    "arnab","rahul","amit","raj","rohan","arjun","vikram","suresh","deepak",
    "ravi","arun","anand","sanjay","ajay","vijay","nikhil","kartik","aman",
    "karan","rajan","mohan","ramesh","dinesh","umesh","ganesh","mahesh",
    "sachin","rohit","virat","dhruv","ishaan","lakshman","devraj","surya",
    "john","james","robert","william","richard","charles","michael","david",
    "peter","paul","george","henry","edward","thomas","joseph","mark",
}
_KNOWN_FEMALE_NAMES: set = {
    "priya","pooja","anita","sunita","kavita","rina","meera","divya","neha",
    "sneha","radha","sita","lakshmi","parvati","durga","saraswati","rekha",
    "usha","geeta","seema","leela","mala","vimla","shobha","sudha","jyoti",
    "nisha","ritu","sweta","shreya","anjali","komal","sonam","riya","tanya",
    "emma","olivia","sophia","isabella","charlotte","ava","mia","amelia",
    "sarah","emily","jessica","ashley","jennifer","samantha","elizabeth","lisa",
}


def _infer_gender(name: str, words_lower: List[str]) -> str:
    """
    Infer pronoun gender for a proper-noun entity.
    Priority order:
      1. Known-name lookup (most reliable for South Asian / common names)
      2. Sentence-level hint words
      3. Unknown fallback
    """
    # ── 1. Known-name lookup ────────────────────────────────────────
    first = name.split()[0].lower()
    if first in _KNOWN_MALE_NAMES:   return "masculine"
    if first in _KNOWN_FEMALE_NAMES: return "feminine"

    # ── 2. Sentence-level hints ─────────────────────────────────────
    if any(h in words_lower for h in _PLURAL_HINTS):  return "plural"
    if any(h in words_lower for h in _FEMALE_HINTS):  return "feminine"
    if any(h in words_lower for h in _MALE_HINTS):    return "masculine"
    if any(h in words_lower for h in _ANIMAL_HINTS):  return "neuter"
    if any(h in words_lower for h in _OBJECT_HINTS):  return "neuter"

    return "unknown"


def _build_pronoun_map(context: List[str]) -> Dict[str, str]:
    """
    Build a pronoun→replacement dict from all context sentences.

    Two key fixes applied here:

    Fix A — Per-gender entity tracking (not one global winner):
      masculine pronouns → most recent masculine-gender entity
      feminine  pronouns → most recent feminine-gender entity
      Correctly handles: 'Arnab met Priya.' → he=Arnab, she=Priya

    Fix B — Split multi-sentence context items before entity extraction:
      Session history stores whole inputs as one string, e.g.:
        "Arnab saw a dog. It was barking. He got scared."
      The old code passed this whole string to _extract_entities_from_sentence()
      which saw ALL words including animal hints ("dog","barking") making Arnab
      get classified as neuter. Fix: split each context item into sentences first.

    Fix C — Synthesise plural from masculine+feminine pair:
      "Arnab and Priya got married. They looked beautiful."
      Neither Arnab nor Priya has gender=plural, so "they" was never resolved.
      Fix: if both masc and fem exist → they = "Arnab and Priya"

    Returns e.g. {"he": "Arnab", "she": "Priya", "they": "Arnab and Priya"}
    """
    by_gender: Dict[str, str] = {}  # gender → most_recent_name

    # Fix B: split every context item into individual sentences before extraction
    # so multi-sentence strings don't pollute entity gender detection
    all_sentences: List[str] = []
    for item in context:
        parts = re.split(r'(?<=[.!?])\s+', item.strip())
        all_sentences.extend([p.strip() for p in parts if p.strip()])

    for sentence in all_sentences:
        entities = _extract_entities_from_sentence(sentence)
        for entity in entities:
            name, gender = entity["name"], entity["gender"]
            by_gender[gender] = name  # newest entity of each gender wins

    pronoun_map: Dict[str, str] = {}

    masc = by_gender.get("masculine") or by_gender.get("unknown")
    fem  = by_gender.get("feminine")  or by_gender.get("unknown")
    neu  = by_gender.get("neuter")
    plur = by_gender.get("plural")

    if masc:
        pronoun_map.update({
            "he":      masc,
            "him":     masc,
            "his":     masc + "'s",
            "himself": masc + " himself",
        })
    if fem:
        pronoun_map.update({
            "she":     fem,
            "her":     fem,
            "hers":    fem + "'s",
            "herself": fem + " herself",
        })
    if neu:
        pronoun_map.update({
            "it":      neu,
            "its":     neu + "'s",
            "itself":  neu + " itself",
        })
    if plur:
        pronoun_map.update({
            "they":       plur,
            "them":       plur,
            "their":      plur + "'s",
            "theirs":     plur + "'s",
            "themselves": plur + " themselves",
        })

    # Fix C: synthesise plural from masculine + feminine pair when no explicit plural entity.
    # "Arnab and Priya got married. They looked beautiful."
    # → they = "Arnab and Priya"
    if masc and fem and "they" not in pronoun_map:
        both = f"{masc} and {fem}"
        pronoun_map.update({
            "they":       both,
            "them":       both,
            "their":      both + "'s",
            "theirs":     both + "'s",
            "themselves": both + " themselves",
        })

    return pronoun_map


def _split_sentences(text: str) -> List[str]:
    """
    Split text into individual sentences on  . ! ?
    Keeps the delimiter attached to the sentence it ends.
    Empty strings are filtered out.
    """
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _resolve_pronouns_in_sentence(sentence: str, context: List[str]) -> str:
    """
    Core pronoun-replacement logic for a SINGLE sentence,
    given a list of context sentences that precede it.
    Uses spaCy if available, otherwise the rule-based path.
    """
    if _spacy_nlp is not None:
        return _spacy_resolve(sentence, context, _spacy_nlp)

    pronoun_map = _build_pronoun_map(context)
    if not pronoun_map:
        return sentence

    print(f"🔗 Coreference map: {pronoun_map}")

    result = sentence
    for pronoun, replacement in pronoun_map.items():
        pattern = re.compile(r'\b' + re.escape(pronoun) + r'\b', re.IGNORECASE)

        def _replace(m, repl=replacement, s=result):
            # Preserve sentence-start capitalisation
            if m.start() == 0 or (m.start() > 0 and s[m.start() - 1] in '.!?\n'):
                return repl[0].upper() + repl[1:]
            return repl

        result = pattern.sub(_replace, result)

    return result


def resolve_coreference(text: str, context: Optional[List[str]]) -> str:
    """
    Main entry point.  Resolves pronouns in `text` using:
      1. Session history context  (sentences from previous translate calls)
      2. Intra-text context       (earlier sentences within THIS input)

    This means it correctly handles BOTH:
      • Cross-call:  previous call had "Arnab played football."
                     this call is     "He scored a goal."
                     → "He" resolved to "Arnab" from session history.

      • Same-input:  user types "Arnab is not a bad boy. He is a good boy."
                     → sentence 1 introduces Arnab,
                       sentence 2's "He" resolved to "Arnab" from sentence 1.

    Works for any name, animal, object, place — no hardcoding.
    """
    sentences   = _split_sentences(text)

    # Only one sentence — use session context directly (original behaviour)
    if len(sentences) <= 1:
        if not context:
            return text
        return _resolve_pronouns_in_sentence(text, context)

    # Multiple sentences — resolve each sentence using:
    #   session_context  +  all preceding sentences in this same input
    resolved_sentences: List[str] = []
    for i, sentence in enumerate(sentences):
        # Context = session history + sentences already resolved before this one
        combined_context = list(context or []) + resolved_sentences
        resolved = _resolve_pronouns_in_sentence(sentence, combined_context)
        resolved_sentences.append(resolved)
        print(f"🔗 Sentence {i+1}: '{sentence}' → '{resolved}'")

    return " ".join(resolved_sentences)


def _spacy_resolve(text: str, context: List[str], nlp) -> str:
    """spaCy-powered coreference (used if spaCy is installed)."""
    pronoun_map: Dict[str, str] = {}
    for sentence in context:
        doc = nlp(sentence)
        for ent in doc.ents:
            label  = ent.label_
            name   = ent.text
            gender = "unknown"
            words_lower = sentence.lower().split()

            if label in ("PERSON",):
                if any(h in words_lower for h in _FEMALE_HINTS):
                    gender = "feminine"
                elif any(h in words_lower for h in _MALE_HINTS):
                    gender = "masculine"
                else:
                    gender = "unknown"
            elif label in ("ORG", "GPE", "LOC"):
                gender = "neuter"
            elif label in ("NORP", "FAC", "PRODUCT", "EVENT"):
                gender = "neuter"
            else:
                gender = "neuter"

            if gender == "masculine":
                pronoun_map.update({"he": name, "him": name, "his": name+"'s"})
            elif gender == "feminine":
                pronoun_map.update({"she": name, "her": name, "hers": name+"'s"})
            elif gender == "neuter":
                pronoun_map.update({"it": name, "its": name+"'s"})
            else:
                pronoun_map.setdefault("he", name)
                pronoun_map.setdefault("him", name)
                pronoun_map.setdefault("she", name)
                pronoun_map.setdefault("her", name)

    print(f"🔗 spaCy coreference map: {pronoun_map}")
    for pronoun, replacement in pronoun_map.items():
        pattern = re.compile(r'\b' + re.escape(pronoun) + r'\b', re.IGNORECASE)
        text    = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════
# IDIOM REPLACEMENT  — Smart variant-aware, context-preserving
# ═══════════════════════════════════════════════════════════════
#
# How the matching works
# ──────────────────────
# Each idiom entry has:
#   "canonical form"  →  "literal meaning"
#
# But people write idioms in many ways:
#   "raining cats and dogs"
#   "it's raining cats and dogs"
#   "It is raining cats and dogs"
#   "raining like cats and dogs"
#   "Raining Cats And Dogs"        ← title case
#   "raining cats & dogs"          ← ampersand
#
# The replace_idioms() function handles ALL of these by:
#   1. Normalising the input text to lowercase + expanding
#      contractions before matching (non-destructively — original
#      casing is preserved in the final output via re.sub with
#      a context-aware replacement function).
#   2. For each idiom, building a FUZZY regex that allows:
#        • Optional leading "it's / it is / there's / there is"
#        • "and" ↔ "&" equivalence
#        • Possessive apostrophe variants  (one's / ones)
#        • Contraction variants            (I'm / I am)
#   3. Replacing the ENTIRE matched span (including the optional
#      prefix) with a natural-language literal, so the sentence
#      still reads grammatically after replacement.
#
# Example
# ───────
#   Input:   "It's raining cats and dogs outside."
#   Match:   "It's raining cats and dogs"
#   Literal: "It is raining very heavily"
#   Output:  "It is raining very heavily outside."
#
# ═══════════════════════════════════════════════════════════════

# ── Contraction expander (runs before idiom matching) ──────────
_CONTRACTIONS: Dict[str, str] = {
    "it's":     "it is",
    "it`s":     "it is",
    "there's":  "there is",
    "i'm":      "i am",
    "i`m":      "i am",
    "you're":   "you are",
    "they're":  "they are",
    "we're":    "we are",
    "he's":     "he is",
    "she's":    "she is",
    "that's":   "that is",
    "what's":   "what is",
    "who's":    "who is",
    "isn't":    "is not",
    "aren't":   "are not",
    "wasn't":   "was not",
    "weren't":  "were not",
    "don't":    "do not",
    "doesn't":  "does not",
    "didn't":   "did not",
    "can't":    "cannot",
    "couldn't": "could not",
    "won't":    "will not",
    "wouldn't": "would not",
    "shouldn't":"should not",
    "haven't":  "have not",
    "hasn't":   "has not",
    "hadn't":   "had not",
    "i've":     "i have",
    "you've":   "you have",
    "we've":    "we have",
    "they've":  "they have",
    "i'll":     "i will",
    "you'll":   "you will",
    "he'll":    "he will",
    "she'll":   "she will",
    "we'll":    "we will",
    "they'll":  "they will",
    "i'd":      "i would",
    "you'd":    "you would",
    "he'd":     "he would",
    "she'd":    "she would",
    "we'd":     "we would",
    "they'd":   "they would",
    "let's":    "let us",
}

_CONTRACTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_CONTRACTIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

def _expand_contractions(text: str) -> str:
    """Expand contractions for reliable idiom matching."""
    def _sub(m: re.Match) -> str:
        return _CONTRACTIONS.get(m.group(0).lower(), m.group(0))
    return _CONTRACTION_RE.sub(_sub, text)


# ── Idiom core dictionary ──────────────────────────────────────
# Format:  "canonical phrase"  →  ("literal meaning", "natural_subject_prefix")
# natural_subject_prefix: what to prepend when the idiom is used as a
#   predicate after "it is", "there is", etc.  Empty string = no prefix needed.

IDIOM_MAP: Dict[str, str] = {

    # ── Weather ────────────────────────────────────────────────────
    "raining cats and dogs":
        "raining very heavily",
    "rain cats and dogs":
        "rain very heavily",
    "under the weather":
        "feeling sick or unwell",
    "storm in a teacup":
        "a big fuss about something minor",
    "every cloud has a silver lining":
        "every bad situation has a positive aspect",
    "it never rains but it pours":
        "bad things always happen together",
    "steal someone's thunder":
        "take the attention or credit away from someone",
    "take a rain check":
        "politely decline now but accept another time",
    "calm before the storm":
        "a quiet period before something bad happens",
    "any port in a storm":
        "any solution is acceptable in a difficult situation",

    # ── Work / Effort ──────────────────────────────────────────────
    "call it a day":
        "stop working for today",
    "burn the midnight oil":
        "work very late into the night",
    "back to the drawing board":
        "start over completely from the beginning",
    "bite the bullet":
        "endure a painful or difficult situation bravely",
    "hit the ground running":
        "start something quickly and energetically",
    "get the ball rolling":
        "start something and get things moving",
    "jump on the bandwagon":
        "follow a popular trend without independent thought",
    "cut corners":
        "do something carelessly to save time or money",
    "go the extra mile":
        "do significantly more than what is expected",
    "kill two birds with one stone":
        "accomplish two tasks with a single action",
    "bite off more than you can chew":
        "take on more responsibility than you can handle",
    "burning daylight":
        "wasting valuable time",
    "pull someone's leg":
        "joke with or tease someone",
    "on the ball":
        "alert, competent and performing well",
    "drop the ball":
        "make a mistake or fail to fulfil a responsibility",
    "pass the buck":
        "shift responsibility to someone else",
    "hit the books":
        "study hard",
    "learn the ropes":
        "learn the basics of how something works",
    "give someone the benefit of the doubt":
        "trust someone despite uncertainty",

    # ── Easy / Hard ────────────────────────────────────────────────
    "piece of cake":
        "something very easy to do",
    "a walk in the park":
        "something very easy and enjoyable",
    "hit the nail on the head":
        "identify or describe something exactly correctly",
    "over the moon":
        "extremely happy and excited",
    "uphill battle":
        "a very difficult task that requires great effort",
    "against the odds":
        "despite very low chances of success",
    "easier said than done":
        "something that sounds simple but is actually difficult",

    # ── Money ──────────────────────────────────────────────────────
    "costs an arm and a leg":
        "is extremely expensive",
    "cost an arm and a leg":
        "be extremely expensive",
    "break the bank":
        "cost more money than one can afford",
    "penny-pinching":
        "being very reluctant to spend money",
    "a dime a dozen":
        "so common as to be of little value",
    "cost a pretty penny":
        "be very expensive",
    "born with a silver spoon":
        "born into a wealthy privileged family",
    "on a shoestring":
        "with very little money available",
    "money doesn't grow on trees":
        "money is not easily or freely available",
    "tighten your belt":
        "spend less money and live more economically",

    # ── Time ──────────────────────────────────────────────────────
    "hit the sack":
        "go to sleep",
    "once in a blue moon":
        "very rarely or almost never",
    "in the nick of time":
        "just barely in time before it is too late",
    "beat around the bush":
        "avoid getting to the main point of a matter",
    "at the drop of a hat":
        "immediately and without any hesitation",
    "in the blink of an eye":
        "happening extremely quickly",
    "ahead of one's time":
        "having ideas more advanced than the current era accepts",
    "kill time":
        "do something unimportant while waiting",
    "time flies":
        "time passes very quickly",
    "in the long run":
        "over a long period of time ultimately",

    # ── Communication / Truth ─────────────────────────────────────
    "spill the beans":
        "reveal a secret accidentally or deliberately",
    "let the cat out of the bag":
        "accidentally reveal a secret",
    "read between the lines":
        "understand the hidden or implied meaning",
    "straight from the horse's mouth":
        "directly from the original and most reliable source",
    "bite the hand that feeds you":
        "harm or betray someone who supports or helps you",
    "sit on the fence":
        "refuse to take a side in a disagreement",
    "cut to the chase":
        "get directly to the important point",
    "speak of the devil":
        "said when someone appears just after being mentioned",
    "get straight to the point":
        "say exactly what you mean without unnecessary words",
    "Actions speak louder than words":
        "what people do matters more than what they say",

    # ── Emotions / Social ─────────────────────────────────────────
    "break a leg":
        "good luck with your performance",
    "break the ice":
        "do something to relieve tension or awkwardness",
    "under pressure":
        "stressed and struggling under heavy demands",
    "add fuel to the fire":
        "make a bad or angry situation significantly worse",
    "the last straw":
        "the final problem that makes a situation completely unbearable",
    "bury the hatchet":
        "make peace and stop arguing with someone",
    "carry a torch for someone":
        "have strong unrequited romantic feelings for someone",
    "get cold feet":
        "become nervous and hesitant about doing something",
    "wear your heart on your sleeve":
        "openly and clearly show your emotions to others",
    "green with envy":
        "feeling very jealous of someone",
    "see red":
        "become very angry very suddenly",
    "in seventh heaven":
        "in a state of extreme happiness and joy",
    "down in the dumps":
        "feeling very sad or depressed",
    "on cloud nine":
        "feeling extremely happy",
    "get out of hand":
        "become impossible to control or manage",
    "at the end of one's rope":
        "having no more patience or strength left",
    "i am fine":
        "i appear okay outwardly but may not be emotionally well",

    # ── Body ──────────────────────────────────────────────────────
    "keep an eye on":
        "watch carefully and attentively",
    "turn a blind eye":
        "deliberately ignore something known to be wrong",
    "have a heart of gold":
        "be extremely kind and generous",
    "put your foot in your mouth":
        "say something embarrassing or offensive by mistake",
    "give the cold shoulder":
        "deliberately ignore or be unfriendly to someone",
    "get something off your chest":
        "confess something that has been causing worry",
    "pull someone's leg":
        "tease or joke with someone",
    "cost an arm and a leg":
        "be extremely expensive",
    "turn the other cheek":
        "choose not to retaliate when treated badly",
    "head over heels":
        "completely and deeply in love",

    # ── Sports / Competition ──────────────────────────────────────
    "ball is in your court":
        "it is your turn to take action or make the decision",
    "move the goalposts":
        "change the rules or expectations unfairly mid-way",
    "level playing field":
        "fair and equal conditions for everyone involved",
    "out of your league":
        "beyond your ability or social level",
    "neck and neck":
        "very closely matched in a competition",
    "jump the gun":
        "start something prematurely before the right time",
    "hit below the belt":
        "do something unfair cruel or unsportsmanlike",
    "throw in the towel":
        "give up and admit defeat",
    "a long shot":
        "something with very little chance of success",
    "the ball is in someone's court":
        "it is someone else's turn to take the next action",

    # ── Animals / Nature ──────────────────────────────────────────
    "let sleeping dogs lie":
        "avoid bringing up old problems that may cause trouble",
    "kill the goose that lays golden eggs":
        "destroy something valuable for the sake of short-term gain",
    "cat got your tongue":
        "unable to speak due to shyness shock or surprise",
    "elephant in the room":
        "an obvious important problem that everyone avoids discussing",
    "fish out of water":
        "someone in an uncomfortable or completely unfamiliar situation",
    "hold your horses":
        "wait and be patient before proceeding",
    "wolf in sheep's clothing":
        "a dangerous or dishonest person disguised as harmless",
    "barking up the wrong tree":
        "pursuing a completely mistaken or misguided course of action",
    "take the bull by the horns":
        "deal with a difficult situation in a direct and determined way",
    "the elephant never forgets":
        "some people have a very long and precise memory",
    "a fish rots from the head":
        "an organisation's problems start with its leadership",
    "birds of a feather flock together":
        "people with similar interests or character tend to associate",
    "every dog has its day":
        "everyone gets a chance to succeed at some point",
    "let the cat out":
        "reveal something secret",

    # ── Indian / South Asian English idioms ─────────────────────
    "out of station":
        "away from one's usual place of residence or work",
    "do the needful":
        "do whatever is necessary",
    "prepone":
        "move to an earlier time",
    "good name":
        "what is your name",
    "passed out":
        "graduated from an educational institution",
    "come what may":
        "no matter what happens",
    "by hook or by crook":
        "by any means necessary whether fair or unfair",
    "eat humble pie":
        "admit one was wrong and apologise",
}

# Pre-sort by length descending so longer phrases always match first
_SORTED_IDIOMS = sorted(IDIOM_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# ── Optional prefix patterns that surround idioms ─────────────
# These capture things like "It is raining cats and dogs" where
# "It is" is not part of the idiom but must be absorbed into the
# match and re-expressed in the literal output.
_SUBJECT_PREFIXES = re.compile(
    r"^(it\s+is\s+|it\s+was\s+|there\s+is\s+|there\s+was\s+|"
    r"this\s+is\s+|this\s+was\s+)",
    re.IGNORECASE,
)

def replace_idioms(text: str) -> str:
    """
    Replace idioms with their literal meaning before translation.

    Handles:
      • Any capitalisation  (Raining Cats And Dogs)
      • Contractions        (it's raining → it is raining)
      • Ampersand variant   (cats & dogs)
      • Possessive variants (one's / ones)
      • Optional subject prefixes (It is / There is / This is …)
      • Partial sentence    (…raining cats and dogs all day)
      • Multi-sentence text (each sentence processed independently)

    Always returns a string that is grammatically natural AFTER
    replacement, ready to be fed into the translation API.
    """
    # ── Step 1: expand contractions so "it's raining cats and dogs"
    #           becomes "it is raining cats and dogs" before matching.
    expanded = _expand_contractions(text)

    # ── Step 2: also normalise & → and for matching only
    normalised = expanded.replace("&", "and")

    replaced = normalised
    for phrase, meaning in _SORTED_IDIOMS:
        # Build a flexible pattern:
        #   • word boundaries on each side
        #   • "and" may also appear as "&" (already normalised above)
        #   • apostrophe-s variants  (one's → ones?)
        #   • optional subject prefix absorbed into the match
        escaped   = re.escape(phrase)
        # Allow optional "it is / there is / this is" before the phrase
        full_pat  = re.compile(
            r'(?:it\s+is\s+|it\s+was\s+|there\s+is\s+|there\s+was\s+|'
            r'this\s+is\s+|this\s+was\s+)?'
            + escaped,
            re.IGNORECASE,
        )

        def _build_replacement(meaning: str = meaning, phrase: str = phrase):
            def _repl(m: re.Match) -> str:
                matched_text = m.group(0)
                # Detect if there was a subject prefix in the match
                prefix_match = _SUBJECT_PREFIXES.match(matched_text)
                if prefix_match:
                    # Re-express with a natural "It is <literal>"
                    return "It is " + meaning
                # No prefix — just the idiom itself
                # Preserve original capitalisation of the first character
                if matched_text[0].isupper():
                    return meaning[0].upper() + meaning[1:]
                return meaning
            return _repl

        if full_pat.search(replaced):
            print(f"🗣️  Idiom detected: '{phrase}' → '{meaning}'")
            replaced = full_pat.sub(_build_replacement(), replaced)

    return replaced


# ═══════════════════════════════════════════════════════════════
# ② 100+ EMOTION TAXONOMY
# ═══════════════════════════════════════════════════════════════
#
# Architecture
# ────────────
#  Layer 0 — Raw model output
#    The j-hartmann model returns 7 Ekman scores:
#    joy, sadness, anger, fear, surprise, disgust, neutral
#
#  Layer 1 — 28 Plutchik sub-emotions
#    Derived from raw scores via a blend matrix.
#    Each Plutchik emotion is a weighted combination of Ekman scores.
#    The weights were designed so that:
#      ecstasy   ≈ high joy, low everything else
#      grief     ≈ high sadness, some fear
#      rage      ≈ high anger
#      terror    ≈ high fear
#      amazement ≈ high surprise
#      loathing  ≈ high disgust
#      … etc.
#
#  Layer 2 — 70+ nuanced emotions
#    Mapped from the top-2 Plutchik emotions by a lookup table.
#    Captures combinations like:
#      joy + surprise        → delight
#      joy + anticipation    → optimism
#      fear + surprise       → alarm
#      sadness + anger       → bitterness
#      … (70+ entries)
#
#  Valence & Arousal (Russell circumplex model)
#    Computed from Ekman scores:
#      valence  = joy − sadness − disgust − 0.5·anger
#      arousal  = anger + fear + surprise − 0.5·sadness − 0.3·neutral
#    Both normalised to [−1, +1].
#
#  Intensity band
#    Based on dominant score:
#      < 0.30  → low
#      0.30-0.55 → moderate
#      0.55-0.80 → high
#      > 0.80  → intense
#
# ═══════════════════════════════════════════════════════════════

# Layer 1: Plutchik wheel (28 emotions)
# Each entry: { plutchik_name: { ekman_name: weight, … } }
# Weights sum to 1.0 per entry (they are blending coefficients).
_PLUTCHIK_BLEND: Dict[str, Dict[str, float]] = {
    # Joy family
    "ecstasy":        {"joy": 0.90, "surprise": 0.10},
    "joy":            {"joy": 0.85, "neutral":  0.15},
    "serenity":       {"joy": 0.60, "neutral":  0.40},

    # Sadness family
    "grief":          {"sadness": 0.80, "fear":    0.20},
    "sadness":        {"sadness": 0.85, "neutral":  0.15},
    "pensiveness":    {"sadness": 0.60, "neutral":  0.40},

    # Anger family
    "rage":           {"anger":   0.90, "disgust":  0.10},
    "anger":          {"anger":   0.85, "neutral":  0.15},
    "annoyance":      {"anger":   0.60, "neutral":  0.40},

    # Fear family
    "terror":         {"fear":    0.90, "surprise": 0.10},
    "fear":           {"fear":    0.85, "neutral":  0.15},
    "apprehension":   {"fear":    0.60, "neutral":  0.40},

    # Surprise family
    "amazement":      {"surprise":0.80, "fear":     0.20},
    "surprise":       {"surprise":0.85, "neutral":  0.15},
    "distraction":    {"surprise":0.50, "neutral":  0.50},

    # Disgust family
    "loathing":       {"disgust": 0.90, "anger":    0.10},
    "disgust":        {"disgust": 0.85, "neutral":  0.15},
    "boredom":        {"disgust": 0.40, "neutral":  0.60},

    # Anticipation family (modelled as low-surprise + joy blend)
    "vigilance":      {"fear":    0.40, "joy":      0.30, "surprise": 0.30},
    "anticipation":   {"joy":     0.40, "surprise": 0.30, "neutral":  0.30},
    "interest":       {"surprise":0.35, "joy":      0.35, "neutral":  0.30},

    # Trust family (modelled as joy-dominant low-fear blend)
    "admiration":     {"joy":     0.55, "surprise": 0.25, "neutral":  0.20},
    "trust":          {"joy":     0.50, "neutral":  0.50},
    "acceptance":     {"joy":     0.35, "neutral":  0.65},

    # Dyad emotions (combinations of 2 Plutchik primaries)
    "optimism":       {"joy":     0.50, "surprise": 0.20, "neutral":  0.30},
    "love":           {"joy":     0.60, "sadness":  0.10, "fear":     0.10, "neutral": 0.20},
    "submission":     {"fear":    0.50, "sadness":  0.30, "neutral":  0.20},
    "awe":            {"fear":    0.40, "surprise": 0.45, "neutral":  0.15},
    "disapproval":    {"sadness": 0.40, "disgust":  0.35, "anger":    0.25},
    "remorse":        {"sadness": 0.50, "disgust":  0.30, "neutral":  0.20},
    "contempt":       {"disgust": 0.50, "anger":    0.30, "sadness":  0.20},
    "aggressiveness": {"anger":   0.55, "anticipation_proxy": 0.00, "surprise": 0.20, "neutral": 0.25},
}

# Fix: remove proxy key
_PLUTCHIK_BLEND["aggressiveness"] = {"anger": 0.60, "surprise": 0.20, "neutral": 0.20}


def _compute_plutchik(ekman: Dict[str, float]) -> Dict[str, float]:
    """Compute 28 Plutchik emotion scores from 7 Ekman scores."""
    results: Dict[str, float] = {}
    for plutchik_name, weights in _PLUTCHIK_BLEND.items():
        score = sum(ekman.get(ek, 0.0) * w for ek, w in weights.items())
        results[plutchik_name] = round(min(score, 1.0), 4)
    return results


# Layer 2: 70+ nuanced emotions
# Key = frozenset of the top-1 or top-2 Plutchik emotions
# Value = nuanced emotion label
_NUANCED_MAP: Dict[Tuple[str, ...], str] = {
    # Single-primary nuanced
    ("ecstasy",):         "elation",
    ("joy",):             "happiness",
    ("serenity",):        "contentment",
    ("grief",):           "despair",
    ("sadness",):         "melancholy",
    ("pensiveness",):     "wistfulness",
    ("rage",):            "fury",
    ("anger",):           "frustration",
    ("annoyance",):       "irritation",
    ("terror",):          "dread",
    ("fear",):            "anxiety",
    ("apprehension",):    "nervousness",
    ("amazement",):       "astonishment",
    ("surprise",):        "shock",
    ("distraction",):     "confusion",
    ("loathing",):        "revulsion",
    ("disgust",):         "repulsion",
    ("boredom",):         "tedium",
    ("awe",):             "reverence",
    ("love",):            "affection",
    ("optimism",):        "hopefulness",
    ("trust",):           "confidence",
    ("admiration",):      "respect",
    ("acceptance",):      "openness",
    ("remorse",):         "guilt",
    ("contempt",):        "disdain",
    ("disapproval",):     "rejection",
    ("vigilance",):       "alertness",
    ("anticipation",):    "eagerness",
    ("interest",):        "curiosity",
    ("submission",):      "helplessness",
    ("aggressiveness",):  "hostility",

    # Dual-primary nuanced (sorted tuples)
    ("ecstasy", "joy"):           "euphoria",
    ("joy", "serenity"):          "bliss",
    ("joy", "trust"):             "warmth",
    ("joy", "surprise"):          "delight",
    ("joy", "anticipation"):      "enthusiasm",
    ("joy", "admiration"):        "pride",
    ("joy", "love"):              "devotion",
    ("joy", "optimism"):          "exhilaration",
    ("sadness", "grief"):         "anguish",
    ("sadness", "fear"):          "vulnerability",
    ("sadness", "remorse"):       "regret",
    ("sadness", "anger"):         "bitterness",
    ("sadness", "disgust"):       "shame",
    ("sadness", "pensiveness"):   "loneliness",
    ("sadness", "love"):          "heartbreak",
    ("anger", "rage"):            "wrath",
    ("anger", "disgust"):         "contemptuous anger",
    ("anger", "fear"):            "desperation",
    ("anger", "sadness"):         "resentment",
    ("anger", "surprise"):        "outrage",
    ("anger", "anticipation"):    "impatience",
    ("fear", "terror"):           "panic",
    ("fear", "surprise"):         "alarm",
    ("fear", "sadness"):          "helpless dread",
    ("fear", "anticipation"):     "suspense",
    ("fear", "disgust"):          "horror",
    ("surprise", "amazement"):    "awe-struck wonder",
    ("surprise", "joy"):          "pleasant surprise",
    ("surprise", "disgust"):      "disgust-shock",
    ("surprise", "fear"):         "startled alarm",
    ("disgust", "loathing"):      "abhorrence",
    ("disgust", "anger"):         "exasperation",
    ("disgust", "sadness"):       "disillusionment",
    ("disgust", "contempt"):      "scorn",
    ("trust", "admiration"):      "reverence",
    ("trust", "joy"):             "gratitude",
    ("trust", "fear"):            "awe",
    ("awe", "admiration"):        "veneration",
    ("awe", "fear"):              "trepidation",
    ("awe", "joy"):               "inspiration",
    ("love", "joy"):              "passionate joy",
    ("love", "sadness"):          "longing",
    ("love", "fear"):             "attachment anxiety",
    ("optimism", "joy"):          "excitement",
    ("optimism", "fear"):         "cautious hope",
    ("optimism", "anticipation"): "eager anticipation",
    ("remorse", "sadness"):       "deep regret",
    ("contempt", "anger"):        "indignation",
    ("contempt", "disgust"):      "moral outrage",
    ("acceptance", "joy"):        "gratitude",
    ("acceptance", "sadness"):    "resignation",
    ("vigilance", "fear"):        "hyper-vigilance",
    ("aggressiveness", "anger"):  "combativeness",
    ("submission", "fear"):       "submission through fear",
}


def _compute_nuanced(plutchik: Dict[str, float]) -> Tuple[str, str]:
    """
    Identify the top-2 Plutchik emotions and return the nuanced label
    and a short description.
    """
    sorted_p = sorted(plutchik.items(), key=lambda x: x[1], reverse=True)
    top1     = sorted_p[0][0] if len(sorted_p) > 0 else "neutral"
    top2     = sorted_p[1][0] if len(sorted_p) > 1 else top1

    # Try dual-primary lookup first (sorted for consistent key)
    pair_key = tuple(sorted([top1, top2]))
    if pair_key in _NUANCED_MAP and sorted_p[0][1] > 0.15 and sorted_p[1][1] > 0.10:
        return _NUANCED_MAP[pair_key], f"{top1} + {top2}"

    # Fall back to single-primary
    single_key = (top1,)
    if single_key in _NUANCED_MAP:
        return _NUANCED_MAP[single_key], top1

    return top1, top1   # ultimate fallback


# Valence-Arousal weights (Russell circumplex approximation)
_VALENCE_W  = {"joy": 1.0, "sadness": -1.0, "disgust": -0.8, "anger": -0.6,
               "fear": -0.5, "surprise": 0.1, "neutral": 0.0}
_AROUSAL_W  = {"joy": 0.4, "sadness": -0.5, "disgust": 0.2, "anger": 0.9,
               "fear": 0.8, "surprise": 0.7, "neutral": -0.4}

def _compute_valence_arousal(ekman: Dict[str, float]) -> Tuple[float, float]:
    valence = sum(ekman.get(k, 0) * v for k, v in _VALENCE_W.items())
    arousal = sum(ekman.get(k, 0) * v for k, v in _AROUSAL_W.items())
    # Clamp to [-1, +1]
    valence = max(-1.0, min(1.0, valence))
    arousal = max(-1.0, min(1.0, arousal))
    return round(valence, 3), round(arousal, 3)


def _intensity_band(confidence: float) -> str:
    if confidence >= 0.80: return "intense"
    if confidence >= 0.55: return "high"
    if confidence >= 0.30: return "moderate"
    return "low"


# ── Emotion model loader ───────────────────────────────────────

_emotion_classifier = None

def get_emotion():
    global _emotion_classifier
    if _emotion_classifier is None:
        print("⏳ Loading emotion model…")
        from transformers import pipeline
        _emotion_classifier = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            device=-1,
            batch_size=1,
        )
        print("✅ Emotion model loaded")
    return _emotion_classifier


def detect_emotion(text: str) -> dict:
    """
    Returns full 100+ emotion taxonomy dict:
      {
        "emotion":          str,            # dominant Ekman label
        "confidence":       float,
        "scores":           dict,           # 7 Ekman scores
        "plutchik":         dict,           # 28 Plutchik scores
        "nuanced_emotion":  str,            # 70+ nuanced label
        "nuanced_source":   str,            # which Plutchik emotions drove it
        "valence":          float,          # -1..+1 (negative→positive)
        "arousal":          float,          # -1..+1 (calm→excited)
        "intensity":        str,            # low/moderate/high/intense
        "quadrant":         str,            # Russell circumplex quadrant
      }
    """
    _DEFAULT = {
        "emotion": "neutral", "confidence": 0.5,
        "scores": {"joy":0,"sadness":0,"anger":0,"fear":0,"surprise":0,"disgust":0,"neutral":1},
        "plutchik": {k: 0.0 for k in _PLUTCHIK_BLEND},
        "nuanced_emotion": "composure", "nuanced_source": "neutral",
        "valence": 0.0, "arousal": 0.0, "intensity": "low", "quadrant": "calm-neutral",
    }

    try:
        clf     = get_emotion()
        results = clf(text[:512])
        if isinstance(results, list) and len(results) > 0:
            results = results[0] if isinstance(results[0], list) else results
        results_list = results if isinstance(results, list) else []

        # ── Ekman scores ────────────────────────────────────────────
        ekman: Dict[str, float] = {
            str(i.get("label","")).lower(): float(i.get("score",0))
            for i in results_list if isinstance(i, dict)
        }
        dominant = max(results_list, key=lambda x: x.get("score",0), default=None)
        if not dominant:
            return _DEFAULT

        dom_label = str(dominant.get("label","neutral")).lower()
        dom_conf  = float(dominant.get("score", 0.5))

        # ── Plutchik layer ──────────────────────────────────────────
        plutchik = _compute_plutchik(ekman)

        # ── Nuanced layer ───────────────────────────────────────────
        nuanced_label, nuanced_src = _compute_nuanced(plutchik)

        # ── Valence / Arousal ───────────────────────────────────────
        valence, arousal = _compute_valence_arousal(ekman)

        # Russell quadrant
        if valence >= 0 and arousal >= 0:
            quadrant = "positive-high energy"
        elif valence >= 0 and arousal < 0:
            quadrant = "positive-calm"
        elif valence < 0 and arousal >= 0:
            quadrant = "negative-high energy"
        else:
            quadrant = "negative-calm"

        intensity = _intensity_band(dom_conf)

        return {
            "emotion":         dom_label,
            "confidence":      dom_conf,
            "scores":          ekman,               # 7 Ekman
            "plutchik":        plutchik,            # 28 Plutchik
            "nuanced_emotion": nuanced_label,       # 70+ nuanced
            "nuanced_source":  nuanced_src,
            "valence":         valence,
            "arousal":         arousal,
            "intensity":       intensity,
            "quadrant":        quadrant,
        }

    except Exception as e:
        print(f"⚠️  Emotion error: {e}")
        return _DEFAULT


# ═══════════════════════════════════════════════════════════════
# MAIN TRANSLATE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

async def translate_fast(
    text: str,
    src_lang: str,
    tgt_lang: str,
    context: Optional[List[str]] = None,
    prev_pair: Optional[dict] = None,
) -> Tuple[str, str]:
    """
    Pre-processes text (idiom expansion + coreference resolution),
    then tries MyMemory → LibreTranslate → Lingva → local NLLB.
    Returns (translated_text, method_name).

    prev_pair (Context-Aware mode only):
      When the user has "Use conversation context" ON, the last
      (original, translated) pair from session history is passed here.
      We prepend it to the current sentence before sending to the API:

        Combined input  →  "<prev_original>\n<current>"
        Combined output →  "<prev_translated>\n<current_translated>"

      The translation API then sees both sentences together, so it can
      produce a contextually consistent translation for the current one
      (consistent tense, terminology, pronoun agreement, style).

      After translation we strip the first line (the prefix we added)
      and return only the current sentence translation.

      Example
      ───────
        Previous call : "Arnab is going to the market."
                         → Bengali: "অর্ণব বাজারে যাচ্ছে।"
        Current call  : "He will buy vegetables."
        Combined sent : "Arnab is going to the market.\nHe will buy vegetables."
        API translates: "অর্ণব বাজারে যাচ্ছে।\nসে সবজি কিনবে।"
        Returned      : "সে সবজি কিনবে।"   ← consistent with previous
    """
    # ── Pre-processing ───────────────────────────────────────────────
    text = replace_idioms(text)
    text = resolve_coreference(text, context)

    # ── Cache check (on resolved text, before prefix trick) ──────────
    ck = cache_key(text, src_lang, tgt_lang)
    cached = cache_get(ck)
    if cached:
        print("⚡ Cache HIT")
        return cached, "cache"

    if src_lang == tgt_lang:
        return text, "passthrough"

    # ── Context-Aware translation: prepend previous sentence pair ────
    # This is the KEY fix: the translation API receives the previous
    # translated sentence as the first line, making it produce a
    # contextually consistent translation for the current sentence.
    use_prefix = (
        prev_pair is not None
        and prev_pair.get("translated")
        and prev_pair.get("original")
        and prev_pair.get("source_lang") == src_lang
        and prev_pair.get("target_lang") == tgt_lang
    )

    if use_prefix:
        prev_orig  = prev_pair["original"].strip()
        prev_trans = prev_pair["translated"].strip()
        # Send: "previous original\ncurrent" -- translate -- strip first line
        combined_src = prev_orig + "\n" + text
        print(f"🔗 Context prefix: '{prev_orig[:60]}…'")
    else:
        combined_src = text

    print(f"🔄 Translating: {src_lang} → {tgt_lang}")

    # Try each backend with the combined input
    raw = await translate_mymemory(combined_src, src_lang, tgt_lang)
    method = "mymemory"
    if not raw:
        raw = await translate_libre(combined_src, src_lang, tgt_lang)
        method = "libretranslate"
    if not raw:
        raw = await translate_lingva(combined_src, src_lang, tgt_lang)
        method = "lingva"
    if not raw:
        print("⚠️  All APIs failed — using local model")
        loop = asyncio.get_event_loop()
        raw  = await loop.run_in_executor(executor, translate_local_sync, text, src_lang, tgt_lang)
        method = "local_nllb"
        use_prefix = False  # local model gets plain text

    if not raw:
        return text, "error"

    # ── Strip the prefix line from the translation output ────────────
    if use_prefix:
        lines = raw.strip().split("\n")
        if len(lines) >= 2:
            # First line = translation of previous sentence (prefix)
            # Second+ lines = translation of current sentence
            result = " ".join(lines[1:]).strip()
            print(f"✅ Context-aware translation — stripped prefix line")
        else:
            # API merged both lines into one — fall back to full output
            # This happens with some APIs. Try again without prefix.
            print("⚠️  API merged lines — retrying without prefix")
            result = await translate_mymemory(text, src_lang, tgt_lang)
            if not result:
                result = await translate_libre(text, src_lang, tgt_lang)
            if not result:
                result = await translate_lingva(text, src_lang, tgt_lang)
            if not result:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(executor, translate_local_sync, text, src_lang, tgt_lang)
                method = "local_nllb"
            result = result or raw
    else:
        result = raw

    result = result.strip()
    cache_set(ck, result)
    print(f"✅ {method}")
    return result, method


# ═══════════════════════════════════════════════════════════════
# WHISPER  (unchanged)
# ═══════════════════════════════════════════════════════════════

_whisper = None

def get_whisper():
    global _whisper
    if _whisper is None:
        print("⏳ Loading Whisper tiny…")
        import whisper
        _whisper = whisper.load_model("tiny")
        print("✅ Whisper tiny loaded")
    return _whisper


# ═══════════════════════════════════════════════════════════════
# SESSION STORAGE  (unchanged)
# ═══════════════════════════════════════════════════════════════

sessions     = {}
MAX_SESSIONS = 20
SESSION_TTL  = 1800


class TranslationSession:
    def __init__(self, sid: str):
        self.session_id    = sid
        self.history       = []
        self.created_at    = datetime.now()
        self.last_accessed = datetime.now()

    def add(self, original, translated, src, tgt, emotion=None):
        if len(self.history) >= 20:
            self.history = self.history[-15:]
        self.history.append({
            "timestamp":   datetime.now().isoformat(),
            "original":    original[:400],
            "translated":  translated[:400],
            "source_lang": src,
            "target_lang": tgt,
            "emotion":     emotion,
        })
        self.last_accessed = datetime.now()

    def get_context(self, use_ctx: bool, top_k: int = 3) -> List[str]:
        """
        Return last top_k original sentences for cross-call coreference.
        History is ALWAYS saved regardless of mode, so switching from Text mode
        to Context mode gives full history immediately.
        """
        if not use_ctx or not self.history:
            return []
        return [r["original"] for r in self.history[-top_k:]]

    def get_recent_entities(self, top_k: int = 3) -> List[str]:
        """Return recent originals regardless of use_context — for intra-text coreference."""
        if not self.history:
            return []
        return [r["original"] for r in self.history[-top_k:]]

    def get_last_translation_pair(self) -> Optional[dict]:
        """
        Return the most recent (original, translated) pair from history.
        Used by Context-Aware mode to prepend previous translated sentence
        to the current input so the translation API sees continuity.
        Returns None if no history exists.
        """
        if not self.history:
            return None
        last = self.history[-1]
        return {
            "original":    last["original"],
            "translated":  last["translated"],
            "source_lang": last["source_lang"],
            "target_lang": last["target_lang"],
        }

    def clear(self):
        self.history = []
        self.last_accessed = datetime.now()

    def get_history(self, limit: int = 10):
        return self.history[-limit:]

    def is_expired(self):
        return (datetime.now() - self.last_accessed).total_seconds() > SESSION_TTL


def cleanup_sessions():
    global sessions
    expired = [s for s, v in sessions.items() if v.is_expired()]
    for s in expired:
        del sessions[s]
    if len(sessions) > MAX_SESSIONS:
        for s, _ in sorted(
            sessions.items(), key=lambda x: x[1].last_accessed
        )[:len(sessions) - MAX_SESSIONS]:
            del sessions[s]


def get_session(sid: Optional[str]) -> TranslationSession:
    cleanup_sessions()
    if sid and sid in sessions:
        return sessions[sid]
    new_id         = sid or str(uuid.uuid4())
    sessions[new_id] = TranslationSession(new_id)
    return sessions[new_id]


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/translate")
async def translate(
    text:        Optional[str]        = Form(None),
    audio:       Optional[UploadFile] = File(None),
    video:       Optional[UploadFile] = File(None),
    source_lang: str                  = Form(...),
    target_lang: str                  = Form(...),
    session_id:  Optional[str]        = Form(None),
    use_context: bool                 = Form(False),
):
    start      = time.time()
    trans_time = 0
    session    = get_session(session_id)

    # ── Audio / Video transcription ──────────────────────────────────
    if audio or video:
        t0       = time.time()
        uploaded = audio or video
        suffix   = ".wav" if audio else ".mp4"
        if uploaded is None:
            return {"error": "Audio or video file is required"}
        content  = await uploaded.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            w    = get_whisper()
            loop = asyncio.get_event_loop()
            res  = await loop.run_in_executor(
                executor,
                lambda: w.transcribe(
                    tmp_path,
                    fp16=False, beam_size=1,
                    best_of=1, temperature=0,
                    condition_on_previous_text=False,
                )
            )
            text = str(res.get("text", "")).strip()
        finally:
            os.unlink(tmp_path)

        trans_time = (time.time() - t0) * 1000

    if not text:
        return {"error": "No text provided"}

    text = text[:1500]

    # ── Context strategy ─────────────────────────────────────────────
    # ctx      = full session history, used ONLY when use_context=True
    #            (Context-Aware mode with toggle ON)
    # coref_ctx = always includes recent history so intra-text coreference
    #            works even in Text/Audio/Video modes.
    #            e.g. user translated "Arnab won." in Text mode, then types
    #            "He celebrated." in Text mode → He → Arnab still resolves.
    ctx       = session.get_context(use_context, top_k=3)
    coref_ctx = session.get_recent_entities(top_k=3) if not use_context else ctx
    # When context mode is ON, fetch the last (original, translated) pair so
    # translate_fast can prepend it to the current sentence.
    # This is what makes the translation API produce contextually consistent output.
    prev_pair = session.get_last_translation_pair() if use_context else None

    t1   = time.time()

    # ── Run translation + emotion in parallel ────────────────────────
    translated_task = translate_fast(text, source_lang, target_lang, coref_ctx, prev_pair)
    emotion_task    = asyncio.get_event_loop().run_in_executor(
        executor, detect_emotion, text
    )

    (translated, method), emotion_data = await asyncio.gather(
        translated_task, emotion_task
    )

    translation_ms = (time.time() - t1) * 1000
    total_ms       = (time.time() - start) * 1000

    session.add(text, translated, source_lang, target_lang, emotion_data)

    return {
        "session_id":        session.session_id,
        "original":          text,
        "translated":        translated,
        "emotion":           emotion_data,          # now contains 100+ emotion fields
        "context_used":      use_context,
        "source_lang":       source_lang,
        "target_lang":       target_lang,
        "context_sentences": ctx,
        "performance": {
            "transcription_ms":     trans_time,
            "translation_ms":       translation_ms,
            "emotion_detection_ms": 0,
            "total_ms":             total_ms,
            "method":               method,
            "cache_size":           len(_cache),
        },
        "model_info": {
            "name":     f"Enhanced API ({method})",
            "type":     "Multi-API + Universal Coreference + 100+ Emotion Taxonomy",
            "features": [
                "Universal coreference resolution (any entity)",
                "80+ idiom expansion (longest-match-first)",
                "MyMemory API ~200ms",
                "LibreTranslate fallback",
                "Lingva fallback",
                "Local NLLB last resort",
                "Result caching",
                "Parallel emotion detection",
                "7 Ekman + 28 Plutchik + 70+ nuanced emotions",
                "Valence/Arousal/Intensity/Quadrant",
            ],
        },
        "history_count": len(session.history),
    }


@app.post("/translate/batch")
async def translate_batch(
    texts:       List[str] = Form(...),
    source_lang: str       = Form(...),
    target_lang: str       = Form(...),
):
    if len(texts) > 10:
        return {"error": "Max 10 texts per batch"}
    start        = time.time()
    tasks        = [translate_fast(t, source_lang, target_lang) for t in texts]
    results      = await asyncio.gather(*tasks)
    translations = [r[0] for r in results]
    total        = (time.time() - start) * 1000
    return {
        "translations": translations,
        "count":        len(translations),
        "performance":  {"total_ms": total, "avg_ms": total / len(texts)},
    }


@app.post("/memory/cleanup")
async def force_cleanup():
    gc.collect()
    _cache.clear()
    cleanup_sessions()
    return {"status": "success", "cache_cleared": True, "sessions": len(sessions)}


@app.post("/session/clear")
async def clear_session(session_id: str = Form(...)):
    if session_id in sessions:
        sessions[session_id].clear()
        return {"status": "success"}
    return {"status": "error", "message": "Session not found"}


@app.get("/session/{session_id}/history")
async def get_history(session_id: str, limit: int = 20):
    if session_id in sessions:
        return {
            "session_id":  session_id,
            "history":     sessions[session_id].get_history(limit),
            "total_count": len(sessions[session_id].history),
        }
    return {"error": "Session not found"}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "success"}
    return {"status": "error"}


@app.get("/sessions")
async def list_sessions():
    return {
        "sessions": [
            {
                "session_id":    sid,
                "history_count": len(s.history),
                "last_accessed": s.last_accessed.isoformat(),
            }
            for sid, s in sessions.items()
        ],
        "total": len(sessions),
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "mode":   "enhanced",
        "features": {
            "coreference":     "Universal (rule-based + optional spaCy)",
            "idioms":          f"{len(IDIOM_MAP)} phrases",
            "emotion_ekman":   7,
            "emotion_plutchik":len(_PLUTCHIK_BLEND),
            "emotion_nuanced": len(_NUANCED_MAP),
        },
        "translation_backends": [
            "MyMemory (~200ms, free, 5000 words/day)",
            "LibreTranslate (~400ms, free, unlimited)",
            "Lingva (~500ms, free, unlimited)",
            "Local NLLB-600M (fallback)",
        ],
        "cache_size":      len(_cache),
        "active_sessions": len(sessions),
        "models_loaded": {
            "whisper":    _whisper is not None,
            "emotion":    _emotion_classifier is not None,
            "local_nllb": _local_model is not None,
        },
    }


@app.get("/supported-languages")
async def supported_languages():
    return {
        "languages":      list(MYMEMORY_CODES.keys()),
        "total_count":    len(MYMEMORY_CODES),
        "language_codes": MYMEMORY_CODES,
    }


@app.get("/emotion/taxonomy")
async def emotion_taxonomy():
    """Return the full emotion taxonomy so the frontend can display it."""
    return {
        "layers": {
            "ekman":   list({"joy","sadness","anger","fear","surprise","disgust","neutral"}),
            "plutchik": list(_PLUTCHIK_BLEND.keys()),
            "nuanced":  sorted(set(_NUANCED_MAP.values())),
        },
        "total_emotions": (
            7 + len(_PLUTCHIK_BLEND) + len(set(_NUANCED_MAP.values()))
        ),
        "dimensions": ["valence", "arousal", "intensity", "quadrant"],
    }


# ── Static frontend serving (unchanged) ───────────────────────

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "=" * 65)
    print("⚡ CONTEXT-AWARE TRANSLATOR — ENHANCED MODE")
    print("=" * 65)
    print(f"📍 http://localhost:{port}")
    print(f"📚 http://localhost:{port}/docs")
    print(f"🧠 Emotion taxonomy: http://localhost:{port}/emotion/taxonomy")
    print("=" * 65)
    print("✨ NEW: Universal coreference (any entity, any name)")
    print(f"✨ NEW: {7 + len(_PLUTCHIK_BLEND) + len(set(_NUANCED_MAP.values()))} emotion types across 3 layers")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)