/**
 * Liquid glass for the DOM.
 *
 * Any element with a `data-glass` attribute becomes a refracting pane: its
 * backdrop is run through an SVG filter built from liquid-glass-core's
 * displacement + specular maps (sized to the element, rebuilt on resize).
 *
 *   data-glass            enable (value is ignored)
 *   data-refract="40"     refraction strength in px (default 34)
 *   data-bezel="18"       how far in from the edge the lens reaches (default 16)
 *   data-frost="2"        backdrop blur in px (default 1.5)
 *   data-dispersion="0.1" chromatic split, fraction of refract (default 0.08)
 *
 * Chromium (WebView2, Stream Deck, Chrome) supports SVG filters in
 * backdrop-filter; anywhere else gets a plain frosted blur via CSS.
 */
import { buildGlassMaps } from "./liquid-glass-core.js";

const NS = "http://www.w3.org/2000/svg";
const cache = new Map(); // size key → filter id
let defs = null;
let seq = 0;

const supported = (() => {
	try {
		return CSS.supports("backdrop-filter", "url(#x)") && /Chrome|Chromium|Edg|QtWebEngine/.test(navigator.userAgent);
	} catch {
		return false;
	}
})();

function ensureDefs() {
	if (defs) return defs;
	const svg = document.createElementNS(NS, "svg");
	svg.setAttribute("aria-hidden", "true");
	svg.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;pointer-events:none";
	defs = document.createElementNS(NS, "defs");
	svg.appendChild(defs);
	document.body.appendChild(svg);
	return defs;
}

function toDataURL(rgba, w, h) {
	const c = document.createElement("canvas");
	c.width = w;
	c.height = h;
	c.getContext("2d").putImageData(new ImageData(rgba, w, h), 0, 0);
	return c.toDataURL("image/png");
}

function el(name, attrs, parent) {
	const n = document.createElementNS(NS, name);
	for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
	parent?.appendChild(n);
	return n;
}

const CHANNEL = {
	R: "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0",
	G: "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0",
	B: "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0",
};

function filterFor(w, h, radius, o) {
	const key = [w, h, radius, o.bezel, o.refract, o.frost, o.dispersion].join("|");
	if (cache.has(key)) return cache.get(key);

	const { displacement, specular } = buildGlassMaps({ width: w, height: h, radius, bezel: o.bezel });
	const id = `lg-${++seq}`;
	const f = el(
		"filter",
		{ id, x: 0, y: 0, width: w, height: h, filterUnits: "userSpaceOnUse", primitiveUnits: "userSpaceOnUse", "color-interpolation-filters": "sRGB" },
		ensureDefs(),
	);

	el("feGaussianBlur", { in: "SourceGraphic", stdDeviation: o.frost, result: "frost" }, f);
	el("feImage", { href: toDataURL(displacement, w, h), x: 0, y: 0, width: w, height: h, preserveAspectRatio: "none", result: "map" }, f);

	// Dispersion: each colour channel refracts a little differently.
	const split = o.dispersion;
	[["R", 1 + split], ["G", 1], ["B", 1 - split]].forEach(([ch, k]) => {
		el("feDisplacementMap", { in: "frost", in2: "map", scale: o.refract * k, xChannelSelector: "R", yChannelSelector: "G", result: `d${ch}` }, f);
		el("feColorMatrix", { in: `d${ch}`, type: "matrix", values: CHANNEL[ch], result: `c${ch}` }, f);
	});
	el("feBlend", { in: "cR", in2: "cG", mode: "screen", result: "rg" }, f);
	el("feBlend", { in: "rg", in2: "cB", mode: "screen", result: "rgb" }, f);
	el("feColorMatrix", { in: "rgb", type: "saturate", values: 1.45, result: "vivid" }, f);

	el("feImage", { href: toDataURL(specular, w, h), x: 0, y: 0, width: w, height: h, preserveAspectRatio: "none", result: "spec" }, f);
	el("feComposite", { in: "spec", in2: "vivid", operator: "over" }, f);

	cache.set(key, id);
	return id;
}

function options(node) {
	const d = node.dataset;
	const num = (v, def) => (v === undefined || v === "" ? def : Number(v));
	return {
		refract: num(d.refract, 34),
		bezel: num(d.bezel, 16),
		frost: num(d.frost, 1.5),
		dispersion: num(d.dispersion, 0.08),
	};
}

function apply(node) {
	// Layout size, not getBoundingClientRect: an element mid-animation
	// (scale transform) would otherwise get a map that doesn't fit it.
	const w = node.offsetWidth;
	const h = node.offsetHeight;
	if (w < 4 || h < 4) return;
	const radius = parseFloat(getComputedStyle(node).borderTopLeftRadius) || 0;
	const id = filterFor(w, h, radius, options(node));
	node.style.backdropFilter = `url(#${id})`;
	node.style.webkitBackdropFilter = `url(#${id})`;
}

const pending = new Set();
let frame = 0;
const ro = supported
	? new ResizeObserver((entries) => {
			for (const e of entries) pending.add(e.target);
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(() => {
				pending.forEach(apply);
				pending.clear();
			});
		})
	: null;

/** Upgrade every [data-glass] element under root (call again after adding panes). */
export function liquidGlass(root = document) {
	document.documentElement.classList.toggle("lg-refract", supported);
	if (!supported) return;
	for (const node of root.querySelectorAll("[data-glass]")) {
		if (node.__lg) continue;
		node.__lg = true;
		ro.observe(node);
	}
}

/** Re-apply after an element's radius or glass options change. */
export function refreshGlass(node) {
	if (supported && node.__lg) apply(node);
}
