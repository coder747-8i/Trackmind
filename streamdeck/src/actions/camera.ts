import { action, type KeyDownEvent, type KeyUpEvent } from "@elgato/streamdeck";

import { trackmind, type TrackmindStatus } from "../trackmind";
import { HoldAction, TrackmindAction, type View } from "./base";

/** "off" pauses tracking so the shot holds; "keep" lets tracking take over from the preset. */
type TrackingOnRecall = "off" | "keep";

// ── Presets ──────────────────────────────────────────────────

type PresetSettings = { preset?: number; label?: string; tracking?: TrackingOnRecall };

@action({ UUID: "com.coder747.trackmind.preset" })
export class PresetAction extends TrackmindAction<PresetSettings> {
	override async onKeyDown(ev: KeyDownEvent<PresetSettings>): Promise<void> {
		const { preset = 1, tracking = "off" } = ev.payload.settings;
		this.flash(ev.action);
		await this.run(ev.action, "preset", { preset, tracking });
	}

	protected view(settings: PresetSettings, _: TrackmindStatus | null, id: string): View {
		const preset = settings.preset ?? 1;
		const onAir = trackmind.onAirPreset === preset;
		const label = settings.label?.trim();
		return {
			key: {
				tone: "red",
				active: onAir || this.pressed.has(id),
				glyph: String(preset),
				label: label || "Preset",
				sub: onAir ? "On air" : label ? `Preset ${preset}` : "Recall",
			},
		};
	}
}

type HomeSettings = { tracking?: TrackingOnRecall };

@action({ UUID: "com.coder747.trackmind.home" })
export class HomeAction extends TrackmindAction<HomeSettings> {
	override async onKeyDown(ev: KeyDownEvent<HomeSettings>): Promise<void> {
		this.flash(ev.action);
		await this.run(ev.action, "home", { tracking: ev.payload.settings.tracking ?? "off" });
	}

	protected view(_: HomeSettings, s: TrackmindStatus | null, id: string): View {
		const home = s?.home_preset ?? 0;
		const onAir = !!s && trackmind.onAirPreset === home;
		return {
			key: {
				tone: "red",
				active: onAir || this.pressed.has(id),
				icon: "home",
				label: "Home",
				sub: onAir ? "On air" : `Preset ${home}`,
			},
		};
	}
}

// ── Profiles ─────────────────────────────────────────────────

type ProfileSettings = { profile?: string };

@action({ UUID: "com.coder747.trackmind.profile" })
export class ProfileAction extends TrackmindAction<ProfileSettings> {
	override async onKeyDown(ev: KeyDownEvent<ProfileSettings>): Promise<void> {
		const name = ev.payload.settings.profile;
		if (!name) {
			await ev.action.showAlert();
			return;
		}
		const res = await this.run(ev.action, "profile", { name });
		if (res.ok) await ev.action.showOk();
	}

	protected view(settings: ProfileSettings, s: TrackmindStatus | null): View {
		const name = settings.profile;
		if (!name) return { key: { tone: "blue", active: false, icon: "profile", label: "Profile", sub: "Pick one" } };
		const exists = !s || s.profiles.includes(name);
		const current = s?.profile === name;
		return {
			key: {
				tone: "blue",
				active: current,
				icon: "profile",
				label: name,
				sub: !exists ? "Not found" : current ? "Active" : "Load",
				subInk: !exists ? "warn" : undefined,
			},
		};
	}
}

// ── Manual pan / tilt & zoom (hold) ──────────────────────────

type Direction = "up" | "down" | "left" | "right" | "up-left" | "up-right" | "down-left" | "down-right";

const VECTOR: Record<Direction, [pan: number, tilt: number]> = {
	up: [0, 1],
	down: [0, -1],
	left: [-1, 0],
	right: [1, 0],
	"up-left": [-1, 1],
	"up-right": [1, 1],
	"down-left": [-1, -1],
	"down-right": [1, -1],
};

const MOVE_LABEL: Record<Direction, string> = {
	up: "Tilt Up",
	down: "Tilt Down",
	left: "Pan Left",
	right: "Pan Right",
	"up-left": "Up-Left",
	"up-right": "Up-Right",
	"down-left": "Down-Left",
	"down-right": "Down-Right",
};

type MoveSettings = { direction?: Direction; speed?: number; pauseTracking?: boolean };

