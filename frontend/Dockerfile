FROM docker.io/library/node:22-alpine3.22 AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi && \
    npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM docker.io/library/nginx:1.28.0-alpine
COPY --chmod=644 deploy/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
