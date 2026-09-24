/**
 * Trackmind × vMix palette.
 *
 * vMix's UI is charcoal glass with tally colours doing the talking: red for
 * Program, green for Preview, amber for overlays. Trackmind already speaks the
 * same language (green = tracking, amber = lock), so every key uses one tone
 * from this list and the rest of the tile stays neutral.
 */
export const Tone = {
	/** Tracking live — vMix Preview green. */
	green: { base: "#22d66f", hi: "#8dffc0", deep: "#0b7a3c" },
	/** Program / on-air — vMix red. Used for the preset that's currently on air. */
	red: { base: "#ff3b45", hi: "#ff9aa0", deep: "#8f0d17" },
	/** Lock-on — Trackmind amber, vMix overlay orange. */
	amber: { base: "#f5a623", hi: "#ffd68a", deep: "#8a5608" },
	/** Zoom / sync / info — cool vMix selection blue. */
	blue: { base: "#3d9bff", hi: "#a8d4ff", deep: "#0d4c94" },
	/** Idle / offline glass. */
	neutral: { base: "#aeb6c4", hi: "#eef2f8", deep: "#3a404b" },
} as const;

export type ToneName = keyof typeof Tone;

export const Ink = {
	primary: "#f5f7fb",
	secondary: "#a3abb9",
	dim: "#5d6472",
	offline: "#ff5c64",
};

export const FONT = "Inter Display";
