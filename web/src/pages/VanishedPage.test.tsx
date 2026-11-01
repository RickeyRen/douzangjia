import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { VanishedPage } from "./VanishedPage";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  fetchVanishedCreators: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const creator = (values: Partial<api.Creator> = {}): api.Creator => ({
  id: "c1",
  nickname: "乐酷",
  uniqueId: "49855631198",
  avatarUrl: "/api/creators/c1/avatar",
  followerCount: 0,
  postCount: 0,
  knownItemCount: 12,
  archivedItemCount: 9,
  lastSeenAt: 1,
  subscription: null,
  archive: {
    status: "reset",
    since: 1_793_000_000,
    checkedAt: 1_793_000_000,
    currentNickname: "49855631198",
    currentAvatarUrl: null,
    preserved: null,
  },
  ...values,
});

it("shows each removed creator under the name they chose, with what Douyin shows now", async () => {
  vi.mocked(api.fetchVanishedCreators).mockResolvedValue({ items: [creator()], nextCursor: null, counts: { reset: 1 } });
  render(
    <WithAppData value={makeAppData()}>
      <VanishedPage />
    </WithAppData>,
  );

  expect(await screen.findByText("乐酷")).toBeTruthy();
  expect(screen.getByText("现在显示为 49855631198")).toBeTruthy();
  expect(screen.getByText("资料被重置")).toBeTruthy();
  expect(screen.getByText("12 个作品 · 已存 9")).toBeTruthy();
  expect(screen.getByRole("link").getAttribute("href")).toBe("#/creator/c1");
});

it("explains the background check when nothing has vanished yet", async () => {
  vi.mocked(api.fetchVanishedCreators).mockResolvedValue({ items: [], nextCursor: null, counts: {} });
  render(
    <WithAppData value={makeAppData()}>
      <VanishedPage />
    </WithAppData>,
  );

  expect(await screen.findByText("还没有发现消失的博主")).toBeTruthy();
});
