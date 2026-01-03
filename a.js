const fs = require('fs');

const code = fs.readFileSync('Ксгоран.js','utf8');

// 1️⃣ Все реальные API пути
const pathRegex = /(const|let|var)?\s*([A-Za-z0-9_$]{1,6})\s*=\s*"\/[^"\n]+"/g;
const paths = [];
let m;

while ((m = pathRegex.exec(code))) {
  paths.push(m[0]);
}

// 2️⃣ Только настоящие сетевые вызовы
const httpRegex = /(?:axios|arg65|client)\.(get|post|put|delete)\([^;]+\);/g;
const calls = code.match(httpRegex) || [];

// 3️⃣ Остальной код
let cleaned = code;
for (const p of paths) cleaned = cleaned.replace(p, '');
for (const c of calls) cleaned = cleaned.replace(c, '');

const output = `
/* ===================== API PATHS ===================== */
${paths.join('\n')}

/* ===================== API CALLS ===================== */
${calls.join('\n')}

/* ===================== APPLICATION CODE ===================== */
${cleaned}
`;

fs.writeFileSync('KsGoran.normalized.js', output);
console.log('Готово → KsGoran.normalized.js');