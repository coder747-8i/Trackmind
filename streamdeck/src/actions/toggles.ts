import { action, type KeyDownEvent } from "@elgato/streamdeck";

import type { TrackmindStatus } from "../trackmind";
import { TrackmindAction, type ToggleMode, type View } from "./base";

type ToggleSettings = { mode?: ToggleMode };

/** Stream-state caption shared by keys that need a live camera. */
function streamCaption(s: TrackmindStatus): string | null {
	if (s.stream === "connecting") return "Connecting…";
	if (s.stream === "offline") return s.error ? "Stream error" : "No stream";
	return null;
}

abstract class ToggleAction extends TrackmindAction<ToggleSettings> {
	protected abstract readonly command: string;

	override async onKeyDown(ev: KeyDownEvent<ToggleSettings>): Promise<void> {
		await this.run(ev.action, this.command, { state: ev.payload.settings.mode ?? "toggle" });
	}
}

@action({ UUID: "com.coder747.trackmind.tracking" })
export class TrackingAction extends ToggleAction {
	protected readonly command = "tracking";

	protected view(_: ToggleSettings, s: TrackmindStatus | null): View {
		if (!s) return { key: { tone: "green", active: false, icon: "tracking", label: "Tracking" } };
		const waiting = streamCaption(s);
		if (s.tracking) {
			return {
				key: {
					tone: "green",
					active: true,
					icon: "tracking",
					label: "Tracking",
					sub: s.locked ? "Locked on" : s.subject ? "Subject" : "Searching",
					subInk: s.subject || s.locked ? "tone" : "warn",
					corner: s.subject ? "green" : "amber",
				},
			};
		}
		return {
			key: {
				tone: "green",
				active: false,
				icon: "tracking",
				label: "Tracking",
				sub: waiting ?? (s.manual ? "Manual" : "Paused"),
				subInk: waiting ? "warn" : "dim",
			},
		};
	}
}

@action({ UUID: "com.coder747.trackmind.lock" })
export class LockAction extends ToggleAction {
	protected readonly command = "lock";

	protected view(_: ToggleSettings, s: TrackmindStatus | null): View {
		if (s?.locked) {
			return { key: { tone: "amber", active: true, icon: "lock", label: "Locked", sub: "On subject" } };
		}
		return {
			key: {
				tone: "amber",
				active: false,
				icon: "unlock",
				label: "Lock",
				sub: s && !s.tracking ? "Needs tracking" : "Off",
			},
		};
	}
}

@action({ UUID: "com.coder747.trackmind.autozoom" })
export class AutoZoomAction extends ToggleAction {
	protected readonly command = "autozoom";

	protected view(_: ToggleSettings, s: TrackmindStatus | null): View {
		const on = !!s?.autozoom;
		const sub = !on ? "Off" : s?.zooming === 1 ? "Zooming in" : s?.zooming === -1 ? "Zooming out" : "On";
		return { key: { tone: "blue", active: on, icon: "autozoom", label: "Auto-Zoom", sub } };
	}
}

@action({ UUID: "com.coder747.trackmind.motionsync" })
export class MotionSyncAction extends ToggleAction {
	protected readonly command = "motion-sync";

	protected view(_: ToggleSettings, s: TrackmindStatus | null): View {
		const on = !!s?.motion_sync;
		return { key: { tone: "blue", active: on, icon: "motionSync", label: "Motion Sync", sub: on ? "On" : "Off" } };
	}
}
