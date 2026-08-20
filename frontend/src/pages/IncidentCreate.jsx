import { useForm } from 'react-hook-form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { incidentApi } from '../api/client'
import Spinner from '../components/Spinner'
import { ArrowLeft, Save } from 'lucide-react'

const CATEGORIES = ['network','hardware','software','database','security','access','email','vpn','application','other']
const PRIORITIES = [{ v:'1',l:'1 - Critical'},{v:'2',l:'2 - High'},{v:'3',l:'3 - Medium'},{v:'4',l:'4 - Low'}]
const SOURCES = ['manual','monitoring','email','phone','self_service','api']

const ASSIGNMENT_GROUPS = [
  'Windows Support','Network Support','Database Support','Linux Support',
  'Cloud Infrastructure','Storage Support','SAP Support','Oracle Support',
  'Security Operations','Middleware Support','Active Directory Support',
  'Backup Support','Citrix Support','Application Support','DevOps Support',
  'Hardware Support','Virtualization Support','Email Support',
  'Telecom Support','Endpoint Support',
  // Common queue
  'IT Service Desk','IT Helpdesk','General IT Support','L1 Support', "Enterprise Support",
    'General Support',
    'Technical Support',
    'Service Operations',
]

function Field({ label, required, children, hint }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
    </div>
  )
}

const cls = "w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"

export default function IncidentCreate() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: {
      priority: '3',
      source: 'manual',
    }
  })

  const mut = useMutation({
    mutationFn: (data) => incidentApi.create(data),
    onSuccess: (created) => {
      qc.invalidateQueries(['incidents'])
      navigate(`/incidents/${created.id}`)
    },
  })

  const onSubmit = (data) => {
    // Clean empty strings to null
    const cleaned = Object.fromEntries(
      Object.entries(data).map(([k, v]) => [k, v === '' ? null : v])
    )
    mut.mutate(cleaned)
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/incidents')}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-xl font-semibold text-gray-800">New Incident</h1>
          <p className="text-sm text-gray-500">The Triage Agent will automatically assign an engineer after creation.</p>
        </div>
      </div>

      {mut.isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm mb-5">
          Failed to create incident: {mut.error?.response?.data?.detail ?? mut.error?.message}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Section: Core */}
        <Section title="Incident Details">
          <div className="grid grid-cols-1 gap-4">
            <Field label="Short Description" required>
              <input
                {...register('short_description', { required: true, minLength: 5 })}
                placeholder="Brief summary of the incident"
                className={cls + (errors.short_description ? ' border-red-400' : '')}
              />
              {errors.short_description && (
                <p className="text-xs text-red-500 mt-0.5">Minimum 5 characters required</p>
              )}
            </Field>

            <Field label="Description">
              <textarea
                {...register('description')}
                rows={4}
                placeholder="Detailed description of the issue, steps to reproduce, error messages..."
                className={cls + ' resize-none'}
              />
            </Field>

            <Field label="Work Notes" hint="Internal notes visible to support team only">
              <textarea
                {...register('work_notes')}
                rows={2}
                placeholder="Add any initial notes or observations..."
                className={cls + ' resize-none'}
              />
            </Field>
          </div>
        </Section>

        {/* Section: Classification */}
        <Section title="Classification">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="Priority" required>
              <select {...register('priority')} className={cls}>
                {PRIORITIES.map(p => <option key={p.v} value={p.v}>{p.l}</option>)}
              </select>
            </Field>

            <Field label="Category">
              <select {...register('category')} className={cls}>
                <option value="">-- Select Category --</option>
                {CATEGORIES.map(c => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </Field>

            <Field label="Subcategory">
              <input
                {...register('subcategory')}
                placeholder="e.g. SMTP, VPN Client"
                className={cls}
              />
            </Field>

            <Field label="Source">
              <select {...register('source')} className={cls}>
                {SOURCES.map(s => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
            </Field>

            <Field label="Environment">
              <select {...register('environment')} className={cls}>
                <option value="">-- Select --</option>
                <option value="production">Production</option>
                <option value="staging">Staging</option>
                <option value="development">Development</option>
                <option value="dr">DR</option>
              </select>
            </Field>
          </div>
        </Section>

        {/* Section: Assignment */}
        <Section title="Assignment">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Assignment Group" hint="Leave blank for AI to determine">
              <select {...register('assignment_group')} className={cls}>
                <option value="">-- Let AI Determine --</option>
                {ASSIGNMENT_GROUPS.map(g => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </Field>

            <Field label="Caller">
              <input
                {...register('caller')}
                placeholder="Reporter name"
                className={cls}
              />
            </Field>
          </div>
        </Section>

        {/* Section: CMDB */}
        <Section title="CMDB References">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Configuration Item">
              <input
                {...register('configuration_item')}
                placeholder="e.g. server-prod-01"
                className={cls}
              />
            </Field>
            <Field label="Business Service">
              <input
                {...register('business_service')}
                placeholder="e.g. Customer Portal"
                className={cls}
              />
            </Field>
          </div>
        </Section>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-200">
          <button
            type="button"
            onClick={() => navigate('/incidents')}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mut.isPending}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-60"
          >
            {mut.isPending ? <Spinner size="sm" /> : <Save size={15} />}
            {mut.isPending ? 'Creating…' : 'Create Incident'}
          </button>
        </div>
      </form>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
