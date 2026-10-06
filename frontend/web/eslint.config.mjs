import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,

  // Accessibility rules.
  //
  // `eslint-config-next` already registers the jsx-a11y plugin but enables only
  // a small subset of its rules, and the sibling Remix app was the only place
  // that opted into the rest. This block promotes the recommended preset so the
  // main surface gets the same coverage.
  //
  // The plugin is not re-registered here -- doing so is a config error, since it
  // is already present from the Next config.
  {
    rules: {
      ...jsxA11y.configs.recommended.rules,
      // A canvas that carries an aria-label is a legitimate decorative chart.
      "jsx-a11y/no-noninteractive-element-interactions": "off",
    },
  },

  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);
