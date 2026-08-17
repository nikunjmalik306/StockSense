FROM node:20-alpine

WORKDIR /app

# Copy package files first so this layer is cached unless dependencies change
COPY package.json package-lock.json* ./

RUN npm install

# Copy source (bind mount in dev overrides this)
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
