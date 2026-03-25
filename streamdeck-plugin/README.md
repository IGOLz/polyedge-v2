# PolyEdge Stream Deck Plugin

Custom Stream Deck plugin for the PolyEdge dashboard summary endpoint.

## What It Does

- Polls `GET /api/streamdeck/summary` from the dashboard every 5-60 seconds.
- Renders live SVG tiles directly on Stream Deck keys.
- Opens the relevant dashboard page when a key is pressed.
- Stores dashboard base URL and bearer token in plugin global settings instead of on individual keys.
- Bundles a preconfigured 15-key profile as `polyedge-main.streamDeckProfile`.

## Local Development

```bash
cd streamdeck-plugin
npm install
npm run build
streamdeck link com.polyedge.streamdeck.sdPlugin
```

Then enable Stream Deck developer mode and install or restart the linked plugin.

## Runtime Configuration

Open any `Monitor Tile` action in the property inspector and set:

- `Dashboard Base URL`, for example `http://192.168.8.164:3000`
- `Bearer Token`, matching `STREAMDECK_READ_TOKEN`
- `Poll Interval`, default `10`
- `Timezone Mode`, default `UTC`

Each key also stores:

- `Tile`
- Optional `Target Path` override

## Bundled Profile

The generated profile lives at:

- `com.polyedge.streamdeck.sdPlugin/polyedge-main.streamDeckProfile`

It targets the standard 15-key Stream Deck layout and places the 15 monitoring tiles on the first page.
