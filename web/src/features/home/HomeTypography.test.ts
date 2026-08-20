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
  expectFontSize(".home-account h1", 17);
  expectFontSize(".home-account p", 12);
  expectFontSize(".home-section-title span", 12);
  expectFontSize(".home-section-title strong", 24);
  expectFontSize(".home-storage-ring strong", 25);
  expectFontSize(".home-storage-ring small", 12);
  expectFontSize(".home-storage-visual dt", 12);
  expectFontSize(".home-health-details dt", 12);
  expectFontSize(".home-storage-visual dd", 12);
  expectFontSize(".home-health-details dd", 12);
  expectFontSize(".home-metric-strip span", 12);
  expectFontSize(".home-metric-strip strong", 24);
  expectFontSize(".home-metric-strip small", 12);
  expectFontSize(".home-system-strip span", 12);
  expectFontSize(".home-system-strip strong", 20);
  expectFontSize(".home-system-strip small", 12);
  expectFontSize(".home-source-heading p", 13);
  expectFontSize(".home-source-identity strong", 14);
  expectFontSize(".home-source-identity small", 12);
  expectFontSize(".home-source-metrics dt", 12);
  expectFontSize(".home-source-metrics dd", 13);
  expectFontSize(".home-source-error", 12);
});
