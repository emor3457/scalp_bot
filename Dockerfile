FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (for better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright install (needed for order_executor web automation)
RUN playwright install chromium --with-deps

# Copy the rest of the application
COPY . .

ENV PYTHONUNBUFFERED=1

# Expose the API port
EXPOSE 8000

# Start the main script using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
