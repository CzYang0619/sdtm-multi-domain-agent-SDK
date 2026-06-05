#!/usr/bin/env node
/**
 * Patch vscode-jsonrpc to support ESM imports with /node path
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const pkgPath = path.join(__dirname, 'node_modules/vscode-jsonrpc/package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));

// Add exports field for ESM support
if (!pkg.exports) {
  pkg.exports = {
    '.': {
      'import': './lib/node/main.js',
      'require': './lib/node/main.js',
      'default': './lib/node/main.js'
    },
    './node': './lib/node/main.js',
    './node.js': './lib/node/main.js',
    './browser': './lib/browser/main.js',
    './browser.js': './lib/browser/main.js'
  };
  
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2));
  console.log('✅ Patched vscode-jsonrpc package.json with exports field');
}

// Also create a node.js wrapper file at the root for direct imports
const nodeWrapperPath = path.join(__dirname, 'node_modules/vscode-jsonrpc/node.js');
if (!fs.existsSync(nodeWrapperPath)) {
  fs.writeFileSync(nodeWrapperPath, `export * from './lib/node/main.js';\nexport { default } from './lib/node/main.js';\n`);
  console.log('✅ Created node.js wrapper file');
}
