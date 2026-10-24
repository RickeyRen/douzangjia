import { expect, it } from "vitest";

import { makeHealth } from "../test/fixtures";
import { describeHealth, errorSuffix } from "./health";

const now = Date.UTC(2026, 9, 24, 12);
const daysAgo = (days: number) => Math.round(now / 1000) - days * 86_400;

it("raises an alert for the month-long silent outage", () => {
  const view = describeHealth(makeHealth({ state: "stale", lastSuccessAt: daysAgo(29), lastErrorCode: "DOUYIN_RESPONSE_CHANGED" }), now);
  expect(view.alert).toBe(true);
  expect(view.tone).toBe("danger");
  expect(view.body).toContain("29 天前");
  expect(view.body).toContain("抖音页面结构有变化");
  expect(view.action).toBe("sync");
});

it("asks for a new QR login when the session expired", () => {
  const view = describeHealth(makeHealth({ state: "login_required" }), now);
  expect(view.action).toBe("login");
  expect(view.title).toContain("登录已失效");
});

it("stays quiet when everything is fine or a sync is running", () => {
  expect(describeHealth(makeHealth(), now).alert).toBe(false);
  expect(describeHealth(makeHealth({ state: "syncing" }), now).alert).toBe(false);
  expect(describeHealth(null, now).alert).toBe(false);
});

it("hides bookkeeping codes but explains real errors", () => {
  expect(errorSuffix("COUNT_UNKNOWN")).toBe("");
  expect(errorSuffix(null)).toBe("");
  expect(errorSuffix("COUNT_MISMATCH")).toContain("不一致");
  expect(errorSuffix("SOMETHING_NEW")).toBe(" · SOMETHING_NEW");
  expect(errorSuffix("DOUYIN_PAGE_CRASHED")).toContain("崩溃");
});
