import streamDeck, { type KeyAction } from "@elgato/streamdeck";

import { renderTileImage } from "./renderer.js";
import {
  DEFAULT_GLOBAL_SETTINGS,
  TILE_DEFINITIONS,
  normalizeGlobalSettings,
  normalizeTileSettings,
  type GlobalSettings,
  type TileSettings,
} from "./tile-definitions.js";
import type { StreamDeckSummaryPayload } from "./types.js";

type TrackedAction = {
  action: KeyAction<TileSettings>;
  settings: TileSettings;
};

function serializeError(error: unknown) {
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : "Unknown error";
}

function buildSummaryUrl(baseUrl: string) {
  const normalizedBaseUrl = baseUrl.trim().replace(/\/+$/, "");
  if (!normalizedBaseUrl) return null;
  return `${normalizedBaseUrl}/api/streamdeck/summary`;
}

function buildNavigationUrl(baseUrl: string, targetPath: string) {
  const normalizedBaseUrl = baseUrl.trim();
  if (!normalizedBaseUrl) return null;

  try {
    return new URL(targetPath, normalizedBaseUrl.endsWith("/") ? normalizedBaseUrl : `${normalizedBaseUrl}/`).toString();
  } catch {
    return null;
  }
}

export class SummaryPoller {
  private globalSettings = DEFAULT_GLOBAL_SETTINGS;
  private trackedActions = new Map<string, TrackedAction>();
  private lastSummary: StreamDeckSummaryPayload | null = null;
  private lastError: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inflight: Promise<void> | null = null;

  async initialize() {
    streamDeck.settings.useExperimentalMessageIdentifiers = true;
    streamDeck.settings.onDidReceiveGlobalSettings<GlobalSettings>((ev) => {
      this.globalSettings = normalizeGlobalSettings(ev.settings as Partial<GlobalSettings>);
      void this.renderAll();
      this.schedule(0);
    });

    try {
      this.globalSettings = normalizeGlobalSettings(
        await streamDeck.settings.getGlobalSettings<Partial<GlobalSettings>>()
      );
    } catch (error) {
      streamDeck.logger.warn(`Failed to load global settings: ${serializeError(error)}`);
    }
  }

  track(action: KeyAction<TileSettings>, rawSettings: Partial<TileSettings> | undefined) {
    this.trackedActions.set(action.id, {
      action,
      settings: normalizeTileSettings(rawSettings),
    });

    void this.renderAction(action.id);
    this.schedule(0);
  }

  untrack(actionId: string) {
    this.trackedActions.delete(actionId);

    if (this.trackedActions.size === 0 && this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  updateSettings(action: KeyAction<TileSettings>, rawSettings: Partial<TileSettings> | undefined) {
    this.trackedActions.set(action.id, {
      action,
      settings: normalizeTileSettings(rawSettings),
    });

    void this.renderAction(action.id);
  }

  async openAction(action: KeyAction<TileSettings>) {
    const tracked = this.trackedActions.get(action.id);
    if (!tracked) {
      await action.showAlert();
      return;
    }

    const url = buildNavigationUrl(
      this.globalSettings.baseUrl,
      tracked.settings.targetPath || TILE_DEFINITIONS[tracked.settings.tileId].targetPath
    );
    if (!url) {
      await action.showAlert();
      return;
    }

    await streamDeck.system.openUrl(url);
  }

  async refreshNow() {
    return this.refreshSummary();
  }

  private schedule(delayMs?: number) {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (this.trackedActions.size === 0) {
      return;
    }

    const delay = delayMs ?? this.globalSettings.pollIntervalSec * 1000;
    this.timer = setTimeout(() => {
      void this.refreshSummary().finally(() => this.schedule());
    }, delay);
  }

  private async refreshSummary() {
    if (this.inflight) {
      return this.inflight;
    }

    this.inflight = this.doRefresh().finally(() => {
      this.inflight = null;
    });
    return this.inflight;
  }

  private async doRefresh() {
    const url = buildSummaryUrl(this.globalSettings.baseUrl);
    if (!url || !this.globalSettings.bearerToken) {
      this.lastError = null;
      await this.renderAll();
      return;
    }

    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${this.globalSettings.bearerToken}`,
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Dashboard returned ${response.status}`);
      }

      const payload = (await response.json()) as StreamDeckSummaryPayload;
      this.lastSummary = payload;
      this.lastError = null;
    } catch (error) {
      this.lastError = serializeError(error);
      streamDeck.logger.error(`Stream Deck summary fetch failed: ${this.lastError}`);
    }

    await this.renderAll();
  }

  private async renderAll() {
    await Promise.allSettled(
      Array.from(this.trackedActions.keys(), (actionId) => this.renderAction(actionId))
    );
  }

  private async renderAction(actionId: string) {
    const tracked = this.trackedActions.get(actionId);
    if (!tracked) return;

    const image = renderTileImage(tracked.settings.tileId, this.lastSummary, {
      isCached: Boolean(this.lastSummary && this.lastError),
      errorMessage: this.lastSummary ? null : this.lastError,
      timezoneMode: this.globalSettings.timezoneMode,
      now: new Date(),
    });

    await tracked.action.setTitle("");
    await tracked.action.setImage(image);
  }
}
