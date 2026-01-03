const fs = require('fs');

const text = fs.readFileSync('Ксгоран.js','utf8');

// 1. Собираем все переменные с путями
const pathMap = {};
const pathRegex = /([A-Za-z0-9_$]{1,6})\s*=\s*"\/[^"\n]+"/g;
let m;

while ((m = pathRegex.exec(text))) {
  const [full] = m;
  const [name, value] = full.split('=');
  pathMap[name.trim()] = value.trim().replace(/"/g,'');
}

// 2. Ищем HTTP вызовы
const callRegex = /(\w+)\.(get|post|put|delete)\(([^)]+)\)/g;

const results = [];

while ((m = callRegex.exec(text))) {
  const [, client, method, args] = m;

  const parts = args.split(',').map(s => s.trim());
  const endpointVar = parts[0];
  const payload = parts[1] || '';

  const endpoint = pathMap[endpointVar] || endpointVar;

  results.push({
    method: method.toUpperCase(),
    endpoint,
    payload
  });
}

// 3. Сохраняем в файл
fs.writeFileSync('api_map.json', JSON.stringify(results, null, 2));

console.log('Готово. Результат сохранён в api_map.json');