import { createSlice } from '@reduxjs/toolkit'

let notifId = 0

const uiSlice = createSlice({
  name: 'ui',
  initialState: {
    sidebarCollapsed: false,
    modals: {
      experimentForm: false,
      testForm: false,
      confirmDialog: false,
    },
    confirmDialog: { title: '', message: '', onConfirmAction: null },
    notifications: [],   // { id, type, message, persistent }
    wsStatus: 'disconnected',  // connected | reconnecting | disconnected
  },
  reducers: {
    toggleSidebar: (state) => { state.sidebarCollapsed = !state.sidebarCollapsed },
    openModal:  (state, { payload }) => { state.modals[payload] = true },
    closeModal: (state, { payload }) => { state.modals[payload] = false },
    openConfirm: (state, { payload }) => {
      state.modals.confirmDialog = true
      state.confirmDialog = payload
    },
    closeConfirm: (state) => { state.modals.confirmDialog = false },
    pushNotification: (state, { payload }) => {
      state.notifications.push({ id: ++notifId, ...payload })
    },
    dismissNotification: (state, { payload }) => {
      state.notifications = state.notifications.filter((n) => n.id !== payload)
    },
    setWsStatus: (state, { payload }) => { state.wsStatus = payload },
  },
})

export const {
  toggleSidebar, openModal, closeModal,
  openConfirm, closeConfirm,
  pushNotification, dismissNotification,
  setWsStatus,
} = uiSlice.actions

export const selectModals      = (s) => s.ui.modals
export const selectSidebarOpen = (s) => !s.ui.sidebarCollapsed
export const selectNotifs      = (s) => s.ui.notifications
export const selectWsStatus    = (s) => s.ui.wsStatus
export const selectConfirm     = (s) => s.ui.confirmDialog

export default uiSlice.reducer
