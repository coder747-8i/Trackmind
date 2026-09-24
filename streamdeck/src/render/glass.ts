import zlib from "node:zlib";

import { buildGlassMaps } from "../../../ui/js/liquid-glass-core.js";
import { ARROW_ANGLE, icons, type IconName } from "./icons";
import { FONT, Ink, Tone, type ToneName } from "./palette";

/**
 * Liquid-glass key renderer (rasterised by resvg — see raster.ts).
 * Produces {@link Layers}: a cacheable glass backdrop + a vector overlay.
 *
 * Each key is a small scene: a charcoal stage lit by the action's tally
 * colour, seen through a pane of glass. The pane genuinely refracts the
 * stage (displacement map from liquid-glass-core — the same optics the
 * desktop app uses), is lightly frosted, carries a specular rim, and floats
 * on a soft shadow. Content sits on the glass.
 */

export type KeySpec = {
	tone: ToneName;
	/** Lit: tally on, stage lit in the tone. */
	active: boolean;
	icon?: IconName;
	/** Direction for the arrow icon (up, down-left, …). */
	direction?: string;
	/** Big text in place of the icon, e.g. a preset number. */
	glyph?: string;
	label: string;
	sub?: string;
	/** Colour of the sub-label; defaults to white-ish when lit, dim otherwise. */
	subInk?: "tone" | "dim" | "warn";
	/** Trackmind unreachable — the key goes dark and says so. */
	offline?: boolean;
	/** Small secondary light in the top-right corner (e.g. subject acquired). */
	corner?: ToneName;
};

const esc = (s: string): string =>
	s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Shrink text until it fits `max` px — an approximation of Inter Display metrics. */
function fit(text: string, size: number, max: number, ratio = 0.58): number {
	const width = text.length * size * ratio;
	return width <= max ? size : Math.max(9, Math.floor((max / (text.length * ratio)) * 10) / 10);
}

// ── Glass maps (computed once per pane size) ─────────────────

function crc32(buf: Uint8Array): number {
	let c = ~0;
	for (const b of buf) {
		c ^= b;
		for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
	}
	return ~c >>> 0;
}

function pngDataUri(rgba: Uint8ClampedArray, w: number, h: number): string {
	const raw = Buffer.alloc((w * 4 + 1) * h);
	for (let y = 0; y < h; y++) Buffer.from(rgba.buffer, rgba.byteOffset + y * w * 4, w * 4).copy(raw, y * (w * 4 + 1) + 1);
	const chunk = (type: string, data: Buffer): Buffer => {
		const len = Buffer.alloc(4);
		len.writeUInt32BE(data.length);
		const td = Buffer.concat([Buffer.from(type), data]);
		const crc = Buffer.alloc(4);
		crc.writeUInt32BE(crc32(td));
		return Buffer.concat([len, td, crc]);
	};
	const ihdr = Buffer.alloc(13);
	ihdr.writeUInt32BE(w, 0);
	ihdr.writeUInt32BE(h, 4);
	ihdr.set([8, 6, 0, 0, 0], 8);
	const png = Buffer.concat([
		Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
		chunk("IHDR", ihdr),
		chunk("IDAT", zlib.deflateSync(raw)),
		chunk("IEND", Buffer.alloc(0)),
	]);
	return `data:image/png;base64,${png.toString("base64")}`;
}

type Pane = { x: number; y: number; w: number; h: number; r: number; bezel: number };
const mapCache = new Map<string, { disp: string; spec: string }>();

function maps(p: Pane): { disp: string; spec: string } {
	const key = `${p.w}x${p.h}r${p.r}b${p.bezel}`;
	let m = mapCache.get(key);
	if (!m) {
		const g = buildGlassMaps({ width: p.w, height: p.h, radius: p.r, bezel: p.bezel });
		m = { disp: pngDataUri(g.displacement, p.w, p.h), spec: pngDataUri(g.specular, p.w, p.h) };
		mapCache.set(key, m);
	}
	return m;
}

// ── Shared composition ───────────────────────────────────────

type Light = { cx: number; cy: number; r: number; color: string; opacity: number };

/**
 * A pane of liquid glass over a lit stage. Stage lights are radial
 * gradients rather than blurred shapes — same look, a fraction of the
 * render time, which matters when a dial spins at 30 updates a second.
 */
