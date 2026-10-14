/** `?a=1&b=x` from the non-empty params, or '' (for `resolve(`/route${query(...)}`)`). */
export function query(
	params: Record<string, string | number | bigint | null | undefined>
): '' | `?${string}` {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
	}
	const s = q.toString();
	return s ? `?${s}` : '';
}
