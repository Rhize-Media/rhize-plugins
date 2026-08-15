export function evaluateCatchUp({lastCompletedAt, now = new Date().toISOString(), intervalMinutes = 15}) {
  if (!Number.isInteger(intervalMinutes) || intervalMinutes < 1) throw new TypeError('intervalMinutes must be a positive integer');
  if (lastCompletedAt === null || lastCompletedAt === undefined) return {shouldRun: true, catchUp: true, missedCount: 1};
  const elapsed = Date.parse(now) - Date.parse(lastCompletedAt);
  if (!Number.isFinite(elapsed) || elapsed < 0) throw new TypeError('catch-up timestamps are invalid');
  const missedCount = Math.floor(elapsed / (intervalMinutes * 60000));
  return missedCount < 1 ? {shouldRun: false, catchUp: false, missedCount: 0} : {shouldRun: true, catchUp: true, missedCount};
}

const phases = [['morning', 'morningTime'], ['midday', 'middayTime'], ['evening', 'eveningTime']];

function parts(value, timeZone) {
  return Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(value).filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
}

export function localDate(value, timeZone) {
  const valueParts = parts(value, timeZone);
  return `${valueParts.year}-${valueParts.month}-${valueParts.day}`;
}

function addDays(date, count) {
  const [year, month, day] = date.split('-').map(Number); const shifted = new Date(Date.UTC(year, month - 1, day + count));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}-${String(shifted.getUTCDate()).padStart(2, '0')}`;
}

export function scheduledInstant(date, time, timeZone) {
  const [year, month, day] = date.split('-').map(Number); const [hour, minute] = time.split(':').map(Number);
  const desired = Date.UTC(year, month - 1, day, hour, minute); let candidate = desired;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const observed = parts(new Date(candidate), timeZone);
    const represented = Date.UTC(Number(observed.year), Number(observed.month) - 1, Number(observed.day), Number(observed.hour), Number(observed.minute));
    candidate += desired - represented;
  }
  const result = new Date(candidate); const check = parts(result, timeZone);
  if (`${check.year}-${check.month}-${check.day}` !== date || `${check.hour}:${check.minute}` !== time) throw new TypeError('scheduled local time does not exist');
  return result.toISOString();
}

export function selectDuePhase({profile, lastRuns = {}, now = new Date()}) {
  const timeZone = profile?.identity?.timezone; const routines = profile?.routines;
  if (typeof timeZone !== 'string' || !routines) throw new TypeError('invalid routine profile');
  const today = localDate(now, timeZone); const candidates = [];
  for (const date of [addDays(today, -1), today]) for (const [phase, key] of phases) {
    const dueAt = scheduledInstant(date, routines[key], timeZone);
    if (Date.parse(dueAt) > now.getTime()) continue;
    const last = lastRuns[phase]; if (typeof last === 'string' && Date.parse(last) >= Date.parse(dueAt)) continue;
    candidates.push({phase, dueAt});
  }
  candidates.sort((left, right) => Date.parse(right.dueAt) - Date.parse(left.dueAt));
  return candidates[0] ? {shouldRun: true, catchUp: true, ...candidates[0], missedCount: candidates.length, covered: candidates.map(item => ({...item}))} : {shouldRun: false, catchUp: false, phase: null, dueAt: null, missedCount: 0, covered: []};
}
