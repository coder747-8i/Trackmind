export type GlassMapOptions = {
	width: number;
	height: number;
	radius: number;
	bezel: number;
	/** Light angle in degrees (0 = from the top, clockwise). Default −45. */
	light?: number;
};

export type GlassMaps = {
	/** RGBA; R = x, G = y displacement, 128 = none. */
	displacement: Uint8ClampedArray;
	/** RGBA; white with alpha = highlight strength. */
	specular: Uint8ClampedArray;
};

export function buildGlassMaps(options: GlassMapOptions): GlassMaps;
