import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LIBRARIAN_CONTRACT } from '../shared/librarian-contract.mts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const defaultTarget = resolve(root, '../contracts/librarian-api.v1.json');
const targets = process.argv.slice(2).map((target) => resolve(process.cwd(), target));

for (const target of targets.length ? targets : [defaultTarget]) {
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, `${JSON.stringify(LIBRARIAN_CONTRACT, null, 2)}\n`);
  process.stdout.write(`${target}\n`);
}
