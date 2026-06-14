import urllib.request
import json
import time

def test_scan():
    url = "http://127.0.0.1:8000/scan"
    print("=== ASENKRON PARALEL TARAMA BASLATILIYOR ===")
    start_time = time.time()
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            duration = time.time() - start_time
            print(f"Tarama {duration:.2f} saniyede tamamlandi! (Yfinance loop ile normalde ~40-60 sn surerdi)")
            print(f"Taranan Hisse Sayisi: {res_json.get('total_scanned')}")
            print(f"Uretilen Sinyal Sayisi: {res_json.get('signals_generated_count')}")
            if res_json.get('signals'):
                print(f"Sinyaller: {json.dumps(res_json.get('signals'), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"Tarama basarisiz: {e}")

if __name__ == "__main__":
    test_scan()
