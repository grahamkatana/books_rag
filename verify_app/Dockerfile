# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# Unprivileged nginx (uid 101, listens on 8080) -- unlike the other two
# frontends, this one renders HTML derived from uploaded documents, so it
# runs non-root with a read-only root filesystem (see the k8s manifest).
FROM nginxinc/nginx-unprivileged:stable-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
