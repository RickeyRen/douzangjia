import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { LocalLoginPage } from "./LocalLoginPage";
import { OwnerMigrationPage } from "./OwnerMigrationPage";
import { SetupPage } from "../setup/SetupPage";

vi.mock("../../app/api", async (importOriginal) => ({
  ...(await importOriginal<typeof api>()),
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

it("focuses the username field so sign-in starts with typing", () => {
  renderPage(<LocalLoginPage onComplete={vi.fn()} />);

  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "用户名" }));
});

it("explains a sign-in lockout with the time left to wait", async () => {
  vi.mocked(api.loginAdmin).mockRejectedValue(
    new api.ApiError(429, "TOO_MANY_ATTEMPTS", "locked", { retryAfterSeconds: 30 }),
  );
  const user = userEvent.setup();
  renderPage(<LocalLoginPage onComplete={vi.fn()} />);

  await user.type(screen.getByRole("textbox", { name: "用户名" }), "RENJIAWEI");
  await user.type(screen.getByLabelText("密码"), "wrong password");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(screen.getByRole("alert")).toHaveTextContent("请 30 秒后再试");
});

it("distinguishes a wrong password from an unreachable server", async () => {
  vi.mocked(api.loginAdmin).mockRejectedValueOnce(
    new api.ApiError(401, "INVALID_CREDENTIALS", "用户名或密码不正确"),
  );
  const user = userEvent.setup();
  renderPage(<LocalLoginPage onComplete={vi.fn()} />);

  await user.type(screen.getByRole("textbox", { name: "用户名" }), "RENJIAWEI");
  await user.type(screen.getByLabelText("密码"), "wrong password");
  await user.click(screen.getByRole("button", { name: "登录" }));
  expect(screen.getByRole("alert")).toHaveTextContent("用户名或密码不正确");

  vi.mocked(api.loginAdmin).mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await user.type(screen.getByLabelText("密码"), "x");
  expect(screen.queryByRole("alert")).toBeNull();
  await user.click(screen.getByRole("button", { name: "登录" }));
  expect(screen.getByRole("alert")).toHaveTextContent("连不上抖藏家服务");
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
