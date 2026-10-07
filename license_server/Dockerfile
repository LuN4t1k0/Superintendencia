FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py README.md ./

EXPOSE 8080

CMD ["sh", "-c", "python server.py serve --host 0.0.0.0 --port \"$PORT\""]
