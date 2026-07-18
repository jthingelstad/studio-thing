import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LIBRARIAN_CONTRACT } from '../shared/librarian-contract.mts';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const defaultTarget = resolve(root, '../contracts/librarian-api.v1.json');
const targets = process.argv.slice(2).map((target) => resolve(process.cwd(), target));

for (const target of targets.length ? targets : [defaultTarget]) {
  const content = `${JSON.stringify(LIBRARIAN_CONTRACT, null, 2)}\n`;
  const checksumTarget = target.replace(/\.json$/, '.sha256');
  const checksum = createHash('sha256').update(content).digest('hex');
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
  writeFileSync(checksumTarget, `${checksum}  ${basename(target)}\n`);
  process.stdout.write(`${target}\n`);
  process.stdout.write(`${checksumTarget}\n`);
}
