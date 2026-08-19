const priorityConfig = {
  '1': { label: 'Critical', class: 'bg-red-100 text-red-700 border border-red-200' },
  '2': { label: 'High',     class: 'bg-orange-100 text-orange-700 border border-orange-200' },
  '3': { label: 'Medium',   class: 'bg-yellow-100 text-yellow-700 border border-yellow-200' },
  '4': { label: 'Low',      class: 'bg-green-100 text-green-700 border border-green-200' },
}

const stateConfig = {
  new:         { label: 'New',         class: 'bg-blue-100 text-blue-700 border border-blue-200' },
  in_progress: { label: 'Active',      class: 'bg-purple-100 text-purple-700 border border-purple-200' },
  on_hold:     { label: 'On Hold',     class: 'bg-gray-100 text-gray-700 border border-gray-200' },
  resolved:    { label: 'Resolved',    class: 'bg-green-100 text-green-700 border border-green-200' },
  closed:      { label: 'Closed',      class: 'bg-gray-200 text-gray-600 border border-gray-300' },
  cancelled:   { label: 'Cancelled',   class: 'bg-red-100 text-red-600 border border-red-200' },
}

export function PriorityBadge({ value }) {
  const cfg = priorityConfig[value] ?? { label: value, class: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cfg.class}`}>
      {cfg.label}
    </span>
  )
}

export function StateBadge({ value }) {
  const cfg = stateConfig[value] ?? { label: value, class: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cfg.class}`}>
      {cfg.label}
    </span>
  )
}
