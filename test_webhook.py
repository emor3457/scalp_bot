import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

def send_request(url, data=None, method='GET', extra_headers=None):
    req_data = json.dumps(data).encode('utf-8') if data else None
    headers = {'Content-Type': 'application/json'} if data else {}
    if extra_headers:
        headers.update(extra_headers)
    
    req = urllib.request.Request(
        url,
        data=req_data,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8')
            try:
                res_data = json.loads(response_body)
            except:
                res_data = response_body
            return status_code, res_data
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode('utf-8'))
        except:
            err_body = e.read().decode('utf-8')
        return e.code, err_body
    except Exception as e:
        return 0, str(e)


def run_tests():
    base_url = "http://127.0.0.1:8000"
    token = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()
    headers = {"X-Webhook-Token": token} if token else None
    
    print("=== 1. BASLANGIC PORTFOY DURUMU ===")
    status, res = send_request(f"{base_url}/portfolio")
    print(f"Durum: {status} | Portfoy: {json.dumps(res, indent=2)}\n")
    
    print("=== 2. GECERLI AL ISLEMI (KRONT) ===")
    al_data = {
        "ticker": "KRONT",
        "action": "AL",
        "price": 75.0,
        "quantity": 100.0
    }
    status, res = send_request(f"{base_url}/webhook", al_data, 'POST', extra_headers=headers)
    print(f"Durum: {status} | Yanit: {json.dumps(res, indent=2)}\n")
    
    print("=== 3. ISLEM SONRASI PORTFOY DURUMU ===")
    status, res = send_request(f"{base_url}/portfolio")
    print(f"Durum: {status} | Portfoy: {json.dumps(res, indent=2)}\n")
    
    print("=== 4. ISLEM GECMISI ===")
    status, res = send_request(f"{base_url}/trades")
    print(f"Durum: {status} | Islemler: {json.dumps(res, indent=2)}\n")

    print("=== 5. GECERLI SAT ISLEMI (KRONT - 50 lot) ===")
    sat_data = {
        "ticker": "KRONT",
        "action": "SAT",
        "price": 80.0,
        "quantity": 50.0
    }
    status, res = send_request(f"{base_url}/webhook", sat_data, 'POST', extra_headers=headers)
    print(f"Durum: {status} | Yanit: {json.dumps(res, indent=2)}\n")

    print("=== 6. SATIS SONRASI PORTFOY DURUMU ===")
    status, res = send_request(f"{base_url}/portfolio")
    print(f"Durum: {status} | Portfoy: {json.dumps(res, indent=2)}\n")
    
    print("=== 7. HATA TESTI: BAKIYE YETERSIZ AL ===")
    zengin_al_data = {
        "ticker": "ARFYE",
        "action": "AL",
        "price": 1000.0,
        "quantity": 200.0  # 200.000 TL maliyet
    }
    status, res = send_request(f"{base_url}/webhook", zengin_al_data, 'POST', extra_headers=headers)
    print(f"Durum: {status} | Yanit: {json.dumps(res, indent=2)}\n")

    print("=== 8. HATA TESTI: ELDE OLMAYAN SATIS ===")
    olmayan_sat_data = {
        "ticker": "ARFYE",
        "action": "SAT",
        "price": 10.0,
        "quantity": 10.0
    }
    status, res = send_request(f"{base_url}/webhook", olmayan_sat_data, 'POST', extra_headers=headers)
    print(f"Durum: {status} | Yanit: {json.dumps(res, indent=2)}\n")

    print("=== 9. GUVENLIK TESTI: YETKISIZ ERISIM (Gecersiz Token) ===")
    yetkisiz_headers = {"X-Webhook-Token": "wrong_token_1234"}
    status, res = send_request(f"{base_url}/webhook", al_data, 'POST', extra_headers=yetkisiz_headers)
    print(f"Durum: {status} (Beklenen: 401) | Yanit: {json.dumps(res, indent=2)}\n")

if __name__ == "__main__":
    run_tests()

