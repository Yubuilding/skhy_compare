export async function waitForNewPublishedSnapshot({
  baselineFetchedAt,
  loadSnapshot,
  wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
  intervalMs = 5_000,
  maxAttempts = 24,
}) {
  const baselineTime = Date.parse(baselineFetchedAt || "");

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const snapshot = await loadSnapshot();
    const publishedTime = Date.parse(snapshot?.fetchedAt || "");
    if (Number.isFinite(publishedTime) && (
      !Number.isFinite(baselineTime) || publishedTime > baselineTime
    )) {
      return snapshot;
    }
    if (attempt < maxAttempts) await wait(intervalMs);
  }

  throw new Error("等待 GitHub Pages 发布新数据超时");
}
