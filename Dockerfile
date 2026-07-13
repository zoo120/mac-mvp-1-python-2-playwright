FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    XIANYU_DB_PATH=/data/xianyu_monitor.db \
    XIANYU_SAVED_PRODUCTS_DIR=/data/saved_products \
    XIANYU_PROFILE_DIR=/data/playwright-profile \
    XIANYU_LOG_DIR=/data/logs \
    XIANYU_HEADLESS=1 \
    XIANYU_NO_SANDBOX=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

RUN mkdir -p /data

EXPOSE 8501

CMD ["sh", "-c", "streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --browser.gatherUsageStats=false"]
