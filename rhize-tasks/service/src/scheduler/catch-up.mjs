export function evaluateCatchUp({lastCompletedAt, now = new Date().toISOString(), intervalMinutes = 15}) {
  if (!Number.isInteger(intervalMinutes) || intervalMinutes < 1) throw new TypeError('intervalMinutes must be a positive integer');
  if (lastCompletedAt === null || lastCompletedAt === undefined) return {shouldRun: true, catchUp: true, missedCount: 1};
  const elapsed = Date.parse(now) - Date.parse(lastCompletedAt);
  if (!Number.isFinite(elapsed) || elapsed < 0) throw new TypeError('catch-up timestamps are invalid');
  const missedCount = Math.floor(elapsed / (intervalMinutes * 60000));
  return missedCount < 1 ? {shouldRun: false, catchUp: false, missedCount: 0} : {shouldRun: true, catchUp: true, missedCount};
}
