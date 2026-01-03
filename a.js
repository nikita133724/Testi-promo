const fs = require('fs');

const text = fs.readFileSync('Ксгоран.js','utf8');

// 1. Карта переменных → реальный путь
const pathMap = {};
const pathRegex = /(const|let|var)?\s*([A-Za-z0-9_$]{1,6})\s*=\s*"\/[^"\n]+"/g;
let m;

while ((m = pathRegex.exec(text))) {
  const name = m[2];
  const value = m[0].split('=').pop().trim().replace(/"/g,'');
  pathMap[name] = value;
}

// 2. Поиск HTTP вызовов
const callRegex = /\.(get|post|put|delete)\(([^)]+)\)/g;
const results = [];

while ((m = callRegex.exec(text))) {
  const method = m[1].toUpperCase();
  const args = m[2].split(',').map(s => s.trim());

  let rawEndpoint = args[0];
  let payload = args[1] || '';

  // Подстановка реального пути
  if (pathMap[rawEndpoint]) {
    rawEndpoint = pathMap[rawEndpoint];
  }

  // Фильтрация мусора
  if (!rawEndpoint.startsWith('/')) continue;

  results.push({ method, endpoint: rawEndpoint, payload });
}

// 3. Удаляем дубликаты
const unique = [];
const seen = new Set();

for (const r of results) {
  const key = `${r.method}|${r.endpoint}`;
  if (!seen.has(key)) {
    seen.add(key);
    unique.push(r);
  }
}

// 4. Сохраняем
fs.writeFileSync('api_clean.json', JSON.stringify(unique, null, 2));
console.log('Готово → api_clean.json');