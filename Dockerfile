# Usa una imagen base de Python
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

# Solo decorativo, para documentar que el contenedor escucha en el PORT de Railway
EXPOSE 8080

CMD ["sh", "-c", "python manage.py migrate && daphne -b 0.0.0.0 -p ${PORT:-8080} ChatHiveProject.asgi:application"]
