export type StartupSignals = {
  fontsLoaded: boolean;
  fontFailed: boolean;
  coreHydrated: boolean;
};

export function isStartupReady({
  fontsLoaded,
  fontFailed,
  coreHydrated,
}: StartupSignals): boolean {
  // 字体失败时继续进入应用，避免单个资源异常把用户永久困在启动页。
  return coreHydrated && (fontsLoaded || fontFailed);
}
