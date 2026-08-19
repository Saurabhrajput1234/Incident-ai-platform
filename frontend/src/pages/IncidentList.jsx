import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { incidentApi } from '../api/client'
import { PriorityBadge, StateBadge } from '../components/Badge'
import Spinner from '../components/Spinner'
import { Plus, Search, RefreshCw, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react'

const PAGE_SIZE = 20

export default function IncidentList() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ state: '', priority: '' })

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['incidents', page, filters],
    queryFn: () => incidentApi.list({ page, page_size: PAGE_SIZE, ...filters }),
    keepPreviousData: true,
  })

  const deleteMut = useMutation({
    mutationFn: (id) => incidentApi.delete(id),
    onSuccess: () => qc.invalidateQueries(['incidents']),
  })

  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ['incidents-search', search],
    queryFn: () => incidentApi.search({ q: search, page_size: 50 }),
    enabled: search.trim().length >= 2,
  })

  const incidents = search.trim().length >= 2
    ? searchData?.items ?? []
    : data?.items ?? []

  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-gray-800">Incidents</h1>
        <button
          onClick={() => navigate('/incidents/new')}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New Incident
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-lg p-3 mb-4 flex flex-wrap gap-3 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search incidents…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <select
          value={filters.state}
          onChange={e => { setFilters(f => ({ ...f, state: e.target.value })); setPage(1) }}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All States</option>
          <option value="new">New</option>
          <option value="in_progress">Active</option>
          <option value="on_hold">On Hold</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>

        <select
          value={filters.priority}
          onChange={e => { setFilters(f => ({ ...f, priority: e.target.value })); setPage(1) }}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All Priorities</option>
          <option value="1">1 - Critical</option>
          <option value="2">2 - High</option>
          <option value="3">3 - Medium</option>
          <option value="4">4 - Low</option>
        </select>

        <button
          onClick={() => qc.invalidateQueries(['incidents'])}
          className="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded transition-colors"
          title="Refresh"
        >
          <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
        </button>

        {total > 0 && (
          <span className="text-sm text-gray-500 ml-auto">{total} records</span>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        {isLoading || searching ? (
          <div className="flex justify-center py-16"><Spinner size="lg" /></div>
        ) : incidents.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg font-medium">No incidents found</p>
            <p className="text-sm mt-1">Create your first incident to get started.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">Number</th>
                <th className="px-4 py-3 font-medium">Short Description</th>
                <th className="px-4 py-3 font-medium">Priority</th>
                <th className="px-4 py-3 font-medium">State</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Assignment Group</th>
                <th className="px-4 py-3 font-medium">Assigned To</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {incidents.map(inc => (
                <tr
                  key={inc.id}
                  className="hover:bg-blue-50 cursor-pointer transition-colors"
                  onClick={() => navigate(`/incidents/${inc.id}`)}
                >
                  <td className="px-4 py-3 font-mono text-blue-600 font-medium whitespace-nowrap">
                    {inc.incident_number}
                  </td>
                  <td className="px-4 py-3 max-w-xs truncate text-gray-800">
                    {inc.short_description}
                  </td>
                  <td className="px-4 py-3"><PriorityBadge value={inc.priority} /></td>
                  <td className="px-4 py-3"><StateBadge value={inc.state} /></td>
                  <td className="px-4 py-3 text-gray-600 capitalize">{inc.category ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-600 max-w-32 truncate">
                    {inc.assignment_group ?? <span className="text-gray-400 italic">unassigned</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {inc.assigned_to ?? <span className="text-gray-400 italic">empty</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                    {new Date(inc.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={e => {
                        e.stopPropagation()
                        if (confirm('Delete this incident?')) deleteMut.mutate(inc.id)
                      }}
                      className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {!search && pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50 text-sm">
            <span className="text-gray-500">
              Page {page} of {pages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-100 transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-100 transition-colors"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
