import { SingletonAction, } from "@elgato/streamdeck";
export const MONITOR_TILE_UUID = "com.polyedge.streamdeck.monitor-tile";
export class MonitorTileAction extends SingletonAction {
    poller;
    constructor(poller) {
        super();
        this.poller = poller;
        Object.defineProperty(this, "manifestId", {
            value: MONITOR_TILE_UUID,
            enumerable: true,
            configurable: false,
            writable: false,
        });
    }
    async onWillAppear(ev) {
        if (!ev.action.isKey())
            return;
        this.poller.track(ev.action, ev.payload.settings);
    }
    onWillDisappear(ev) {
        this.poller.untrack(ev.action.id);
    }
    async onDidReceiveSettings(ev) {
        if (!ev.action.isKey())
            return;
        this.poller.updateSettings(ev.action, ev.payload.settings);
    }
    async onKeyDown(ev) {
        await this.poller.openAction(ev.action);
    }
}
