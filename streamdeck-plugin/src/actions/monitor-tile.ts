import {
  type DidReceiveSettingsEvent,
  type KeyAction,
  type KeyDownEvent,
  SingletonAction,
  type WillAppearEvent,
  type WillDisappearEvent,
} from "@elgato/streamdeck";

import { SummaryPoller } from "../poller.js";
import { type TileSettings } from "../tile-definitions.js";

export const MONITOR_TILE_UUID = "com.polyedge.streamdeck.monitor-tile";

export class MonitorTileAction extends SingletonAction<TileSettings> {
  constructor(private readonly poller: SummaryPoller) {
    super();
    Object.defineProperty(this, "manifestId", {
      value: MONITOR_TILE_UUID,
      enumerable: true,
      configurable: false,
      writable: false,
    });
  }

  override async onWillAppear(ev: WillAppearEvent<TileSettings>) {
    if (!ev.action.isKey()) return;
    this.poller.track(ev.action as KeyAction<TileSettings>, ev.payload.settings);
  }

  override onWillDisappear(ev: WillDisappearEvent<TileSettings>) {
    this.poller.untrack(ev.action.id);
  }

  override async onDidReceiveSettings(ev: DidReceiveSettingsEvent<TileSettings>) {
    if (!ev.action.isKey()) return;
    this.poller.updateSettings(ev.action as KeyAction<TileSettings>, ev.payload.settings);
  }

  override async onKeyDown(ev: KeyDownEvent<TileSettings>) {
    await this.poller.openAction(ev.action);
  }
}
