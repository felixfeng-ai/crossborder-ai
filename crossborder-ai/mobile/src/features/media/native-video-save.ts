import * as FileSystem from "expo-file-system/legacy";
import * as MediaLibrary from "expo-media-library/legacy";
import { Platform } from "react-native";

import {
  saveVideoWithDependencies,
  VideoSaveError,
} from "./video-save";

export async function saveVideoToDevice(url: string) {
  if (Platform.OS === "web") {
    throw new VideoSaveError(
      "unsupported",
      "网页预览不支持写入系统相册",
    );
  }
  return saveVideoWithDependencies(url, {
    requestPermission: async () => {
      const permission = await MediaLibrary.requestPermissionsAsync(true);
      return permission.granted;
    },
    download: async (sourceUrl) => {
      const directory =
        FileSystem.cacheDirectory || FileSystem.documentDirectory;
      if (!directory) {
        throw new Error("temporary directory unavailable");
      }
      const target = `${directory}veyaship-video-${Date.now()}.mp4`;
      const result = await FileSystem.downloadAsync(sourceUrl, target);
      if (result.status < 200 || result.status >= 300) {
        throw new Error(`download status ${result.status}`);
      }
      return result.uri;
    },
    saveToLibrary: async (localUri) => {
      await MediaLibrary.saveToLibraryAsync(localUri);
    },
    removeFile: async (localUri) => {
      await FileSystem.deleteAsync(localUri, { idempotent: true });
    },
  });
}

export function videoSaveErrorMessage(error: unknown) {
  if (error instanceof VideoSaveError) {
    if (error.code === "permission") {
      return "请在系统设置中允许 VeyaShip 写入相册。";
    }
    if (error.code === "download") {
      return "视频链接可能已过期，请刷新任务后重试。";
    }
    if (error.code === "save") {
      return "视频没有写入相册，请检查系统存储空间。";
    }
    return "当前环境不支持保存到相册。";
  }
  return "视频保存失败，请稍后重试。";
}
