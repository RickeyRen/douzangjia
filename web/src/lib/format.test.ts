import { expect, it } from "vitest";

import { formatBytes, formatCount, formatDuration, formatRelative } from "./format";

it("formats Chinese counts, sizes and durations", () => {
  expect(formatCount(9_999)).toBe("9,999");
  expect(formatCount(153_000)).toBe("15.3 万");
  expect(formatCount(1_200_000_000)).toBe("12 亿");
  expect(formatBytes(6_429_035_725)).toBe("6.0 GB");
  expect(formatBytes(0)).toBe("0 B");
  expect(formatDuration(14_400)).toBe("0:14");
  expect(formatDuration(3_725_000)).toBe("1:02:05");
  expect(formatDuration(null)).toBeNull();
});

it("describes how long ago something happened", () => {
  const now = Date.UTC(2026, 9, 24, 12) ;
  const seconds = now / 1000;
  expect(formatRelative(seconds - 10, now)).toBe("刚刚");
  expect(formatRelative(seconds - 300, now)).toBe("5 分钟前");
  expect(formatRelative(seconds - 29 * 86_400, now)).toBe("29 天前");
  expect(formatRelative(null, now)).toBe("从未");
});
