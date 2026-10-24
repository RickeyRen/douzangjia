import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { makeItem } from "../test/fixtures";
import { FeedBrowser } from "./FeedBrowser";

vi.mock("../app/api", async (original) => ({ ...(await original<typeof api>()), fetchFeed: vi.fn() }));

beforeEach(() => {
  vi.mocked(api.fetchFeed).mockReset();
  vi.mocked(api.fetchFeed).mockResolvedValue({ items: [makeItem()], nextCursor: null });
});
afterEach(cleanup);

it("turns toolbar choices into filters and feed queries", async () => {
  const user = userEvent.setup();
  const onFiltersChange = vi.fn();
  const base = { sourceId: "account:likes" };
  const { rerender } = render(
    <WithAppData value={makeAppData()}>
      <FeedBrowser base={base} filters={{}} sorts={["source", "published"]} onFiltersChange={onFiltersChange} />
    </WithAppData>,
  );
  await waitFor(() => expect(api.fetchFeed).toHaveBeenCalledWith(expect.objectContaining({ sourceId: "account:likes", sort: "source" })));

  await user.click(screen.getByRole("button", { name: "图集" }));
  await user.click(screen.getByRole("button", { name: "仅看已存到 NAS" }));
  await user.selectOptions(screen.getByLabelText("排序方式"), "published");

  expect(onFiltersChange).toHaveBeenNthCalledWith(1, { type: "gallery" });
  expect(onFiltersChange).toHaveBeenNthCalledWith(2, { downloaded: true });
  expect(onFiltersChange).toHaveBeenNthCalledWith(3, { sort: "published" });

  rerender(
    <WithAppData value={makeAppData()}>
      <FeedBrowser base={base} filters={{ type: "gallery", downloaded: true, sort: "published" }} sorts={["source", "published"]} onFiltersChange={onFiltersChange} />
    </WithAppData>,
  );
  await waitFor(() =>
    expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ sourceId: "account:likes", sort: "published", type: "gallery", downloaded: true })),
  );
});

it("offers to clear filters when nothing matches", async () => {
  vi.mocked(api.fetchFeed).mockResolvedValue({ items: [], nextCursor: null });
  const user = userEvent.setup();
  const onFiltersChange = vi.fn();
  render(
    <WithAppData value={makeAppData()}>
      <FeedBrowser base={{}} filters={{ type: "video", sort: "published" }} sorts={["archived", "published"]} onFiltersChange={onFiltersChange} />
    </WithAppData>,
  );

  await user.click(await screen.findByRole("button", { name: "清除筛选" }));

  expect(onFiltersChange).toHaveBeenCalledWith({ sort: "published" });
});
