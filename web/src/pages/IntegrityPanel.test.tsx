import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { IntegrityPanel } from "./IntegrityPanel";
import { axeViolations } from "../test/axe";

afterEach(cleanup);

const base = { totalFiles: 11_397, verifiedFiles: 3_200, allCheckedSince: null, lastCheckedAt: 1_800_000_000, repairingFiles: 0, repairedFiles: 0 };

it("shows how far the self-check has got", async () => {
  render(<IntegrityPanel initial={base} />);
  expect(screen.getByText("已检查 3,200 / 11,397 个文件")).toBeInTheDocument();
  expect(await axeViolations()).toEqual([]);
});

it("says everything is intact once every file was checked, and what it is repairing", () => {
  render(<IntegrityPanel initial={{ ...base, verifiedFiles: 11_397, allCheckedSince: 1_800_000_000, repairingFiles: 2, repairedFiles: 5 }} />);
  expect(screen.getByText("全部 11,397 个文件都完好")).toBeInTheDocument();
  expect(screen.getByText(/发现 2 个文件丢失或损坏，已经在重新下载/)).toBeInTheDocument();
  expect(screen.getByText("已自动补回 5 个文件。")).toBeInTheDocument();
});

it("says every file is there while contents are still being hashed", () => {
  render(<IntegrityPanel initial={{ ...base, presentFiles: 11_397, allPresentSince: 1_800_000_000 }} />);
  expect(screen.getByText("全部 11,397 个文件都在，内容已核对 3,200 个")).toBeInTheDocument();
});
