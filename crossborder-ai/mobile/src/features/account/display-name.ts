export function formatGreetingName(value: string) {
  const normalized = value.trim();
  const characters = Array.from(normalized);

  if (characters.length <= 8) return normalized;
  return `${characters.slice(0, 6).join("")}…`;
}
