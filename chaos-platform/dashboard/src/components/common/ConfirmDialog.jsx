import { useDispatch, useSelector } from 'react-redux'
import { closeConfirm, selectModals, selectConfirm } from '../../store/slices/uiSlice'

export default function ConfirmDialog() {
  const dispatch = useDispatch()
  const open = useSelector(selectModals).confirmDialog
  const { title, message, onConfirmAction } = useSelector(selectConfirm)

  if (!open) return null

  const handleConfirm = () => {
    onConfirmAction?.()
    dispatch(closeConfirm())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 w-full max-w-sm shadow-2xl">
        <h3 className="text-base font-semibold text-gray-100 mb-2">{title}</h3>
        <p className="text-sm text-gray-400 mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button className="btn-ghost" onClick={() => dispatch(closeConfirm())}>Cancel</button>
          <button className="btn-danger" onClick={handleConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  )
}
