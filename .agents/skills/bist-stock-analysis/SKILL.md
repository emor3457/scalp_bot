---
name: bist-stock-analysis
description: "BIST (Borsa Istanbul) hisseleri icin tam kapsamli temel + teknik analiz. Projenin auto_analyst / news_analyst / market_data modullerini kullanir; KAP ve isYatirim veri kaynaklarini destekler. Turkce rapor uretir."
version: "1.0.0"
author: claude-office-skills (fork: bist)
license: MIT

category: finance
tags:
  - bist
  - borsa-istanbul
  - turkiye
  - stock
  - analysis
  - fundamental
  - technical
  - temel-analiz
  - teknik-analiz

languages:
  - tr

capabilities:
  - fundamental_analysis
  - technical_analysis
  - valuation_metrics
  - peer_comparison
  - risk_assessment

related_skills:
  - technical-analysis
  - trading-analysis
  - yahoo-finance
  - finance-news
---

# BIST Hisse Analiz Skill'i

## Genel Bakis

BIST (Borsa Istanbul) hisselerini **temel ve teknik analiz** yontemleriyle analiz eder.
Bu skill, projenin hazir analiz motoruna dayanir:

- **Teknik skor (0-100):** `auto_analyst.calculate_technical_score` — gunluk + saatlik cift zaman
  dilimi (EMA dizilimi, RSI, MACD, Bollinger, hacim teyidi)
- **Temel skor (0-100):** `auto_analyst.calculate_fundamental_score` — F/K, ROE, EPS, 52 haftalik dip
- **Haber skoru (0-100):** `news_analyst.get_news_score` — Yahoo RSS haber duyarliligi
- **Kompozit skor:** Teknik %50 + Temel %25 + Haber %25 (AL >= 65, SAT <= 30, digerleri HOLD)

**Yapabildikleri:**
- Tek hisse icin derin analiz raporu (temel + teknik + haber)
- Emsal karsilastirma (BIST sektor endeksleri uzerinden)
- Risk degerlendirmesi ve yatirim tezi
- Yapilandirilmis Turkce rapor ciktisi (TL biriminde)

**Yapamadiklari:**
- Gercek zamanli fiyat garantisi (veri gecikmeli olabilir — yfinance BIST verisi)
- Yatirim tavsiyesi / kesin oneri
- KAP uzerindeki ozel/isyeri verilerine erisim (kullanici saglamali)

---

## Veri Kaynaklari (BIST)

| Kaynak | Ne Icin | Erisim |
|---|---|---|
| **yfinance (`{TICKER}.IS`)** | Fiyat geçmisi, teknik gostergeler, temel bilgi (kismi) | Proje modulleri (`market_data`, `auto_analyst`) |
| **`scripts/bist_data.py`** | Tum yukaridakileri tek JSON'da toplar | `python .../bist_data.py THYAO` |
| **KAP (kamuyu Aydinlatma Platformu)** | **Birincil temel veri**: mali tablolar, bagimsiz denetim raporlari, ozel durum aciklamalari | https://www.kap.org.tr (web/manuel) |
| **isYatirim API** | BIST gunluk OHLC, emsal karsilastirma, sektor verisi | https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/Temel-Degerler.aspx |
| **Yahoo RSS (haber)** | Haber duyarliligi skoru | `news_analyst` |

> **Kritik:** Yahoo'nun BIST temel verisi (`info`) kismi ve bazen bos olabilir (ornek: KOZAA).
> Derin temel analiz icin **KAP mali tablolarini** kullanin; yoksa temel skoru notr (50)
> varsayip raporda veri eksikligini belirtin.

---

## BIST'e Ozgu Eskikler (ABD Eskikleri GECERSIZ)

Turkkiye'nin yuksek enflasyon ve faiz ortami nedeniyle ABD esikleri yaniltici olur:

| Metrik | BIST Yaklasimi |
|---|---|
| **F/K (P/E)** | Banka disi: 6-12 makul, >20 pahali. Bankalar F/K yerine **P/B** ile degerlenir |
| **P/B** | Bankalar: 0.5-1.5 bandi normal; >2 pahali. Sanayi: <1 deger firsati |
| **ROE** | Bankalar >%20 guclu; sanayi >%15 guclu (enflasyon cagi karliligi sisirir) |
| **Buyume** | Nominal buyume enflasyonla sisiktir: **reel buyume = nominal - enflasyon** |
| **PEG** | Yuksek enflasyonda guvenilmez — kullanma |
| **EV/EBITDA** | TCMB politika faizi yuksekken <6 cekici, >10 pahali |
| **Kur etkisi** | Kurlardaki hareket (USD/TRY) BIST karliligini dogrudan etkiler — rapora not dus |

**BIST piyasa yapisi notlari:**
- Seans: 10:00-18:00 Istanbul (ogle arasi 13:00-14:00). Seans disinda fiyatlar bayattir.
- Takas: **T+2**. Bazli hisselerde **brut takas / kredili islem yasagi** gibi kisitlar olabilir.
- Banka hisseleri (AKBNK, GARAN, YKBNK, ISCTR) endeks agirligini olusturur — emsal karsilastirmada
  sektor endeksi kullan: XBANK / XUSIN / XULAS / XGMYO / XTRZM / XGIDA / XUTEK / XKMYA / XHOLD / XTAST / XILTM
  (esleme `scripts/bist_data.py` icindeki `SEKTOR_ENDEX`).

---

## Proje Modulleriyle Entegrasyon

Veriyi toplamanin iki yolu vardir:

### 1) Hazir veri toplayici (oneri)

