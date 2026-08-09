# build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-factor 2 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set fetch-timeout 300000 \
    && npm ci --no-audit --no-fund
COPY . .

# build-time env for Vite. VITE_BACKEND_URL is the canonical name;
# REACT_APP_BACKEND_URL is still read as a fallback (see src/lib/env.js).
ARG VITE_BACKEND_URL
ARG REACT_APP_BACKEND_URL
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN npm run build

# run stage (static)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html

# Cloud Run listens on $PORT, so nginx must listen there
COPY nginx.conf /etc/nginx/conf.d/default.conf
