export type VideoSaveErrorCode =
  | "permission"
  | "download"
  | "save"
  | "unsupported";

export class VideoSaveError extends Error {
  code: VideoSaveErrorCode;

  constructor(code: VideoSaveErrorCode, message: string) {
    super(message);
    this.name = "VideoSaveError";
    this.code = code;
  }
}

export type VideoSaveDependencies = {
  requestPermission: () => Promise<boolean>;
  download: (url: string) => Promise<string>;
  saveToLibrary: (localUri: string) => Promise<void>;
  removeFile: (localUri: string) => Promise<void>;
};

/** 编排权限、下载、相册写入与临时文件清理。 */
export async function saveVideoWithDependencies(
  url: string,
  dependencies: VideoSaveDependencies,
) {
  if (!(await dependencies.requestPermission())) {
    throw new VideoSaveError("permission", "没有相册写入权限");
  }
  let localUri = "";
  try {
    localUri = await dependencies.download(url);
  } catch {
    throw new VideoSaveError("download", "视频下载失败或链接已过期");
  }
  try {
    await dependencies.saveToLibrary(localUri);
  } catch {
    throw new VideoSaveError("save", "视频没有写入系统相册");
  } finally {
    await dependencies.removeFile(localUri).catch(() => undefined);
  }
}
