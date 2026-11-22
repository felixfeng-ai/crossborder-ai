export type QueryDisplayState =
  | "loading"
  | "error"
  | "content"
  | "empty";

type QuerySnapshot = {
  isLoading: boolean;
  isError: boolean;
  hasData: boolean;
};

/** 统一查询页面状态，避免把网络错误误显示成空态或业务终态。 */
export function resolveQueryState({
  isLoading,
  isError,
  hasData,
}: QuerySnapshot): QueryDisplayState {
  if (isLoading && !hasData) return "loading";
  if (isError && !hasData) return "error";
  if (hasData) return "content";
  return "empty";
}
