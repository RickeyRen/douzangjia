import { describe, expect, it } from "vitest";

import { en } from "./en";
import { zhCN } from "./zh-CN";

describe("translations", () => {
  it("keeps English and Simplified Chinese resource keys in sync", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhCN).sort());
  });

  it("uses the Yingcang product identity in both supported languages", () => {
    expect(zhCN.brand).toBe("影仓");
    expect(zhCN.brandSubtitle).toBe("私人短视频媒体库");
    expect(en.brand).toBe("Yingcang");
    expect(en.brandSubtitle).toBe("Private short-video media library");
  });
});
