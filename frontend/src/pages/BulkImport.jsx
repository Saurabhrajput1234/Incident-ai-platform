import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { incidentApi } from '../api/client'
import Spinner from '../components/Spinner'
import { Upload, FileText, CheckCircle, XCircle, Download, ArrowRight } from 'lucide-react'

export default function BulkImport() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [result, setResult] = useState(null)

  const importMut = useMutation({
    mutationFn: (file) => incidentApi.bulkImport(file),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries(['incidents'])
      qc.invalidateQueries(['dash-stats'])
      qc.invalidateQueries(['dash-trends'])
      qc.invalidateQueries(['dash-group'])
      qc.invalidateQueries(['dash-priority'])
      qc.invalidateQueries(['dash-state'])
      qc.invalidateQueries(['dash-triage'])
    },
  })

  const handleFile = (file) => {
    if (!file) return
    if (!file.name.endsWith('.csv')) {
      alert('Only .csv files are supported.')
      return
    }
    setResult(null)
    importMut.mutate(file)
  }

  const downloadSample = () => {
    window.open('/sample_incidents.csv', '_blank')
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Bulk Import Incidents</h1>
        <button
          onClick={downloadSample}
          className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 border border-blue-200 hover:border-blue-400 px-3 py-1.5 rounded transition-colors"
        >
          <Download size={14} /> Download Sample CSV
        </button>
      </div>

      {/* CSV Format Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
        <p className="font-medium mb-1">CSV Format</p>
        <p className="text-xs text-blue-700">
          Required column: <code className="bg-blue-100 px-1 rounded">short_description</code>
          &nbsp;· Optional: description, priority (1-4), category, assignment_group, caller,
          environment, source, state, work_notes
        </p>
        <p className="text-xs text-blue-600 mt-1">
          Each row becomes one incident. Triage agent runs automatically on all created incidents.
        </p>
      </div>

      {/* Drop zone */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">Upload CSV</h2>
        </div>
        <div className="p-5">
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }}
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-12 flex flex-col items-center justify-center cursor-pointer transition-colors
              ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
          >
            <input ref={fileRef} type="file" accept=".csv" className="hidden"
              onChange={e => { handleFile(e.target.files[0]); e.target.value = '' }} />
            {importMut.isPending ? (
              <div className="flex flex-col items-center gap-3">
                <Spinner size="lg" />
                <p className="text-sm text-gray-500">Importing incidents and queuing triage…</p>
              </div>
            ) : (
              <>
                <FileText size={40} className="text-gray-400 mb-3" />
                <p className="text-sm font-medium text-gray-700">Drop your incidents.csv here</p>
                <p className="text-xs text-gray-400 mt-1">or click to browse</p>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {importMut.isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {importMut.error?.response?.data?.detail ?? importMut.error?.message}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-gray-800">{result.total_rows}</p>
              <p className="text-xs text-gray-500 mt-0.5">Total Rows</p>
            </div>
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold text-green-700">{result.created}</p>
              <p className="text-xs text-green-600 mt-0.5">Created</p>
            </div>
            <div className={`${result.failed > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'} border rounded-lg p-4 text-center`}>
              <p className={`text-2xl font-bold ${result.failed > 0 ? 'text-red-700' : 'text-gray-400'}`}>{result.failed}</p>
              <p className="text-xs text-gray-500 mt-0.5">Failed</p>
            </div>
          </div>

          <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
            <p className="flex items-center gap-1.5 font-medium">
              <CheckCircle size={15} />
              {result.created} incidents created — Triage Agent is running in the background
            </p>
          </div>

          {/* Created list */}
          {result.incidents.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 text-xs text-gray-500 font-medium uppercase tracking-wider">
                Created Incidents
              </div>
              <div className="max-h-64 overflow-y-auto divide-y divide-gray-100">
                {result.incidents.map((inc, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2.5 text-sm hover:bg-gray-50">
                    <div className="flex items-center gap-2">
                      <CheckCircle size={13} className="text-green-500 shrink-0" />
                      <span className="font-mono text-blue-600 text-xs font-medium">{inc.incident_number}</span>
                      <span className="text-gray-700 truncate max-w-xs">{inc.short_description}</span>
                    </div>
                    <button
                      onClick={() => navigate(`/incidents/${inc.id}`)}
                      className="text-blue-500 hover:text-blue-700 shrink-0"
                    >
                      <ArrowRight size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <div className="bg-white border border-red-200 rounded-lg overflow-hidden">
              <div className="px-4 py-2.5 bg-red-50 border-b border-red-200 text-xs text-red-600 font-medium uppercase tracking-wider">
                Failed Rows
              </div>
              <div className="max-h-48 overflow-y-auto divide-y divide-red-50">
                {result.errors.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 px-4 py-2.5 text-sm">
                    <XCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
                    <span className="text-gray-500 text-xs">Row {e.row}:</span>
                    <span className="text-red-700 text-xs">{e.error}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors"
            >
              View Dashboard <ArrowRight size={14} />
            </button>
            <button
              onClick={() => navigate('/incidents')}
              className="px-4 py-2 border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm rounded transition-colors"
            >
              View Incidents
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
