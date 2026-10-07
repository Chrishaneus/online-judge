import assert from 'node:assert/strict';
import { test } from 'node:test';

import { timeAgo } from '../public/js/dom.js';

test('timeAgo buckets', () => {
  const now = Date.parse('2026-01-01T12:00:00Z');
  assert.equal(timeAgo('2026-01-01T11:59:30Z', now), '30s ago');
  assert.equal(timeAgo('2026-01-01T11:55:00Z', now), '5m ago');
  assert.equal(timeAgo('2026-01-01T09:00:00Z', now), '3h ago');
  assert.equal(timeAgo('2026-01-01T12:00:05Z', now), '0s ago'); // clock skew
});
