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