function glassBackdrop(W: number, H: number, pane: Pane, lights: Light[], tint: string, tintOpacity: number): string {
	const m = maps(pane);
	const grads = lights
		.map(
			(l, i) =>
				`<radialGradient id="L${i}" cx="${l.cx}" cy="${l.cy}" r="${l.r * 1.7}" gradientUnits="userSpaceOnUse">` +
				`<stop offset="0" stop-color="${l.color}" stop-opacity="${l.opacity}"/>` +
				`<stop offset="0.45" stop-color="${l.color}" stop-opacity="${(l.opacity * 0.55).toFixed(3)}"/>` +
				`<stop offset="1" stop-color="${l.color}" stop-opacity="0"/></radialGradient>`,
		)
		.join("");
	const stage = `<rect width="${W}" height="${H}" fill="#07090c"/>` + lights.map((_, i) => `<rect width="${W}" height="${H}" fill="url(#L${i})"/>`).join("");
	const pad = 14;
	const { x, y, w, h, r } = pane;
	// Surround: dim everything outside the pane so the key reads as a glass
	// tile with its light bleeding out, not a coloured square.
	const hole = `M0 0H${W}V${H}H0Z M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`;
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs>
${grads}
<filter id="refract" x="${x - pad}" y="${y - pad}" width="${w + pad * 2}" height="${h + pad * 2}" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse">
<feGaussianBlur in="SourceGraphic" stdDeviation="1.6" result="frost"/>
<feImage href="${m.disp}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="none" result="map"/>
<feDisplacementMap in="frost" in2="map" scale="${Math.round(pane.bezel * 2.3)}" xChannelSelector="R" yChannelSelector="G" result="bent"/>
<feColorMatrix in="bent" type="saturate" values="1.5"/>
</filter>
<filter id="shadow" x="${x - 20}" y="${y - 12}" width="${w + 40}" height="${h + 40}" filterUnits="userSpaceOnUse"><feGaussianBlur stdDeviation="5"/></filter>
<clipPath id="pane"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}"/></clipPath>
<linearGradient id="sheen" x1="0" y1="0" x2="0.35" y2="1">
<stop offset="0" stop-color="#ffffff" stop-opacity="0.24"/>
<stop offset="0.45" stop-color="#ffffff" stop-opacity="0.05"/>
<stop offset="1" stop-color="#ffffff" stop-opacity="0.10"/>
</linearGradient>
<linearGradient id="legible" x1="0" y1="0" x2="0" y2="1">
<stop offset="0.45" stop-color="#000000" stop-opacity="0"/>
<stop offset="1" stop-color="#000000" stop-opacity="0.30"/>
</linearGradient>
</defs>
${stage}
<path d="${hole}" fill="#050608" fill-rule="evenodd" opacity="0.62"/>
<rect x="${x + 2}" y="${y + 7}" width="${w - 4}" height="${h - 4}" rx="${r}" fill="#000000" opacity="0.6" filter="url(#shadow)"/>
<g clip-path="url(#pane)">
${stage}
<g filter="url(#refract)">${stage}</g>
<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${tint}" opacity="${tintOpacity}"/>
<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#sheen)"/>
<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#legible)"/>
<image href="${m.spec}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="none"/>
</g>
<rect x="${x + 0.5}" y="${y + 0.5}" width="${w - 1}" height="${h - 1}" rx="${r - 0.5}" fill="none" stroke="#ffffff" stroke-opacity="0.10"/></svg>`;
}

/**
 * A key is two layers: the glass backdrop (expensive — refraction, lights —
 * but it only depends on tone and state, so it's rendered once and cached)
 * and a light vector overlay (icon, text) composited over it.
 */
export type Layers = { width: number; height: number; backdrop: string; overlay: (backdropUri: string) => string };

const overlaySvg = (W: number, H: number, body: string) => (backdropUri: string) =>
	`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs></defs>` +
	`<image href="${backdropUri}" x="0" y="0" width="${W}" height="${H}" preserveAspectRatio="none"/>${body}</svg>`;

/** Text with a crisp drop shadow so it reads on bright glass. */
function label(x: number, y: number, size: number, weight: number, fill: string, content: string, anchor = "middle"): string {
	const common = `x="${x}" text-anchor="${anchor}" font-family="${FONT}" font-size="${size}" font-weight="${weight}"`;
	return (
		`<text ${common} y="${y + 1.2}" fill="#000000" opacity="0.28">${esc(content)}</text>` +
		`<text ${common} y="${y}" fill="${fill}">${esc(content)}</text>`
	);
}

/** Soft round light without a blur filter. */
function glow(cx: number, cy: number, rx: number, ry: number, color: string, opacity: number, id: string): string {
	return (
		`<radialGradient id="${id}" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="${color}" stop-opacity="${opacity}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>` +
		`<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="url(#${id})"/>`
	);
}

