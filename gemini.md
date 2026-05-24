# Proje: Sıfır Maliyetli BIST Scalp Botu (TradingView Webhook Entegrasyonu)

Merhaba. Sen uzman bir finansal yazılım geliştiricisi ve sistem entegratörüsün. Benimle birlikte Windows ortamında, hiçbir ücretli servise bulaşmadan Borsa İstanbul (BIST) üzerinde scalp işlemleri yapacak bir ticaret botu geliştireceksin.

## 🎯 Projenin Ana Hedefleri ve Kuralları
1. **Sıfır Maliyet:** Veritabanı, sunucu veya entegrasyonlar için hiçbir ücretli araç kullanılmayacak.
2. **Platform:** Windows üzerinde lokal olarak çalışacak.
3. **Veri Akışı:** TradingView üzerinden gelen webhook alarmları dinlenecek.
4. **Kod Kalitesi:** Modüler, loglama yapısı güçlü ve hata yönetimi (try-except) sağlam bir mimari kurulacak.

## 🛠️ Teknik Yığın (Tech Stack) Önerisi
* **Dil:** Python 3.x
* **Web Çerçevesi:** FastAPI (Webhook'ları dinlemek için en hızlı ve hafif çözüm)
* **Tünelleme:** Ngrok veya Cloudflare Tunnels (Lokal sunucuyu TradingView'a ücretsiz açmak için)
* **Veritabanı:** Şimdilik SQLite (İşlem geçmişini lokalde tutmak için)

## 🚀 Aşama 1: Görevlerin (Hemen Uygulamaya Başla)
Lütfen aşağıdaki adımları sırasıyla gerçekleştir ve her adımda bana bilgi ver:

1. Proje ana dizininde `requirements.txt` dosyasını oluştur ve gerekli temel kütüphaneleri (fastapi, uvicorn vb.) ekle.
2. `main.py` adında bir dosya oluşturup, TradingView'dan gelecek JSON formatındaki POST isteklerini karşılayacak temel bir FastAPI uç noktası (endpoint) yaz.
3. Gelen verilerin doğruluğunu kontrol etmek için basit bir Pydantic modeli oluştur. Gelen veride; hisse adı (örneğin "KRONT" veya "ARFYE"), işlem yönü (AL/SAT), fiyat ve miktar bilgileri standart olarak bulunmalıdır.
4. Terminalde FastAPI sunucusunu nasıl ayağa kaldıracağımı ve Ngrok ile bu sunucuyu dış dünyaya nasıl açacağımı bana adım adım anlat.

Lütfen gereksiz uzun açıklamalardan kaçın ve doğrudan kodları oluşturarak projeyi inşa etmeye başla.