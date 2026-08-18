import { expect, it } from "vitest";

import { formatBytes, formatEta, formatSpeed } from "./downloadFormat";

it("formats byte progress and speed using binary units", () => {
  expect(formatBytes(15_429_894)).toBe("14.7 MB");
  expect(formatBytes(50_000_000)).toBe("47.7 MB");
  expect(formatSpeed(1_240_000)).toBe("1.2 MB/s");
});

it("formats short and long remaining times without fake precision", () => {
  expect(formatEta(28, "zh-CN")).toBe("约 28 秒");
  expect(formatEta(95, "zh-CN")).toBe("约 2 分钟");
  expect(formatEta(3_700, "zh-CN")).toBe("约 1 小时");
  expect(formatEta(null, "zh-CN")).toBe("—");
  expect(formatEta(28, "en")).toBe("about 28 sec");
});
