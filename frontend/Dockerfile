# Dockerfile — Frontend React/Vite
#
# Compilación multi-stage:
#   Stage 1 (builder): instala dependencias y compila la SPA
#   Stage 2 (runtime): sirve los archivos estáticos con nginx
#
# Este enfoque produce una imagen final ligera sin node_modules.

# ── Stage 1: Build ─────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar manifests primero (cache de capas de Docker)
COPY package*.json ./
RUN npm install

# Copiar código y compilar
COPY . .
# La variable de entorno se pasa en build time desde docker-compose
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Stage 2: Serve ─────────────────────────────────────────────────
FROM nginx:alpine AS runtime

# Configuración de nginx para SPA (redirige todo a index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar archivos compilados del stage anterior
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
