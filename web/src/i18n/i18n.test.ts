import { describe, expect, it } from "vitest";

import { en } from "./en";
import { zhCN } from "./zh-CN";

describe("translations", () => {
  it("keeps English and Simplified Chinese resource keys in sync", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zhCN).sort());
  });
});