```bash
# Proje kokunden (venv):
.venv/Scripts/python.exe .agents/skills/bist-stock-analysis/scripts/bist_data.py THYAO
.venv/Scripts/python.exe .agents/skills/bist-stock-analysis/scripts/bist_data.py THYAO --out thyao.json
```

Cikti JSON su bolumleri icerir: `meta` (ticker, sektor endeksi), `prices` (canli fiyat,
52 haftalik mesafeler), `technical` (skor + tum gostergeler), `fundamental` (skor + yfinance
info), `news` (skor + basliklar), `composite` (kompozit skor + sinyal ipucu).

### 2) Modul API'sini dogrudan kullan

```python
import asyncio
import yfinance as yf
import auto_analyst, news_analyst, market_data

async def analiz_et(ticker: str):
    stock = yf.Ticker(f"{ticker}.IS")
    df_d, df_h, info = await asyncio.gather(
        asyncio.to_thread(auto_analyst._fetch_history, stock, "6mo", "1d"),
        asyncio.to_thread(auto_analyst._fetch_history, stock, "1mo", "1h"),
        asyncio.to_thread(auto_analyst._fetch_info, stock),
    )
    tek, detay = auto_analyst.calculate_technical_score(df_d, df_h)
    tem = auto_analyst.calculate_fundamental_score(info, detay.get("dist_from_52w_low", 50.0))
    hab = await news_analyst.get_news_score(ticker)
    fiyat = await market_data.get_stock_price(ticker)
    kompozit = tek * 0.50 + tem * 0.25 + hab * 0.25
    return {"ticker": ticker, "teknik": tek, "temel": tem, "haber": hab,
            "kompozit": kompozit, "fiyat": fiyat, "gostergeler": detay,
            "basliklar": await news_analyst.get_news_headlines(ticker)}
```

### KAP ile derin temel analiz

Yahoo verisi yetersizse KAP'tan mali tablo verisini (gelir tablosu, bilanco, nakit akisi)
toplayip `calculate_fundamental_score` disinda manuel hesaplayin:
- P/E = Fiyat / (Net Kar / Odenmis Sermaye x ...) — KAP verisindeki hisse basi kar
- ROE = Net Kar / Ozkaynaklar (KAP bilanco)
- Buyume = (Bu yil Net Kar - Gecen yil Net Kar) / Gecen yil Net Kar — enflasyon duzeltmesi notuyla

---

## Rapor Ciktisi (Turkce, TL)

```markdown
# BIST Analiz Raporu: [TICKER]

**Sirket**: [Unvan] | **Sektor**: [BIST sektor endeksi]
**Analiz Tarihi**: [Tarih] | **Fiyat**: [X.XX] TL

---

## Ozet

[2-3 cumle: sirket tanimi + kompozit skor yorumu]
**Degerlendirme**: [Guclu / Notr / Zayif]
**Risk Seviyesi**: [Dusuk / Orta / Yuksek]

---

## Kompozit Skor

| Bilesen | Agirlik | Skor |
|---|---|---|
| Teknik | %50 | XX.X |
| Temel | %25 | XX.X |
| Haber | %25 | XX.X |
| **Kompozit** | | **XX.X** (>=65 AL / <=30 SAT) |

---

## Temel Analiz

### Isletme Genel Bakis
[sirket, gelir kaynaklari, rekabet avantaji]

### Finansal Gorunum
[gelir/karlilik/ROE; KAP verisi varsa reel buyume ve enflasyon duzeltmesi]

### Degerleme
[F/K, P/B — BIST esiklerine gore (bankaysa P/B odakli)]

---

## Teknik Analiz

### Fiyat Trendi
[EMA dizilimi, MACD, RSI — auto_analyst gostergelerinden]

### Onemli Seviyeler
- Destek: [X.XX] TL
- Direnc: [X.XX] TL
- 52 Haftalik Aralik: [X.XX] - [X.XX] TL

---

## Haber Gorunumu
[haber skoru + ilk 2-3 baslik; negatif (<30) ise sinyal bloklandigini belirt]

---

## Risk Faktorleri
1. [risk 1]
2. [risk 2]
3. [risk 3]

---

## Yatirim Tezi
### Yapici (Bull)
[pozitif senaryo]
### Yikici (Bear)
[negatif senaryo]

---

**Uyari**: Bu analiz yalnizca bilgilendirme amaclidir, yatirim tavsiyesi degildir.
Gecmis performans gelecekteki sonuclari garanti etmez. Turkkiye'de yuksek enflasyon ve
kur oynakligi degerleme varsayimlarini hizla degistirebilir.
```

---

## Ornek Kullanim

**Kullanici:** "THYAO hissesini analiz et, temel ve teknik analiz yap"
**Siz:**
1. `python .../bist_data.py THYAO` calistirin (veya modul API'sini kullanin)
2. Yahoo temel verisi eksikse KAP'tan mali tablo arayin (web)
3. Sektor endeksini (XULAS/XUSIN) belirleyin, emsal karsilastirmasini yapin
4. Turkce raporu yukaridaki sablona gore yazin, TL biriminde

---

## Sinirlamalar

- Gercek zamanli fiyat yok (gecikmeli yfinance verisi; seans disinda bayat)
- Yahoo BIST temel verisi kismi/eksik olabilir — KAP birincil kaynaktir
- Haber skoru yalnizca Yahoo RSS kaynaklarina dayanir
- Enflasyon/kur ozellikleri degerlemeyi hizla degistirebilir
- Profesyonel finansal tavsiye degildir
