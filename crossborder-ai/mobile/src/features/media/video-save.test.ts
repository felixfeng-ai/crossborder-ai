import { describe, expect, it } from "vitest";

import {
  saveVideoWithDependencies,
  VideoSaveError,
} from "./video-save";

describe("视频保存编排", () => {
  it("权限拒绝时不下载文件", async () => {
    let downloaded = false;
    await expect(
      saveVideoWithDependencies("https://example.com/video.mp4", {
        requestPermission: async () => false,
        download: async () => {
          downloaded = true;
          return "file:///video.mp4";
        },
        saveToLibrary: async () => undefined,
        removeFile: async () => undefined,
      }),
    ).rejects.toMatchObject({ code: "permission" });
    expect(downloaded).toBe(false);
  });

  it("下载后写入相册并清理临时文件", async () => {
    const calls: string[] = [];
    await saveVideoWithDependencies("https://example.com/video.mp4", {
      requestPermission: async () => true,
      download: async () => {
        calls.push("download");
        return "file:///video.mp4";
      },
      saveToLibrary: async (uri) => {
        calls.push(`save:${uri}`);
      },
      removeFile: async () => {
        calls.push("cleanup");
      },
    });

    expect(calls).toEqual([
      "download",
      "save:file:///video.mp4",
      "cleanup",
    ]);
  });

  it("下载失败时返回网络错误并仍清理临时状态", async () => {
    await expect(
      saveVideoWithDependencies("https://example.com/video.mp4", {
        requestPermission: async () => true,
        download: async () => {
          throw new Error("network");
        },
        saveToLibrary: async () => undefined,
        removeFile: async () => undefined,
      }),
    ).rejects.toBeInstanceOf(VideoSaveError);
  });
});
