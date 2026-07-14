import assert from "node:assert/strict";
import test from "node:test";

import { waitForNewPublishedSnapshot } from "../static/admin-refresh.mjs";


test("waits until GitHub Pages publishes a snapshot newer than the baseline", async () => {
  const snapshots = [
    { fetchedAt: "2026-07-14T08:00:00Z" },
    { fetchedAt: "2026-07-14T08:05:00Z" },
  ];
  let waitCount = 0;

  const result = await waitForNewPublishedSnapshot({
    baselineFetchedAt: "2026-07-14T08:00:00Z",
    loadSnapshot: async () => snapshots.shift(),
    wait: async () => { waitCount += 1; },
    maxAttempts: 2,
  });

  assert.equal(result.fetchedAt, "2026-07-14T08:05:00Z");
  assert.equal(waitCount, 1);
});

test("stops polling when GitHub Pages never publishes a newer snapshot", async () => {
  let loadCount = 0;

  await assert.rejects(
    waitForNewPublishedSnapshot({
      baselineFetchedAt: "2026-07-14T08:00:00Z",
      loadSnapshot: async () => {
        loadCount += 1;
        return { fetchedAt: "2026-07-14T08:00:00Z" };
      },
      wait: async () => {},
      maxAttempts: 3,
    }),
    /发布新数据超时/,
  );

  assert.equal(loadCount, 3);
});
