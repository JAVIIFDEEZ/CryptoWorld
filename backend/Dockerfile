# Dockerfile — Backend Django
#
# #
# Uso:
#   docker build -t cryptoworld-backend .
#   docker run -p 8000:8000 cryptoworld-backend

FROM python:3.11-slim

# Variables de entorno para Python en Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Directorio de trabajo
WORKDIR /app

# Copiar e instalar dependencias primero (cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt

# Copiar el código fuente
COPY . .

# Puerto expuesto
EXPOSE 8000

# Comando de arranque
# --reload solo para desarrollo; en producción usar gunicorn
CMD ["python", "src/manage.py", "runserver", "0.0.0.0:8000"]
