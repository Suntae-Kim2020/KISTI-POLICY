FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py auth.py admin.py audit.py compute.py ./
COPY templates/ ./templates/
COPY data_cache.json ./

ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
