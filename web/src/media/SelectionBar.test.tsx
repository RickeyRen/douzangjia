import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeItem } from "../test/fixtures";
import { makeAppData } from "../test/makeAppData";
import { MediaGrid } from "./MediaGrid";
import { SelectionBar } from "./SelectionBar";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  bulkStar: vi.fn(),
  archiveSelection: vi.fn(),
  bulkAddTags: vi.fn(),
  fetchTags: vi.fn(),
}));

const items = ["701", "702", "703", "704"].map((id) => makeItem({ awemeId: `70000000000000000${id.slice(1)}`, description: `作品 ${id}` }));

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it("toggles tiles in selection mode and extends ranges with shift", () => {
  const onToggleSelect = vi.fn();
  render(<MediaGrid items={items} loading={false} onOpen={vi.fn()} selected={new Set([items[0].awemeId])} onToggleSelect={onToggleSelect} />);

  expect(screen.getByRole("button", { name: "取消选择：作品 701" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "选择：作品 703" }), { shiftKey: true });

  expect(onToggleSelect).toHaveBeenCalledWith(2, true);
});

it("stars the selection and queues the ones missing from the NAS", async () => {
  vi.mocked(api.bulkStar).mockResolvedValue({ starred: [items[0].awemeId, items[1].awemeId] });
  vi.mocked(api.archiveSelection).mockResolvedValue({ skipped: 1, batch: { id: 1, kind: "selection", targetId: "sel", status: "queued" } });
  const user = userEvent.setup();
  const onItemsPatched = vi.fn();
  const onClear = vi.fn();
  const mixed = [items[0], { ...items[1], local: { ...items[1].local, state: "waiting" as const } }];
  render(
    <WithAppData value={makeAppData()}>
      <SelectionBar items={mixed} selected={new Set(mixed.map((item) => item.awemeId))} onSelectAll={vi.fn()} onClear={onClear} onItemsPatched={onItemsPatched} />
    </WithAppData>,
  );

  await user.click(screen.getByRole("button", { name: "精选" }));
  await waitFor(() => expect(api.bulkStar).toHaveBeenCalledWith([mixed[0].awemeId, mixed[1].awemeId], true));
  expect(onItemsPatched).toHaveBeenCalledWith([mixed[0].awemeId, mixed[1].awemeId], { starred: true });

  await user.click(screen.getByRole("button", { name: "存到 NAS (1)" }));
  await waitFor(() => expect(api.archiveSelection).toHaveBeenCalledWith([mixed[0].awemeId, mixed[1].awemeId]));
  expect(onItemsPatched).toHaveBeenLastCalledWith([mixed[1].awemeId], expect.objectContaining({ local: expect.objectContaining({ state: "waiting" }) }));

  fireEvent.keyDown(window, { key: "Escape" });
  expect(onClear).toHaveBeenCalled();
});

it("exports only the selected works that are already on the NAS", () => {
  const mixed = [items[0], items[1], { ...items[2], local: { ...items[2].local, state: "waiting" as const } }];
  render(
    <WithAppData value={makeAppData()}>
      <SelectionBar items={mixed} selected={new Set(mixed.map((item) => item.awemeId))} onSelectAll={vi.fn()} onClear={vi.fn()} onItemsPatched={vi.fn()} />
    </WithAppData>,
  );

  expect(screen.getByRole("link", { name: "导出 (2)" })).toHaveAttribute("href", `/api/export?items=${items[0].awemeId},${items[1].awemeId}`);
});

it("keeps export disabled until something is on the NAS", () => {
  const waiting = [{ ...items[0], local: { ...items[0].local, state: "waiting" as const } }];
  render(
    <WithAppData value={makeAppData()}>
      <SelectionBar items={waiting} selected={new Set([waiting[0].awemeId])} onSelectAll={vi.fn()} onClear={vi.fn()} onItemsPatched={vi.fn()} />
    </WithAppData>,
  );

  expect(screen.getByRole("button", { name: "导出" })).toBeDisabled();
});

it("tags the whole selection with a known or new tag and patches each tile", async () => {
  vi.mocked(api.fetchTags).mockResolvedValue({ items: [{ tag: "做饭", itemCount: 4 }, { tag: "周末", itemCount: 2 }] });
  vi.mocked(api.bulkAddTags).mockResolvedValue({
    added: 2,
    tags: { [items[0].awemeId]: ["周末", "做饭"], [items[1].awemeId]: ["做饭"] },
  });
  const user = userEvent.setup();
  const onItemsPatched = vi.fn();
  const two = [items[0], items[1]];
  render(
    <WithAppData value={makeAppData()}>
      <SelectionBar items={two} selected={new Set(two.map((item) => item.awemeId))} onSelectAll={vi.fn()} onClear={vi.fn()} onItemsPatched={onItemsPatched} />
    </WithAppData>,
  );

  await user.click(screen.getByRole("button", { name: "加标签" }));
  expect(await screen.findByRole("dialog", { name: "加标签" })).toHaveTextContent("给 2 个作品加标签");
  await user.click(await screen.findByRole("button", { name: /做饭/ }));

  await waitFor(() => expect(api.bulkAddTags).toHaveBeenCalledWith([two[0].awemeId, two[1].awemeId], ["做饭"]));
  expect(onItemsPatched).toHaveBeenCalledWith([two[0].awemeId], { tags: ["周末", "做饭"] });
  expect(onItemsPatched).toHaveBeenCalledWith([two[1].awemeId], { tags: ["做饭"] });
  expect(screen.queryByRole("dialog", { name: "加标签" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "加标签" }));
  await user.type(await screen.findByRole("textbox", { name: "新标签" }), "#想去{Enter}");
  await waitFor(() => expect(api.bulkAddTags).toHaveBeenLastCalledWith([two[0].awemeId, two[1].awemeId], ["想去"]));
});
