from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import tempfile
import os
import time
import hashlib
import asyncio
import aiohttp
import gc
import uuid
from typing import Optional, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

app = FastAPI(title="Context-Aware Translation API — Fast Mode")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

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

_cache: dict = {}
MAX_CACHE = 300

def cache_key(text: str, src: str, tgt: str) -> str:
    return hashlib.md5(f"{text[:200]}{src}{tgt}".encode()).hexdigest()

def cache_get(k: str): return _cache.get(k)

def cache_set(k: str, v: str):
    global _cache
    if len(_cache) >= MAX_CACHE:
        for old in list(_cache.keys())[:50]:
            del _cache[old]
    _cache[k] = v

# ── MyMemory API ───────────────────────────────────────────────
# FIX: Added robust validation to reject bogus results like "EN", "BN"
# that MyMemory returns when rate-limited or when the language pair fails.
async def translate_mymemory(text: str, src: str, tgt: str) -> Optional[str]:
    try:
        src_code = MYMEMORY_CODES.get(src, "en")
        tgt_code = MYMEMORY_CODES.get(tgt, "hi")
        lang_pair = f"{src_code}|{tgt_code}"

        url = "https://api.mymemory.translated.net/get"
        params = {"q": text[:500], "langpair": lang_pair}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("responseData", {}).get("translatedText", "")
                    response_status = data.get("responseStatus", 0)

                    if not result or result.upper().startswith("MYMEMORY WARNING"):
                        return None

                    result_stripped = result.strip()

                    # Reject if result is just an ISO language code (e.g. "EN", "BN")
                    # This is what MyMemory returns when it fails for a language pair
                    all_codes_upper = {c.upper() for c in MYMEMORY_CODES.values()}
                    if result_stripped.upper() in all_codes_upper:
                        print(f"⚠️  MyMemory returned lang code '{result_stripped}' for {src}→{tgt} — skipping")
                        return None

                    # Reject if result is identical to input (no translation happened)
                    if result_stripped.lower() == text.strip().lower():
                        print(f"⚠️  MyMemory returned unchanged text for {src}→{tgt} — skipping")
                        return None

                    # Reject suspiciously short result for longer input
                    if len(text.strip()) > 10 and len(result_stripped) <= 3:
                        print(f"⚠️  MyMemory returned too-short result '{result_stripped}' — skipping")
                        return None

                    # Reject non-200 response status from MyMemory
                    if response_status != 200:
                        print(f"⚠️  MyMemory bad responseStatus {response_status} for {src}→{tgt} — skipping")
                        return None

                    return result_stripped
    except Exception as e:
        print(f"⚠️  MyMemory failed: {e}")
    return None

# ── LibreTranslate ─────────────────────────────────────────────
LIBRE_INSTANCES = [
    "https://libretranslate.com",
    "https://translate.argosopentech.com",
    "https://libretranslate.de",
]

async def translate_libre(text: str, src: str, tgt: str) -> Optional[str]:
    src_code = LIBRE_CODES.get(src, "en")
    tgt_code = LIBRE_CODES.get(tgt, "hi")

    payload = {
        "q":      text[:500],
        "source": src_code,
        "target": tgt_code,
        "format": "text",
    }

    for instance in LIBRE_INSTANCES:
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            ) as session:
                async with session.post(
                    f"{instance}/translate",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("translatedText", "")
                        if result:
                            return result.strip()
        except Exception as e:
            print(f"⚠️  LibreTranslate {instance} failed: {e}")
            continue
    return None

# ── Lingva ─────────────────────────────────────────────────────
LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://lingva.garudalinux.org",
    "https://translate.plausibility.cloud",
]

async def translate_lingva(text: str, src: str, tgt: str) -> Optional[str]:
    src_code = LINGVA_CODES.get(src, "en")
    tgt_code = LINGVA_CODES.get(tgt, "hi")

    import urllib.parse
    encoded = urllib.parse.quote(text[:500])

    for instance in LINGVA_INSTANCES:
        try:
            url = f"{instance}/api/v1/{src_code}/{tgt_code}/{encoded}"
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            ) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("translation", "")
                        if result:
                            return result.strip()
        except Exception as e:
            print(f"⚠️  Lingva {instance} failed: {e}")
            continue
    return None

# ── Local NLLB fallback ────────────────────────────────────────
_local_tokenizer = None
_local_model     = None

