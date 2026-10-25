import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { _resetGridPrefs, useGridPrefs } from "./useGridPrefs";

beforeEach(() => {
  window.localStorage.clear();
  _resetGridPrefs();
});

it("persists density and aspect choices across hook instances", () => {
  const first = renderHook(() => useGridPrefs());
  expect(first.result.current[0]).toEqual({ density: "comfortable", aspect: "crop" });

  act(() => first.result.current[1]({ density: "compact" }));
  act(() => first.result.current[1]({ aspect: "natural" }));

  _resetGridPrefs();
  const second = renderHook(() => useGridPrefs());
  expect(second.result.current[0]).toEqual({ density: "compact", aspect: "natural" });
});

it("ignores garbage in storage", () => {
  window.localStorage.setItem("douzangjia.grid.v1", "{bad json");
  expect(renderHook(() => useGridPrefs()).result.current[0]).toEqual({ density: "comfortable", aspect: "crop" });
});
