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

it("cycles playback speed, applies it to the video and remembers it", () => {
  window.localStorage.clear();
  const ref = createRef<HTMLVideoElement>();
  const { unmount } = render(
    <div>
      <video ref={ref} />
      <VideoControls videoRef={ref} muted={false} onToggleMute={vi.fn()} />
    </div>,
  );
  const video = ref.current!;
  expect(video.playbackRate).toBe(1);
  fireEvent.click(screen.getByRole("button", { name: /播放速度 1×/ }));
  expect(video.playbackRate).toBe(1.25);
  fireEvent.click(screen.getByRole("button", { name: /播放速度 1.25×/ }));
  expect(video.playbackRate).toBe(1.5);
  expect(screen.getByRole("button", { name: /播放速度 1.5×/ })).toHaveTextContent("1.5×");
  // A new source resets the rate in real browsers; the choice must come back.
  video.playbackRate = 1;
  fireEvent(video, new Event("loadedmetadata"));
  expect(video.playbackRate).toBe(1.5);
  unmount();

  // The next video opens at the speed picked last time.
  const next = createRef<HTMLVideoElement>();
  render(
    <div>
      <video ref={next} />
      <VideoControls videoRef={next} muted={false} onToggleMute={vi.fn()} />
    </div>,
  );
  expect(next.current!.playbackRate).toBe(1.5);
  for (let i = 0; i < 3; i += 1) fireEvent.click(screen.getByRole("button", { name: /播放速度/ }));
  expect(next.current!.playbackRate).toBe(1);
  expect(screen.getByRole("button", { name: /播放速度/ })).toHaveTextContent("倍速");
  expect(window.localStorage.getItem("douzangjia.speed.v1")).toBeNull();
});

it("steps speed with < and > and stops at the ends", () => {
  window.localStorage.clear();
  const ref = createRef<HTMLVideoElement>();
  render(
    <div>
      <video ref={ref} />
      <VideoControls videoRef={ref} muted={false} onToggleMute={vi.fn()} />
    </div>,
  );
  const video = ref.current!;
  fireEvent.keyDown(window, { key: ">" });
  expect(video.playbackRate).toBe(1.25);
  for (let press = 0; press < 5; press += 1) fireEvent.keyDown(window, { key: ">" });
  expect(video.playbackRate).toBe(2);
  for (let press = 0; press < 9; press += 1) fireEvent.keyDown(window, { key: "<" });
  expect(video.playbackRate).toBe(0.75);
  expect(window.localStorage.getItem("douzangjia.speed.v1")).toBe("0.75");
});
