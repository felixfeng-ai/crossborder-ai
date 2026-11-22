const roleLabels: Record<string, string> = {
  owner: "所有者",
  admin: "管理员",
  operator: "运营",
  viewer: "只读成员",
};

const workspaceTypeLabels: Record<string, string> = {
  personal: "个人",
  team: "团队",
};

export function workspaceRoleLabel(role: string | null | undefined) {
  if (!role) return "未知角色";
  return roleLabels[role] ?? role;
}

export function workspaceTypeLabel(type: string | null | undefined) {
  if (!type) return "未知类型";
  return workspaceTypeLabels[type] ?? type;
}
