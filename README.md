# BIST Scalper Bot & Sistem Mimarisi Referansı

Bu proje, **"Sıfır Maliyet (Zero-Cost)"** prensibiyle inşa edilmiş, bağımsız, 7/24 çalışabilen ve anlık veri analizi yapabilen bir Borsa İstanbul (BIST) botunun kaynak kodlarını ve mimari dokümantasyonunu içermektedir.

Bu repo aynı zamanda gelecekte geliştirilmesi planlanan **Risk Analizi Değerlendirme Uygulaması** ve benzeri otonom veri/olay güdümlü sistemler için bir "Hafıza Dosyası" (Global Workshop Reference) niteliğindedir.

---

## 🚀 Projenin Özeti ve "Sıfır Maliyet" Felsefesi
Bu proje, bütçe gerektiren karmaşık finansal altyapıları by-pass ederek tamamen ücretsiz araçlarla inşa edilmiştir:
- **Veri Kaynağı (Data Sourcing):** Ücretli ve kısıtlı borsa API'leri yerine, Telegram üzerindeki bir Mini App'in (Web App) WebSocket trafiği dinlenmiş; tersine mühendislik (reverse engineering) ile ücretsiz, saniyelik canlı derinlik ve işlem akışı verisi elde edilmiştir.
- **Sunucu Altyapısı (Cloud Hosting):** Google Cloud'un "Always Free" (e2-micro) katmanı kullanılarak ömür boyu ücretsiz, kesintisiz çalışan bir Linux sunucu (Docker) ortamı oluşturulmuştur.
- **Dağıtım (Deployment):** Sistem `Docker` ve `docker-compose` ile paketlenerek donanımdan/işletim sisteminden bağımsız hale getirilmiştir.
- **Bildirimler:** SMS veya ücretli push servisleri yerine Telegram Bot API kullanılarak anlık loglama ve karar bildirimleri ücretsiz hale getirilmiştir.

---

## 🏗️ Sistemin Mantıksal Akışı ve Mimarisi
Uygulama, birbirinden bağımsız çalışabilen ancak birbirini besleyen 4 ana mikro-bileşenden oluşmaktadır:

1. **Veri Toplayıcı (Data Ingestion - `veri_terminal.py`):** 
   Asenkron (asyncio) WebSocket üzerinden saniyede onlarca canlı fiyat, emir defteri (bid/ask) ve işlem bilgisini alır.
   
2. **Analiz ve Karar Motoru (Auto Analyst - `auto_analyst.py`):** 
   Gecikmeli veri (yfinance mumları) ile saniyelik mikro veriyi (emir defteri baskısı) harmanlar. MACD, RSI, Bollinger gibi teknik göstergelerle kurumsal para girişini/çıkışını çapraz kontrol ederek "AL/SAT" kararı üretir.

3. **İşlem ve Veritabanı Yöneticisi (Database & Executor - `database.py`, `order_executor.py`):** 
   Sinyalleri lokal bir SQLite veritabanına kaydeder. Sanal bir portföy üzerinden risk ve bakiye kontrolü yaparak işlemleri gerçekleştirir.

4. **Haberleşme ve Sunum (FastAPI & Telegram - `main.py`, `telegram_utils.py`):** 
   FastAPI tabanlı bir web sunucusu ayağa kaldırarak dışarıdan gelen tetiklemeleri dinler ve periyodik görevleri yönetir.

---

## 🔮 Gelecekteki Projeler (Risk Analizi) İçin Referans Çıkarımlar
Bu mimari, olay-güdümlü (event-driven) herhangi bir sürekli izleme (continuous monitoring) uygulaması için doğrudan şablondur:

- **Sürekli Arka Plan Taraması:** Bu projedeki `periodic_scan_loop()` yapısı, riskleri ve anormallikleri düzenli olarak tarayan "Health Checker" sistemlerine ilham vermelidir.
- **Olay Güdümlü Karar Verme:** Verilerin ağırlıklandırılarak (Örn: Makro Trend %40 + Mikro Saniyelik Baskı %60) skorlanması, Risk Analizi uygulamalarındaki "Risk Skoru" mantığının temelini atar.
- **Güvenli Bulut İzolasyonu:** Şifreler ve API anahtarları asla kod içine yazılmaz; `.env` dosyasından okunur. Docker kullanılarak sistem istenilen an her yerde sıfırdan aynı şekilde çalıştırılabilir.
- **Anlık Uyarı (Alerting):** Hata veya yüksek risk durumunda Telegram (veya benzeri webhook servisleri) ile yetkililere saniyesinde bildirim (Push notification) gitmesi sağlanmıştır.

---

## ⚙️ Kurulum ve Çalıştırma (Geliştiriciler İçin)

### 1. Gereksinimler
- Python 3.11+
- Docker ve Docker Compose

### 2. Yapılandırma
1. Repoyu bilgisayarınıza klonlayın.
2. Klasör içindeki `.env.example` dosyasının adını `.env` olarak değiştirin ve kendi Telegram API bilgilerinizi doldurun.
3. Telethon `*.session` dosyanızı oluşturarak ana dizine ekleyin.

### 3. Çalıştırma
Sistemi Docker üzerinden ayağa kaldırmak için:
```bash
docker-compose up -d --build
docker-compose logs -f
```

*(Not: Güvenlik nedeniyle `.env`, `.session` ve `.db` dosyaları repo dışında tutulmuş olup `.gitignore` dosyası ile engellenmiştir. Hassas verileriniz GitHub'a gönderilmez.)*