def get_local_model():
    global _local_tokenizer, _local_model
    if _local_model is None:
        print("⏳ Loading local fallback model (all APIs failed)...")
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        torch.set_grad_enabled(False)
        name = "facebook/nllb-200-distilled-600M"
        _local_tokenizer = AutoTokenizer.from_pretrained(name)
        _local_model = AutoModelForSeq2SeqLM.from_pretrained(
            name,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True,
        )
        _local_model.eval()
        print("✅ Local fallback model loaded")
    return _local_tokenizer, _local_model

def translate_local_sync(text: str, src: str, tgt: str) -> str:
    import torch
    tokenizer, model = get_local_model()
    src_code = NLLB_LANG_CODES.get(src, "eng_Latn")
    tgt_code = NLLB_LANG_CODES.get(tgt, "hin_Deva")
    if tokenizer is not None:
        tokenizer.src_lang = src_code
        inputs = tokenizer(text[:300], return_tensors="pt", truncation=True, max_length=128)
    else:
        raise RuntimeError("Tokenizer failed to load")
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id[tgt_code],
            max_new_tokens=80,
            num_beams=1,
            do_sample=False,
        )
    return tokenizer.batch_decode(outputs, skip_special_tokens=True)[0].strip()

# ── Idiom + Coreference ────────────────────────────────────────
IDIOM_MAP = {
    "call it a day":          "finish the day's work",
    "I'm fine":               "I'm fine but emotionally not okay",
    "under the weather":      "feeling sick",
    "hit the sack":           "go to sleep",
    "break a leg":            "good luck",
    "piece of cake":          "very easy task",
    "costs an arm and a leg": "very expensive",
}

def replace_idioms(text: str) -> str:
    for k, v in IDIOM_MAP.items():
        text = text.replace(k, v)
    return text

def resolve_coreference(text: str, context: Optional[List[str]]) -> str:
    if not context: return text
    last = context[-1]
    if "Rahul" in last:   text = text.replace(" he ", " Rahul ")
    if "manager" in last: text = text.replace(" she ", " the manager ")
    return text

# ── Main translate orchestrator ────────────────────────────────
async def translate_fast(
    text: str,
    src_lang: str,
    tgt_lang: str,
    context: Optional[List[str]] = None
) -> tuple[str, str]:
    text = replace_idioms(text)
    text = resolve_coreference(text, context)

    ck = cache_key(text, src_lang, tgt_lang)
    cached = cache_get(ck)
    if cached:
        print("⚡ Cache HIT")
        return cached, "cache"

    if src_lang == tgt_lang:
        return text, "passthrough"

    print(f"🔄 Translating: {src_lang} → {tgt_lang}")

    result = await translate_mymemory(text, src_lang, tgt_lang)
    if result:
        cache_set(ck, result)
        print("✅ MyMemory ~200ms")
        return result, "mymemory"

    result = await translate_libre(text, src_lang, tgt_lang)
    if result:
        cache_set(ck, result)
        print("✅ LibreTranslate ~400ms")
        return result, "libretranslate"

    result = await translate_lingva(text, src_lang, tgt_lang)
    if result:
        cache_set(ck, result)
        print("✅ Lingva ~500ms")
        return result, "lingva"

    print("⚠️  All APIs failed — using local model (will be slow)")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor, translate_local_sync, text, src_lang, tgt_lang
    )
    cache_set(ck, result)
    return result, "local_nllb"

# ── Emotion detection ──────────────────────────────────────────
_emotion_classifier = None

def get_emotion():
    global _emotion_classifier
    if _emotion_classifier is None:
        print("⏳ Loading emotion model...")
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
    try:
        clf = get_emotion()
        results = clf(text[:512])
        if isinstance(results, list) and len(results) > 0:
            results = results[0] if isinstance(results[0], list) else results
        results_list = results if isinstance(results, list) else []
        scores = {
            str(i.get('label', '')).lower(): float(i.get('score', 0))
            for i in results_list if isinstance(i, dict)
        }
        dominant = max(
            (i for i in results_list if isinstance(i, dict)),
            key=lambda x: x.get('score', 0), default=None
        )
        if not dominant:
            return {"emotion": "neutral", "confidence": 0.5, "scores": scores}
        return {
            "emotion":    dominant.get('label', 'neutral'),
            "confidence": dominant.get('score', 0.5),
            "scores":     scores,
        }
    except Exception as e:
        print(f"⚠️  Emotion error: {e}")
        return {
            "emotion": "neutral", "confidence": 0.5,
            "scores": {"joy": 0, "sadness": 0, "anger": 0,
                       "fear": 0, "surprise": 0, "neutral": 1}
        }

