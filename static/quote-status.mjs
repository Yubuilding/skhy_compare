const ACTIVE_STATUSES = new Set(["OPEN", "REGULAR", "PRE", "PREPRE", "POST", "POSTPOST"]);
const ACTIVE_SESSIONS = new Set(["OVERNIGHT", "REGULAR", "PREMARKET", "AFTER_HOURS"]);
const CLOSED_STATUSES = new Set(["CLOSE", "CLOSED"]);

export function isLiveQuote(quote) {
  if (!quote?.isRealTime) return false;

  const status = String(quote.marketStatus || "").toUpperCase();
  const session = String(quote.session || "").toUpperCase();
  if (CLOSED_STATUSES.has(status)) return false;

  return ACTIVE_STATUSES.has(status) || ACTIVE_SESSIONS.has(session);
}
