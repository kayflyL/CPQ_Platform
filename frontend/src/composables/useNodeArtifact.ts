import { ref } from 'vue'

export interface NodeArtifact {
  kind: string
  title: string
  data?: any
  input?: any
  output?: any
}

const artifact = ref<NodeArtifact | null>(null)

export function useNodeArtifact() {
  function open(next: NodeArtifact | null | undefined) {
    artifact.value = next || null
  }
  function close() {
    artifact.value = null
  }
  return { artifact, open, close }
}
