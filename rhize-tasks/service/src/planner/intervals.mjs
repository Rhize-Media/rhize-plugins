import {isoDateTime, realDate} from '../domain.mjs';

const PROTECTED_KEYS = new Set(['id', 'start', 'end', 'kind', 'sourceSystem', 'mutable']);
const PROTECTED_KINDS = new Set(['fixed', 'outside', 'break', 'manual_lock', 'freeze']);
const SOURCE_SYSTEMS = new Set(['calendar', 'reminders', 'local']);

function timestamp(value) {
  isoDateTime(value, 'interval time');
  return Date.parse(value);
}

function localParts(instant, timeZone) {
  const values = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(instant)).filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function zonedInstant(date, time, timeZone) {
  const desired = `${date}T${time}`;
  const naive = Date.parse(`${desired}:00.000Z`);
  if (timeZone === 'UTC') return new Date(naive).toISOString();
  const matches = [];
  for (let instant = naive - 50400000; instant <= naive + 50400000; instant += 60000) if (localParts(instant, timeZone) === desired) matches.push(instant);
  if (matches.length !== 1) throw new RangeError(`${desired} is nonexistent or ambiguous in ${timeZone}`);
  return new Date(matches[0]).toISOString();
}

function canonical(start, end) { return {start: new Date(start).toISOString(), end: new Date(end).toISOString()}; }

export function normalizeIntervals(intervals) {
  const sorted = [...intervals].map(interval => canonical(timestamp(interval.start), timestamp(interval.end))).sort((left, right) => timestamp(left.start) - timestamp(right.start));
  return sorted.reduce((merged, interval) => {
    const last = merged.at(-1);
    if (last && timestamp(interval.start) <= timestamp(last.end)) {
      if (timestamp(interval.end) > timestamp(last.end)) last.end = interval.end;
    } else merged.push(interval);
    return merged;
  }, []);
}

export function materializeWorkingIntervals(profile, planningDate, intervals = profile.workingIntervals) {
  realDate(planningDate, 'planningDate');
  const day = new Date(`${planningDate}T00:00:00.000Z`).getUTCDay() || 7;
  return normalizeIntervals(intervals.filter(interval => interval.dayOfWeek === day).map(interval => ({
    start: zonedInstant(planningDate, interval.start, profile.identity.timezone),
    end: zonedInstant(planningDate, interval.end, profile.identity.timezone),
  })));
}

export function overlaps(left, right) {
  return timestamp(left.start) < timestamp(right.end) && timestamp(right.start) < timestamp(left.end);
}

export function totalMinutes(intervals) {
  const milliseconds = normalizeIntervals(intervals).reduce((total, interval) => total + timestamp(interval.end) - timestamp(interval.start), 0);
  return Math.floor(milliseconds / 60000);
}

export function assertProtectedIntervals(intervals) {
  if (!Array.isArray(intervals)) throw new TypeError('protectedIntervals must be an array');
  intervals.forEach((interval, index) => {
    if (interval === null || typeof interval !== 'object' || Array.isArray(interval) || Object.getPrototypeOf(interval) !== Object.prototype || Object.keys(interval).length !== PROTECTED_KEYS.size || Object.keys(interval).some(key => !PROTECTED_KEYS.has(key))) throw new TypeError(`protectedIntervals[${index}] must have exactly the protected interval keys`);
    if (typeof interval.id !== 'string' || !PROTECTED_KINDS.has(interval.kind) || !SOURCE_SYSTEMS.has(interval.sourceSystem) || interval.mutable !== false) throw new TypeError(`protectedIntervals[${index}] is invalid`);
    if (timestamp(interval.start) >= timestamp(interval.end)) throw new RangeError(`protectedIntervals[${index}] start must precede end`);
  });
  return intervals;
}

export function withMeetingBuffers(intervals, meetingBufferMinutes) {
  if (meetingBufferMinutes === 0) return intervals.map(interval => ({start: interval.start, end: interval.end}));
  const buffer = meetingBufferMinutes * 60000;
  return intervals.map(interval => interval.kind === 'fixed'
    ? canonical(timestamp(interval.start) - buffer, timestamp(interval.end) + buffer)
    : {start: interval.start, end: interval.end});
}

export function subtractIntervals(windows, protectedIntervals) {
  const cuts = normalizeIntervals(protectedIntervals);
  return normalizeIntervals(windows).flatMap(window => cuts.reduce((pieces, cut) => pieces.flatMap(piece => {
    if (!overlaps(piece, cut)) return [piece];
    const result = [];
    if (timestamp(piece.start) < timestamp(cut.start)) result.push(canonical(timestamp(piece.start), timestamp(cut.start)));
    if (timestamp(cut.end) < timestamp(piece.end)) result.push(canonical(timestamp(cut.end), timestamp(piece.end)));
    return result;
  }), [{...window}]).filter(piece => timestamp(piece.start) < timestamp(piece.end)));
}
