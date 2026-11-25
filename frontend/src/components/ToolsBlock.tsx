import type { ToolCall } from '../api/types'

/** Resumo de uma linha dos argumentos (ex.: a query da busca). */
function preview(args: Record<string, unknown>): string {
  const first = Object.values(args)[0]
  if (first === undefined) return ''
  return typeof first === 'string' ? first : JSON.stringify(first)
}

export default function ToolsBlock({ tools }: { tools: ToolCall[] }) {
  if (tools.length === 0) return null
  const label = tools.length === 1 ? '1 ferramenta usada' : `${tools.length} ferramentas usadas`
  return (
    <details className="tools">
      <summary>
        <b>{label}</b>
      </summary>
      <div className="tools-list">
        {tools.map((tool, i) => (
          <details className="tool-item" key={`${tool.name}-${i}`}>
            <summary>
              <span className="tool-name">{tool.name}</span>
              <span className="tool-preview">{preview(tool.args)}</span>
            </summary>
            <pre className="tool-args">{JSON.stringify(tool.args, null, 2)}</pre>
          </details>
        ))}
      </div>
    </details>
  )
}
