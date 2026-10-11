import { api } from '#lib/server/api.js';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ fetch }) => ({
	// Streamed: pages render without waiting for the status check.
	judgeStatus: api.status(fetch)
});
