import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rosterApi } from '../api/client'
import Spinner from '../components/Spinner'
import { Upload, CheckCircle, XCircle, Clock, FileSpreadsheet } from 'lucide-react'

export default function ShiftRoster() {
  const qc = useQueryClient()
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadedBy, setUploadedBy] = useState('')

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['roster-uploads'],
    queryFn: () => rosterApi.uploads(),
  })

  const uploadMut = useMutation({
    mutationFn: (file) => rosterApi.upload(file, uploadedBy || undefined),
    onSuccess: () => qc.invalidateQueries(['roster-uploads']),
  })

  const handleFile = (file) => {
    if (!file) return
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.csv')) {
      alert('Only .xlsx and .csv files are supported.')
      return
    }
    uploadMut.mutate(file)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files[0])
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
            className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center justify-center cursor-pointer transition-colors
              ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv"
              className="hidden"
              onChange={e => handleFile(e.target.files[0])}
            />
            {uploadMut.isPending ? (
              <div className="flex flex-col items-center gap-2">
                <Spinner size="lg" />
                <p className="text-sm text-gray-500">Uploading and processing…</p>
              </div>
            ) : (
              <>
                <FileSpreadsheet size={36} className="text-gray-400 mb-3" />
                <p className="text-sm font-medium text-gray-700">Drop your .xlsx or .csv here</p>
                <p className="text-xs text-gray-400 mt-1">or click to browse</p>
              </>
            )}
          </div>

          {/* Result banner */}
          {uploadMut.isSuccess && uploadMut.data && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
              <p className="font-medium flex items-center gap-1.5">
                <CheckCircle size={15} /> Upload successful
              </p>
              <div className="mt-1.5 grid grid-cols-3 gap-2 text-xs text-green-700">
                <span>Total: <strong>{uploadMut.data.total_records}</strong></span>
                <span>Imported: <strong>{uploadMut.data.imported_records}</strong></span>
                <span>Failed: <strong>{uploadMut.data.failed_records}</strong></span>
              </div>
              {uploadMut.data.roster_start_date && (
                <p className="text-xs mt-1 text-green-600">
                  Period: {uploadMut.data.roster_start_date} → {uploadMut.data.roster_end_date}
                </p>
              )}
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
                    {u.roster_start_date
                      ? `${u.roster_start_date} → ${u.roster_end_date}`
                      : '—'}
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
