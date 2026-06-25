/// <reference types="vite/client" />

declare module "virtual:rhize-plan" {
  import type { ComponentType } from "react";
  const Plan: ComponentType<Record<string, unknown>>;
  export default Plan;
  export const frontmatter: Record<string, unknown>;
}

declare module "virtual:rhize-plan-meta" {
  export const frontmatter: Record<string, unknown>;
}
