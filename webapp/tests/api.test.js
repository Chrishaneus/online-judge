import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ApiError, api, formatDetail, toQuery } from '../public/js/api.js';

function fakeFetch(status, body, headers = {}) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: 'X',
      headers: { get: (k) => headers[k] ?? null },
      json: async () => {
        if (body === undefined) throw new Error('no body');
        return body;
      },
    };
  };
  return { impl, calls };
}

test('toQuery drops empty values', () => {
  assert.equal(toQuery({ a: 1, b: '', c: null, d: 'x y' }), '?a=1&d=x+y');
  assert.equal(toQuery({}), '');
});

test('formatDetail handles FastAPI validation errors', () => {
  assert.equal(
    formatDetail([{ loc: ['body', 'username'], msg: 'bad' }, { loc: ['body'], msg: 'worse' }]),
    'username: bad; worse',
  );
  assert.equal(formatDetail('plain'), 'plain');
  assert.equal(formatDetail(undefined), '');
});

test('request sends JSON and parses the response', async () => {
  const f = fakeFetch(200, { id: 7 });
  const out = await api.request('POST', '/submissions', { body: { a: 1 }, fetchImpl: f.impl });
  assert.deepEqual(out, { id: 7 });
  assert.equal(f.calls[0].url, '/api/v1/submissions');
  assert.equal(f.calls[0].init.body, '{"a":1}');
  assert.equal(f.calls[0].init.headers['Content-Type'], 'application/json');
});

test('request raises ApiError with readable messages', async () => {
  await assert.rejects(
    api.request('GET', '/x', { fetchImpl: fakeFetch(404, { detail: 'not found' }).impl }),
    (e) => e instanceof ApiError && e.status === 404 && e.message === 'not found',
  );
  await assert.rejects(
    api.request('POST', '/run', { fetchImpl: fakeFetch(429, { detail: 'slow down' }, { 'Retry-After': '3' }).impl }),
    (e) => e.status === 429 && e.message.includes('3s'),
  );
  await assert.rejects(
    api.request('GET', '/x', { fetchImpl: async () => { throw new TypeError('offline'); } }),
    (e) => e.status === 0,
  );
});

test('204 returns null', async () => {
  assert.equal(await api.request('DELETE', '/x', { fetchImpl: fakeFetch(204).impl }), null);
});
