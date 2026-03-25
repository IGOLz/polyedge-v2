import { mkdtemp, rm, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const pluginDir = path.resolve("com.polyedge.streamdeck.sdPlugin");
const outputProfile = path.join(pluginDir, "polyedge-main.streamDeckProfile");

const rootProfileDir = "C784B6DB-FB59-49BF-A19A-B1C5FE8170C6.sdProfile";
const blankPageDir = "B00IVBB5AP2299JIA60KWIPPDGZ";
const mainPageDir = "PIH1N4R4OL2NH2IOKR1LRVD5V8Z";

const tiles = [
  { coordinate: "0,0", tileId: "collector_overall", targetPath: "/" },
  { coordinate: "1,0", tileId: "asset_btc", targetPath: "/" },
  { coordinate: "2,0", tileId: "asset_eth", targetPath: "/" },
  { coordinate: "3,0", tileId: "asset_sol", targetPath: "/" },
  { coordinate: "4,0", tileId: "asset_xrp", targetPath: "/" },
  { coordinate: "0,1", tileId: "trading_status", targetPath: "/bot" },
  { coordinate: "1,1", tileId: "trading_pnl_24h", targetPath: "/bot" },
  { coordinate: "2,1", tileId: "trading_open", targetPath: "/bot" },
  { coordinate: "3,1", tileId: "trading_last_trade", targetPath: "/bot" },
  { coordinate: "4,1", tileId: "trading_alerts", targetPath: "/bot" },
  { coordinate: "0,2", tileId: "merge_status", targetPath: "/bot" },
  { coordinate: "1,2", tileId: "merge_positions", targetPath: "/bot" },
  { coordinate: "2,2", tileId: "clone_status", targetPath: "/bot" },
  { coordinate: "3,2", tileId: "clone_coverage", targetPath: "/bot" },
  { coordinate: "4,2", tileId: "ops_alerts", targetPath: "/bot" },
];

const actionIds = [
  "2478862b-8e7f-47b8-bb1e-84fab993c717",
  "30a90a0f-b4b5-473d-b8e7-a73e5db54c1a",
  "e79186f0-e9f0-4519-af6d-914b1c0f8226",
  "b4e1c2bf-7ec0-4f77-9052-f611b75f47b5",
  "1be3f298-6052-476b-844e-ac56a1f2a7fe",
  "cb0b5389-c8cb-4722-9df1-67fce662f2f4",
  "96db7747-6be7-4c31-89fd-1a783ba907c3",
  "9376ff87-762d-421d-bd54-c50f8f6fc4fd",
  "6eaed0fd-1d2d-4787-907e-e2f5014f4ec7",
  "b559ee0d-a85b-4b5f-b3ea-9d8d4c120f43",
  "ca7ce7bc-0df6-43f6-a318-b7ad13d3d4e1",
  "8b6a45b3-8927-4207-9359-7775e2d2791c",
  "7b1e7d1d-7f55-4ff7-84c5-a174e2cd627d",
  "97da3a54-a6f8-4f69-baaf-a48ef6cf341d",
  "3cbf3f68-c8f7-40cc-b861-90f6f1507fd2",
];

const rootManifest = {
  Device: {
    Model: "20GAA9901",
    UUID: "",
  },
  Name: "PolyEdge Monitor",
  Pages: {
    Current: "cca21b93-64c5-4578-8a58-a6c35df9a5f2",
    Default: "58012f2d-6556-4424-a672-51814fcb396c",
    Pages: ["cca21b93-64c5-4578-8a58-a6c35df9a5f2"],
  },
  Version: "2.0",
};

const blankPageManifest = {
  Controllers: [{ Actions: {}, Type: "Keypad" }],
  Icon: "",
  Name: "",
};

const mainPageManifest = {
  Controllers: [
    {
      Actions: Object.fromEntries(
        tiles.map((tile, index) => [
          tile.coordinate,
          {
            ActionID: actionIds[index],
            LinkedTitle: false,
            Name: "Monitor Tile",
            Settings: {
              tileId: tile.tileId,
              targetPath: tile.targetPath,
            },
            State: 0,
            States: [
              {
                FontFamily: "",
                FontSize: 9,
                FontStyle: "",
                FontUnderline: false,
                OutlineThickness: 2,
                ShowTitle: false,
                TitleAlignment: "middle",
                TitleColor: "#ffffff",
              },
            ],
            UUID: "com.polyedge.streamdeck.monitor-tile",
          },
        ])
      ),
      Type: "Keypad",
    },
  ],
  Icon: "",
  Name: "PolyEdge Monitor",
};

async function main() {
  await rm(outputProfile, { force: true });

  const tempRoot = await mkdtemp(path.join(os.tmpdir(), "polyedge-streamdeck-profile-"));

  try {
    const profileRoot = path.join(tempRoot, rootProfileDir);
    const profilesRoot = path.join(profileRoot, "Profiles");
    const blankProfilePath = path.join(profilesRoot, blankPageDir, "Images");
    const mainProfilePath = path.join(profilesRoot, mainPageDir, "Images");

    await mkdir(blankProfilePath, { recursive: true });
    await mkdir(mainProfilePath, { recursive: true });

    await writeFile(
      path.join(profileRoot, "manifest.json"),
      JSON.stringify(rootManifest),
      "utf8"
    );
    await writeFile(
      path.join(profilesRoot, blankPageDir, "manifest.json"),
      JSON.stringify(blankPageManifest),
      "utf8"
    );
    await writeFile(
      path.join(profilesRoot, mainPageDir, "manifest.json"),
      JSON.stringify(mainPageManifest),
      "utf8"
    );

    await execFileAsync("zip", ["-qrX", outputProfile, rootProfileDir], {
      cwd: tempRoot,
    });
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
}

await main();
