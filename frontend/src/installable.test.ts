import { describe, expect, it } from "vitest";
import manifestText from "../public/site.webmanifest?raw";

const manifest = JSON.parse(manifestText) as {
  display: string;
  start_url: string;
  scope: string;
  name: string;
  theme_color: string;
  icons: { src: string; purpose?: string }[];
};
// What actually ships in public/, keyed "../public/<file>".
const shipped = Object.keys(import.meta.glob("../public/*"));
const ships = (src: string) => shipped.includes(`../public${src}`);

describe("installing Ardoise as an app", () => {
  it("opens without the browser's address bar and tabs", () => {
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");
    expect(manifest.scope).toBe("/");
  });

  it("names itself and has every icon it points to", () => {
    expect(manifest.name).toBe("Ardoise");
    for (const icon of manifest.icons) expect(ships(icon.src), icon.src).toBe(true);
    expect(ships("/apple-touch-icon.png")).toBe(true);
  });

  it("colours Android's bottom bar brand green, which reads in both themes", () => {
    // Chrome and Brave take the installed app's bottom (navigation) bar colour from the
    // manifest, once, whatever the theme: the page's theme-color only reaches the top bar. The
    // old light ground left a light strip under the dark theme's tab bar.
    expect(manifest.theme_color).toBe("#1f4e4a");
  });

  it("has a maskable icon, so Android launchers can reshape it without a white border", () => {
    expect(manifest.icons.some((icon) => icon.purpose === "maskable")).toBe(true);
  });
});
