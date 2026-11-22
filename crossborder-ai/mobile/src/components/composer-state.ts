export function shouldShowSendButton(input: {
  value: string;
  voiceMode: boolean;
}) {
  return !input.voiceMode && input.value.trim().length > 0;
}
