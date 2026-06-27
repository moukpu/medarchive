# --- build stage: собираем статику Vite ---
FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
# URL бэкенда пробрасывается на этапе сборки (Vite инлайнит import.meta.env при build).
# Render/Railway передают сервисные env как build-arg.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- runtime stage: отдаём dist через nginx ---
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# nginx.conf слушает 8080; на Render/Railway подставляем $PORT в конфиг при старте.
EXPOSE 8080
CMD ["sh", "-c", "sed -i \"s/listen 8080/listen ${PORT:-8080}/\" /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
