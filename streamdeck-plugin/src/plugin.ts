import streamDeck from "@elgato/streamdeck";

import { MonitorTileAction } from "./actions/monitor-tile.js";
import { SummaryPoller } from "./poller.js";

const poller = new SummaryPoller();

streamDeck.actions.registerAction(new MonitorTileAction(poller));
streamDeck.system.onSystemDidWakeUp(() => {
  void poller.refreshNow();
});

await streamDeck.connect();
await poller.initialize();
await poller.refreshNow();

streamDeck.logger.info("PolyEdge Stream Deck plugin connected");
