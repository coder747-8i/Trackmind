import commonjs from "@rollup/plugin-commonjs";
import nodeResolve from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";
import typescript from "@rollup/plugin-typescript";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const isWatching = !!process.env.ROLLUP_WATCH;
const sdPlugin = "com.coder747.trackmind.sdPlugin";
const ui = "../ui"; // the desktop app's design system — shared, not duplicated

/** Copy files into the plugin folder (and watch them). */
function copy(pairs) {
	return {
		name: "copy-shared",
		buildStart() {
			for (const [from] of pairs) this.addWatchFile(path.resolve(from));
		},
		writeBundle() {
			for (const [from, to] of pairs) {
				fs.mkdirSync(path.dirname(to), { recursive: true });
				fs.copyFileSync(from, to);
			}
		},
	};
}

/**
 * @type {import('rollup').RollupOptions[]}
 */
export default [
	// The plugin itself (Node, runs inside Stream Deck)
	{
		input: "src/plugin.ts",
		output: {
			file: `${sdPlugin}/bin/plugin.js`,
			sourcemap: isWatching,
			sourcemapPathTransform: (relativeSourcePath, sourcemapPath) => {
				return url.pathToFileURL(path.resolve(path.dirname(sourcemapPath), relativeSourcePath)).href;
			},
		},
		plugins: [
			{
				name: "watch-externals",
				buildStart: function () {
					this.addWatchFile(`${sdPlugin}/manifest.json`);
				},
			},
			typescript({
				mapRoot: isWatching ? "./" : undefined,
			}),
			nodeResolve({
				browser: false,
				exportConditions: ["node"],
				preferBuiltins: true,
			}),
			commonjs(),
			!isWatching && terser(),
			{
				name: "emit-module-package-file",
				generateBundle() {
					this.emitFile({ fileName: "package.json", source: `{ "type": "module" }`, type: "asset" });
				},
			},
			copy([["node_modules/@resvg/resvg-wasm/index_bg.wasm", `${sdPlugin}/bin/resvg.wasm`]]),
		],
	},

	// Liquid-glass engine for the property inspector, as a classic script
	// (ES modules don't load from file:// in Chromium).
	{
		input: `${ui}/js/liquid-glass.js`,
		output: {
			file: `${sdPlugin}/ui/shared/liquid-glass.js`,
			format: "iife",
			name: "TrackmindGlass",
		},
		plugins: [
			!isWatching && terser(),
			copy([
				[`${ui}/css/glass.css`, `${sdPlugin}/ui/shared/css/glass.css`],
				[`${ui}/fonts/InterVariable.woff2`, `${sdPlugin}/ui/shared/fonts/InterVariable.woff2`],
				[`${ui}/img/mark.svg`, `${sdPlugin}/ui/shared/img/mark.svg`],
				[`${ui}/img/wordmark.svg`, `${sdPlugin}/ui/shared/img/wordmark.svg`],
			]),
		],
	},
];
