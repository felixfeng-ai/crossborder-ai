type Identified = { id: string };

/** 在筛选结果内移动素材，只交换两个可见项在完整列表中的位置。 */
export function moveVisibleAsset<T extends Identified>(
  assets: T[],
  visibleIds: string[],
  selectedId: string,
  direction: -1 | 1,
) {
  const visibleIndex = visibleIds.indexOf(selectedId);
  const targetVisibleId = visibleIds[visibleIndex + direction];
  if (visibleIndex < 0 || !targetVisibleId) return assets;

  const sourceIndex = assets.findIndex((asset) => asset.id === selectedId);
  const targetIndex = assets.findIndex(
    (asset) => asset.id === targetVisibleId,
  );
  if (sourceIndex < 0 || targetIndex < 0) return assets;

  const next = [...assets];
  [next[sourceIndex], next[targetIndex]] = [
    next[targetIndex],
    next[sourceIndex],
  ];
  return next;
}
