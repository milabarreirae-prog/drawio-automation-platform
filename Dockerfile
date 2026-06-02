# syntax=docker/dockerfile:1
# Imagen del normalizador C4: Python + Node.js (elkjs) sirviendo la API FastAPI.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Node.js para el layout ELK real (elkjs). Sin Node, c4norm usa el fallback Python.
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

WORKDIR /app

# Código + metadata necesarios para instalar el paquete.
COPY pyproject.toml README.md ./
COPY api ./api
COPY c4norm ./c4norm

# Instalación editable: así c4norm/layout/node_modules (instalado abajo) es el que
# resuelve el motor en tiempo de ejecución.
RUN python -m pip install --upgrade pip && python -m pip install -e .

# Puente ELK (elkjs) en c4norm/layout.
RUN npm install --prefix c4norm/layout --no-audit --no-fund

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
