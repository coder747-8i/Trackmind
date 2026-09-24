/**
 * Liquid glass — the optics, with no DOM dependency.
 *
 * A glass pane is modelled as a slab with a curved bezel around its edge.
 * Light passing through the bezel refracts (Snell's law, n = 1.5), so the
 * background behind the rim is sampled from a shifted position — that shift,
 * per pixel, is the displacement map. A second map holds the specular rim:
 * the bright line where the curved edge catches the light.
 *
 * Shared by the desktop UI (canvas → SVG feImage), the Stream Deck property
 * inspector, and the Stream Deck key renderer (PNG → resvg).
 */

const IOR = 1.5;

/** Convex squircle bezel profile: height 0 at the outer edge → 1 at the plateau. */
function profile(t) {
	const u = 1 - t;
	return Math.pow(1 - u * u * u * u, 0.25);
}

/** Slope of the profile, numerically. */
function slope(t) {
	const e = 1e-3;
	const a = profile(Math.max(0, t - e));
	const b = profile(Math.min(1, t + e));
	return (b - a) / (Math.min(1, t + e) - Math.max(0, t - e));
}

/**
 * Lateral shift (0..1, relative) of a vertical ray entering the bezel at
 * normalised position t (0 = outer edge, 1 = start of flat top).
 */
function refractShift(t) {
	const s = slope(t); // dh/dx
	// Surface normal tilts outward by atan(s); angle of incidence = that tilt.
	const incidence = Math.atan(s);
	const refracted = Math.asin(Math.sin(incidence) / IOR);
	// Horizontal travel through the remaining thickness.
	return Math.tan(incidence - refracted) * profile(t);
}

/** Signed distance to a rounded rectangle centred at origin (negative inside). */
function sdRoundRect(px, py, hw, hh, r) {
	const qx = Math.abs(px) - (hw - r);
	const qy = Math.abs(py) - (hh - r);
	const ox = Math.max(qx, 0);
	const oy = Math.max(qy, 0);
	return Math.hypot(ox, oy) + Math.min(Math.max(qx, qy), 0) - r;
}

/**
 * Build the two maps for a pane of the given size.
 *
 * @param {object} o
 * @param {number} o.width   Pane width in px
 * @param {number} o.height  Pane height in px
 * @param {number} o.radius  Corner radius in px
 * @param {number} o.bezel   Bezel width in px (how far in the refraction reaches)
 * @param {number} [o.light] Light angle in degrees (0 = from the top, clockwise). Default −45 (top-left).
 * @returns {{ displacement: Uint8ClampedArray, specular: Uint8ClampedArray }}
 *   RGBA buffers. Displacement: R = x, G = y, 128 = none; the filter's
 *   `scale` sets how many px ±127 means.
 *   Specular: white with alpha = highlight strength.
 */
export function buildGlassMaps({ width, height, radius, bezel, light = -45 }) {
	const w = Math.max(1, Math.round(width));
	const h = Math.max(1, Math.round(height));
	const hw = w / 2;
	const hh = h / 2;
	const r = Math.min(radius, hw, hh);
	const bz = Math.max(1, Math.min(bezel, hw, hh));

	// Pre-sample the shift curve so the per-pixel loop stays cheap.
	const N = 128;
	const curve = new Float32Array(N + 1);
	let peak = 1e-6;
	for (let i = 0; i <= N; i++) {
		curve[i] = refractShift(i / N);
		peak = Math.max(peak, Math.abs(curve[i]));
	}

	const la = ((light - 90) * Math.PI) / 180;
	const lx = Math.cos(la);
	const ly = Math.sin(la);

	const disp = new Uint8ClampedArray(w * h * 4);
	const spec = new Uint8ClampedArray(w * h * 4);

	for (let y = 0; y < h; y++) {
		for (let x = 0; x < w; x++) {
			const px = x + 0.5 - hw;
			const py = y + 0.5 - hh;
			const d = sdRoundRect(px, py, hw, hh, r);
			const i = (y * w + x) * 4;
			disp[i + 2] = 128;
			disp[i + 3] = 255;
			spec[i] = spec[i + 1] = spec[i + 2] = 255;

			const inside = -d;
			if (inside <= 0 || inside >= bz) {
				disp[i] = disp[i + 1] = 128;
				spec[i + 3] = 0;
				continue;
			}

			// Outward normal from the SDF gradient.
			const e = 0.5;
			let nx = sdRoundRect(px + e, py, hw, hh, r) - sdRoundRect(px - e, py, hw, hh, r);
			let ny = sdRoundRect(px, py + e, hw, hh, r) - sdRoundRect(px, py - e, hw, hh, r);
			const nl = Math.hypot(nx, ny) || 1;
			nx /= nl;
			ny /= nl;

			const t = inside / bz;
			const shift = curve[Math.min(N, Math.round(t * N))] / peak; // 0..1
			// Sample from further in: the rim magnifies what's under the pane,
			// bending it toward the edge — the "liquid" lensing. (Sampling
			// outward would read past the backdrop the browser provides.)
			disp[i] = 128 - nx * shift * 127;
			disp[i + 1] = 128 - ny * shift * 127;

			// Specular: strongest right at the lip, facing the light, with a
			// softer bounce on the opposite corner.
			const facing = nx * lx + ny * ly;
			const lip = Math.pow(1 - t, 2.4);
			const key = Math.pow(Math.max(0, facing), 1.6);
			const bounce = Math.pow(Math.max(0, -facing), 2.2) * 0.55;
			const rim = Math.pow(Math.max(0, 1 - inside / 2.2), 1.5) * 0.5; // hairline all round
			spec[i + 3] = Math.min(255, 255 * (0.85 * lip * (key + bounce) + rim));
		}
	}

	return { displacement: disp, specular: spec };
}
