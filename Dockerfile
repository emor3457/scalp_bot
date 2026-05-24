FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (for better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright install (needed for yfinance backend or any browser tasks if they arise, though not strictly required for websockets)
RUN playwright install chromium --with-deps

# Copy the rest of the application
COPY . .

# Expose the API port if they want to access the fastAPI web interface
EXPOSE 8000

# Start the main script using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

