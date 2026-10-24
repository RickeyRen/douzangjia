import type { ReactNode } from "react";

import { AppDataContext, type AppData } from "../app/appDataContext";


export function WithAppData({ value, children }: { value: AppData; children: ReactNode }) {
  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}
