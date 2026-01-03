const fs = require('fs');

const code = fs.readFileSync('Ксгоран.js','utf8');

const sections = {
  constants: [],
  api: [],
  utils: [],
  others: []
};

const lines = code.split('\n');

for (const line of lines) {
  if (/=\s*"\/[^"]+"/.test(line)) {
    sections.constants.push(line);
  } 
  else if (/\.(get|post|put|delete)\(/.test(line)) {
    sections.api.push(line);
  } 
  else if (/function|\=\s*\(/.test(line)) {
    sections.utils.push(line);
  } 
  else {
    sections.others.push(line);
  }
}

let output = `
/* ===================== CONSTANTS ===================== */
${sections.constants.join('\n')}

/* ===================== API CALLS ===================== */
${sections.api.join('\n')}

/* ===================== FUNCTIONS ===================== */
${sections.utils.join('\n')}

/* ===================== OTHER ===================== */
${sections.others.join('\n')}
`;

fs.writeFileSync('KsGoran.normalized.js', output.trim());
console.log('Готово → KsGoran.normalized.js');