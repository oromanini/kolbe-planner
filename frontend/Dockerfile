# build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
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
