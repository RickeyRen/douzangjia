import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { LocalLoginPage } from "./LocalLoginPage";
import { OwnerMigrationPage } from "./OwnerMigrationPage";
import { SetupPage } from "../setup/SetupPage";

vi.mock("../../app/api", () => ({
  setupAdmin: vi.fn(),
  loginAdmin: vi.fn(),
  migrateOwner: vi.fn(),
}));

function renderPage(page: React.ReactNode) {
  return render(<ThemeProvider>{page}</ThemeProvider>);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it("creates the first administrator with a username and password", async () => {
  vi.mocked(api.setupAdmin).mockResolvedValue({ configured: true, username: "RENJIAWEI" });
  const completed = vi.fn();
  const user = userEvent.setup();
  renderPage(<SetupPage onComplete={completed} />);

  await user.type(screen.getByRole("textbox", { name: /^用户名/ }), "RENJIAWEI");
  const passwordFields = screen.getAllByLabelText(/密码/);
  await user.type(passwordFields[0], "a secure local passphrase");
  await user.type(passwordFields[1], "a secure local passphrase");
  await user.click(screen.getByRole("button", { name: "创建资料库" }));

  expect(api.setupAdmin).toHaveBeenCalledWith("RENJIAWEI", "a secure local passphrase");
  expect(completed).toHaveBeenCalledOnce();
});

it("logs in using both username and password", async () => {
  vi.mocked(api.loginAdmin).mockResolvedValue({ authenticated: true, username: "RENJIAWEI" });
  const completed = vi.fn();
  const user = userEvent.setup();
  renderPage(<LocalLoginPage onComplete={completed} />);

  await user.type(screen.getByRole("textbox", { name: "用户名" }), "RENJIAWEI");
  await user.type(screen.getByLabelText("密码"), "a secure local passphrase");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(api.loginAdmin).toHaveBeenCalledWith("RENJIAWEI", "a secure local passphrase");
  expect(completed).toHaveBeenCalledOnce();
});

it("migrates a legacy password only after verifying the existing password", async () => {
  vi.mocked(api.migrateOwner).mockResolvedValue({
    configured: true,
    authenticated: true,
    username: "RENJIAWEI",
  });
  const completed = vi.fn();
  const useExistingAccount = vi.fn();
  const user = userEvent.setup();
  renderPage(
    <OwnerMigrationPage
      onComplete={completed}
      onUseExistingAccount={useExistingAccount}
    />,
  );

  await user.type(screen.getByRole("textbox", { name: "新用户名" }), "RENJIAWEI");
  await user.type(screen.getByLabelText("当前密码"), "the original secure password");
  await user.click(screen.getByRole("button", { name: "升级本地账户" }));

  expect(api.migrateOwner).toHaveBeenCalledWith("RENJIAWEI", "the original secure password");
  expect(completed).toHaveBeenCalledOnce();

  await user.click(screen.getByRole("button", { name: "使用其他管理员账户登录" }));
  expect(useExistingAccount).toHaveBeenCalledOnce();
});
