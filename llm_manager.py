"""
llm_manager.py — Dinamik LLM (Yapay Zeka) Sağlayıcı ve Model Yönetim Modülü
---------------------------------------------------------------------------
Özellikler:
1. Google Gemini (varsayılan) ve OpenAI sağlayıcı desteği.
2. Girilen API anahtarına göre sağlayıcıdan o hesaba açık olan tüm aktif modelleri anlık çekme.
3. Seçilen aktif modelin veritabanında (bot_settings) ve ortamda global olarak saklanması.
4. Tam reset durumunda ayarların korunması.
5. Haber duyarlılığı ve derin hisse analizi için asenkron metin üretimi (generate_text).
"""

import os
import json
import logging
import asyncio
import urllib.request
import urllib.error
import database

logger = logging.getLogger("BistScalpBot")

DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

DEFAULT_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "o1",
    "o3-mini"
]


def mask_key(key: str) -> str:
    """API anahtarını güvenlik için maskeler (Örn: AIzaSy...94xQ)."""
    if not key or len(key.strip()) < 8:
        return ""
    k = key.strip()
    return f"{k[:6]}...{k[-4:]}"


async def get_llm_settings() -> dict:
    """Veritabanından ve ortamdan mevcut LLM ayarlarını okur."""
    provider = await database.get_setting("llm_provider", "gemini")
    model = await database.get_setting("llm_model", "gemini-2.5-flash")
    db_key = await database.get_setting("llm_api_key", "")
    
    # Ortam değişkeni fallback'i
    if not db_key:
        if provider == "gemini":
            db_key = os.getenv("GEMINI_API_KEY", "")
        elif provider == "openai":
            db_key = os.getenv("OPENAI_API_KEY", "")

    models_raw = await database.get_setting("llm_available_models", "")
    try:
        available_models = json.loads(models_raw) if models_raw else (
            DEFAULT_GEMINI_MODELS if provider == "gemini" else DEFAULT_OPENAI_MODELS
        )
    except Exception:
        available_models = DEFAULT_GEMINI_MODELS if provider == "gemini" else DEFAULT_OPENAI_MODELS

    return {
        "status": "success",
        "provider": provider,
        "model": model,
        "active_model": model,
        "api_key": db_key,
        "has_key": bool(db_key and len(db_key.strip()) > 5),
        "api_key_masked": mask_key(db_key),
        "available_models": available_models
    }


def _fetch_gemini_models_sync(api_key: str) -> list[str]:
    """Gemini API'sinden o anahtara ait tüm aktif modelleri çeker."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}"
    req = urllib.request.Request(url, headers={"User-Agent": "BistScalpBot/2.0"})
    
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        models = data.get("models", [])
        
        valid_models = []
        for m in models:
            name = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            # Metin üretimi destekleyen modeller
            if "generateContent" in methods:
                valid_models.append(name)

        # Flash ve Pro modellerini öne al
        def model_sort_key(m_name: str):
            score = 50
            if "2.5-flash" in m_name: score = 1
            elif "2.5-pro" in m_name: score = 2
            elif "2.0-flash" in m_name: score = 3
            elif "1.5-flash" in m_name: score = 4
            elif "1.5-pro" in m_name: score = 5
            return (score, m_name)

        valid_models.sort(key=model_sort_key)
        return valid_models if valid_models else DEFAULT_GEMINI_MODELS


def _fetch_openai_models_sync(api_key: str) -> list[str]:
    """OpenAI API'sinden aktif chat modellerini çeker."""
    url = "https://api.openai.com/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "BistScalpBot/2.0"
        }
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        models = data.get("data", [])
        
        valid = []
        for m in models:
            mid = m.get("id", "")
            if any(prefix in mid for prefix in ["gpt-4", "gpt-3.5", "o1", "o3"]):
                valid.append(mid)

        valid.sort()
        return valid if valid else DEFAULT_OPENAI_MODELS


