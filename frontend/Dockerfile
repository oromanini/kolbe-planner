# build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-factor 2 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set fetch-timeout 300000 \
    && npm install --no-audit --no-fund
COPY . .

# build-time env for React
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN npm run build

# run stage (static)
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html

# Cloud Run listens on $PORT, so nginx must listen there
COPY nginx.conf /etc/nginx/conf.d/default.conf