# ── Whisper ────────────────────────────────────────────────────
_whisper = None

def get_whisper():
    global _whisper
    if _whisper is None:
        print("⏳ Loading Whisper tiny...")
        import whisper
        _whisper = whisper.load_model("tiny")
        print("✅ Whisper tiny loaded")
    return _whisper

# ── Session storage ────────────────────────────────────────────
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

    def get_context(self, use_ctx: bool, top_k: int = 2) -> List[str]:
        if not use_ctx or not self.history: return []
        return [r["original"] for r in self.history[-top_k:]]

    def clear(self):
        self.history = []
        self.last_accessed = datetime.now()

    def get_history(self, limit=10):
        return self.history[-limit:]

    def is_expired(self):
        return (datetime.now() - self.last_accessed).total_seconds() > SESSION_TTL

def cleanup_sessions():
    global sessions
    expired = [s for s, v in sessions.items() if v.is_expired()]
    for s in expired: del sessions[s]
    if len(sessions) > MAX_SESSIONS:
        for s, _ in sorted(sessions.items(), key=lambda x: x[1].last_accessed)[:len(sessions)-MAX_SESSIONS]:
            del sessions[s]

def get_session(sid: Optional[str]) -> TranslationSession:
    cleanup_sessions()
    if sid and sid in sessions: return sessions[sid]
    new_id = sid or str(uuid.uuid4())
    sessions[new_id] = TranslationSession(new_id)
    return sessions[new_id]

# ── Endpoints ──────────────────────────────────────────────────
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
                    best_of=1,  temperature=0,
                    condition_on_previous_text=False,
                )
            )
            text = str(res.get("text", "")).strip()
        finally:
            os.unlink(tmp_path)

        trans_time = (time.time() - t0) * 1000

    if not text:
        return {"error": "No text provided"}

    text    = text[:1500]
    ctx     = session.get_context(use_context)
    t1      = time.time()

    translated_task = translate_fast(text, source_lang, target_lang, ctx)
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
        "emotion":           emotion_data,
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
            "name":     f"Fast API ({method})",
            "type":     "Multi-API with local fallback",
            "features": [
                "MyMemory API ~200ms",
                "LibreTranslate fallback",
                "Lingva fallback",
                "Local NLLB last resort",
                "Result caching",
                "Parallel emotion detection",
            ]
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
    start   = time.time()
    tasks   = [translate_fast(t, source_lang, target_lang) for t in texts]
    results = await asyncio.gather(*tasks)
    translations = [r[0] for r in results]
    total = (time.time() - start) * 1000
    return {
        "translations": translations,
        "count":        len(translations),
        "performance":  {"total_ms": total, "avg_ms": total / len(texts)}
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
            {"session_id": sid, "history_count": len(s.history),
             "last_accessed": s.last_accessed.isoformat()}
            for sid, s in sessions.items()
        ],
        "total": len(sessions)
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "mode":   "fast-api",
        "translation_backends": [
            "MyMemory (~200ms, free, 5000 words/day)",
            "LibreTranslate (~400ms, free, unlimited)",
            "Lingva (~500ms, free, unlimited)",
            "Local NLLB-600M (fallback, slow)",
        ],
        "cache_size":      len(_cache),
        "active_sessions": len(sessions),
        "models_loaded": {
            "whisper":    _whisper is not None,
            "emotion":    _emotion_classifier is not None,
            "local_nllb": _local_model is not None,
        }
    }

@app.get("/supported-languages")
async def supported_languages():
    return {
        "languages":      list(MYMEMORY_CODES.keys()),
        "total_count":    len(MYMEMORY_CODES),
        "language_codes": MYMEMORY_CODES,
    }

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(
        directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

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
    print("⚡ CONTEXT-AWARE TRANSLATOR — FAST API MODE")
    print("=" * 65)
    print(f"📍 http://localhost:{port}")
    print(f"📚 http://localhost:{port}/docs")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)