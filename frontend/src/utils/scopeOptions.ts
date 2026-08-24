export type ScopeOption = {
  key: string
  label?: string
  description?: string
  data_sources?: string[]
}

export type ScopeCatalog = {
  data_sources: ScopeOption[]
  page_scopes: ScopeOption[]
}

export function deriveDataSources(pageScopes: unknown, catalog: Pick<ScopeCatalog, 'page_scopes'>): string[] {
  const selected = new Set((Array.isArray(pageScopes) ? pageScopes : []).map((key) => String(key)))
  const sources = new Set<string>()
  for (const page of catalog.page_scopes || []) {
    if (selected.has(String(page.key))) {
      for (const source of page.data_sources || []) sources.add(String(source))
    }
  }
  return [...sources]
}

export function reconcileDataSources(
  effectiveSources: unknown,
  oldPages: unknown,
  newPages: unknown,
  catalog: Pick<ScopeCatalog, 'page_scopes'>,
): string[] {
  const oldDerived = new Set(deriveDataSources(oldPages, catalog))
  const newDerived = deriveDataSources(newPages, catalog)
  const manual = (Array.isArray(effectiveSources) ? effectiveSources : [])
    .map((item) => String(item))
    .filter((source) => !oldDerived.has(source))
  return Array.from(new Set([...manual, ...newDerived]))
}

export function manualDataSources(
  effectiveSources: unknown,
  pageScopes: unknown,
  catalog: Pick<ScopeCatalog, 'page_scopes'>,
): string[] {
  const derived = new Set(deriveDataSources(pageScopes, catalog))
  return (Array.isArray(effectiveSources) ? effectiveSources : [])
    .map((item) => String(item))
    .filter((source) => !derived.has(source))
}
