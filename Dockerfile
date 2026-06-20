# ============================================================
# Aşama 1 — Bağımlılıkları kur (Builder stage)
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Sadece gereksinimler dosyasını kopyala (layer cache için)
COPY requirements.txt .

# Bağımlılıkları kullanıcı dizinine kur (site-packages kopyalanabilir)
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
# Aşama 2 — Üretim imajı (Runtime stage)
# ============================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Builder'dan yalnızca kurulu paketleri al (imaj boyutunu küçültür)
COPY --from=builder /root/.local /root/.local

# Uygulama kodunu kopyala
COPY . .

# PATH'e kullanıcı bin dizinini ekle
ENV PATH=/root/.local/bin:$PATH

# Python tamponlamayı kapat (log'ların anlık görünmesi için)
ENV PYTHONUNBUFFERED=1

# FastAPI portu
EXPOSE 8000

# Uvicorn ile başlat
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
