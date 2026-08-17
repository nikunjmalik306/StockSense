/**
 * Generic Table wrapper with a consistent visual style.
 *
 * Usage:
 *   <Table>
 *     <Table.Head>
 *       <Table.Row><Table.Th>Name</Table.Th></Table.Row>
 *     </Table.Head>
 *     <Table.Body>
 *       {items.map(item => (
 *         <Table.Row key={item.id}>
 *           <Table.Td>{item.name}</Table.Td>
 *         </Table.Row>
 *       ))}
 *     </Table.Body>
 *   </Table>
 */

interface TableProps { children: React.ReactNode; className?: string }
interface ThProps { children: React.ReactNode; className?: string }
interface TdProps { children: React.ReactNode; className?: string; colSpan?: number }
interface RowProps { children: React.ReactNode; className?: string; onClick?: () => void }

function TableRoot({ children, className = '' }: TableProps) {
  return (
    <div className={`overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 ${className}`}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200">{children}</table>
      </div>
    </div>
  )
}

function Head({ children }: { children: React.ReactNode }) {
  return <thead className="bg-slate-50">{children}</thead>
}

function Body({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-slate-100 bg-white">{children}</tbody>
}

function Th({ children, className = '' }: ThProps) {
  return (
    <th
      scope="col"
      className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 ${className}`}
    >
      {children}
    </th>
  )
}

function Td({ children, className = '', colSpan }: TdProps) {
  return (
    <td colSpan={colSpan} className={`px-4 py-3 text-sm text-slate-700 ${className}`}>
      {children}
    </td>
  )
}

function Row({ children, className = '', onClick }: RowProps) {
  return (
    <tr
      className={`transition-colors hover:bg-slate-50 ${onClick ? 'cursor-pointer' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </tr>
  )
}

export const Table = Object.assign(TableRoot, { Head, Body, Th, Td, Row })
