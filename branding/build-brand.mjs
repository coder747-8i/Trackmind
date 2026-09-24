/**
 * Trackmind brand builder — every logo, icon and installer image comes from
 * here, so they can't drift apart. Run `npm run build` in this folder.
 *
 * The mark: a tracking frame (four rounded corner brackets) holding the
 * subject — a tally-green dot — with two fading echoes trailing it to show
 * motion. In the wordmark, the same green dot is the dot of the "i".
 *
 * Outputs (paths relative to the repo root):
 *   logos/trackmind_icon.svg / .ico   app icon (Windows exe, installer, shortcuts)
 *   logos/trackmind_logo.svg          README banner
 *   logos/trackmind_installer.bmp     NSIS welcome/finish page art (164×314)
 *   ui/img/mark.svg, icon.svg, wordmark.svg, favicon.png
 *   streamdeck/…/imgs/plugin/*     Stream Deck marketplace & category icons
 */
import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import zlib from "node:zlib";

import { Resvg } from "@resvg/resvg-js";
import opentype from "opentype.js";

import { buildGlassMaps } from "../ui/js/liquid-glass-core.js";

const here = path.dirname(url.fileURLToPath(import.meta.url));
const root = path.dirname(here);
const out = (rel) => path.join(root, rel);

const GREEN = "#22d66f";
const GREEN_HI = "#9dffc8";
const BLUE = "#3d9bff";
const RED = "#ff3b45";

// ── Small binary helpers ─────────────────────────────────────

function crc32(buf) {
	let c = ~0;
	for (const b of buf) {
		c ^= b;
		for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
	}
	return ~c >>> 0;
}

