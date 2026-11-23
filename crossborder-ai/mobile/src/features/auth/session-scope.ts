export type UserRuntimeStateDependencies = {
  cancelQueries: () => Promise<void>;
  clearQueries: () => void;
  clearWorkspace: () => Promise<void>;
  resetComposer: () => void;
};

export async function clearUserRuntimeState(
  dependencies: UserRuntimeStateDependencies,
) {
  // 先停止正在回写的旧账号查询，再清空缓存和只属于当前会话的本地状态。
  await dependencies.cancelQueries();
  dependencies.clearQueries();
  dependencies.resetComposer();
  await dependencies.clearWorkspace();
}
