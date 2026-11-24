import { describe, expect, it } from "vitest";

import { decMul, inr, localToday, toPaise } from "./format.js";

describe("toPaise", () => {
  it("parses rupees exactly", () => {
    expect(toPaise("1200")).toBe(120000);
    expect(toPaise("600.5")).toBe(60050);
    expect(toPaise("₹1,200.05")).toBe(120005);
  });
  it("rejects bad input", () => {
    expect(toPaise("12.345")).toBeNull();
    expect(toPaise("-5")).toBeNull();
    expect(toPaise("abc")).toBeNull();
  });
});

describe("decMul", () => {
  it("is exact where floats are not", () => {
    expect(decMul("1.2", "3")).toBe("3.6");
    expect(decMul("40000.000", "0.001")).toBe("40");
    expect(decMul("10500", "0.001")).toBe("10.5");
    expect(decMul("200", "1")).toBe("200");
  });
});

describe("localToday / inr", () => {
  it("uses the local calendar date", () => {
    expect(localToday(new Date(2026, 10, 24, 1, 0))).toBe("2026-11-24");
  });
  it("formats Indian grouping", () => {
    expect(inr(787500)).toBe("₹7,875.00");
  });
});
