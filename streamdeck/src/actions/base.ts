import streamDeck, {
	type DialAction,
	type DidReceiveSettingsEvent,
	type KeyAction,
	SingletonAction,
	type WillAppearEvent,
	type WillDisappearEvent,
} from "@elgato/streamdeck";
import type { JsonObject } from "@elgato/utils";

import { dialLayers, keyLayers, type DialSpec, type KeySpec, type Layers } from "../render/glass";
import { rasterizeLayers } from "../render/raster";
import { trackmind, type CommandResult, type TrackmindStatus } from "../trackmind";

export type ToggleMode = "toggle" | "on" | "off";

/** What an action draws, given its settings and the live Trackmind state. */
export type View = { key?: KeySpec; dial?: DialSpec };

/**
 * Shared plumbing for every Trackmind action: remembers each visible
 * instance's settings, redraws all of them when Trackmind's state changes,
 * and skips setImage calls when the picture hasn't changed.
 */
export abstract class TrackmindAction<S extends JsonObject> extends SingletonAction<S> {
	protected settings = new Map<string, S>();
	#drawn = new Map<string, string>();
	/** Instances that are mid-press and should render lit. */
	protected pressed = new Set<string>();

	constructor() {
		super();
		trackmind.on("change", () => this.redrawAll());
	}

	protected abstract view(settings: S, status: TrackmindStatus | null, id: string): View;

	override onWillAppear(ev: WillAppearEvent<S>): void {
		this.settings.set(ev.action.id, ev.payload.settings);
		this.#drawn.delete(ev.action.id);
		trackmind.start();
		void this.redraw(ev.action);
	}

	override onWillDisappear(ev: WillDisappearEvent<S>): void {
		this.settings.delete(ev.action.id);
		this.#drawn.delete(ev.action.id);
		this.pressed.delete(ev.action.id);
	}

	override onDidReceiveSettings(ev: DidReceiveSettingsEvent<S>): void {
		this.settings.set(ev.action.id, ev.payload.settings);
		void this.redraw(ev.action);
	}

	protected settingsFor(id: string): S {
		return this.settings.get(id) ?? ({} as S);
	}

	protected redrawAll(): void {
		for (const action of this.actions) void this.redraw(action);
	}

	protected async redraw(action: KeyAction<S> | DialAction<S>): Promise<void> {
		const view = this.view(this.settingsFor(action.id), trackmind.online ? trackmind.status : null, action.id);
		const offline = !trackmind.online;
		const layers: Layers | null =
			action.isKey() && view.key
				? keyLayers({ ...view.key, offline: offline || view.key.offline })
				: action.isDial() && view.dial
					? dialLayers({ ...view.dial, offline: offline || view.dial.offline })
					: null;
		if (!layers) return;
		// Identity of the picture: backdrop + overlay (with a placeholder for the backdrop image).
		const svg = layers.backdrop + layers.overlay("");
		if (this.#drawn.get(action.id) === svg) return;
		this.#drawn.set(action.id, svg);
		try {
			const uri = await rasterizeLayers(layers);
			if (this.#drawn.get(action.id) !== svg) return; // a newer frame won the race
			if (action.isKey()) await action.setImage(uri);
			else if (action.isDial()) await action.setFeedback({ canvas: uri });
		} catch (err) {
			this.#drawn.delete(action.id);
			streamDeck.logger.error(`Render failed: ${err instanceof Error ? err.message : err}`);
		}
	}

	/** Send a command; flash an alert on the key if Trackmind refused it. */
	protected async run(
		action: KeyAction<S> | DialAction<S>,
		command: string,
		body: Record<string, unknown> = {},
	): Promise<CommandResult> {
		const res = await trackmind.send(command, body);
		if (!res.ok) {
			streamDeck.logger.warn(`${command} failed: ${res.error}`);
			await action.showAlert();
		}
		return res;
	}

	/** Light the key briefly — feedback for one-shot presses. */
	protected flash(action: KeyAction<S> | DialAction<S>, ms = 450): void {
		this.pressed.add(action.id);
		void this.redraw(action);
		setTimeout(() => {
			this.pressed.delete(action.id);
			void this.redraw(action);
		}, ms);
	}
}

/**
 * Keys that act while held (manual pan/tilt, zoom). Trackmind stops any
 * manual move it hasn't heard about for ~1.2 s, so while the key is down we
 * re-send the command as a keep-alive; a lost key-up can never leave the
 * camera spinning.
 */
export abstract class HoldAction<S extends JsonObject> extends TrackmindAction<S> {
	#keepAlive = new Map<string, NodeJS.Timeout>();

	protected abstract start(settings: S): [command: string, body: Record<string, unknown>];
	protected abstract stop(settings: S): [command: string, body: Record<string, unknown>];

	protected async begin(action: KeyAction<S> | DialAction<S>, settings: S): Promise<void> {
		this.pressed.add(action.id);
		void this.redraw(action);
		const [cmd, body] = this.start(settings);
		const res = await this.run(action, cmd, body);
		if (!res.ok) {
			this.pressed.delete(action.id);
			void this.redraw(action);
			return;
		}
		if (!this.pressed.has(action.id)) {
			// Released while the start request was in flight — the stop may have
			// been handled first, so send it again now that the start has landed.
			const [stopCmd, stopBody] = this.stop(settings);
			await trackmind.send(stopCmd, stopBody);
			return;
		}
		clearInterval(this.#keepAlive.get(action.id));
		this.#keepAlive.set(
			action.id,
			setInterval(() => void trackmind.send(cmd, body), 400),
		);
	}

	protected async end(action: KeyAction<S> | DialAction<S>, settings: S): Promise<void> {
		clearInterval(this.#keepAlive.get(action.id));
		this.#keepAlive.delete(action.id);
		this.pressed.delete(action.id);
		void this.redraw(action);
		const [cmd, body] = this.stop(settings);
		await trackmind.send(cmd, body);
	}

	override onWillDisappear(ev: WillDisappearEvent<S>): void {
		const id = ev.action.id;
		if (this.pressed.has(id) || this.#keepAlive.has(id)) {
			// Page flipped mid-hold: no key-up is coming, so stop the camera now.
			clearInterval(this.#keepAlive.get(id));
			this.#keepAlive.delete(id);
			const [cmd, body] = this.stop(this.settingsFor(id));
			void trackmind.send(cmd, body);
		}
		super.onWillDisappear(ev);
	}
}
