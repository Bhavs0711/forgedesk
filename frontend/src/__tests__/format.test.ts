import { clock, duration, parseDate, sessionSeconds, usd } from "../lib/format";

describe("format", () => {
  it("treats naive timestamps as UTC", () => {
    expect(parseDate("2026-01-01T10:00:00").toISOString()).toBe("2026-01-01T10:00:00.000Z");
    expect(parseDate("2026-01-01T10:00:00+02:00").toISOString()).toBe("2026-01-01T08:00:00.000Z");
    expect(parseDate("2026-01-01T10:00:00Z").toISOString()).toBe("2026-01-01T10:00:00.000Z");
  });
  it("formats durations", () => {
    expect(duration(0)).toBe("0s");
    expect(duration(59.6)).toBe("1m 0s");
    expect(duration(75)).toBe("1m 15s");
    expect(duration(3720)).toBe("1h 2m");
  });
  it("formats money", () => {
    expect(usd(0.01234)).toBe("$0.0123");
    expect(usd(12.5)).toBe("$12.50");
  });
  it("computes session length, using now for open sessions", () => {
    const now = Date.parse("2026-01-01T10:01:00Z");
    expect(sessionSeconds({ started_at: "2026-01-01T10:00:00", ended_at: null }, now)).toBe(60);
    expect(sessionSeconds({ started_at: "2026-01-01T10:00:00", ended_at: "2026-01-01T10:00:30" })).toBe(30);
  });
  it("renders a clock string", () => expect(clock("2026-01-01T10:00:00Z")).toMatch(/\d{2}:\d{2}:\d{2}/));
});
