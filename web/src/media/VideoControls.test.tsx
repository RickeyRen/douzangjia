import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { formatClock } from "../lib/format";
import { VideoControls } from "./VideoControls";

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("formats clocks like a player", () => {
  expect(formatClock(0)).toBe("0:00");
  expect(formatClock(75.9)).toBe("1:15");
  expect(formatClock(3725)).toBe("1:02:05");
  expect(formatClock(Number.NaN)).toBe("0:00");
});

it("toggles playback and reflects the video clock", () => {
  const ref = createRef<HTMLVideoElement>();
  render(
    <div>
      <video ref={ref} />
      <VideoControls videoRef={ref} muted={false} onToggleMute={vi.fn()} />
    </div>,
  );
  const video = ref.current!;
  Object.defineProperty(video, "duration", { value: 120, configurable: true });
  Object.defineProperty(video, "paused", { value: true, configurable: true, writable: true });
  video.currentTime = 30;
  fireEvent(video, new Event("loadedmetadata"));

  expect(screen.getByRole("slider", { name: "播放进度" })).toHaveAttribute("aria-valuetext", "0:30 / 2:00");
  fireEvent.click(screen.getByRole("button", { name: "播放" }));
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
});