/** RGBA → PNG (no dependencies). */
export function encodePng(rgba, w, h) {
	const raw = Buffer.alloc((w * 4 + 1) * h);
	for (let y = 0; y < h; y++) {
		raw[y * (w * 4 + 1)] = 0;
		Buffer.from(rgba.buffer, rgba.byteOffset + y * w * 4, w * 4).copy(raw, y * (w * 4 + 1) + 1);
	}
	const chunk = (type, data) => {
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
	return Buffer.concat([
		Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
		chunk("IHDR", ihdr),
		chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
		chunk("IEND", Buffer.alloc(0)),
	]);
}

const dataPng = (rgba, w, h) => `data:image/png;base64,${encodePng(rgba, w, h).toString("base64")}`;

const fonts = [path.join(here, "fonts", "InterDisplay-SemiBold.ttf"), path.join(here, "fonts", "InterDisplay-Bold.ttf")];

function raster(svg, width) {
	return new Resvg(svg, {
		fitTo: { mode: "width", value: width },
		font: { loadSystemFonts: false, fontFiles: fonts, defaultFontFamily: "Inter Display" },
	}).render();
}

function write(rel, data) {
	fs.mkdirSync(path.dirname(out(rel)), { recursive: true });
	fs.writeFileSync(out(rel), data);
	console.log("  ✓", rel);
}

// ── The mark (48-unit grid) ──────────────────────────────────

const FRAME = "M6 17v-5a6 6 0 0 1 6-6h5M31 6h5a6 6 0 0 1 6 6v5M42 31v5a6 6 0 0 1-6 6h-5M17 42h-5a6 6 0 0 1-6-6v-5";

/**
 * @param {object} o
 * @param {string} o.frame    Bracket colour
 * @param {string} o.subject  Dot colour
 * @param {number} [o.stroke] Bracket weight
 * @param {boolean} [o.glow]  Soft halo behind the subject (needs filter support)
 * @param {string} [o.id]     Unique prefix for defs
 */
function mark({ frame, subject, stroke = 4.2, glow = false, id = "m" }) {
	return `
<path d="${FRAME}" fill="none" stroke="${frame}" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round"/>
${glow ? `<circle cx="27" cy="24" r="10" fill="${subject}" opacity="0.55" filter="url(#${id}-halo)"/>` : ""}
<circle cx="11.6" cy="24" r="2.1" fill="${subject}" opacity="0.28"/>
<circle cx="17.6" cy="24" r="3.4" fill="${subject}" opacity="0.52"/>
<circle cx="27" cy="24" r="6.4" fill="${subject}"/>
<circle cx="25.2" cy="21.9" r="2" fill="#ffffff" opacity="0.55"/>`;
}

const markDefs = (id) =>
	`<filter id="${id}-halo" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3.2"/></filter>`;

// ── App icon (1024) ──────────────────────────────────────────

/** Superellipse ("squircle") path — the shape of modern app icons. */
function squircle(x, y, size, n = 5) {
	const a = size / 2;
	const cx = x + a;
	const cy = y + a;
	const pts = [];
	for (let i = 0; i < 128; i++) {
		const t = (i / 128) * Math.PI * 2;
		const c = Math.cos(t);
		const s = Math.sin(t);
		pts.push([cx + a * Math.sign(c) * Math.abs(c) ** (2 / n), cy + a * Math.sign(s) * Math.abs(s) ** (2 / n)]);
	}
	return `M${pts.map((p) => p.map((v) => v.toFixed(2)).join(" ")).join("L")}Z`;
}

/**
 * The full app icon: tally-coloured light under a pane of liquid glass that
 * genuinely refracts it (displacement map from liquid-glass-core), with the
 * mark floating on the glass.
 */
function appIcon({ detail = true } = {}) {
	const S = 1024;
	const pane = { x: 176, y: 176, w: 672, h: 672, r: 196 };
	const maps = buildGlassMaps({ width: pane.w, height: pane.h, radius: pane.r, bezel: 120, light: -45 });

	const lights = `
<rect width="${S}" height="${S}" fill="#06080b"/>
<circle cx="300" cy="760" r="330" fill="${GREEN}" opacity="0.95"/>
<circle cx="800" cy="230" r="260" fill="${BLUE}" opacity="0.75"/>
<circle cx="860" cy="880" r="170" fill="${RED}" opacity="0.55"/>
<circle cx="520" cy="470" r="120" fill="#ffffff" opacity="0.10"/>`;

	return `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">
<defs>
<clipPath id="shape"><path d="${squircle(0, 0, S)}"/></clipPath>
<clipPath id="pane"><rect x="${pane.x}" y="${pane.y}" width="${pane.w}" height="${pane.h}" rx="${pane.r}"/></clipPath>
<filter id="stage" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="120"/></filter>
<filter id="refract" x="${pane.x}" y="${pane.y}" width="${pane.w}" height="${pane.h}" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse">
<feGaussianBlur in="SourceGraphic" stdDeviation="10" result="frost"/>
<feImage href="${dataPng(maps.displacement, pane.w, pane.h)}" x="${pane.x}" y="${pane.y}" width="${pane.w}" height="${pane.h}" preserveAspectRatio="none" result="map"/>
<feDisplacementMap in="frost" in2="map" scale="150" xChannelSelector="R" yChannelSelector="G" result="bent"/>
<feColorMatrix in="bent" type="saturate" values="1.35"/>
</filter>
<linearGradient id="tint" x1="0" y1="0" x2="0.4" y2="1">
<stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>
<stop offset="0.5" stop-color="#ffffff" stop-opacity="0.06"/>
<stop offset="1" stop-color="#ffffff" stop-opacity="0.12"/>
</linearGradient>
<linearGradient id="bracket" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dfe7f1"/>
</linearGradient>
<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="28"/></filter>
${markDefs("icon")}
</defs>
<g clip-path="url(#shape)">
<!-- Opaque base: the stage blur pulls transparency in from outside the
     canvas, which left a half-see-through rim (a white fringe on light
     backgrounds). Blurring over a solid base keeps the edge fully opaque. -->
<rect width="${S}" height="${S}" fill="#06080b"/>
<g filter="url(#stage)">${lights}</g>
<rect x="${pane.x + 10}" y="${pane.y + 46}" width="${pane.w - 20}" height="${pane.h - 20}" rx="${pane.r}" fill="#000000" opacity="0.45" filter="url(#shadow)"/>
<g clip-path="url(#pane)">
<g filter="url(#refract)"><g filter="url(#stage)">${lights}</g></g>
<rect x="${pane.x}" y="${pane.y}" width="${pane.w}" height="${pane.h}" rx="${pane.r}" fill="url(#tint)"/>
<image href="${dataPng(maps.specular, pane.w, pane.h)}" x="${pane.x}" y="${pane.y}" width="${pane.w}" height="${pane.h}" preserveAspectRatio="none"/>
</g>
<g transform="translate(${pane.x + 96} ${pane.y + 96}) scale(${(pane.w - 192) / 48})">
${mark({ frame: "url(#bracket)", subject: GREEN, stroke: detail ? 3.6 : 4.4, glow: true, id: "icon" })}
</g>
</g>
</svg>`;
}

/** Tiny sizes (≤ 32 px): skip the glass, keep a bold mark on the lit squircle. */
function smallIcon() {
	const S = 256;
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">
<defs>
<clipPath id="shape"><path d="${squircle(0, 0, S)}"/></clipPath>
<radialGradient id="bg" cx="30%" cy="80%" r="95%">
<stop offset="0" stop-color="#0f5a33"/><stop offset="0.55" stop-color="#0b1f18"/><stop offset="1" stop-color="#06080b"/>
</radialGradient>
</defs>
<g clip-path="url(#shape)">
<rect width="${S}" height="${S}" fill="url(#bg)"/>
<g transform="translate(20 20) scale(${216 / 48})">${mark({ frame: "#ffffff", subject: GREEN, stroke: 5.2 })}</g>
</g>
</svg>`;
}

// ── Wordmark (outlined text, no font needed to display) ──────

const display = opentype.loadSync(path.join(here, "fonts", "InterDisplay-SemiBold.ttf"));

/** Outline `text` at `size`, returning path data, advance width and glyph positions. */
function outline(font, text, size, tracking = 0) {
	const scale = size / font.unitsPerEm;
	let x = 0;
	let d = "";
	const positions = [];
	const glyphs = font.stringToGlyphs(text);
	glyphs.forEach((g, i) => {
		positions.push({ x, glyph: g });
		d += g.getPath(x, 0, size).toPathData(2);
		x += g.advanceWidth * scale + tracking * size;
		if (i < glyphs.length - 1) x += font.getKerningValue(g, glyphs[i + 1]) * scale;
	});
	return { d, width: x - tracking * size, positions };
}

/** Where the dot of a real "i" sits, so the green subject can take its place. */
function iDot(font, size) {
	const cmds = font.charToGlyph("i").getPath(0, 0, size).commands;
	const contours = [];
	let cur = [];
	for (const c of cmds) {
		if (c.type === "M" && cur.length) (contours.push(cur), (cur = []));
		if (c.x !== undefined) cur.push([c.x, c.y]);
	}
	if (cur.length) contours.push(cur);
	const top = contours.reduce((a, b) => (Math.min(...a.map((p) => p[1])) < Math.min(...b.map((p) => p[1])) ? a : b));
	const xs = top.map((p) => p[0]);
	const ys = top.map((p) => p[1]);
	return {
		cy: (Math.min(...ys) + Math.max(...ys)) / 2,
		r: (Math.max(...xs) - Math.min(...xs)) / 2,
	};
}

function wordmark(size, { color = "#f5f7fb", tracking = -0.018 } = {}) {
	const text = "trackmınd"; // dotless ı — the subject dot replaces it
	const w = outline(display, text, size, tracking);
	const idx = [...text].indexOf("ı");
	const dot = iDot(display, size);
	// Centre on the dotless ı's own stem (its sidebearings differ from "i").
	const stem = w.positions[idx].glyph.getBoundingBox();
	const scale = size / display.unitsPerEm;
	const cx = w.positions[idx].x + ((stem.x1 + stem.x2) / 2) * scale;
	const r = dot.r * 1.18;
	return {
		width: w.width,
		svg: `<path d="${w.d}" fill="${color}"/>
<circle cx="${cx.toFixed(2)}" cy="${dot.cy.toFixed(2)}" r="${(r * 2.4).toFixed(2)}" fill="${GREEN}" opacity="0.35" filter="url(#wm-glow)"/>
<circle cx="${cx.toFixed(2)}" cy="${dot.cy.toFixed(2)}" r="${r.toFixed(2)}" fill="${GREEN}"/>`,
		defs: `<filter id="wm-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="${(size * 0.035).toFixed(2)}"/></filter>`,
	};
}

