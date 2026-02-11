import { create } from 'zustand'

interface TTSState {
  selectedVoice: string
  setSelectedVoice: (v: string) => void
}

export const useTTSStore = create<TTSState>((set) => ({
  selectedVoice: 'default',
  setSelectedVoice: (v) => set({ selectedVoice: v })
}))
