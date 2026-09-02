import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";

import { I18nProvider } from "../../i18n/context";
import { AppShell } from "./AppShell";
import { PrimaryRail } from "./PrimaryRail";

afterEach(cleanup);

it("keeps navigation, content, and optional details in stable regions", () => {
  render(
    <AppShell
      primary={<button type="button">首页</button>}
      context={<nav>收藏分类</nav>}
      details={<aside>视频详情</aside>}
    >
      <main>实时归档</main>
    </AppShell>,
  );

  expect(screen.getByTestId("app-primary-rail")).toHaveTextContent("首页");
  expect(screen.getByTestId("app-context-rail")).toHaveTextContent("收藏分类");
  expect(screen.getByTestId("app-main-stage")).toHaveTextContent("实时归档");
  expect(screen.getByTestId("app-details-rail")).toHaveTextContent("视频详情");
});

it("opens top-level destinations from the compact primary rail", async () => {
  const opened: string[] = [];
  render(
    <I18nProvider>
      <PrimaryRail active="home" dashboard={null} onOpen={(destination) => opened.push(destination)} />
    </I18nProvider>,
  );

  expect(screen.getByRole("button", { name: "抖藏家 · 首页" })).toHaveAttribute("aria-current", "page");
  await userEvent.click(screen.getByRole("button", { name: "抖藏家 · 活动" }));
  expect(opened).toEqual(["activity"]);
});

it("removes the details track when the page has no details", () => {
  render(
    <AppShell primary={<span>导航</span>} context={<span>分类</span>}>
      <main>首页</main>
    </AppShell>,
  );

  expect(screen.queryByTestId("app-details-rail")).not.toBeInTheDocument();
  expect(screen.getByTestId("credit-pros-shell")).toHaveAttribute("data-has-details", "false");
});
