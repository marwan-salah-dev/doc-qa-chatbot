# syntax=docker/dockerfile:1
# Web image: the built React app served by nginx, which also proxies /api to the backend.

# --- build: static files into /app/dist --------------------------------------------------------
FROM node:24.22.2-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_BASE_URL stays unset, so the app calls /api on its own origin (proxied below)
RUN npm run build

# --- runtime: unprivileged nginx (runs as uid 101, listens on 8080) ----------------------------
FROM nginxinc/nginx-unprivileged:1.31.7-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
