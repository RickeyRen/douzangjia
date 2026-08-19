import { X } from "@phosphor-icons/react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FriendlyButton } from "./FriendlyButton";
import { FriendlyIconButton } from "./FriendlyIconButton";

afterEach(cleanup);

describe("friendly controls", () => {
  it("keeps the primary action semantic and tactile class contract", () => {
    const onClick = vi.fn();
    render(
      <FriendlyButton tone="primary" onClick={onClick}>
        立即同步
      </FriendlyButton>,
    );

    const button = screen.getByRole("button", { name: "立即同步" });
    expect(button).toHaveClass("friendly-button", "friendly-button-primary");
    button.click();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("gives an icon-only action an accessible name", () => {
    render(
      <FriendlyIconButton label="关闭">
        <X />
      </FriendlyIconButton>,
    );

    expect(screen.getByRole("button", { name: "关闭" })).toHaveClass(
      "friendly-icon-button",
    );
  });
});
