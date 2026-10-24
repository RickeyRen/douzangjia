import { expect, it } from "vitest";

import { feedQueryString } from "./api";

it("sends the seed only for random order and flags only when set", () => {
  const random = new URLSearchParams(feedQueryString({ sort: "random", seed: 42, downloaded: true, sourceId: "account:likes" }));
  expect(Object.fromEntries(random)).toEqual({
    limit: "24",
    sourceId: "account:likes",
    sort: "random",
    seed: "42",
    downloaded: "true",
  });

  const plain = new URLSearchParams(feedQueryString({ sort: "published", seed: 42, downloaded: false, starred: false, search: "" }));
  expect(Object.fromEntries(plain)).toEqual({ limit: "24", sort: "published" });
});

it("keeps cursors so pages continue the same query", () => {
  const query = new URLSearchParams(feedQueryString({ starred: true, cursor: "abc", limit: 10 }));
  expect(query.get("starred")).toBe("true");
  expect(query.get("cursor")).toBe("abc");
  expect(query.get("limit")).toBe("10");
});
