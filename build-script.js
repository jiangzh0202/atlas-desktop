const fs = require('fs');
const path = require('path');

// Ensure dist exists
const dist = path.join(__dirname, 'dist');
fs.mkdirSync(dist, { recursive: true });

// Copy desktop.html as index.html in dist
const src = path.join(__dirname, 'public', 'desktop.html');
const dst = path.join(dist, 'index.html');
fs.copyFileSync(src, dst);

console.log('✅ Build: desktop.html → dist/index.html');
console.log(`   Size: ${(fs.statSync(dst).size / 1024).toFixed(1)} KB`);
