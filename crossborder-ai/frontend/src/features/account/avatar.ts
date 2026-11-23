export function avatarInitial(
  name?: string | null,
): string {
  const value = name?.trim()
  return value ? value.charAt(0).toUpperCase() : 'U'
}
