import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { AutoBackupSetting } from "./AutoBackupSetting";

afterEach(cleanup);

it("says when the database was last backed up and how many copies are kept", () => {
  const now = Math.floor(Date.now() / 1000);
  render(
    <WithAppData value={makeAppData()}>
      <AutoBackupSetting initial={{ directory: "data/backups", keep: 7, lastError: null, backups: [{ name: "auto-x.sqlite3", bytes: 1_057_595_392, createdAt: now - 7200 }] }} />
    </WithAppData>,
  );
  expect(screen.getByText(/最近一次 2 小时前.*保留最近 7 份.*data\/backups/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "立即备份" })).toBeEnabled();
});
