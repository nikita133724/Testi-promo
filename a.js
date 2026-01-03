// extract_endpoints.js
const fs = require('fs');
const path = require('path');

// Имя файла с минифицированным бандлом
const filename = path.join(__dirname, 'Ксгоран.js');

// Проверяем, что файл существует
if (!fs.existsSync(filename)) {
  console.error(`Файл "${filename}" не найден!`);
  process.exit(1);
}

// Читаем содержимое файла
const text = fs.readFileSync(filename, 'utf8');

// Регулярка для поиска переменных вида: Jk="/profile"
const regex = /([A-Za-z0-9_$]{1,6})\s*=\s*"((\/|https?:\/\/)[^"\n]+)"/g;

let match;
const endpoints = {};

// Ищем все совпадения
while ((match = regex.exec(text))) {
  endpoints[match[1]] = match[2];
}

// Выводим красиво в консоль
console.log(
  Object.entries(endpoints)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n')
);