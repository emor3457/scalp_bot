"""
bist_data.py — bist-stock-analysis skill'i icin CLI veri katmani.

Veri toplama ve rapor uretme mantigi artik proje kokundeki `bist_analysis`
modulunde (tek kaynak — dashboard `/api/deep-analysis` endpoint'i de ayni
modulu kullanir). Bu script yalnizca komut satiri ara yuzudur.

Kullanim (proje kokunden):
    .venv/Scripts/python.exe .agents/skills/bist-stock-analysis/scripts/bist_data.py THYAO            # JSON veri
    .venv/Scripts/python.exe .../bist_data.py THYAO --out thyao.json                                  # JSON dosyaya
    .venv/Scripts/python.exe .../bist_data.py THYAO --markdown                                         # Turkce Markdown rapor
"""

import argparse
import asyncio
import json
import os
import sys

# Proje kokunu path'e ekle (script .agents/skills/bist-stock-analysis/scripts icinde)
# 5x dirname: scripts -> bist-stock-analysis -> skills -> .agents -> proje koku
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bist_analysis  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="BIST hisse analiz verisi/raporu")
    parser.add_argument("ticker", help="BIST ticker (Orn: THYAO)")
    parser.add_argument("--out", help="JSON cikti dosyasi (verilmezse stdout)")
    parser.add_argument("--markdown", action="store_true", help="SKILL.md sablonuna uygun Turkce Markdown rapor uret")
    args = parser.parse_args()

    ticker = args.ticker.upper().replace(".IS", "")
    try:
        if args.markdown:
            md = asyncio.run(bist_analysis.build_markdown(ticker))
            print(md)
            return
        data = asyncio.run(bist_analysis.collect(ticker))
    except Exception as e:
        print(json.dumps({"error": f"{ticker} analiz verisi toplanamadi: {str(e)}"}, ensure_ascii=False))
        sys.exit(1)

    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Yazildi: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
