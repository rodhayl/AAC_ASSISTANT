import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ResetPasswordModal } from '../components/common/ResetPasswordModal'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog'
import api, { extractError } from '../lib/api'
import { walkPages } from '../lib/pagination'
import type { User } from '../types'
import { useAuthStore } from '../store/authStore'
import { useToastStore } from '../store/toastStore'
import { Button } from '../components/ui/button'

export type ManagedUserRole = 'teacher' | 'admin'

/**
 * Split text into literal and highlighted segments for an active search
 * term. Case-insensitive, and the term is regex-escaped so wildcards such
 * as "100%" match literally. Returns the original string when no term is
 * given so cells render as plain text.
 */
function splitHighlight(text: string, term: string): Array<{ text: string; highlight: boolean }> {
  if (!term) return [{ text, highlight: false }]
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = text.split(new RegExp(`(${escaped})`, 'ig'))
  return parts
    .filter(part => part !== '')
    .map(part => ({ text: part, highlight: part.toLowerCase() === term.toLowerCase() }))
}

interface UserManagementPageProps {
  role: ManagedUserRole
}

export function UserManagementPage({ role }: UserManagementPageProps) {
  const user = useAuthStore((state) => state.user)
  const addToast = useToastStore((state) => state.addToast)
  const namespace = role === 'teacher' ? 'teachers' : 'admins'
  const { t } = useTranslation([namespace, 'settings'])
  const [managedUsers, setManagedUsers] = useState<User[]>([])
  const [managedUsersContextKey, setManagedUsersContextKey] = useState<string | null>(null)
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

  // Admin-only view of every teacher's saved topics (management surface on
  // the /teachers page). Loaded separately so the section degrades cleanly
  // if the topic API is unavailable. Large collections are paginated via the
  // backend's limit/offset; the unpaginated total arrives as X-Total-Count.
  const showSavedTopics = role === 'teacher' && user?.user_type === 'admin'
  const managementContextKey = `${user?.id ?? 'anonymous'}:${user?.user_type ?? 'anonymous'}:${role}`
  const SAVED_TOPICS_PAGE_SIZES = [25, 50, 100] as const
  const [savedTopics, setSavedTopics] = useState<Array<{
    id: number
    user_id: number
    board: string
    topic: string
    created_by: string
    // Refreshed from the creator's current display name (stable identity).
    created_by_name?: string | null
    created_at: string | null
  }>>([])
  const [savedTopicsContextKey, setSavedTopicsContextKey] = useState<string | null>(null)
  const [savedTopicsError, setSavedTopicsError] = useState<string | null>(null)
  const [savedTopicsPage, setSavedTopicsPage] = useState(1)
  const [savedTopicsPageSize, setSavedTopicsPageSize] = useState<number>(25)
  const [savedTopicsTotal, setSavedTopicsTotal] = useState(0)
  const [savedTopicsSearch, setSavedTopicsSearch] = useState('')
  const [savedTopicsSearchQuery, setSavedTopicsSearchQuery] = useState('')
  const savedTopicsSearchEffectMountedRef = useRef(false)
  // Debounced copy of the search box: requests fire only after typing stops,
  // keeping keystrokes from hammering the API.
  useEffect(() => {
    if (!savedTopicsSearchEffectMountedRef.current) {
      savedTopicsSearchEffectMountedRef.current = true
      return
    }
    const timer = setTimeout(() => {
      setSavedTopicsSearchQuery(savedTopicsSearch.trim())
      setSavedTopicsPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [savedTopicsSearch])
  const [deleteTopicState, setDeleteTopicState] = useState<{ isOpen: boolean; topic: { id: number; topic: string } | null }>({
    isOpen: false,
    topic: null,
  })
  const [deleteTopicLoading, setDeleteTopicLoading] = useState(false)
  const [resetPasswordModalOpen, setResetPasswordModalOpen] = useState(false)
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [resetPasswordLoading, setResetPasswordLoading] = useState(false)
  const [updateLoading, setUpdateLoading] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const managedUsersRequestRef = useRef(0)
  const savedTopicsRequestRef = useRef(0)
  const managementMutationRequestRef = useRef(0)
  const mountedRef = useRef(false)
  const managementContextRef = useRef(managementContextKey)
  managementContextRef.current = managementContextKey

  const visibleManagedUsers = managedUsersContextKey === managementContextKey ? managedUsers : []
  const visibleSavedTopics = savedTopicsContextKey === managementContextKey ? savedTopics : []
  const loadUsers = useCallback(async () => {
    const contextKey = managementContextKey
    const requestId = ++managedUsersRequestRef.current
    const users = await walkPages<User>({
      pageSize: 1000,
      fetchPage: async (skip) => {
        if (
          !mountedRef.current ||
          requestId !== managedUsersRequestRef.current ||
          managementContextRef.current !== contextKey
        ) return []
        const response = await api.get('/auth/users', {
          params: {
            ...(skip > 0 ? { skip } : {}),
            limit: 1000,
            user_type: role,
          },
        })
        return response.data as User[]
      },
      isCancelled: () =>
        !mountedRef.current ||
        requestId !== managedUsersRequestRef.current ||
        managementContextRef.current !== contextKey,
    })
    if (
      !mountedRef.current ||
      requestId !== managedUsersRequestRef.current ||
      managementContextRef.current !== contextKey
    ) return
    setManagedUsers(users)
    setManagedUsersContextKey(contextKey)
  }, [managementContextKey, role])


  const loadSavedTopics = useCallback(async () => {
    if (!showSavedTopics) return
    const contextKey = managementContextKey
    const requestId = ++savedTopicsRequestRef.current
    try {
      const response = await api.get('/learning/topics/saved', {
        params: {
          scope: 'all',
          limit: savedTopicsPageSize,
          offset: (savedTopicsPage - 1) * savedTopicsPageSize,
          ...(savedTopicsSearchQuery ? { search: savedTopicsSearchQuery } : {}),
        },
      })
      if (
        !mountedRef.current ||
        requestId !== savedTopicsRequestRef.current ||
        managementContextRef.current !== contextKey
      ) return
      if (!Array.isArray(response.data)) {
        throw new Error('Invalid response format: expected array')
      }
      setSavedTopics(response.data)
      setSavedTopicsContextKey(contextKey)
      const total = Number(response.headers?.['x-total-count'])
      setSavedTopicsTotal(Number.isFinite(total) ? total : response.data.length)
      // A deletion on the last page can leave the page number past the end;
      // step back one page instead of showing an empty grid forever.
      if (response.data.length === 0 && savedTopicsPage > 1) {
        setSavedTopicsPage(savedTopicsPage - 1)
        return
      }
      setSavedTopicsError(null)
    } catch (loadError: unknown) {
      if (
        !mountedRef.current ||
        requestId !== savedTopicsRequestRef.current ||
        managementContextRef.current !== contextKey
      ) return
      console.error('Failed to load saved topics:', loadError)
      setSavedTopicsError(extractError(loadError, t('savedTopics.loadFailed')))
    }
  }, [showSavedTopics, t, savedTopicsPage, savedTopicsPageSize, savedTopicsSearchQuery, managementContextKey])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      managedUsersRequestRef.current += 1
      savedTopicsRequestRef.current += 1
      managementMutationRequestRef.current += 1
    }
  }, [])

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
      managedUsersRequestRef.current += 1
    }
  }, [loadUsers, managementContextKey, role, t])

  useEffect(() => {
    if (!showSavedTopics) {
      savedTopicsRequestRef.current += 1
      return
    }
    void loadSavedTopics()
    return () => {
      savedTopicsRequestRef.current += 1
    }
  }, [showSavedTopics, loadSavedTopics])

  const beginMutation = () => {
    const requestId = ++managementMutationRequestRef.current
    const contextKey = managementContextKey
    return {
      requestId,
      contextKey,
      isCurrent: () =>
        mountedRef.current &&
        requestId === managementMutationRequestRef.current &&
        managementContextRef.current === contextKey,
    }
  }

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

    const mutation = beginMutation()
    setDeleteLoading(true)
    try {
      await api.delete(`/auth/users/${selectedUser.id}`)
      if (!mutation.isCurrent()) return
      setManagedUsers(previous => previous.filter(item => item.id !== selectedUser.id))
      setManagedUsersContextKey(mutation.contextKey)
      addToast(t('success.deleted'), 'success')
    } catch (deleteError: unknown) {
      if (mutation.isCurrent()) {
        setError(extractError(deleteError, t('errors.deleteFailed')))
      }
    } finally {
      if (mutation.isCurrent()) {
        setDeleteLoading(false)
        setDeleteState({ isOpen: false, user: null })
      }
    }
  }

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      setError(t('errors.passwordsDoNotMatch'))
      return
    }

    const mutation = beginMutation()
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
      if (!mutation.isCurrent()) return
      clearCreateForm()
      setCreateModalOpen(false)
      addToast(t('success.created'), 'success')
    } catch (createError: unknown) {
      if (mutation.isCurrent()) {
        setError(extractError(createError, t('errors.createFailed')))
      }
    } finally {
      if (mutation.isCurrent()) setCreateLoading(false)
    }
  }

  const handleUpdate = async () => {
    if (!editId) return
    const mutation = beginMutation()
    setUpdateLoading(true)
    try {
      // Send the email as typed (empty string included) so clearing the
      // field in the editor actually removes the stored email; the backend
      // normalizes an empty string to NULL, mirroring update_profile.
      const response = await api.put(`/auth/users/${editId}`, {
        display_name: editDisplayName,
        email: editEmail,
      })
      if (!mutation.isCurrent()) return
      setManagedUsers(previous => previous.map(item => item.id === editId ? response.data : item))
      setManagedUsersContextKey(mutation.contextKey)
      setEditId(null)
      addToast(t('success.updated'), 'success')
    } catch (updateError: unknown) {
      if (mutation.isCurrent()) {
        setError(extractError(updateError, t('errors.updateFailed')))
      }
    } finally {
      if (mutation.isCurrent()) setUpdateLoading(false)
    }
  }

  const handleDeleteTopic = async () => {
    const selectedTopic = deleteTopicState.topic
    if (!selectedTopic) return

    const mutation = beginMutation()
    setDeleteTopicLoading(true)
    try {
      await api.delete(`/learning/topics/saved/${selectedTopic.id}`)
      // Refetch instead of filtering locally so the total and page position
      // stay correct when the deleted row was on the current page.
      await loadSavedTopics()
      if (!mutation.isCurrent()) return
      addToast(t('savedTopics.deleteSuccess'), 'success')
    } catch (deleteError: unknown) {
      if (mutation.isCurrent()) {
        setError(extractError(deleteError, t('savedTopics.deleteFailed')))
      }
    } finally {
      if (mutation.isCurrent()) {
        setDeleteTopicLoading(false)
        setDeleteTopicState({ isOpen: false, topic: null })
      }
    }
  }

  const handleResetPassword = async (event: FormEvent) => {
    event.preventDefault()
    if (!resetPasswordUser) return

    const mutation = beginMutation()
    setResetPasswordLoading(true)
    setError(null)
    try {
      await api.post('/users/reset-password', {
        user_id: resetPasswordUser.id,
        new_password: resetPasswordValue,
      })
      if (!mutation.isCurrent()) return
      setResetPasswordModalOpen(false)
      setResetPasswordValue('')
      setResetPasswordUser(null)
      addToast(t('success.passwordReset'), 'success')
    } catch (resetError: unknown) {
      if (mutation.isCurrent()) {
        setError(extractError(resetError, t('errors.resetPasswordFailed')))
      }
    } finally {
      if (mutation.isCurrent()) setResetPasswordLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-foreground to-muted-foreground">{t('title')}</h1>
          <p className="mt-1 text-sm font-medium text-muted-foreground">{t('subtitle')}</p>
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
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-brand" />
        </div>
      ) : (
        <div className="glass-panel overflow-hidden rounded-xl">
          <table className="min-w-full divide-y divide-border divide-border">
            <thead className="border-b border-border/50 bg-background/50">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('table.name')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('table.username')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('table.email')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-transparent divide-border">
              {visibleManagedUsers.map(item => (
                <tr key={item.id}>
                  <td className="px-6 py-4 text-sm text-foreground">
                    {item.display_name}
                    {role === 'admin' && item.id === user?.id && (
                      <span className="ml-2 rounded-full bg-brand/10 px-2 py-0.5 text-xs text-brand">{t('you')}</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{item.username}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{item.email || '-'}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setEditId(item.id)
                          setEditDisplayName(item.display_name)
                          setEditEmail(item.email || '')
                          setError(null)
                        }}
                        className="rounded px-3 py-1 text-brand hover:bg-brand/10 text-brand hover:bg-brand/20"
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
                        className="rounded px-3 py-1 text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-900/30 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label={t('actions.resetPasswordAria', { name: item.username })}
                        title={role === 'admin' && item.id === user?.id ? t('actions.resetSelfTitle') : t('actions.resetPasswordTitle')}
                      >{t('actions.resetPassword')}</button>
                      <button
                        onClick={() => setDeleteState({ isOpen: true, user: item })}
                        disabled={role === 'admin' && item.id === user?.id}
                        className="rounded px-3 py-1 text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                        aria-label={t('actions.deleteAria', { name: item.username })}
                        title={role === 'admin' && item.id === user?.id ? t('actions.deleteSelfTitle') : t('actions.deleteTitle')}
                      >{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleManagedUsers.length === 0 && (
            <div className="p-6 text-center text-muted-foreground">
              {t(role === 'teacher' ? 'noTeachers' : 'noAdmins')}
            </div>
          )}
        </div>
      )}

      {showSavedTopics && (
        <section className="space-y-3" data-testid="admin-saved-topics">
          <div>
            <h2 className="text-xl font-bold text-foreground">{t('savedTopics.title')}</h2>
            <p className="mt-1 text-sm font-medium text-muted-foreground">{t('savedTopics.subtitle')}</p>
          </div>
          {savedTopicsError && (
            <div className="rounded-lg bg-red-50 p-4 text-red-600 dark:bg-red-900/30 dark:text-red-400">
              {savedTopicsError}
            </div>
          )}
          <input
            type="search"
            value={savedTopicsSearch}
            onChange={(event) => setSavedTopicsSearch(event.target.value)}
            placeholder={t('savedTopics.searchPlaceholder')}
            aria-label={t('savedTopics.searchAria')}
            data-testid="saved-topics-search"
            className="w-full max-w-sm rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground"
          />
          {visibleSavedTopics.length === 0 ? (
            !savedTopicsError && (
              <div className="glass-panel rounded-xl p-6 text-center text-muted-foreground">
                {t('savedTopics.empty')}
              </div>
            )
          ) : (
            <div className="glass-panel overflow-hidden rounded-xl">
              <table className="min-w-full divide-y divide-border">
                <thead className="border-b border-border/50 bg-background/50">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('savedTopics.topic')}</th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('savedTopics.board')}</th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('savedTopics.teacher')}</th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('savedTopics.savedAt')}</th>
                    <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('table.actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border bg-transparent">
                  {visibleSavedTopics.map(item => (
                    <tr key={item.id}>
                      <td className="px-6 py-4 text-sm font-medium text-foreground">
                        {splitHighlight(item.topic, savedTopicsSearchQuery).map((segment, index) =>
                          segment.highlight
                            ? <mark key={index} className="rounded bg-yellow-100 px-0.5 text-inherit dark:bg-yellow-500/30">{segment.text}</mark>
                            : <span key={index}>{segment.text}</span>,
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {item.board
                          ? splitHighlight(item.board, savedTopicsSearchQuery).map((segment, index) =>
                              segment.highlight
                                ? <mark key={index} className="rounded bg-yellow-100 px-0.5 text-inherit dark:bg-yellow-500/30">{segment.text}</mark>
                                : <span key={index}>{segment.text}</span>,
                            )
                          : '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">{item.created_by_name || item.created_by}</td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {item.created_at ? new Date(item.created_at).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        <button
                          onClick={() => setDeleteTopicState({ isOpen: true, topic: { id: item.id, topic: item.topic } })}
                          className="rounded px-3 py-1 text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30"
                          aria-label={t('savedTopics.actions.deleteAria', { topic: item.topic })}
                          title={t('savedTopics.actions.deleteTitle')}
                        >{t('savedTopics.delete')}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/50 px-6 py-3 text-sm text-muted-foreground">
                <span data-testid="saved-topics-total">
                  {t('savedTopics.total', { count: savedTopicsTotal })}
                </span>
                <div className="flex items-center gap-2">
                  <select
                    aria-label={t('savedTopics.pageSizeAria')}
                    value={savedTopicsPageSize}
                    onChange={(event) => {
                      setSavedTopicsPageSize(Number(event.target.value))
                      setSavedTopicsPage(1)
                    }}
                    className="rounded-lg border border-border bg-surface px-2 py-1 text-sm text-foreground"
                  >
                    {SAVED_TOPICS_PAGE_SIZES.map(size => (
                      <option key={size} value={size}>{t('savedTopics.pageSize', { size })}</option>
                    ))}
                  </select>
                  <Button
                    variant="ghost"
                    onClick={() => setSavedTopicsPage(page => Math.max(1, page - 1))}
                    disabled={savedTopicsPage <= 1}
                    aria-label={t('savedTopics.prevPage')}
                  >{t('savedTopics.prevPage')}</Button>
                  <span data-testid="saved-topics-page-indicator">
                    {t('savedTopics.pageIndicator', {
                      page: savedTopicsPage,
                      pages: Math.max(1, Math.ceil(savedTopicsTotal / savedTopicsPageSize)),
                    })}
                  </span>
                  <Button
                    variant="ghost"
                    onClick={() => setSavedTopicsPage(page => page + 1)}
                    disabled={savedTopicsPage >= Math.ceil(savedTopicsTotal / savedTopicsPageSize)}
                    aria-label={t('savedTopics.nextPage')}
                  >{t('savedTopics.nextPage')}</Button>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {editId != null && (
        <Dialog open onOpenChange={(open) => { if (!open) setEditId(null) }}>
          <DialogContent showCloseButton={false} className="max-w-md p-6">
            <DialogHeader>
              <DialogTitle className="text-lg font-semibold text-foreground">{t('edit')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <label className="block text-sm font-medium text-foreground">
                {t('labels.displayName')}
                <input value={editDisplayName} onChange={event => setEditDisplayName(event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" />
              </label>
              <label className="block text-sm font-medium text-foreground">
                {t('labels.email')}
                <input type="email" value={editEmail} onChange={event => setEditEmail(event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditId(null)} disabled={updateLoading}>{t('cancel')}</Button>
              <Button onClick={handleUpdate} loading={updateLoading}>{updateLoading ? t('security.saving', { ns: 'settings' }) : t('profile.save', { ns: 'settings' })}</Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {createModalOpen && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setCreateModalOpen(false)
              clearCreateForm()
              setError(null)
            }
          }}
        >
          <DialogContent showCloseButton={false} className="max-w-md p-6">
            <DialogHeader>
              <DialogTitle className="text-lg font-semibold text-foreground">{t('createTitle')}</DialogTitle>
            </DialogHeader>
            {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">{error}</div>}
            <form onSubmit={handleCreate} className="space-y-4">
              <label className="block text-sm font-medium text-foreground">
                {t('labels.username')}
                <input id="username" name="username" value={newUsername} onChange={event => setNewUsername(event.target.value)} required autoComplete="username" className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" placeholder={t('placeholders.username')} />
              </label>
              <label className="block text-sm font-medium text-foreground">
                {t('labels.displayName')}
                <input id="displayName" name="displayName" value={newDisplayName} onChange={event => setNewDisplayName(event.target.value)} required autoComplete="name" className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" placeholder={t('placeholders.displayName')} />
              </label>
              <label className="block text-sm font-medium text-foreground">
                {t('labels.email')}
                <input id="email" name="email" type="email" value={newEmail} onChange={event => setNewEmail(event.target.value)} autoComplete="email" className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" placeholder={t('placeholders.email')} />
              </label>
              <label className="block text-sm font-medium text-foreground">
                {t('labels.password')}
                <input id="password" name="password" type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" placeholder={t('labels.passwordHint')} />
              </label>
              <label className="block text-sm font-medium text-foreground">
                {t('labels.confirmPassword')}
                <input id="confirmPassword" name="confirmPassword" type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required minLength={8} autoComplete="new-password" className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-foreground" />
              </label>
              <div className="mt-6 flex justify-end gap-3">
                <Button type="button" variant="ghost" onClick={() => { setCreateModalOpen(false); clearCreateForm(); setError(null) }} disabled={createLoading}>{t('cancel')}</Button>
                <Button type="submit" loading={createLoading}>{createLoading ? t('security.saving', { ns: 'settings' }) : t('createBtn')}</Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
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

      <ConfirmDialog
        isOpen={deleteTopicState.isOpen}
        title={t('savedTopics.actions.deleteTitle')}
        description={t('savedTopics.deleteConfirm')}
        confirmText={t('savedTopics.delete')}
        cancelText={t('cancel')}
        onConfirm={handleDeleteTopic}
        onClose={() => setDeleteTopicState({ isOpen: false, topic: null })}
        variant="danger"
        isLoading={deleteTopicLoading}
      />
    </div>
  )
}
