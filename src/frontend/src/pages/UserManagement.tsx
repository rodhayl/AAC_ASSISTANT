import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ResetPasswordModal } from '../components/common/ResetPasswordModal'
import api, { extractError } from '../lib/api'
import type { User } from '../types'
import { useAuthStore } from '../store/authStore'
import { useModalFocusTrap } from '../hooks/useModalFocusTrap'
import { useToastStore } from '../store/toastStore'

export type ManagedUserRole = 'teacher' | 'admin'

interface UserManagementPageProps {
  role: ManagedUserRole
}

export function UserManagementPage({ role }: UserManagementPageProps) {
  const user = useAuthStore((state) => state.user)
  const addToast = useToastStore((state) => state.addToast)
  const namespace = role === 'teacher' ? 'teachers' : 'admins'
  const { t } = useTranslation([namespace, 'settings'])
  const [managedUsers, setManagedUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [editId, setEditId] = useState<number | null>(null)
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editEmail, setEditEmail] = useState('')

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [createLoading, setCreateLoading] = useState(false)

  const [deleteState, setDeleteState] = useState<{ isOpen: boolean; user: User | null }>({
    isOpen: false,
    user: null,
  })
  const [resetPasswordModalOpen, setResetPasswordModalOpen] = useState(false)
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [resetPasswordLoading, setResetPasswordLoading] = useState(false)
  const [updateLoading, setUpdateLoading] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const loadUsers = useCallback(async () => {
    const response = await api.get('/auth/users', {
      params: { limit: 1000, user_type: role },
    })
    if (!Array.isArray(response.data)) {
      throw new Error('Invalid response format: expected array')
    }
    setManagedUsers(response.data as User[])
  }, [role])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        await loadUsers()
      } catch (loadError: unknown) {
        if (!cancelled) {
          console.error(`Failed to load ${role}s:`, loadError)
          setError(extractError(loadError, t('errors.loadFailed')))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [loadUsers, role, t, user])

  const clearCreateForm = () => {
    setNewUsername('')
    setNewDisplayName('')
    setNewEmail('')
    setNewPassword('')
    setConfirmPassword('')
  }

  const handleDelete = async () => {
    const selectedUser = deleteState.user
    if (!selectedUser) return

    setDeleteLoading(true)
    try {
      await api.delete(`/auth/users/${selectedUser.id}`)
      setManagedUsers(previous => previous.filter(item => item.id !== selectedUser.id))
      addToast(t('success.deleted'), 'success')
    } catch (deleteError: unknown) {
      setError(extractError(deleteError, t('errors.deleteFailed')))
    } finally {
      setDeleteLoading(false)
      setDeleteState({ isOpen: false, user: null })
    }
  }

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      setError(t('errors.passwordsDoNotMatch'))
      return
    }

    setCreateLoading(true)
    setError(null)
    try {
      await api.post('/auth/admin/create-user', {
        username: newUsername,
        password: newPassword,
        confirm_password: confirmPassword,
        display_name: newDisplayName,
        email: newEmail || undefined,
        user_type: role,
      })
      await loadUsers()
      clearCreateForm()
      setCreateModalOpen(false)
      addToast(t('success.created'), 'success')
    } catch (createError: unknown) {
      setError(extractError(createError, t('errors.createFailed')))
    } finally {
      setCreateLoading(false)
    }
  }

  const handleUpdate = async () => {
    if (!editId) return
    setUpdateLoading(true)
    try {
      // Send the email as typed (empty string included) so clearing the
      // field in the editor actually removes the stored email; the backend
      // normalizes an empty string to NULL, mirroring update_profile.
      const response = await api.put(`/auth/users/${editId}`, {
        display_name: editDisplayName,
        email: editEmail,
      })
      setManagedUsers(previous => previous.map(item => item.id === editId ? response.data : item))
      setEditId(null)
      addToast(t('success.updated'), 'success')
    } catch (updateError: unknown) {
      setError(extractError(updateError, t('errors.updateFailed')))
    } finally {
      setUpdateLoading(false)
    }
  }

  const handleResetPassword = async (event: FormEvent) => {
    event.preventDefault()
    if (!resetPasswordUser) return

    setResetPasswordLoading(true)
    setError(null)
    try {
      await api.post('/users/reset-password', {
        user_id: resetPasswordUser.id,
        new_password: resetPasswordValue,
      })
      setResetPasswordModalOpen(false)
      setResetPasswordValue('')
      setResetPasswordUser(null)
      addToast(t('success.passwordReset'), 'success')
    } catch (resetError: unknown) {
      setError(extractError(resetError, t('errors.resetPasswordFailed')))
    } finally {
      setResetPasswordLoading(false)
    }
  }

  const editDialogRef = useRef<HTMLDivElement | null>(null)
  const createDialogRef = useRef<HTMLDivElement | null>(null)

  useModalFocusTrap(editDialogRef, editId != null, () => setEditId(null))
  useModalFocusTrap(createDialogRef, createModalOpen, () => {
    setCreateModalOpen(false)
    clearCreateForm()
    setError(null)
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-400">{t('title')}</h1>
          <p className="mt-1 text-sm font-medium text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
        </div>
        <button
          onClick={() => { setCreateModalOpen(true); setError(null) }}
          className="inline-flex items-center rounded-xl bg-brand px-5 py-2.5 font-medium text-white shadow-lg shadow-brand/25 transition-all duration-200 hover:scale-[1.02] hover:shadow-brand/40 active:scale-[0.98]"
        >
          <span className="mr-2">+</span>
          {t('create')}
        </button>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-4 text-red-600 dark:bg-red-900/30 dark:text-red-400">{error}</div>}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-indigo-600" />
        </div>
      ) : (
        <div className="glass-panel overflow-hidden rounded-xl">
          <table className="min-w-full divide-y divide-border dark:divide-white/5">
            <thead className="border-b border-border/50 bg-gray-50/50 dark:border-white/5 dark:bg-white/5">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{t('table.name')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{t('table.username')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{t('table.email')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-transparent dark:divide-white/5">
              {managedUsers.map(item => (
                <tr key={item.id}>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">
                    {item.display_name}
                    {role === 'admin' && item.id === user?.id && (
                      <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-800">{t('you')}</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{item.username}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{item.email || '-'}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setEditId(item.id)
                          setEditDisplayName(item.display_name)
                          setEditEmail(item.email || '')
                          setError(null)
                        }}
                        className="rounded px-3 py-1 text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-900/30"
                        aria-label={t('actions.editAria', { name: item.username })}
                        title={t('actions.editTitle')}
                      >{t('edit')}</button>
                      <button
                        onClick={() => {
                          setResetPasswordUser(item)
                          setResetPasswordModalOpen(true)
                          setResetPasswordValue('')
                          setError(null)
                        }}
                        disabled={role === 'admin' && item.id === user?.id}
                        className="rounded px-3 py-1 text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-900/30 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label={t('actions.resetPasswordAria', { name: item.username })}
                        title={role === 'admin' && item.id === user?.id ? t('actions.resetSelfTitle') : t('actions.resetPasswordTitle')}
                      >{t('actions.resetPassword')}</button>
                      <button
                        onClick={() => setDeleteState({ isOpen: true, user: item })}
                        disabled={role === 'admin' && item.id === user?.id}
                        className="rounded px-3 py-1 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label={t('actions.deleteAria', { name: item.username })}
                        title={role === 'admin' && item.id === user?.id ? t('actions.deleteSelfTitle') : t('actions.deleteTitle')}
                      >{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {managedUsers.length === 0 && (
            <div className="p-6 text-center text-gray-500 dark:text-gray-400">
              {t(role === 'teacher' ? 'noTeachers' : 'noAdmins')}
            </div>
          )}
        </div>
      )}

      {editId != null && (
        <div
          ref={editDialogRef}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-managed-user-title"
        >
          <div className="glass-card w-full max-w-md p-6">
            <h3 id="edit-managed-user-title" className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">{t('edit')}</h3>
            <div className="space-y-3">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.displayName')}
                <input value={editDisplayName} onChange={event => setEditDisplayName(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.email')}
                <input type="email" value={editEmail} onChange={event => setEditEmail(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setEditId(null)} disabled={updateLoading} className="rounded-lg px-4 py-2 text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">{t('cancel')}</button>
              <button onClick={handleUpdate} disabled={updateLoading} className="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50">{updateLoading ? t('security.saving', { ns: 'settings' }) : t('profile.save', { ns: 'settings' })}</button>
            </div>
          </div>
        </div>
      )}

      {createModalOpen && (
        <div
          ref={createDialogRef}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-managed-user-title"
        >
          <div className="glass-card w-full max-w-md p-6">
            <h3 id="create-managed-user-title" className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">{t('createTitle')}</h3>
            {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">{error}</div>}
            <form onSubmit={handleCreate} className="space-y-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.username')}
                <input id="username" name="username" value={newUsername} onChange={event => setNewUsername(event.target.value)} required autoComplete="username" className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder={t('placeholders.username')} />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.displayName')}
                <input id="displayName" name="displayName" value={newDisplayName} onChange={event => setNewDisplayName(event.target.value)} required autoComplete="name" className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder={t('placeholders.displayName')} />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.email')}
                <input id="email" name="email" type="email" value={newEmail} onChange={event => setNewEmail(event.target.value)} autoComplete="email" className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder={t('placeholders.email')} />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.password')}
                <input id="password" name="password" type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder={t('labels.passwordHint')} />
              </label>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('labels.confirmPassword')}
                <input id="confirmPassword" name="confirmPassword" type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:bg-gray-700 dark:text-gray-100" />
              </label>
              <div className="mt-6 flex justify-end gap-3">
                <button type="button" onClick={() => { setCreateModalOpen(false); clearCreateForm(); setError(null) }} disabled={createLoading} className="rounded-lg px-4 py-2 text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700">{t('cancel')}</button>
                <button type="submit" disabled={createLoading} className="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50">{createLoading ? t('security.saving', { ns: 'settings' }) : t('createBtn')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {resetPasswordModalOpen && resetPasswordUser && (
        <ResetPasswordModal
          user={resetPasswordUser}
          value={resetPasswordValue}
          loading={resetPasswordLoading}
          error={error}
          t={t}
          onChange={setResetPasswordValue}
          onClose={() => { setResetPasswordModalOpen(false); setResetPasswordValue(''); setResetPasswordUser(null); setError(null) }}
          onSubmit={handleResetPassword}
        />
      )}

      <ConfirmDialog
        isOpen={deleteState.isOpen}
        title={t('actions.deleteTitle')}
        description={t('deleteConfirm')}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        onConfirm={handleDelete}
        onClose={() => setDeleteState({ isOpen: false, user: null })}
        variant="danger"
        isLoading={deleteLoading}
      />
    </div>
  )
}
