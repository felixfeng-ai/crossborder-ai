import { useEffect, useState } from "react";

import { API_BASE_URL, PREVIEW_MODE } from "@/api/client";

const POLL_INTERVAL = 20_000;

async function probeApi() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

function previewOffline() {
  const search = (globalThis as { location?: { search?: string } }).location
    ?.search;
  return typeof search === "string" && /[?&]offline=1/.test(search);
}

/**
 * 离线判定来自一次真实请求：打到后端 /health，失败才算离线。
 * 预览模式不连真后端，用 ?offline=1 造离线态，避免截图受本机网络影响。
 */
export function useNetworkStatus() {
  const [online, setOnline] = useState(
    () => !(PREVIEW_MODE && previewOffline()),
  );

  useEffect(() => {
    if (PREVIEW_MODE) return;
    let cancelled = false;
    const check = async () => {
      const reachable = await probeApi();
      if (!cancelled) setOnline(reachable);
    };
    void check();
    const timer = setInterval(() => void check(), POLL_INTERVAL);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const recheck = () => {
    if (PREVIEW_MODE) {
      setOnline(!previewOffline());
      return;
    }
    void probeApi().then(setOnline);
  };

  return { online, recheck };
}
