/**
 * Talking to the Trackmind engine (autotrack.py's local server).
 *
 * The app window opens /?token=…; that per-launch token unlocks the full
 * state, settings and app-only commands. It's kept in sessionStorage so a
 * reload without the query string still works.
 */
const params = new URLSearchParams(location.search);
export const TOKEN = params.get("token") || sessionStorage.getItem("tm-token") || "";
if (TOKEN) sessionStorage.setItem("tm-token", TOKEN);

export class CommandError extends Error {
	constructor(message, status, state) {
		super(message);
		this.status = status;
		this.state = state;
	}
}

/** POST /api/<cmd>. Resolves with the reply; rejects with CommandError. */
export async function call(cmd, body = {}) {
	let res;
	try {
		res = await fetch(`/api/${cmd}`, {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Trackmind-Token": TOKEN },
			body: JSON.stringify(body),
		});
	} catch {
		throw new CommandError("Trackmind isn't responding", 0);
	}
	const json = await res.json().catch(() => ({ ok: false, error: `HTTP ${res.status}` }));
	// The server moved (Control API port changed) — follow it.
	if (json.reload) setTimeout(() => location.replace(json.reload), 250);
	if (!json.ok) throw new CommandError(json.error || "Something went wrong", res.status, json.state);
	return json;
}

/**
 * Live state via Server-Sent Events. `onState` gets every snapshot;
 * `onLink(bool)` reports whether the engine is reachable.
 */
export function subscribe(onState, onLink) {
	let es;
	let retry;
	const open = () => {
		es = new EventSource(`/api/events?token=${encodeURIComponent(TOKEN)}`);
		es.onopen = () => onLink(true);
		es.onmessage = (e) => {
			try {
				onState(JSON.parse(e.data));
			} catch {
				/* ignore a torn frame */
			}
		};
		es.onerror = () => {
			onLink(false);
			es.close();
			clearTimeout(retry);
			retry = setTimeout(open, 1500);
		};
	};
	open();
}

export const previewUrl = () => `/api/preview.mjpg?token=${encodeURIComponent(TOKEN)}&t=${Date.now()}`;
