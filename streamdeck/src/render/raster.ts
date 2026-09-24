import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

import { initWasm, Resvg } from "@resvg/resvg-wasm";

import type { Layers } from "./glass";

/**
 * SVG → PNG with resvg (WebAssembly), so keys can use real filters —
 * blur, displacement (refraction), saturation — which Stream Deck's own
 * SVG renderer doesn't support. Fonts are bundled (Inter), so keys look
 * identical on every machine.
 *
 * Files live next to the bundle: bin/resvg.wasm and ../fonts/*.ttf.
 */
const here = path.dirname(url.fileURLToPath(import.meta.url));

let ready: Promise<void> | null = null;
let fonts: Uint8Array[] = [];

export function initRaster(): Promise<void> {
	ready ??= (async () => {
		await initWasm(fs.readFileSync(path.join(here, "resvg.wasm")));
		const dir = path.join(here, "..", "fonts");
		fonts = fs
			.readdirSync(dir)
			.filter((f) => f.endsWith(".ttf"))
			.map((f) => new Uint8Array(fs.readFileSync(path.join(dir, f))));
	})();
	return ready;
}

const cache = new Map<string, string>();
const MAX = 300;

/** Render an SVG to a PNG data URI at `width` px, memoised. */
export async function rasterize(svg: string, width: number): Promise<string> {
	const key = createHash("sha1").update(`${width}|`).update(svg).digest("base64");
	const hit = cache.get(key);
	if (hit) {
		cache.delete(key);
		cache.set(key, hit); // LRU bump
		return hit;
	}
	await initRaster();
	const png = new Resvg(svg, {
		fitTo: { mode: "width", value: width },
		font: { fontBuffers: fonts, defaultFontFamily: "Inter Display", loadSystemFonts: false },
	})
		.render()
		.asPng();
	const uri = `data:image/png;base64,${Buffer.from(png).toString("base64")}`;
	cache.set(key, uri);
	if (cache.size > MAX) cache.delete(cache.keys().next().value!);
	return uri;
}

/** Composite a key: cached glass backdrop + fresh overlay. */
export async function rasterizeLayers(layers: Layers): Promise<string> {
	const backdrop = await rasterize(layers.backdrop, layers.width);
	return rasterize(layers.overlay(backdrop), layers.width);
}
