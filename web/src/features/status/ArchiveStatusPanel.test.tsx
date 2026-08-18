import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ArchiveStatusPanel } from "./ArchiveStatusPanel";

vi.mock("../../app/api", () => ({
  fetchJobs: vi.fn(),
  fetchStatus: vi.fn(),
  fetchSyncRuns: vi.fn(),
  triggerSync: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(api.fetchJobs).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchSyncRuns).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchStatus).mockResolvedValue({ configured: true, authenticated: true, douyinAuthenticated: true });
  vi.mocked(api.triggerSync).mockResolvedValue({ runId: 41 });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("refreshes activity while open and stops after unmount", async () => {
  vi.useFakeTimers();
  const view = render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);
  await act(async () => undefined);
  expect(api.fetchJobs).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);

  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);
});

it("switches between download and sync activity", async () => {
  const user = userEvent.setup();
  render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);

  const downloads = await screen.findByRole("tab", { name: "下载" });
  const sync = screen.getByRole("tab", { name: "同步" });
  expect(downloads).toHaveAttribute("aria-selected", "true");
  await user.click(sync);
  expect(sync).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "立即全量同步" })).toBeVisible();
});
