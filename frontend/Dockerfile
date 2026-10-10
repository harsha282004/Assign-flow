FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Public, build-time, browser-facing API URL (embedded in the bundle; contains no secrets).
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build && chown -R node:node /app

USER node
EXPOSE 5173

CMD ["npm", "run", "preview"]
