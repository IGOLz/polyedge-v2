import streamDeck from "@elgato/streamdeck";
import { renderTileImage } from "./renderer.js";
import { DEFAULT_GLOBAL_SETTINGS, TILE_DEFINITIONS, normalizeGlobalSettings, normalizeTileSettings, } from "./tile-definitions.js";
function serializeError(error) {
    if (error instanceof Error)
        return error.message;
    return typeof error === "string" ? error : "Unknown error";
}
function buildSummaryUrl(baseUrl) {
    const normalizedBaseUrl = baseUrl.trim().replace(/\/+$/, "");
    if (!normalizedBaseUrl)
        return null;
    return `${normalizedBaseUrl}/api/streamdeck/summary`;
}
function buildNavigationUrl(baseUrl, targetPath) {
    const normalizedBaseUrl = baseUrl.trim();
    if (!normalizedBaseUrl)
        return null;
    try {
        return new URL(targetPath, normalizedBaseUrl.endsWith("/") ? normalizedBaseUrl : `${normalizedBaseUrl}/`).toString();
    }
    catch {
        return null;
    }
}
export class SummaryPoller {
    globalSettings = DEFAULT_GLOBAL_SETTINGS;
    trackedActions = new Map();
    lastSummary = null;
    lastError = null;
    timer = null;
    inflight = null;
    async initialize() {
        streamDeck.settings.useExperimentalMessageIdentifiers = true;
        streamDeck.settings.onDidReceiveGlobalSettings((ev) => {
            this.globalSettings = normalizeGlobalSettings(ev.settings);
            void this.renderAll();
            this.schedule(0);
        });
        try {
            this.globalSettings = normalizeGlobalSettings(await streamDeck.settings.getGlobalSettings());
        }
        catch (error) {
            streamDeck.logger.warn(`Failed to load global settings: ${serializeError(error)}`);
        }
    }
    track(action, rawSettings) {
        this.trackedActions.set(action.id, {
            action,
            settings: normalizeTileSettings(rawSettings),
        });
        void this.renderAction(action.id);
        this.schedule(0);
    }
    untrack(actionId) {
        this.trackedActions.delete(actionId);
        if (this.trackedActions.size === 0 && this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }
    updateSettings(action, rawSettings) {
        this.trackedActions.set(action.id, {
            action,
            settings: normalizeTileSettings(rawSettings),
        });
        void this.renderAction(action.id);
    }
    async openAction(action) {
        const tracked = this.trackedActions.get(action.id);
        if (!tracked) {
            await action.showAlert();
            return;
        }
        const url = buildNavigationUrl(this.globalSettings.baseUrl, tracked.settings.targetPath || TILE_DEFINITIONS[tracked.settings.tileId].targetPath);
        if (!url) {
            await action.showAlert();
            return;
        }
        await streamDeck.system.openUrl(url);
    }
    async refreshNow() {
        return this.refreshSummary();
    }
    schedule(delayMs) {
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
    async refreshSummary() {
        if (this.inflight) {
            return this.inflight;
        }
        this.inflight = this.doRefresh().finally(() => {
            this.inflight = null;
        });
        return this.inflight;
    }
    async doRefresh() {
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
            const payload = (await response.json());
            this.lastSummary = payload;
            this.lastError = null;
        }
        catch (error) {
            this.lastError = serializeError(error);
            streamDeck.logger.error(`Stream Deck summary fetch failed: ${this.lastError}`);
        }
        await this.renderAll();
    }
    async renderAll() {
        await Promise.allSettled(Array.from(this.trackedActions.keys(), (actionId) => this.renderAction(actionId)));
    }
    async renderAction(actionId) {
        const tracked = this.trackedActions.get(actionId);
        if (!tracked)
            return;
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
