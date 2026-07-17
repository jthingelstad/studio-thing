import { execFileSync } from 'node:child_process';
import { copyFileSync, cpSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = resolve(root, 'dist');

rmSync(dist, { recursive: true, force: true });
execFileSync(process.execPath, [resolve(root, 'node_modules/typescript/bin/tsc'), '-p', resolve(root, 'tsconfig.build.json')], {
  cwd: root,
  stdio: 'inherit'
});

cpSync(resolve(root, 'prompts'), resolve(dist, 'prompts'), { recursive: true });
mkdirSync(resolve(dist, 'shared'), { recursive: true });
copyFileSync(resolve(root, 'shared/faq.json'), resolve(dist, 'shared/faq.json'));
