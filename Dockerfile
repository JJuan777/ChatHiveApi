# Usa una imagen base de Python
FROM python:3.12-slim

# Opcionales, pero recomendados
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema que puedas necesitar (ej: psycopg2, Pillow, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código de la aplicación
COPY . .

# (Opcional) Si usas variables de entorno para settings, ya las pondrás en Railway
# ENV DJANGO_SETTINGS_MODULE=ChatHiveProject.settings

# Recolecta archivos estáticos en build-time
RUN python manage.py collectstatic --noinput

# Railway usa la variable de entorno PORT
# EXPOSE es solo informativo, pero ponemos 8000 por convención
EXPOSE 8005

# Comando de arranque:
#  - Corre migraciones
#  - Levanta Daphne usando el PORT que Railway define
CMD ["sh", "-c", "python manage.py migrate && daphne -b 0.0.0.0 -p ${PORT:-8005} ChatHiveProject.asgi:application"]