// ── Compositions ─────────────────────────────────────────────

/** The icon as an embedded PNG — resvg mis-clips nested <svg> with filters. */
const iconPng = (px) => `data:image/png;base64,${raster(appIcon(), px).asPng().toString("base64")}`;

function banner() {
	const W = 1400;
	const H = 420;
	const wm = wordmark(150);
	const tag = outline(opentype.loadSync(fonts[0]), "Intelligent PTZ auto-tracking", 40, 0.01);
	const iconSize = 260;
	const gx = 110;
	const tx = gx + iconSize + 64;
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs>
<clipPath id="card"><rect width="${W}" height="${H}" rx="48"/></clipPath>
<filter id="bglow" x="-300" y="-300" width="${W + 600}" height="${H + 600}" filterUnits="userSpaceOnUse"><feGaussianBlur stdDeviation="90"/></filter>
${wm.defs}
</defs>
<g clip-path="url(#card)">
<rect width="${W}" height="${H}" fill="#07090c"/>
<g filter="url(#bglow)" opacity="0.55">
<circle cx="220" cy="360" r="220" fill="${GREEN}"/>
<circle cx="1180" cy="40" r="220" fill="${BLUE}"/>
<circle cx="1320" cy="420" r="140" fill="${RED}" opacity="0.7"/>
</g>
<rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="47" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="2"/>
<image href="${iconPng(iconSize * 2)}" x="${gx}" y="${(H - iconSize) / 2}" width="${iconSize}" height="${iconSize}"/>
<g transform="translate(${tx} 222)">${wm.svg}</g>
<g transform="translate(${tx + 6} 296)"><path d="${tag.d}" fill="#a3acbb"/></g>
</g>
</svg>`;
}

function wordmarkSvg() {
	const size = 96;
	const wm = wordmark(size);
	const h = Math.round(size * 1.25);
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(wm.width)}" height="${h}" viewBox="0 ${-size * 0.95} ${Math.ceil(wm.width)} ${h}">
<defs>${wm.defs}</defs>${wm.svg}
</svg>`;
}