// ── Keys (144 × 144) ─────────────────────────────────────────

const KEY_PANE: Pane = { x: 9, y: 9, w: 126, h: 126, r: 36, bezel: 22 };

export function keyLayers(spec: KeySpec): Layers {
	const offline = !!spec.offline;
	const tone = Tone[offline ? "neutral" : spec.tone];
	const lit = spec.active && !offline;

	const lights: Light[] = offline
		? [{ cx: 72, cy: 120, r: 60, color: "#2a2f38", opacity: 0.9 }]
		: lit
			? [
					{ cx: 72, cy: 118, r: 74, color: tone.base, opacity: 1 },
					{ cx: 30, cy: 30, r: 42, color: tone.hi, opacity: 0.55 },
					{ cx: 124, cy: 60, r: 34, color: tone.deep, opacity: 0.9 },
				]
			: [
					{ cx: 40, cy: 124, r: 64, color: "#2b3342", opacity: 1 },
					{ cx: 118, cy: 22, r: 42, color: tone.base, opacity: 0.32 },
					{ cx: 120, cy: 128, r: 30, color: tone.deep, opacity: 0.5 },
				];

	const ink = offline ? Ink.dim : "#ffffff";
	const accent = offline ? Ink.dim : lit ? "#ffffff" : tone.base;

	let centre = "";
	if (spec.glyph !== undefined) {
		const size = fit(spec.glyph, 54, 100, 0.6);
		centre = label(72, 82 - (54 - size) * 0.32, size, 700, offline ? Ink.dim : "#ffffff", spec.glyph);
	} else if (spec.icon) {
		const rot = spec.icon === "arrow" ? (ARROW_ANGLE[spec.direction ?? "up"] ?? 0) : 0;
		const name: IconName = offline && spec.icon !== "arrow" ? "offline" : spec.icon;
		const glyph = icons[name](ink, accent);
		centre =
			(lit ? `<g transform="translate(50 29.5) scale(1.84)${rot ? ` rotate(${rot} 12 12)` : ""}" opacity="0.22">${icons[name]("#000000", "#000000")}</g>` : "") +
			`<g transform="translate(50 28) scale(1.84)${rot ? ` rotate(${rot} 12 12)` : ""}">${glyph}</g>`;
	}

	const title = spec.label.toUpperCase();
	const sub = offline ? "OFFLINE" : (spec.sub ?? "").toUpperCase();
	const subFill = offline
		? Ink.offline
		: spec.subInk === "warn"
			? lit
				? "#fff2c9"
				: Tone.amber.base
			: spec.subInk === "tone"
				? lit
					? "#ffffff"
					: tone.hi
				: lit
					? "rgba(255,255,255,0.86)"
					: Ink.secondary;

	const corner = spec.corner && !offline ? Tone[spec.corner] : null;

	const body = `${lit ? glow(72, 21.5, 30, 10, "#ffffff", 0.55, "tg") : ""}
<rect x="54" y="18.5" width="36" height="6" rx="3" fill="#ffffff" opacity="${lit ? 0.95 : 0.16}"/>
${corner ? `${glow(114, 30, 12, 12, corner.base, 0.9, "cg")}<circle cx="114" cy="30" r="4.2" fill="${corner.base}" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.2"/>` : ""}
${centre}
${label(72, sub ? 108 : 114, fit(title, 16, 112), 700, offline ? Ink.dim : "#ffffff", title)}
${sub ? label(72, 124.5, fit(sub, 11.5, 108), 600, subFill, sub) : ""}`;
	return {
		width: 144,
		height: 144,
		backdrop: glassBackdrop(144, 144, KEY_PANE, lights, lit ? tone.base : "#0b0e13", lit ? 0.16 : 0.34),
		overlay: overlaySvg(144, 144, body),
	};
}

// ── Stream Deck + touch strip segment (200 × 100) ────────────

export type DialSpec = {
	tone: ToneName;
	active: boolean;
	offline?: boolean;
	status: string;
	name: string;
	value: string;
	min: number;
	max: number;
	current: number;
	/** Bar grows from the middle (signed values like offset). */
	centred?: boolean;
	/** Show the lock badge (subject locked). */
	locked?: boolean;
};

const DIAL_PANE: Pane = { x: 5, y: 5, w: 190, h: 90, r: 26, bezel: 18 };

export function dialLayers(spec: DialSpec): Layers {
	const offline = !!spec.offline;
	const tone = Tone[offline ? "neutral" : spec.tone];
	const lit = spec.active && !offline;
	const span = Math.max(1, spec.max - spec.min);
	const t = Math.min(1, Math.max(0, (spec.current - spec.min) / span));
	const x0 = 22;
	const w = 156;
	const thumb = x0 + w * t;
	const from = spec.centred ? x0 + w * ((0 - spec.min) / span) : x0;
	const fillX = Math.min(from, thumb);
	const fillW = Math.max(0.01, Math.abs(thumb - from));

	// The light follows the value, quantised so a handful of cached backdrops cover every position.
	const glowX = x0 + w * (Math.round(t * 8) / 8);
	const lights: Light[] = offline
		? [{ cx: 100, cy: 90, r: 60, color: "#2a2f38", opacity: 0.9 }]
		: [
				{ cx: glowX, cy: 92, r: 58, color: tone.base, opacity: lit ? 1 : 0.45 },
				{ cx: 180, cy: 10, r: 40, color: lit ? tone.hi : "#2b3342", opacity: lit ? 0.45 : 1 },
			];

	const status = offline ? "OFFLINE" : spec.status;
	const statusFill = offline ? Ink.offline : lit ? "#ffffff" : Ink.secondary;

	const body = `${lit ? glow(22, 22, 9, 9, "#ffffff", 0.6, "sg") : ""}
<circle cx="22" cy="22" r="4" fill="${offline ? Ink.offline : "#ffffff"}" opacity="${lit || offline ? 1 : 0.3}"/>
${label(32, 26, 11, 700, statusFill, status, "start")}
${spec.locked && !offline ? `<g transform="translate(166 11) scale(0.62)">${icons.lock("#ffffff", Tone.amber.hi)}</g>` : ""}
${label(22, 49, 10.5, 600, lit ? "rgba(255,255,255,0.82)" : Ink.secondary, spec.name.toUpperCase(), "start")}
${label(178, 53, 25, 700, offline ? Ink.dim : "#ffffff", spec.value, "end")}
<rect x="${x0}" y="67" width="${w}" height="7" rx="3.5" fill="#000000" opacity="0.4"/>
${spec.centred ? `<rect x="${from - 0.75}" y="64" width="1.5" height="13" rx="0.75" fill="#ffffff" opacity="0.4"/>` : ""}
<rect x="${fillX}" y="67" width="${fillW}" height="7" rx="3.5" fill="${offline ? Ink.dim : lit ? "#ffffff" : tone.base}"/>
<rect x="${thumb - 12.5}" y="61.5" width="25" height="19" rx="9.5" fill="#000000" opacity="0.3"/>
<rect x="${thumb - 12}" y="60.5" width="24" height="18" rx="9" fill="#f5f7fb"/>
<rect x="${thumb - 9}" y="61.5" width="18" height="5" rx="2.5" fill="#ffffff"/>
${label(22, 90, 8, 600, lit ? "rgba(255,255,255,0.6)" : Ink.dim, "PUSH · TRACKING", "start")}
${label(178, 90, 8, 600, lit ? "rgba(255,255,255,0.6)" : Ink.dim, "TAP · LOCK", "end")}`;
	return {
		width: 200,
		height: 100,
		backdrop: glassBackdrop(200, 100, DIAL_PANE, lights, lit ? tone.base : "#0b0e13", lit ? 0.14 : 0.34),
		overlay: overlaySvg(200, 100, body),
	};
}
