import type { Config } from "@remix-run/dev";

export default {
  ignoredRouteFiles: ["**/.*"],
  serverModuleFormat: "cjs",
  future: {
    unstable_optimizeDeps: true,
  },
} satisfies Config;
