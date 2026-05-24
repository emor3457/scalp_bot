"""
Veri Terminali API Keşif Scripti v2
- input() yok, tarayici arka planda kalmaz
- Siz web.telegram.org'u kendi Chrome'unuzda acin
- Chrome DevTools Network sekmesinden API URL'lerini kopyalayin
- Bu script o URL'lere direkt istek atar ve veriyi ceker
"""

import sys
import json
import urllib.request
import urllib.parse

# =============================================================
# ADIM 1: Chrome'da kesfedilen API URL'lerini buraya yapin
# Ornek: "https://api.ucretsizderinlik.com/v1/stocks/ASELS"
# =============================================================

# Chrome DevTools -> Network sekmesinde gordugunuz API URL'lerini buraya ekleyin:
DISCOVERED_URLS = [
    # Bos birakin, ilk calistirmada otomatik dolduracagiz
]

# =============================================================
# ADIM 2: Kendi Chrome'unuzda su adresi acin:
# https://web.telegram.org/a/#8507819282
# Sonra F12 -> Network sekmesi -> XHR/Fetch filtresini secin
# =============================================================

def test_api_url(url: str, headers: dict = None):
    """Bir API URL'ini test eder ve sonucu dondurur."""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
        }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            try:
                return json.loads(body)
            except:
                return body
    except Exception as e:
        return {"error": str(e)}


def scan_known_endpoints():
    """
    Bilinen veya tahmin edilen endpoint'leri tarar.
    Bu sayede Chrome olmadan da API'leri bulabiliriz.
    """
    # Olasi base URL'ler
    base_candidates = [
        "https://api.ucretsizderinlikbot.com",
        "https://ucretsizderinlikbot.com/api",
        "https://api.veriterminal.com",
        "https://backend.ucretsizderinlik.com",
        "https://ucretsizderinlik.com/api",
    ]
    
    # Olasi endpoint'ler
    endpoint_candidates = [
        "/v1/stocks",
        "/api/stocks",
        "/stocks",
        "/v1/depth/ASELS",
        "/api/depth/ASELS",
        "/v1/trades/ASELS",
        "/health",
        "/",
    ]
    
    print("API endpoint taraması başlıyor...\n")
    found = []
    
    for base in base_candidates:
        for endpoint in endpoint_candidates:
            url = base + endpoint
            print(f"Deneniyor: {url}")
            result = test_api_url(url)
            if "error" not in str(result)[:50]:
                print(f"  ✅ BULUNDU: {url}")
                found.append({"url": url, "response": result})
            else:
                print(f"  ❌ Yok")
    
    return found


if __name__ == "__main__":
    print("="*60)
    print("VERİ TERMİNALİ - API TARAMA")
    print("="*60)
    
    results = scan_known_endpoints()
    
    if results:
        print(f"\n✅ {len(results)} endpoint bulundu!")
        with open("found_endpoints.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    else:
        print("\n❌ Otomatik taramada endpoint bulunamadı.")
        print("\nAlternatif yöntem için şu adımları yapın:")
        print("1. Chrome'u açın")
        print("2. web.telegram.org/a/#8507819282 adresine gidin")
        print("3. F12 -> Network -> Fetch/XHR filtresi")
        print("4. OPEN APP'e tıklayın")
        print("5. Gördüğünüz API URL'lerini bana bildirin")
