import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** HTML cru não é renderizado (comportamento padrão do react-markdown, sem rehype-raw). */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
          table: ({ node: _node, ...props }) => (
            <div className="table-wrap">
              <table {...props} />
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
