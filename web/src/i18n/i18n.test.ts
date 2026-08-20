import { describe, expect, it } from "vitest";

import { en } from "./en";
import { zhCN } from "./zh-CN";

describe("translations", () => {
  it("keeps English and Simplified Chinese resource keys in sync", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhCN).sort());
  });

  it("uses the DouZangJia product identity in both supported languages", () => {
    expect(zhCN.brand).toBe("抖藏家");
    expect(zhCN.brandSubtitle).toBe("抖音私人收藏库");
    expect(en.brand).toBe("DouZangJia");
    expect(en.brandSubtitle).toBe("Private Douyin collection library");
  });
});