function markSvg() {
	return `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><defs>${markDefs("mk")}</defs>${mark({ frame: "#ffffff", subject: GREEN, glow: true, id: "mk" })}</svg>`;
}

function installerArt() {
	// NSIS MUI welcome bitmap: 164 × 314
	const W = 164;
	const H = 314;
	const wm = wordmark(30);
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<defs><filter id="bg" x="-120" y="-120" width="${W + 240}" height="${H + 240}" filterUnits="userSpaceOnUse"><feGaussianBlur stdDeviation="40"/></filter>${wm.defs}</defs>
<rect width="${W}" height="${H}" fill="#07090c"/>
<g filter="url(#bg)" opacity="0.7">
<circle cx="30" cy="300" r="110" fill="${GREEN}"/>
<circle cx="160" cy="20" r="90" fill="${BLUE}"/>
<circle cx="170" cy="330" r="60" fill="${RED}" opacity="0.7"/>
</g>
<image href="${iconPng(220)}" x="27" y="72" width="110" height="110"/>
<g transform="translate(${(W - wm.width) / 2} 232)">${wm.svg}</g>
</svg>`;
}

// ── Writers for .ico and .bmp ────────────────────────────────

function ico(entries) {
	const header = Buffer.alloc(6);
	header.writeUInt16LE(0, 0);
	header.writeUInt16LE(1, 2);
	header.writeUInt16LE(entries.length, 4);
	const dir = [];
	const blobs = [];
	let offset = 6 + entries.length * 16;
	for (const { size, png } of entries) {
		const e = Buffer.alloc(16);
		e.writeUInt8(size >= 256 ? 0 : size, 0);
		e.writeUInt8(size >= 256 ? 0 : size, 1);
		e.writeUInt16LE(1, 4);
		e.writeUInt16LE(32, 6);
		e.writeUInt32LE(png.length, 8);
		e.writeUInt32LE(offset, 12);
		offset += png.length;
		dir.push(e);
		blobs.push(png);
	}
	return Buffer.concat([header, ...dir, ...blobs]);
}

function bmp24(img) {
	const { width: w, height: h } = img;
	const px = img.pixels; // RGBA
	const row = Math.ceil((w * 3) / 4) * 4;
	const buf = Buffer.alloc(54 + row * h);
	buf.write("BM", 0);
	buf.writeUInt32LE(buf.length, 2);
	buf.writeUInt32LE(54, 10);
	buf.writeUInt32LE(40, 14);
	buf.writeInt32LE(w, 18);
	buf.writeInt32LE(h, 22);
	buf.writeUInt16LE(1, 26);
	buf.writeUInt16LE(24, 28);
	buf.writeUInt32LE(row * h, 34);
	for (let y = 0; y < h; y++) {
		for (let x = 0; x < w; x++) {
			const s = ((h - 1 - y) * w + x) * 4;
			const d = 54 + y * row + x * 3;
			buf[d] = px[s + 2];
			buf[d + 1] = px[s + 1];
			buf[d + 2] = px[s];
		}
	}
	return buf;
}

// ── Build ────────────────────────────────────────────────────

console.log("Building Trackmind brand assets…");
const icon = appIcon();
const small = smallIcon();

write("logos/trackmind_icon.svg", icon);
write("ui/img/icon.svg", icon);
write("ui/img/mark.svg", markSvg());
write("ui/img/wordmark.svg", wordmarkSvg());
write("logos/trackmind_logo.svg", banner());
write("ui/img/favicon.png", raster(small, 64).asPng());

write(
	"logos/trackmind_icon.ico",
	ico([16, 20, 24, 32, 40, 48, 64, 128, 256].map((size) => ({ size, png: raster(size <= 32 ? small : icon, size).asPng() }))),
);

const art = raster(installerArt(), 164);
write("logos/trackmind_installer.bmp", bmp24({ width: art.width, height: art.height, pixels: art.pixels }));

// Stream Deck: marketplace icon (PNG required) + monochrome category icon
const sd = "streamdeck/com.coder747.trackmind.sdPlugin/imgs/plugin";
write(`${sd}/marketplace.png`, raster(icon, 256).asPng());
write(`${sd}/marketplace@2x.png`, raster(icon, 512).asPng());
write(
	`${sd}/category-icon.svg`,
	`<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 48 48">${mark({ frame: "#ffffff", subject: "#ffffff", stroke: 4.6 })}</svg>`,
);

