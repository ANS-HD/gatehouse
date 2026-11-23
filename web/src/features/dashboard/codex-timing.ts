import type { CodexSessionDetail } from "./schemas";

type Turn = CodexSessionDetail["turns"][number];

function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const result = Date.parse(value);
  return Number.isFinite(result) ? result : null;
}

export function elapsedMs(start: string | null | undefined, end: string | null | undefined): number | null {
  const first = timestamp(start);
  const last = timestamp(end);
  return first !== null && last !== null && last >= first ? last - first : null;
}

export function formatElapsed(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) return "未记录";
  if (value > 0 && value < 1000) return `${Math.round(value)} 毫秒`;
  let seconds = Math.floor(value / 1000);
  const parts: string[] = [];
  for (const [unit, size] of [["天", 86400], ["小时", 3600], ["分", 60]] as const) {
    const count = Math.floor(seconds / size);
    if (count) parts.push(`${count} ${unit}`);
    seconds %= size;
  }
  if (seconds || !parts.length) parts.push(`${seconds} 秒`);
  return parts.join(" ");
}

export function formatLogTime(value: string | null | undefined): string {
  const instant = timestamp(value);
  return instant === null ? "未记录" : new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(instant);
}

export function formatTurnOffset(start: string | null, value: string | null): string | null {
  const first = timestamp(start);
  const last = timestamp(value);
  if (first === null || last === null) return null;
  return `${last < first ? "−" : "+"}${formatElapsed(Math.abs(last - first))}`;
}

export function turnTiming(turn: Turn) {
  let endedAt = turn.ended_at;
  if (turn.status !== "completed" && (elapsedMs(turn.started_at, endedAt) ?? 0) === 0) {
    // Older imports used the start time as the end of incomplete turns.
    // Use the latest recorded event, never the current wall clock.
    const candidates = [turn.started_at, turn.ended_at, ...turn.events.flatMap((event) => [event.timestamp, event.ended_at])];
    const latest = candidates.filter((value): value is string => timestamp(value) !== null)
      .sort((a, b) => timestamp(b)! - timestamp(a)!)[0];
    endedAt = latest ?? null;
  }
  return {
    startedAt: turn.started_at,
    endedAt,
    durationMs: elapsedMs(turn.started_at, endedAt),
    partial: turn.status !== "completed",
  };
}
