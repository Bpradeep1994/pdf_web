import { formatBytes, truncate, formatRelative, formatDate, cn } from "@/lib/utils";

describe("formatBytes", () => {
  it("formats zero and units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1048576)).toBe("1 MB");
  });
});

describe("truncate", () => {
  it("truncates long strings and leaves short ones", () => {
    expect(truncate("hello world", 5)).toBe("hello…");
    expect(truncate("hi", 5)).toBe("hi");
  });
});

describe("cn", () => {
  it("merges and drops falsy classes", () => {
    expect(cn("a", false && "b", "c")).toBe("a c");
    expect(cn("p-2", "p-4")).toBe("p-4"); // tailwind-merge dedupes
  });
});

describe("formatRelative / formatDate", () => {
  it("returns 'just now' for current time", () => {
    expect(formatRelative(new Date().toISOString())).toBe("just now");
  });
  it("formats an absolute date", () => {
    expect(formatDate("2026-01-15T00:00:00Z")).toMatch(/2026/);
  });
});
