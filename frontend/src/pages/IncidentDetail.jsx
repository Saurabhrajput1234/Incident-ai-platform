import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { incidentApi, triageApi } from '../api/client'
import { PriorityBadge, StateBadge } from '../components/Badge'
import Spinner from '../components/Spinner'
import { ArrowLeft, Bot, RefreshCw, User, Clock, Tag, Server, Pencil, X, CheckCircle } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'

export default function IncidentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [triageResult, setTriageResult] = useState(null)
  const [editOpen, setEditOpen] = useState(false)
  const [triagePopup, setTriagePopup] = useState(null)
  const prevAssignedTo = useRef('__initial__') // sentinel: skip the very first load
  const reloadedRef = useRef(false)

  // Poll while incident is new/in_progress with no assigned_to
  const { data: incident, isLoading } = useQuery({
    queryKey: ['incident', id],
    queryFn: () => incidentApi.get(id),
    refetchInterval: (query) => {
      const inc = query.state.data
      if (!inc) return false
      const shouldPoll = (inc.state === 'new' || inc.state === 'in_progress') && !inc.assigned_to
      return shouldPoll ? 3000 : false
    },
  })

  // Only show popup when assigned_to transitions null → value AFTER initial load
  useEffect(() => {
    if (!incident) return
    const prev = prevAssignedTo.current
    const curr = incident.assigned_to ?? null

    if (prev === '__initial__') {
      // First load — just record the current value, never show popup
      prevAssignedTo.current = curr
      return
    }

    if (!prev && curr && !reloadedRef.current) {
      // Transitioned from empty to assigned during this session
      reloadedRef.current = true
      setTriagePopup({ assignedTo: curr, assignmentGroup: incident.assignment_group })
      qc.invalidateQueries(['incidents'])
      setTimeout(() => {
        setTriagePopup(null)
        qc.invalidateQueries(['incident', id])
      }, 2500)
    }

    prevAssignedTo.current = curr
  }, [incident?.assigned_to])

  const triageMut = useMutation({
    mutationFn: () => triageApi.run(id),
    onSuccess: (res) => {
      setTriageResult(res)
      qc.invalidateQueries(['incident', id])
      qc.invalidateQueries(['incidents'])
    },
    onMutate: () => {
      // Reset sentinels so popup fires if triage assigns a new engineer
      prevAssignedTo.current = null
      reloadedRef.current = false
    },
  })

  const updateMut = useMutation({
    mutationFn: (data) => incidentApi.update(id, data),
    onSuccess: async (updatedIncident) => {
      setEditOpen(false)

      // Step 1: Immediately refetch so UI shows the saved state (e.g. cleared assigned_to)
      await qc.refetchQueries({ queryKey: ['incident', id] })
      qc.invalidateQueries(['incidents'])

      // Step 2: If ticket is still active, run triage now (synchronously) so result
      // is reflected immediately — don't wait for background task polling
      if (updatedIncident.state === 'new' || updatedIncident.state === 'in_progress') {
        try {
          const triageRes = await triageApi.run(id)
          // Refetch again to pick up any assignment changes from triage
          await qc.refetchQueries({ queryKey: ['incident', id] })
          qc.invalidateQueries(['incidents'])
          // Show result banner
          setTriageResult(triageRes)
        } catch {
          // Triage error — still refetch to show latest state
          await qc.refetchQueries({ queryKey: ['incident', id] })
        }
      }
    },
  })

  if (isLoading) {
    return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  }

  if (!incident) {
    return <div className="text-center py-20 text-gray-400">Incident not found.</div>
  }

  const canTriage = incident.state === 'new' || incident.state === 'in_progress'

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/incidents')}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-bold text-blue-600">{incident.incident_number}</span>
              <StateBadge value={incident.state} />
              <PriorityBadge value={incident.priority} />
            </div>
            <p className="text-gray-700 mt-0.5">{incident.short_description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded transition-colors"
          >
            <Pencil size={14} /> Edit
          </button>
          <button
            onClick={() => triageMut.mutate()}
            disabled={triageMut.isPending || !canTriage}
            title={!canTriage ? 'Triage only runs for new or active incidents' : 'Re-run triage to reassign engineer'}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors"
          >
            {triageMut.isPending ? <Spinner size="sm" /> : <Bot size={15} />}
            {triageMut.isPending ? 'Running Triage…' : 'Run Triage Agent'}
          </button>
        </div>
      </div>

      {/* Triage result banner */}
      {triageResult && (
        <div className={`rounded-lg border px-4 py-3 mb-5 text-sm ${triageResult.success ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-700'}`}>
          <p className="font-medium flex items-center gap-1.5">
            <Bot size={15} />
            {triageResult.success ? 'Triage Agent completed' : 'Triage failed'}
          </p>
          {triageResult.reasoning && <p className="mt-1">{triageResult.reasoning}</p>}
          {triageResult.errors?.length > 0 && (
            <ul className="mt-1 list-disc list-inside">{triageResult.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
          )}
        </div>
      )}

      {triageMut.isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm mb-5">
          {triageMut.error?.response?.data?.detail ?? triageMut.error?.message}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* Main col */}
        <div className="col-span-2 space-y-4">
          <Card title="Description">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">
              {incident.description ?? <span className="text-gray-400 italic">No description provided.</span>}
            </p>
          </Card>

          <Card title="Work Notes">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">
              {incident.work_notes ?? <span className="text-gray-400 italic">No work notes.</span>}
            </p>
          </Card>

          {incident.comments && (
            <Card title="Comments">
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{incident.comments}</p>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card title="Classification">
            <dl className="space-y-2 text-sm">
              <Row icon={<Tag size={13} />} label="Priority"><PriorityBadge value={incident.priority} /></Row>
              <Row icon={<RefreshCw size={13} />} label="State"><StateBadge value={incident.state} /></Row>
              <Row label="Category">{incident.category ?? '—'}</Row>
              <Row label="Subcategory">{incident.subcategory ?? '—'}</Row>
              <Row label="Impact">{mapImpact(incident.impact)}</Row>
              <Row label="Urgency">{mapUrgency(incident.urgency)}</Row>
              <Row label="Environment">{incident.environment ?? '—'}</Row>
              <Row label="Source">{incident.source}</Row>
            </dl>
          </Card>

          <Card title="Assignment">
            <dl className="space-y-2 text-sm">
              <Row icon={<User size={13} />} label="Group">
                {incident.assignment_group ?? <span className="text-gray-400 italic">unassigned</span>}
              </Row>
              <Row label="Assigned To">
                {incident.assigned_to ?? <span className="text-gray-400 italic">empty</span>}
              </Row>
              <Row label="Caller">{incident.caller ?? '—'}</Row>
            </dl>
          </Card>

          <Card title="CMDB">
            <dl className="space-y-2 text-sm">
              <Row icon={<Server size={13} />} label="Config Item">{incident.configuration_item ?? '—'}</Row>
              <Row label="Business Service">{incident.business_service ?? '—'}</Row>
            </dl>
          </Card>

          <Card title="Timestamps">
            <dl className="space-y-2 text-sm">
              <Row icon={<Clock size={13} />} label="Created">
                {new Date(incident.created_at).toLocaleString()}
              </Row>
              <Row label="Updated">
                {new Date(incident.updated_at).toLocaleString()}
              </Row>
            </dl>
          </Card>
        </div>
      </div>

      {/* Edit Modal */}
      {editOpen && (
        <EditModal
          incident={incident}
          onClose={() => setEditOpen(false)}
          onSave={(data) => updateMut.mutate(data)}
          isSaving={updateMut.isPending}
          saveError={updateMut.error}
        />
      )}

      {/* Triage completion toast — slides in from top */}
      {triagePopup && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-md mx-auto px-4 animate-slide-down">
          <div className="bg-green-600 text-white rounded-lg shadow-lg px-5 py-3.5 flex items-center gap-3">
            <CheckCircle size={20} className="shrink-0" />
            <div className="flex-1 text-sm">
              <p className="font-semibold">Triage complete — assigned to {triagePopup.assignedTo}</p>
              {triagePopup.assignmentGroup && (
                <p className="text-green-100 text-xs mt-0.5">{triagePopup.assignmentGroup} · Reloading…</p>
              )}
            </div>
            <Spinner size="sm" />
          </div>
        </div>
      )}
    </div>
  )
}

function Card({ title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

function Row({ label, icon, children }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <dt className="text-gray-500 flex items-center gap-1 shrink-0">
        {icon}{label}
      </dt>
      <dd className="text-gray-800 text-right capitalize">{children}</dd>
    </div>
  )
}

function mapImpact(v) {
  return { '1': 'High', '2': 'Medium', '3': 'Low' }[v] ?? v
}
function mapUrgency(v) {
  return { '1': 'High', '2': 'Medium', '3': 'Low' }[v] ?? v
}

const CATEGORIES = ['network','hardware','software','database','security','access','email','vpn','application','other']
const ASSIGNMENT_GROUPS = [
  'Windows Support','Network Support','Database Support','Linux Support',
  'Cloud Infrastructure','Storage Support','SAP Support','Oracle Support',
  'Security Operations','Middleware Support','Active Directory Support',
  'Backup Support','Citrix Support','Application Support','DevOps Support',
  'Hardware Support','Virtualization Support','Email Support',
  'Telecom Support','Endpoint Support',
  'IT Service Desk','IT Helpdesk','General IT Support','L1 Support',
]

const iCls = "w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"

function EditField({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      {children}
    </div>
  )
}

function EditModal({ incident, onClose, onSave, isSaving, saveError }) {
  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: {
      short_description: incident.short_description ?? '',
      description: incident.description ?? '',
      work_notes: incident.work_notes ?? '',
      comments: incident.comments ?? '',
      priority: incident.priority ?? '3',
      state: incident.state ?? 'new',
      category: incident.category ?? '',
      subcategory: incident.subcategory ?? '',
      impact: incident.impact ?? '2',
      urgency: incident.urgency ?? '2',
      assignment_group: incident.assignment_group ?? '',
      assigned_to: incident.assigned_to ?? '',
      caller: incident.caller ?? '',
      configuration_item: incident.configuration_item ?? '',
      business_service: incident.business_service ?? '',
      environment: incident.environment ?? '',
    },
  })

  const onSubmit = (data) => {
    const cleaned = Object.fromEntries(
      Object.entries(data).map(([k, v]) => [k, v === '' ? null : v])
    )
    onSave(cleaned)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 overflow-y-auto py-8">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4">
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">
            Edit {incident.incident_number}
          </h2>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded">
            <X size={18} />
          </button>
        </div>

        {/* Error */}
        {saveError && (
          <div className="mx-5 mt-4 bg-red-50 border border-red-200 text-red-700 rounded px-3 py-2 text-sm">
            {saveError?.response?.data?.detail ?? saveError?.message}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="p-5 space-y-4">
            {/* Core */}
            <EditField label="Short Description *">
              <input
                {...register('short_description', { required: true, minLength: 5 })}
                className={iCls + (errors.short_description ? ' border-red-400' : '')}
              />
              {errors.short_description && (
                <p className="text-xs text-red-500 mt-0.5">Minimum 5 characters required</p>
              )}
            </EditField>

            <EditField label="Description">
              <textarea {...register('description')} rows={3} className={iCls + ' resize-none'} />
            </EditField>

            <EditField label="Work Notes">
              <textarea {...register('work_notes')} rows={2} className={iCls + ' resize-none'} />
            </EditField>

            <EditField label="Comments">
              <textarea {...register('comments')} rows={2} className={iCls + ' resize-none'} />
            </EditField>

            {/* Classification */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <EditField label="Priority">
                <select {...register('priority')} className={iCls}>
                  <option value="1">1 - Critical</option>
                  <option value="2">2 - High</option>
                  <option value="3">3 - Medium</option>
                  <option value="4">4 - Low</option>
                </select>
              </EditField>

              <EditField label="State">
                <select {...register('state')} className={iCls}>
                  <option value="new">New</option>
                  <option value="in_progress">Active</option>
                  <option value="on_hold">On Hold</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </EditField>

              <EditField label="Category">
                <select {...register('category')} className={iCls}>
                  <option value="">— None —</option>
                  {CATEGORIES.map(c => (
                    <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                  ))}
                </select>
              </EditField>

              <EditField label="Subcategory">
                <input {...register('subcategory')} className={iCls} placeholder="e.g. SMTP" />
              </EditField>

              <EditField label="Impact">
                <select {...register('impact')} className={iCls}>
                  <option value="1">High</option>
                  <option value="2">Medium</option>
                  <option value="3">Low</option>
                </select>
              </EditField>

              <EditField label="Urgency">
                <select {...register('urgency')} className={iCls}>
                  <option value="1">High</option>
                  <option value="2">Medium</option>
                  <option value="3">Low</option>
                </select>
              </EditField>

              <EditField label="Environment">
                <select {...register('environment')} className={iCls}>
                  <option value="">— None —</option>
                  <option value="production">Production</option>
                  <option value="staging">Staging</option>
                  <option value="development">Development</option>
                  <option value="dr">DR</option>
                </select>
              </EditField>
            </div>

            {/* Assignment */}
            <div className="grid grid-cols-2 gap-3">
              <EditField label="Assignment Group">
                <select {...register('assignment_group')} className={iCls}>
                  <option value="">— Unassigned —</option>
                  {ASSIGNMENT_GROUPS.map(g => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </EditField>

              <EditField label="Assigned To">
                <input {...register('assigned_to')} className={iCls} placeholder="Engineer name" />
              </EditField>

              <EditField label="Caller">
                <input {...register('caller')} className={iCls} placeholder="Reporter name" />
              </EditField>
            </div>

            {/* CMDB */}
            <div className="grid grid-cols-2 gap-3">
              <EditField label="Configuration Item">
                <input {...register('configuration_item')} className={iCls} placeholder="e.g. server-prod-01" />
              </EditField>
              <EditField label="Business Service">
                <input {...register('business_service')} className={iCls} placeholder="e.g. Customer Portal" />
              </EditField>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-200 bg-gray-50">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-60"
            >
              {isSaving ? <Spinner size="sm" /> : null}
              {isSaving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
