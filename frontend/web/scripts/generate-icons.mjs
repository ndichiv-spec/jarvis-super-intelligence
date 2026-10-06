/**
 * Icon rasteriser.
 *
 * `public/manifest.json` declares PNG icons, but `public/` contained only the
 * manifest, so every icon path 404'd and the app was not installable. Browsers
 * do accept an SVG icon for `purpose: "any"`, but maskable icons and some
 * install prompts still require a raster bitmap, so the source SVG is rendered
 * to PNG here at each declared size.
 *
 * Run with: node scripts/generate-icons.mjs
 * Requires `sharp` (already a transitive dependency of Next.js; declared
 * explicitly in devDependencies so this script does not rely on that).
 */

import { readFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import sharp from 'sharp';

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(here, '..', 'public');
const iconsDir = resolve(publicDir, 'icons');

/** Sizes referenced by manifest.json. */
const SIZES = [96, 192, 384, 512];

/**
 * Maskable icons are cropped to a safe zone: the outer 20% on each side may be
 * masked away by the platform, so the artwork is inset and the background is
 * bled to the edges.
 */
async function renderMaskable(svg, size) {
  const inset = Math.round(size * 0.12);
  const inner = size - inset * 2;

  return sharp(Buffer.from(svg))
    .resize(inner, inner)
    .extend({
      top: inset,
      bottom: inset,
      left: inset,
      right: inset,
      background: '#030712',
    })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toBuffer();
}

async function main() {
  await mkdir(iconsDir, { recursive: true });

  const svg = await readFile(resolve(iconsDir, 'icon.svg'), 'utf8');

  for (const size of SIZES) {
    const png = await sharp(Buffer.from(svg))
      .resize(size, size)
      .png({ compressionLevel: 9 })
      .toBuffer();

    await sharp(png).toFile(resolve(iconsDir, `icon-${size}x${size}.png`));
    console.log(`wrote icons/icon-${size}x${size}.png`);
  }

  const maskable = await renderMaskable(svg, 512);
  await sharp(maskable).toFile(resolve(iconsDir, 'icon-maskable-512x512.png'));
  console.log('wrote icons/icon-maskable-512x512.png');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});