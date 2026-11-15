import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { usePlaybackResume } from "./usePlaybackResume";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  fetchPlayback: vi.fn(),
  savePlayback: vi.fn(),
}));

function fakeVideo(duration: number) {
  const element = { duration, currentTime: 0, readyState: 1, ended: false, addEventListener: vi.fn() } as unknown as HTMLVideoElement;
  return { current: element as HTMLVideoElement | null };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.savePlayback).mockResolvedValue({ positionMs: null });
});

it("jumps to the saved spot of a long video and saves where it was left", async () => {
  vi.mocked(api.fetchPlayback).mockResolvedValue({ positionMs: 95_000 });
  const video = fakeVideo(600);
  const { result, rerender } = renderHook(({ current }) => usePlaybackResume("501", video, current, 600_000), {
    initialProps: { current: true },
  });

  await waitFor(() => expect(result.current.resumedAt).toBe(95_000));
  expect(video.current!.currentTime).toBe(95);

  video.current!.currentTime = 130;
  rerender({ current: false });
  expect(api.savePlayback).toHaveBeenLastCalledWith("501", 130_000, 600_000);
});

it("still saves when the player closes and React has already let go of the video", async () => {
  vi.mocked(api.fetchPlayback).mockResolvedValue({ positionMs: null });
  const video = fakeVideo(600);
  const element = video.current!;
  const { unmount } = renderHook(() => usePlaybackResume("504", video, true, 600_000));
  element.currentTime = 200;
  video.current = null;
  unmount();
  expect(api.savePlayback).toHaveBeenLastCalledWith("504", 200_000, 600_000);
});

it("start over clears the jump, and finishing tells the NAS to forget it", async () => {
  vi.mocked(api.fetchPlayback).mockResolvedValue({ positionMs: 95_000 });
  const video = fakeVideo(600);
  const { result } = renderHook(() => usePlaybackResume("502", video, true, 600_000));
  await waitFor(() => expect(result.current.resumedAt).toBe(95_000));

  act(() => result.current.restart());
  expect(video.current!.currentTime).toBe(0);
  expect(result.current.resumedAt).toBeNull();

  act(() => result.current.onEnded());
  expect(api.savePlayback).toHaveBeenLastCalledWith("502", 600_000, 600_000);
});

it("never asks about or saves short clips", () => {
  const video = fakeVideo(45);
  const { result, unmount } = renderHook(() => usePlaybackResume("503", video, true, 45_000));
  act(() => result.current.onPause());
  unmount();
  expect(api.fetchPlayback).not.toHaveBeenCalled();
  expect(api.savePlayback).not.toHaveBeenCalled();
});
