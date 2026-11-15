import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { ReviewPage } from "./ReviewPage";

vi.mock("../app/api", async (original) => ({ ...(await original<typeof api>()), fetchReview: vi.fn() }));

afterEach(cleanup);

it("explains the first-time wait while the NAS builds the review", async () => {
  vi.mocked(api.fetchReview).mockResolvedValue({ state: "building" });
  render(<ReviewPage />);
  expect(await screen.findByText("第一次生成要一分钟左右，好了会自动显示。")).toBeInTheDocument();
});

it("shows monthly collecting, vanished works and favourite creators", async () => {
  vi.mocked(api.fetchReview).mockResolvedValue({
    builtAt: Math.floor(Date.now() / 1000) - 60,
    totals: { items: 120, saved: 90, since: 1_786_000_000 },
    firstMonth: "2026-08",
    months: [
      { month: "2026-08", added: 100, saved: 80 },
      { month: "2026-09", added: 20, saved: 10 },
    ],
    publishedYears: [{ year: "2025", count: 120 }],
    topCreators: [{ id: "c1", name: "露营的阿光", count: 30, vanished: 2, avatarUrl: null }],
    vanished: { total: 5, saved: 4, lost: 1 },
  });
  render(<ReviewPage />);

  expect(await screen.findByText(/你一共收藏了 120 个作品，90 个已经存到 NAS（75%）/)).toBeInTheDocument();
  expect(screen.getByText("首次导入")).toBeInTheDocument();
  expect(screen.getByText("幸好存下了 4 个")).toBeInTheDocument();
  expect(screen.getByText("没来得及存 1 个")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /露营的阿光/ })).toHaveAttribute("href", "#/creator/c1");
  expect(screen.getByText("2 个已消失")).toBeInTheDocument();
});
