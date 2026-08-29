import { expect, it } from "vitest";

import { formatDelta, formatLoadAverage, formatRuntimeStatus } from "./dashboardFormat";

it("formats a real byte comparison without hiding its direction", () => {
  expect(formatDelta(1024, true, "数据积累中")).toBe("+1.0 KB");
  expect(formatDelta(-2048, true, "数据积累中")).toBe("-2.0 KB");
});

it("does not invent a comparison before enough history exists", () => {
  expect(formatDelta(1024, false, "数据积累中")).toBe("数据积累中");
});

it("keeps all three load-average windows visible", () => {
  expect(formatLoadAverage(0.74, 0.62, 0.58)).toBe("0.74 / 0.62 / 0.58");
});

it("maps runtime states to user-facing translated labels", () => {
  const labels = {
    running: "运行中",
    busy: "忙碌",
    unavailable: "不可用",
  };
  expect(formatRuntimeStatus("busy", labels)).toBe("忙碌");
  expect(formatRuntimeStatus("unknown", labels)).toBe("不可用");
});
