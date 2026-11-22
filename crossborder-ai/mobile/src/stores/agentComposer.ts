import { create } from "zustand";

type ComposerDraft = {
  id: number;
  text: string;
};

type AgentComposerState = {
  draft: ComposerDraft | null;
  requestDraft: (text: string) => void;
  consumeDraft: (id: number) => void;
};

let draftSequence = 0;

export const useAgentComposerStore = create<AgentComposerState>((set) => ({
  draft: null,
  requestDraft: (text) => {
    draftSequence += 1;
    set({ draft: { id: draftSequence, text } });
  },
  consumeDraft: (id) =>
    set((state) => (state.draft?.id === id ? { draft: null } : state)),
}));
