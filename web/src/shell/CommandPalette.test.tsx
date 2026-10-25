import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { CommandPalette } from "./CommandPalette";

vi.mock("../app/api", async (original) => ({ ...(await original<typeof api>()), fetchCreators: vi.fn() }));

const album: api.Album = { id: 3, name: "旅行参考", itemCount: 12, createdAt: 1, updatedAt: 1, lastAddedAt: null, covers: [] };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchCreators).mockResolvedValue({ items: [], nextCursor: null });
  window.location.hash = "#/";
});
afterEach(cleanup);

it("filters pages and albums, then navigates with the keyboard", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  render(
    <WithAppData value={makeAppData({ albums: [album] })}>
      <CommandPalette onClose={onClose} />
    </WithAppData>,
  );

  await user.type(screen.getByLabelText("跳转或搜索"), "旅行");
  await waitFor(() => expect(screen.getByRole("option", { name: /旅行参考/ })).toBeInTheDocument());
  expect(screen.queryByRole("option", { name: /^首页/ })).toBeNull();
  await user.keyboard("{Enter}");

  expect(onClose).toHaveBeenCalled();
  expect(window.location.hash).toBe("#/album/3");
});

it("offers a full-text search for unknown terms", async () => {
  const user = userEvent.setup();
  render(
    <WithAppData value={makeAppData()}>
      <CommandPalette onClose={vi.fn()} />
    </WithAppData>,
  );

  await user.type(screen.getByLabelText("跳转或搜索"), "番茄炒蛋");
  await user.click(await screen.findByRole("option", { name: /搜索“番茄炒蛋”/ }));

  expect(window.location.hash).toBe("#/search?q=%E7%95%AA%E8%8C%84%E7%82%92%E8%9B%8B");
});