@action({ UUID: "com.coder747.trackmind.ptz" })
export class MoveAction extends HoldAction<MoveSettings> {
	override onKeyDown(ev: KeyDownEvent<MoveSettings>): Promise<void> {
		return this.begin(ev.action, ev.payload.settings);
	}

	override onKeyUp(ev: KeyUpEvent<MoveSettings>): Promise<void> {
		return this.end(ev.action, ev.payload.settings);
	}

	protected start(s: MoveSettings): [string, Record<string, unknown>] {
		const [pan, tilt] = VECTOR[s.direction ?? "up"] ?? VECTOR.up;
		const speed = Math.max(1, Math.min(24, s.speed ?? 6));
		return ["move", { pan: pan * speed, tilt: tilt * speed, pause_tracking: s.pauseTracking ?? true }];
	}

	protected stop(): [string, Record<string, unknown>] {
		return ["move", { pan: 0, tilt: 0 }];
	}

	protected view(settings: MoveSettings, _: TrackmindStatus | null, id: string): View {
		const dir = settings.direction ?? "up";
		return {
			key: {
				tone: "blue",
				active: this.pressed.has(id),
				icon: "arrow",
				direction: dir,
				label: MOVE_LABEL[dir] ?? "Pan / Tilt",
				sub: `Speed ${settings.speed ?? 6}`,
			},
		};
	}
}

type ZoomSettings = { direction?: "in" | "out"; speed?: number; pauseTracking?: boolean };

@action({ UUID: "com.coder747.trackmind.zoom" })
export class ZoomAction extends HoldAction<ZoomSettings> {
	override onKeyDown(ev: KeyDownEvent<ZoomSettings>): Promise<void> {
		return this.begin(ev.action, ev.payload.settings);
	}

	override onKeyUp(ev: KeyUpEvent<ZoomSettings>): Promise<void> {
		return this.end(ev.action, ev.payload.settings);
	}

	protected start(s: ZoomSettings): [string, Record<string, unknown>] {
		return [
			"zoom",
			{
				dir: s.direction === "out" ? "out" : "in",
				speed: Math.max(0, Math.min(7, s.speed ?? 3)),
				pause_tracking: s.pauseTracking ?? true,
			},
		];
	}

	protected stop(): [string, Record<string, unknown>] {
		return ["zoom", { dir: "stop" }];
	}

	protected view(settings: ZoomSettings, _: TrackmindStatus | null, id: string): View {
		const out = settings.direction === "out";
		return {
			key: {
				tone: "blue",
				active: this.pressed.has(id),
				icon: out ? "zoomOut" : "zoomIn",
				label: out ? "Zoom Out" : "Zoom In",
				sub: `Speed ${settings.speed ?? 3}`,
			},
		};
	}
}

// ── Status tile ──────────────────────────────────────────────

type StatusSettings = { detail?: "camera" | "profile" | "version" };

@action({ UUID: "com.coder747.trackmind.status" })
export class StatusAction extends TrackmindAction<StatusSettings> {
	override async onKeyDown(ev: KeyDownEvent<StatusSettings>): Promise<void> {
		trackmind.refresh();
		if (trackmind.online) await ev.action.showOk();
		else await ev.action.showAlert();
	}

	protected view(settings: StatusSettings, s: TrackmindStatus | null): View {
		if (!s) return { key: { tone: "green", active: false, icon: "camera", label: "Trackmind" } };

		const detail =
			settings.detail === "profile"
				? (s.profile ?? "No profile")
				: settings.detail === "version"
					? `v${s.version}`
					: s.camera_ip || "No camera";

		if (s.stream !== "live") {
			const err = s.stream === "offline" && !!s.error;
			return {
				key: {
					tone: err ? "red" : "amber",
					active: err,
					icon: "camera",
					label: err ? "No Stream" : "Connecting",
					sub: detail,
					subInk: "dim",
				},
			};
		}
		if (s.tracking) {
			return {
				key: {
					tone: "green",
					active: true,
					icon: "camera",
					label: s.locked ? "Locked" : "Tracking",
					sub: detail,
					corner: s.subject ? "green" : "amber",
				},
			};
		}
		return {
			key: { tone: "amber", active: true, icon: "camera", label: s.manual ? "Manual" : "Paused", sub: detail },
		};
	}
}
