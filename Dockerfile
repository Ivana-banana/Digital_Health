FROM python:3.11-slim

# UTF-8 вывод (отчёт на русском) и небуферизованные логи — контракт ИИ-судьи.
ENV PYTHONIOENCODING=UTF-8 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

CMD ["python", "-m", "src.app.main"]
