const TILE_OPTIONS = [
  { value: "collector_overall", label: "Collector overall", targetPath: "/" },
  { value: "asset_btc", label: "BTC feed", targetPath: "/" },
  { value: "asset_eth", label: "ETH feed", targetPath: "/" },
  { value: "asset_sol", label: "SOL feed", targetPath: "/" },
  { value: "asset_xrp", label: "XRP feed", targetPath: "/" },
  { value: "trading_status", label: "Trading status", targetPath: "/bot" },
  { value: "trading_pnl_24h", label: "Trading PnL 24h", targetPath: "/bot" },
  { value: "trading_open", label: "Trading open positions", targetPath: "/bot" },
  { value: "trading_last_trade", label: "Trading last trade", targetPath: "/bot" },
  { value: "trading_alerts", label: "Trading alerts", targetPath: "/bot" },
  { value: "merge_status", label: "Weather merge status", targetPath: "/bot" },
  { value: "merge_positions", label: "Weather merge positions", targetPath: "/bot" },
  { value: "clone_status", label: "Weather clone status", targetPath: "/bot" },
  { value: "clone_coverage", label: "Weather clone coverage", targetPath: "/bot" },
  { value: "ops_alerts", label: "Ops alerts", targetPath: "/bot" },
];

const DEFAULT_GLOBAL_SETTINGS = {
  baseUrl: "",
  bearerToken: "",
  pollIntervalSec: 10,
  timezoneMode: "utc",
};

const DEFAULT_TILE_SETTINGS = {
  tileId: "collector_overall",
  targetPath: "/",
};

const state = {
  socket: null,
  registrationInfo: null,
  uuid: "",
  pluginUuid: "",
  actionUuid: "",
  context: "",
  globalSettings: { ...DEFAULT_GLOBAL_SETTINGS },
  tileSettings: { ...DEFAULT_TILE_SETTINGS },
  suppressChanges: false,
};

const elements = {
  baseUrl: document.getElementById("baseUrl"),
  bearerToken: document.getElementById("bearerToken"),
  pollIntervalSec: document.getElementById("pollIntervalSec"),
  timezoneMode: document.getElementById("timezoneMode"),
  tileId: document.getElementById("tileId"),
  targetPath: document.getElementById("targetPath"),
  statusText: document.getElementById("statusText"),
  tileHelp: document.getElementById("tileHelp"),
};

function setStatus(message) {
  elements.statusText.textContent = message;
}

function defaultTargetPathFor(tileId) {
  return TILE_OPTIONS.find((option) => option.value === tileId)?.targetPath || "/";
}

function populateTileOptions() {
  for (const option of TILE_OPTIONS) {
    const element = document.createElement("option");
    element.value = option.value;
    element.textContent = option.label;
    elements.tileId.appendChild(element);
  }
}

function send(payload) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    return;
  }
  state.socket.send(JSON.stringify(payload));
}

function saveGlobalSettings() {
  if (state.suppressChanges || !state.pluginUuid) return;

  const payload = {
    baseUrl: elements.baseUrl.value.trim(),
    bearerToken: elements.bearerToken.value.trim(),
    pollIntervalSec: Math.max(5, Math.min(60, Number(elements.pollIntervalSec.value || "10"))),
    timezoneMode: elements.timezoneMode.value === "local" ? "local" : "utc",
  };

  state.globalSettings = payload;
  send({
    event: "setGlobalSettings",
    context: state.pluginUuid,
    payload,
  });
}

function saveTileSettings() {
  if (state.suppressChanges || !state.actionUuid || !state.context) return;

  const tileId = elements.tileId.value || DEFAULT_TILE_SETTINGS.tileId;
  const targetPath = elements.targetPath.value.trim() || defaultTargetPathFor(tileId);

  state.tileSettings = { tileId, targetPath };
  updateTileHelp();

  send({
    event: "setSettings",
    action: state.actionUuid,
    context: state.context,
    payload: state.tileSettings,
  });
}

function applyGlobalSettings(payload) {
  state.globalSettings = {
    ...DEFAULT_GLOBAL_SETTINGS,
    ...payload,
  };

  state.suppressChanges = true;
  elements.baseUrl.value = state.globalSettings.baseUrl || "";
  elements.bearerToken.value = state.globalSettings.bearerToken || "";
  elements.pollIntervalSec.value = String(state.globalSettings.pollIntervalSec || 10);
  elements.timezoneMode.value = state.globalSettings.timezoneMode || "utc";
  state.suppressChanges = false;
}

function applyTileSettings(payload) {
  state.tileSettings = {
    ...DEFAULT_TILE_SETTINGS,
    ...payload,
  };

  state.suppressChanges = true;
  elements.tileId.value = state.tileSettings.tileId || DEFAULT_TILE_SETTINGS.tileId;
  elements.targetPath.value = state.tileSettings.targetPath || defaultTargetPathFor(elements.tileId.value);
  updateTileHelp();
  state.suppressChanges = false;
}

function updateTileHelp() {
  const tileId = elements.tileId.value || DEFAULT_TILE_SETTINGS.tileId;
  const defaultPath = defaultTargetPathFor(tileId);
  elements.tileHelp.textContent = `Default path: ${defaultPath}`;
}

function handleMessage(message) {
  if (message.event === "didReceiveGlobalSettings") {
    applyGlobalSettings(message.payload?.settings || {});
    setStatus("Global settings loaded");
  }

  if (message.event === "didReceiveSettings") {
    applyTileSettings(message.payload?.settings || {});
    setStatus("Tile settings loaded");
  }
}

function bindInputs() {
  const saveGlobal = () => saveGlobalSettings();
  const saveTile = () => saveTileSettings();

  elements.baseUrl.addEventListener("input", saveGlobal);
  elements.bearerToken.addEventListener("input", saveGlobal);
  elements.pollIntervalSec.addEventListener("input", saveGlobal);
  elements.timezoneMode.addEventListener("change", saveGlobal);

  elements.tileId.addEventListener("change", () => {
    if (!elements.targetPath.value.trim()) {
      elements.targetPath.value = defaultTargetPathFor(elements.tileId.value);
    }
    saveTile();
  });
  elements.targetPath.addEventListener("input", saveTile);
}

window.connectElgatoStreamDeckSocket = function connectElgatoStreamDeckSocket(
  port,
  uuid,
  registerEvent,
  info,
  actionInfo
) {
  populateTileOptions();
  bindInputs();

  state.uuid = uuid;
  state.registrationInfo = JSON.parse(info);
  state.pluginUuid = state.registrationInfo?.plugin?.uuid || "";

  const parsedActionInfo = JSON.parse(actionInfo);
  state.actionUuid = parsedActionInfo.action;
  state.context = parsedActionInfo.context;

  applyGlobalSettings(state.globalSettings);
  applyTileSettings(parsedActionInfo.payload?.settings || {});

  state.socket = new WebSocket(`ws://127.0.0.1:${port}`);
  state.socket.onopen = function onOpen() {
    send({ event: registerEvent, uuid });
    send({ event: "getGlobalSettings", context: state.pluginUuid });
    send({ event: "getSettings", action: state.actionUuid, context: state.context });
    setStatus("Connected");
  };

  state.socket.onmessage = function onMessage(event) {
    try {
      handleMessage(JSON.parse(event.data));
    } catch (error) {
      setStatus(`Parse error: ${String(error)}`);
    }
  };

  state.socket.onerror = function onError() {
    setStatus("Socket error");
  };

  state.socket.onclose = function onClose() {
    setStatus("Disconnected");
  };
};
