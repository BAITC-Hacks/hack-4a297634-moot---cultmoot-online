FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_ENV=production APP_MODE=assistant
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
COPY frontend/public/pcm-worklet.js ./frontend/public/pcm-worklet.js
RUN mkdir runtime && chown appuser:appuser runtime
USER appuser
EXPOSE 8010
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8010","--no-access-log","--no-server-header","--limit-concurrency","64","--ws-max-size","24000","--ws-max-queue","8"]
