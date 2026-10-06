import { defineConfig } from "vite";
import { viteCommonjs } from "@originjs/vite-plugin-commonjs";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  css: {
    postcss: "./postcss.config.js",
  },
  plugins: [
    tsconfigPaths(),
    viteCommonjs(),
  ],
  server: {
    port: 3001,
  },
});
