#!/usr/bin/env node

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const dir = dirname(fileURLToPath(import.meta.url));
const proc = spawn('npm', ['run', 'dev'], {
  cwd: dir,
  stdio: 'inherit'
});

process.on('SIGINT', () => proc.kill());



