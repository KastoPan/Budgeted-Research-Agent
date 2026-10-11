import {
  formatDuration,
  formatNumber,
  formatTimestamp,
  parseTimestamp,
  shortRunId,
} from "./format";

describe("format helpers", () => {
  it("formats budget values for the dashboard", () => {
    expect(formatNumber(50_000)).toBe("50,000");
    expect(formatDuration(0.25)).toBe("250 ms");
    expect(formatDuration(75)).toBe("1m 15s");
  });

  it("uses a stable short run identifier", () => {
    expect(shortRunId("89933ea9-61ee-4e98-b7ad-aaad1b8e7329")).toBe("89933ea9");
  });

  it("treats timezone-free backend timestamps as UTC and displays Beijing time", () => {
    const timestamp = "2026-10-08T08:30:00";

    expect(parseTimestamp(timestamp).toISOString()).toBe(
      "2026-10-08T08:30:00.000Z",
    );
    expect(formatTimestamp(timestamp)).toContain("16:30");
  });
});
