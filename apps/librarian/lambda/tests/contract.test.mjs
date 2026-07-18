import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const contractModule = await import('../dist/shared/librarian-contract.mjs');
const http = await import('../dist/shared/http.mjs');
const artifactUrl = new URL('../../contracts/librarian-api.v1.json', import.meta.url);
const artifactContent = await readFile(artifactUrl, 'utf8');
const artifact = JSON.parse(artifactContent);
const artifactChecksum = (await readFile(new URL('../../contracts/librarian-api.v1.sha256', import.meta.url), 'utf8'))
  .trim()
  .split(/\s+/)[0];

test('generated Librarian contract artifact matches the backend source', () => {
  assert.deepEqual(artifact, contractModule.LIBRARIAN_CONTRACT);
  assert.equal(artifact.version, contractModule.LIBRARIAN_CONTRACT_VERSION);
  assert.equal(createHash('sha256').update(artifactContent).digest('hex'), artifactChecksum);
});

test('contract negotiation remains additive for existing clients', () => {
  assert.equal(contractModule.supportsRequestedContract({}), true);
  assert.equal(contractModule.supportsRequestedContract({ 'X-Librarian-Contract-Version': artifact.version }), true);
  assert.equal(contractModule.supportsRequestedContract({ 'x-librarian-contract-version': '1.9.0' }), true);
  assert.equal(contractModule.supportsRequestedContract({ 'x-librarian-contract-version': '2.0.0' }), false);
  assert.equal(contractModule.supportsRequestedContract({ 'x-librarian-contract-version': 'not-semver' }), false);
});

test('endpoint actions declare response-specific successful contracts', () => {
  assert.deepEqual(artifact.endpoints['/conversations'].actions.list.required, ['conversations']);
  assert.deepEqual(artifact.endpoints['/dispatch'].actions.list.required, ['dispatches']);
});

test('JSON responses advertise the authoritative contract version', () => {
  const response = http.jsonResponse(200, { ok: true });
  assert.equal(response.headers['x-librarian-contract-version'], artifact.version);
  assert.match(response.headers['access-control-allow-headers'], /x-librarian-contract-version/);
  assert.match(response.headers['access-control-expose-headers'], /x-librarian-contract-version/);
});
