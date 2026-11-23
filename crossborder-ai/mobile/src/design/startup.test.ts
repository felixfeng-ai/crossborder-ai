import { describe, expect, it } from "vitest";

import appConfig from "../../app.config";
import { isStartupReady } from "./startup-state";

describe("startup splash contract", () => {
  it("configures the branded native splash with the app canvas color", () => {
    const splashPlugin = appConfig.plugins?.find(
      (plugin) => Array.isArray(plugin) && plugin[0] === "expo-splash-screen",
    );

    expect(splashPlugin).toEqual([
      "expo-splash-screen",
      {
        backgroundColor: "#F2F3F5",
        image: "./assets/splash-icon.png",
        imageWidth: 164,
        resizeMode: "contain",
        dark: {
          backgroundColor: "#F2F3F5",
          image: "./assets/splash-icon.png",
        },
      },
    ]);
  });

  it("keeps startup blocked until fonts and local state are ready", () => {
    expect(
      isStartupReady({
        fontsLoaded: false,
        fontFailed: false,
        coreHydrated: false,
      }),
    ).toBe(false);
    expect(
      isStartupReady({
        fontsLoaded: true,
        fontFailed: false,
        coreHydrated: false,
      }),
    ).toBe(false);
    expect(
      isStartupReady({
        fontsLoaded: true,
        fontFailed: false,
        coreHydrated: true,
      }),
    ).toBe(true);
  });

  it("does not keep users trapped when a font asset fails", () => {
    expect(
      isStartupReady({
        fontsLoaded: false,
        fontFailed: true,
        coreHydrated: true,
      }),
    ).toBe(true);
  });
});
