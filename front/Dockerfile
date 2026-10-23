# Build the web client, then serve it with nginx, which also proxies /api to the backend.
FROM node:22-alpine AS build
WORKDIR /src/front
COPY front/package.json ./
RUN npm install --no-audit --no-fund
COPY contracts /src/contracts
COPY front/ ./
RUN npm run typecheck && npm run build

FROM nginx:1.27-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/front/dist /usr/share/nginx/html
EXPOSE 8080
