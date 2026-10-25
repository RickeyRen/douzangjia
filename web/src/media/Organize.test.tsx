import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeItem } from "../test/fixtures";
import { makeAppData } from "../test/makeAppData";
import { AlbumPicker, TagEditor } from "./Organize";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  addToAlbum: vi.fn(),
  removeFromAlbum: vi.fn(),
  createAlbum: vi.fn(),
  setItemTags: vi.fn(),
}));

const album = (id: number, name: string): api.Album => ({ id, name, itemCount: 3, createdAt: 1, updatedAt: 1, lastAddedAt: null, covers: [] });

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it("toggles membership and creates a new album inline", async () => {
  vi.mocked(api.addToAlbum).mockResolvedValue({ added: 1, album: album(1, "旅行") });
  vi.mocked(api.removeFromAlbum).mockResolvedValue({ removed: 1, album: album(2, "做饭") });
  vi.mocked(api.createAlbum).mockResolvedValue(album(9, "新的"));
  const appData = makeAppData({ albums: [album(1, "旅行"), album(2, "做饭")] });
  const onChange = vi.fn();
  const user = userEvent.setup();
  render(
    <WithAppData value={appData}>
      <AlbumPicker itemIds={["701"]} selected={[2]} onChange={onChange} onClose={vi.fn()} />
    </WithAppData>,
  );

  await user.click(screen.getByRole("button", { name: /旅行/ }));
  await user.click(screen.getByRole("button", { name: /做饭/ }));
  await user.click(screen.getByRole("button", { name: "新建相册" }));
  await user.type(screen.getByLabelText("新相册名称"), "新的{Enter}");

  await waitFor(() => expect(api.createAlbum).toHaveBeenCalledWith("新的"));
  expect(api.addToAlbum).toHaveBeenCalledWith(1, ["701"]);
  expect(api.removeFromAlbum).toHaveBeenCalledWith(2, ["701"]);
  expect(api.addToAlbum).toHaveBeenCalledWith(9, ["701"]);
  expect(onChange.mock.calls).toEqual([
    [1, true, "旅行"],
    [2, false, "做饭"],
    [9, true, "新的"],
  ]);
  expect(appData.refreshAlbums).toHaveBeenCalledTimes(3);
});

it("adds tags on enter, strips hashes and removes with backspace", async () => {
  vi.mocked(api.setItemTags).mockImplementation(async (_id, tags) => ({ tags }));
  const onChange = vi.fn();
  const user = userEvent.setup();
  const { rerender } = render(
    <WithAppData value={makeAppData()}>
      <TagEditor item={makeItem({ tags: [] })} onChange={onChange} />
    </WithAppData>,
  );

  await user.type(screen.getByLabelText("添加标签"), "#做饭{Enter}");
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(["做饭"]));
  rerender(
    <WithAppData value={makeAppData()}>
      <TagEditor item={makeItem({ tags: ["做饭"] })} onChange={onChange} />
    </WithAppData>,
  );
  expect(screen.getByText("#做饭")).toBeInTheDocument();

  fireEvent.keyDown(screen.getByLabelText("添加标签"), { key: "Backspace" });
  await waitFor(() => expect(api.setItemTags).toHaveBeenLastCalledWith(makeItem().awemeId, []));
});
