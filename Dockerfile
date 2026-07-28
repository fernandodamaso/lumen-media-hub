FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build:live

FROM nginx:1.28-alpine
COPY --from=builder /app/dist/dashboard/browser /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER=^ACTIONS_TOKEN$
EXPOSE 80
