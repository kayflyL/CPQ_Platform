declare module 'dagre' {
  export interface GraphLabel {
    rankdir?: 'TB' | 'LR' | 'BT' | 'RL'
    nodesep?: number
    ranksep?: number
    marginx?: number
    marginy?: number
  }

  export interface Node {
    width: number
    height: number
    x: number
    y: number
  }

  export function layout(g: Graph): void

  export class Graph {
    constructor(options?: GraphLabel)
    setGraph(label: GraphLabel): void
    setNode(id: string, label: { width: number; height: number } & Record<string, any>): void
    setEdge(source: string, target: string, label?: Record<string, any>): void
    node(id: string): Node | undefined
    edges(): { v: string; w: string; name?: string }[]
    nodes(): string[]
    setDefaultEdgeLabel(fn: () => Record<string, any>): void
  }

  const graphlib: {
    Graph: typeof Graph
  }

  export { graphlib }
}