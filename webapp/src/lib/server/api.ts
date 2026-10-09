import { API_URL } from '$app/env/private';
import { createApi } from './client.js';

export type { ApiResult } from './client.js';

/** The oj-rest repository, bound to the configured API_URL. */
export const api = createApi(API_URL.replace(/\/+$/, ''));
