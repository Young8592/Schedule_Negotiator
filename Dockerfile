FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SCHEDULE_ENABLE_DEMO=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY app.py core.py start_server.py ./
COPY .streamlit/config.toml .streamlit/config.toml
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8501')+'/_stcore/health',timeout=3)"
CMD ["python", "start_server.py"]
