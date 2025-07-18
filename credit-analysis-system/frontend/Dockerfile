
FROM node:18-alpine

WORKDIR /app

# Копирование package.json
COPY package.json ./

# Установка зависимостей (заменили npm ci на npm install)
RUN npm install --omit=dev

# Копирование исходного кода
COPY . .

# Сборка приложения
RUN npm run build

# Использование nginx для раздачи статики
FROM nginx:alpine

# Копирование собранного приложения
COPY --from=0 /app/build /usr/share/nginx/html

# Копирование конфигурации nginx
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 3030

CMD ["nginx", "-g", "daemon off;"]
