import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rosterApi } from '../api/client'
import Spinner from '../components/Spinner'
import { Upload, CheckCircle, XCircle, Clock, FileSpreadsheet, X } from 'lucide-react'

export default function ShiftRoster() {
  const qc = useQueryClient()
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadedBy, setUploadedBy] = useState('')
  const [selectedFiles, setSelectedFiles] = useState([]) // queued files
  const [bulkResults, setBulkResults] = useState([])     // per-file results

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['roster-uploads'],
    queryFn: () => rosterApi.uploads(),
  })

  const uploadMut = useMutation({
    mutationFn: (files) => rosterApi.uploadBulk(files, uploadedBy || undefined),
    onSuccess: (results) => {
      setBulkResults(results)
      setSelectedFiles([])
      qc.invalidateQueries(['roster-uploads'])
    },
  })

  const addFiles = (incoming) => {
    const valid = Array.from(incoming).filter(
      f => f.name.endsWith('.xlsx') || f.name.endsWith('.csv')
    )
    const invalid = Array.from(incoming).filter(
      f => !f.name.endsWith('.xlsx') && !f.name.endsWith('.csv')
    )
    if (invalid.length) alert(`Skipped ${invalid.length} unsupported file(s). Only .xlsx and .csv allowed.`)
    if (valid.length) setSelectedFiles(prev => [...prev, ...valid])
  }

  const removeFile = (idx) => setSelectedFiles(prev => prev.filter((_, i) => i !== idx))

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    addFiles(e.dataTransfer.files)
  }

  const statusIcon = (s) => {
    if (s === 'success') return <CheckCircle size={15} className="text-green-500" />
    if (s === 'failed') return <XCircle size={15} className="text-red-500" />
    return <Clock size={15} className="text-yellow-500" />
  }

  const statusClass = (s) => {
    if (s === 'success') return 'text-green-700 bg-green-50 border-green-200'
    if (s === 'failed') return 'text-red-700 bg-red-50 border-red-200'
    return 'text-yellow-700 bg-yellow-50 border-yellow-200'
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-xl font-semibold text-gray-800">Shift Roster</h1>

      {/* Upload card */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">Upload Roster</h2>
        </div>
        <div className="p-5 space-y-4">
          {/* Uploader name */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Uploaded By (optional)</label>
            <input
              value={uploadedBy}
              onChange={e => setUploadedBy(e.target.value)}
              placeholder="Your name or email"
              className="w-64 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center cursor-pointer transition-colors
              ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv"
              multiple
              className="hidden"
              onChange={e => { addFiles(e.target.files); e.target.value = '' }}
            />
            <FileSpreadsheet size={36} className="text-gray-400 mb-3" />
            <p className="text-sm font-medium text-gray-700">Drop your .xlsx or .csv files here</p>
            <p className="text-xs text-gray-400 mt-1">or click to browse — multiple files supported</p>
          </div>

          {/* Selected files queue */}
          {selectedFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-600">{selectedFiles.length} file(s) ready to upload</p>
              <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-48 overflow-y-auto">
                {selectedFiles.map((f, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileSpreadsheet size={14} className="text-blue-500 shrink-0" />
                      <span className="truncate text-gray-700">{f.name}</span>
                      <span className="text-gray-400 text-xs shrink-0">
                        {(f.size / 1024).toFixed(0)} KB
                      </span>
                    </div>
                    <button
                      onClick={e => { e.stopPropagation(); removeFile(i) }}
                      className="p-1 text-gray-400 hover:text-red-500 rounded shrink-0"
                    >
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={() => uploadMut.mutate(selectedFiles)}
                disabled={uploadMut.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded transition-colors disabled:opacity-60"
              >
                {uploadMut.isPending ? <Spinner size="sm" /> : <Upload size={14} />}
                {uploadMut.isPending
                  ? `Uploading ${selectedFiles.length} file(s)…`
                  : `Upload ${selectedFiles.length} file(s)`}
              </button>
            </div>
          )}

          {/* Bulk results */}
          {bulkResults.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-600">Upload results</p>
              {bulkResults.map((r, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-4 py-3 text-sm ${
                    r.upload_status === 'success'
                      ? 'bg-green-50 border-green-200 text-green-800'
                      : r.upload_status === 'failed'
                      ? 'bg-red-50 border-red-200 text-red-700'
                      : 'bg-yellow-50 border-yellow-200 text-yellow-800'
                  }`}
                >
                  <p className="font-medium flex items-center gap-1.5">
                    {statusIcon(r.upload_status)} {r.file_name}
                  </p>
                  <div className="mt-1 grid grid-cols-3 gap-2 text-xs opacity-80">
                    <span>Total: <strong>{r.total_records}</strong></span>
                    <span>Imported: <strong>{r.imported_records}</strong></span>
                    <span>Failed: <strong>{r.failed_records}</strong></span>
                  </div>
                  {r.roster_start_date && (
                    <p className="text-xs mt-0.5 opacity-70">
                      {r.roster_start_date} → {r.roster_end_date}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {uploadMut.isError && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
              {uploadMut.error?.response?.data?.detail ?? uploadMut.error?.message}
            </div>
          )}
        </div>
      </div>

      {/* Upload history */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">Upload History</h2>
        </div>

        {historyLoading ? (
          <div className="flex justify-center py-10"><Spinner size="lg" /></div>
        ) : !history?.length ? (
          <div className="text-center py-10 text-gray-400 text-sm">No uploads yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">File</th>
                <th className="px-4 py-3 font-medium">Period</th>
                <th className="px-4 py-3 font-medium">Records</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {history.map(u => (
                <tr key={u.upload_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-800 max-w-xs truncate">
                    <div className="flex items-center gap-1.5">
                      <Upload size={13} className="text-gray-400 shrink-0" />
                      {u.file_name}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap text-xs">
                    {u.roster_start_date ? `${u.roster_start_date} → ${u.roster_end_date}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">
                    {u.total_records} total · {u.imported_records} ok · {u.failed_records} failed
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${statusClass(u.upload_status)}`}>
                      {statusIcon(u.upload_status)}
                      {u.upload_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