// Preview sheet for review (not shipped)
if (process.argv.includes("--preview")) {
	const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="980">
<rect width="1500" height="980" fill="#1b1c1f"/>
<image href="data:image/png;base64,${raster(banner(), 1400).asPng().toString("base64")}" x="50" y="40" width="1400" height="420"/>
<image href="data:image/png;base64,${raster(icon, 360).asPng().toString("base64")}" x="50" y="500" width="360" height="360"/>
${[128, 64, 48, 32, 24, 16]
	.map((s, i) => `<image href="data:image/png;base64,${raster(s <= 32 ? small : icon, s).asPng().toString("base64")}" x="${450 + i * 140}" y="${680 - s / 2}" width="${s}" height="${s}"/>`)
	.join("")}
<image href="data:image/png;base64,${art.asPng().toString("base64")}" x="1300" y="520" width="164" height="314"/>
<rect x="450" y="520" width="800" height="90" rx="20" fill="#f4f5f7"/>
<g transform="translate(480 590)">${wordmark(64, { color: "#0b0d10" }).svg}</g>
<defs>${wordmark(64).defs}</defs>
</svg>`;
	fs.writeFileSync(process.argv[process.argv.indexOf("--preview") + 1], raster(sheet, 1500).asPng());
}
console.log("Done.");