async def fetch_available_models(provider: str, api_key: str) -> dict:
    """
    Belirtilen sağlayıcı ve API anahtarı için aktif modelleri çeker.
    Bağlantıyı ve API anahtarının geçerliliğini doğrular.
    """
    prov = (provider or "gemini").lower()
    clean_key = (api_key or "").strip()

    # Eğer maskeli geldiyse mevcut veritabanındaki anahtarı al
    if "..." in clean_key or not clean_key:
        clean_key = await database.get_setting("llm_api_key", "")
        if not clean_key and prov == "gemini":
            clean_key = os.getenv("GEMINI_API_KEY", "")

    if not clean_key:
        return {
            "status": "error",
            "message": "Lütfen geçerli bir API anahtarı girin."
        }

    try:
        if prov == "gemini":
            models = await asyncio.to_thread(_fetch_gemini_models_sync, clean_key)
        elif prov == "openai":
            models = await asyncio.to_thread(_fetch_openai_models_sync, clean_key)
        else:
            return {"status": "error", "message": f"Desteklenmeyen sağlayıcı: {provider}"}

        return {
            "status": "success",
            "provider": prov,
            "models": models,
            "count": len(models)
        }
    except urllib.error.HTTPError as he:
        logger.error(f"LLM API HTTP hatası [{prov}]: {he.code} - {he.reason}")
        if he.code in [400, 401, 403]:
            return {"status": "error", "message": "API Anahtarı geçersiz veya yetkisiz. Lütfen anahtarınızı kontrol edin."}
        return {"status": "error", "message": f"API Sağlayıcı Hatası ({he.code}): {he.reason}"}
    except Exception as e:
        logger.error(f"LLM Modelleri çekilirken hata [{prov}]: {str(e)}")
        return {"status": "error", "message": f"Bağlantı hatası: {str(e)}"}


async def save_llm_settings(provider: str, api_key: str, model: str) -> dict:
    """
    Kullanıcının girdiği API sağlayıcısını, anahtarını ve seçtiği modeli
    veritabanına ve çalışma ortamına kalıcı olarak kaydeder.
    """
    prov = (provider or "gemini").lower()
    clean_key = (api_key or "").strip()
    clean_model = (model or "").strip()

    await database.set_setting("llm_provider", prov)

    # Eğer anahtar girilmişse ve maskeli değilse kaydet
    if clean_key and "..." not in clean_key:
        await database.set_setting("llm_api_key", clean_key)
        if prov == "gemini":
            os.environ["GEMINI_API_KEY"] = clean_key
        elif prov == "openai":
            os.environ["OPENAI_API_KEY"] = clean_key

        # Modelleri güncelle
        fetch_res = await fetch_available_models(prov, clean_key)
        if fetch_res.get("status") == "success" and fetch_res.get("models"):
            await database.set_setting("llm_available_models", json.dumps(fetch_res["models"]))
            if not clean_model:
                clean_model = fetch_res["models"][0]

    if clean_model:
        await database.set_setting("llm_model", clean_model)

    logger.info(f"LLM Ayarları Güncellendi -> Sağlayıcı: {prov} | Model: {clean_model}")
    return await get_llm_settings()


def _generate_gemini_sync(api_key: str, model: str, prompt: str, system_prompt: str = None) -> str:
    """Gemini generateContent REST API çağrısı."""
    clean_model = model.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key.strip()}"
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048
        }
    }

    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "BistScalpBot/2.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        candidates = res_json.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
        return "Modelden yanıt alınamadı."


def _generate_openai_sync(api_key: str, model: str, prompt: str, system_prompt: str = None) -> str:
    """OpenAI chat/completions REST API çağrısı."""
    url = "https://api.openai.com/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "BistScalpBot/2.0"
        }
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        choices = res_json.get("choices", [])
        if choices and "message" in choices[0]:
            return choices[0]["message"].get("content", "")
        return "Modelden yanıt alınamadı."


async def generate_text(prompt: str, system_prompt: str = None) -> dict:
    """
    Global olarak yapılandırılmış aktif LLM sağlayıcısını ve modelini
    kullanarak metin (analiz, yorum, özet) üretir.
    """
    settings = await get_llm_settings()
    provider = settings.get("provider", "gemini")
    model = settings.get("model", "gemini-2.5-flash")
    
    api_key = await database.get_setting("llm_api_key", "")
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY", "") if provider == "gemini" else os.getenv("OPENAI_API_KEY", "")

    if not api_key:
        return {
            "status": "no_key",
            "text": "⚠️ Yapay Zeka API Anahtarı tanımlanmamış. Dashboard üzerinden 'API Ayarları' butonuna tıklayarak anahtarınızı girebilirsiniz.",
            "provider": provider,
            "model": model
        }

    try:
        if provider == "gemini":
            text = await asyncio.to_thread(_generate_gemini_sync, api_key, model, prompt, system_prompt)
        elif provider == "openai":
            text = await asyncio.to_thread(_generate_openai_sync, api_key, model, prompt, system_prompt)
        else:
            text = f"Bilinmeyen sağlayıcı: {provider}"

        return {
            "status": "success",
            "text": text,
            "provider": provider,
            "model": model
        }
    except Exception as e:
        logger.error(f"LLM Metin Üretim Hatası [{provider} - {model}]: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "text": f"Yapay zeka analizi sırasında bir hata oluştu: {str(e)}",
            "provider": provider,
            "model": model
        }
