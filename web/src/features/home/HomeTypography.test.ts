import { expect, it } from "vitest";

import homeStyles from "../../styles/app.css?raw";

function declaration(selector: string): string {
  const matches = [...homeStyles.matchAll(/([^{}]+)\{([^{}]+)\}/g)]
    .filter((match) =>
      match[1].split(",").some((candidate) => candidate.trim() === selector),
    )
    .map((match) => match[2]);
  expect(matches, `missing CSS rule for ${selector}`).not.toHaveLength(0);
  return matches.join("\n");
}

function expectFontSize(selector: string, size: number): void {
  expect(declaration(selector)).toMatch(
    new RegExp(`font-size:\\s*${size}px(?:;|\\s)`),
  );
}

it("keeps home dashboard labels and values comfortably readable", () => {
  expectFontSize(".home-brand h1", 18);
  expectFontSize(".home-brand p", 11);
  expectFontSize(".home-account strong", 13);
  expectFontSize(".home-account small", 11);
  expectFontSize(".home-live-state strong", 11);
  expectFontSize(".home-live-state small", 10);
  expectFontSize(".home-dashboard-section > h2", 16);
  expectFontSize(".home-dashboard-metric-copy > small", 12);
  expectFontSize(".home-dashboard-metric-copy > strong", 20);
  expectFontSize(".home-dashboard-metric-copy > span", 11);
  expectFontSize(".home-runtime-card header strong", 14);
  expectFontSize(".home-runtime-card header small", 11);
  expectFontSize(".home-runtime-card dt", 11);
  expectFontSize(".home-runtime-card dd", 13);
  expectFontSize(".home-source-identity strong", 13);
  expectFontSize(".home-source-identity small", 11);
  expectFontSize(".home-source-metrics dt", 11);
  expectFontSize(".home-source-metrics dd", 12);
  expectFontSize(".home-source-error", 12);
});

it("defines desktop and iPhone sibling layouts without horizontal overflow", () => {
  expect(homeStyles).toContain(".home-dashboard-grid.is-four");
  expect(homeStyles).toContain("grid-template-columns: repeat(4, minmax(0, 1fr))");
  expect(homeStyles).toContain(".home-runtime-grid");
  expect(homeStyles).toContain("grid-template-columns: repeat(3, minmax(0, 1fr))");
  expect(homeStyles).toContain("@media (max-width: 719px)");
  expect(homeStyles).toContain("overflow-x: hidden");
});

it("adapts dashboard columns to the content width left by the desktop rail", () => {
  expect(declaration(".home-scroll")).toMatch(/container-type:\s*inline-size/);
  const start = homeStyles.indexOf("@container dashboard (min-width: 720px) and (max-width: 1249px)");
  const end = homeStyles.indexOf("@media (min-width: 720px) and (max-width: 1199px)", start);
  const responsiveRules = homeStyles.slice(start, end);
  expect(start).toBeGreaterThanOrEqual(0);
  expect(responsiveRules).toContain(".home-dashboard-grid.is-four { grid-template-columns: repeat(2");
  expect(responsiveRules).toContain(".home-dashboard-grid.is-five { grid-template-columns: repeat(3");
});
