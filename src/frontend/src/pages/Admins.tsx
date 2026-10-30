import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import type { User } from '../types'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { useNavigate } from 'react-router-dom'

export function Admins() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const { t } = useTranslation(['admins', 'settings'])
  const [admins, setAdmins] = useState<User[]>([])
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

  const [deleteState, setDeleteState] = useState<{ isOpen: boolean; admin: User | null }>({ isOpen: false, admin: null })

  const [resetPasswordModalOpen, setResetPasswordModalOpen] = useState(false)
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [resetPasswordLoading, setResetPasswordLoading] = useState(false)

  useEffect(() => {
    if (user?.user_type !== 'admin') {
      navigate('/')
      return
    }

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await api.get('/auth/users', { params: { limit: 1000, user_type: 'admin' } })

        if (!Array.isArray(res.data)) {
          console.error('Expected array of admins but got:', res.data)
          throw new Error('Invalid response format: expected array')
        }

        const list: User[] = res.data
        setAdmins(list)
      } catch (e: unknown) {
        console.error('Failed to load admins:', e)

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const r = e as any;
        const d = r.response?.data?.detail;

        let msg = t('errors.loadFailed');
        if (Array.isArray(d)) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          msg = d.map((err: any) => err.msg).join(', ');
        } else if (typeof d === 'string') {
          msg = d;
        } else if (d) {
          msg = JSON.stringify(d);
        } else if (r.message) {
          msg = `${t('errors.loadFailed')}: ${r.message}`;
        }
        setError(msg)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [user, navigate, t])

  const handleDeleteAdmin = async () => {
    const s = deleteState.admin
    if (!s) return

    // Prevent deleting self
    if (s.id === user?.id) {
      setError(t('errors.deleteSelf'))
      setDeleteState({ isOpen: false, admin: null })
      return
    }

    try {
      await api.delete(`/auth/users/${s.id}`)
      setAdmins(prev => prev.filter(x => x.id !== s.id))
      setDeleteState({ isOpen: false, admin: null })
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.deleteFailed'))
      setDeleteState({ isOpen: false, admin: null })
    }
  }

  const handleCreateAdmin = async (e: React.FormEvent) => {
    e.preventDefault()
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
        user_type: 'admin'
      })

      const res = await api.get('/auth/users', { params: { limit: 1000, user_type: 'admin' } })
      const list: User[] = res.data
      setAdmins(list)

      setNewUsername('')
      setNewDisplayName('')
      setNewEmail('')
      setNewPassword('')
      setConfirmPassword('')
      setCreateModalOpen(false)
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.createFailed'))
    } finally {
      setCreateLoading(false)
    }
  }

  const handleUpdateAdmin = async () => {
    if (!editId) return
    try {
      const res = await api.put(`/auth/users/${editId}`, {
        display_name: editDisplayName,
        email: editEmail || undefined
      })
      setAdmins(prev => prev.map(x => x.id === editId ? res.data : x))
      setEditId(null)
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.updateFailed'))
    }
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetPasswordUser) return
    setResetPasswordLoading(true)
    setError(null)
    try {
      await api.post('/users/reset-password', {
        user_id: resetPasswordUser.id,
        new_password: resetPasswordValue
      })

      setResetPasswordModalOpen(false)
      setResetPasswordValue('')
      setResetPasswordUser(null)
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.resetPasswordFailed'))
    } finally {
      setResetPasswordLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-400 tracking-tight">{t('title')}</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 font-medium">{t('subtitle')}</p>
        </div>
        <button
          onClick={() => { setCreateModalOpen(true); setError(null); }}
          className="inline-flex items-center px-5 py-2.5 rounded-xl bg-brand text-white shadow-lg shadow-brand/25 hover:shadow-brand/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 font-medium"
        >
          <span className="mr-2">+</span>
          {t('create')}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-4 rounded-lg">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : (
        <div className="glass-panel rounded-xl overflow-hidden">
          <table className="min-w-full divide-y divide-border dark:divide-white/5">
            <thead className="bg-gray-50/50 dark:bg-white/5 border-b border-border/50 dark:border-white/5">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.name')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.username')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.email')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border dark:divide-white/5 bg-transparent">
              {admins.map(s => (
                <tr key={s.id}>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">{s.display_name} {s.id === user?.id && <span className="ml-2 text-xs bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded-full">{t('you')}</span>}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{s.username}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{s.email || '-'}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setEditId(s.id);
                          setEditDisplayName(s.display_name);
                          setEditEmail(s.email || '');
                          setError(null);
                        }}
                        className="px-3 py-1 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded"
                        aria-label={t('actions.editAria', { name: s.username })}
                        title={t('actions.editTitle')}
                      >{t('edit')}</button>
                      <button
                        onClick={() => {
                          setResetPasswordUser(s);
                          setResetPasswordModalOpen(true);
                          setResetPasswordValue('');
                          setError(null);
                        }}
                        className="px-3 py-1 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded"
                        aria-label={t('actions.resetPasswordAria', { name: s.username })}
                        title={t('actions.resetPasswordTitle')}
                      >{t('actions.resetPassword')}</button>
                      <button
                        onClick={() => setDeleteState({ isOpen: true, admin: s })}
                        className={`px-3 py-1 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded ${s.id === user?.id ? 'opacity-50 cursor-not-allowed' : ''}`}
                        aria-label={t('actions.deleteAria', { name: s.username })}
                        title={t('actions.deleteTitle')}
                        disabled={s.id === user?.id}
                      >{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table >
          {
            admins.length === 0 && (
              <div className="p-6 text-center text-gray-500 dark:text-gray-400">{t('noAdmins')}</div>
            )
          }
        </div >
      )
      }

      {/* Edit Modal */}
      {
        editId != null && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50" role="dialog" aria-modal="true">
            <div className="glass-card w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('edit')}</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.displayName')}</label>
                  <input type="text" value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.email')}</label>
                  <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                </div>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button onClick={() => setEditId(null)} className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">{t('cancel')}</button>
                <button
                  onClick={handleUpdateAdmin}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                >{t('profile.save', { ns: 'settings' })}</button>
              </div>
            </div>
          </div>
        )
      }

      {/* Create Modal */}
      {
        createModalOpen && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50" role="dialog" aria-modal="true">
            <div className="glass-card w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {t('createTitle')}
              </h3>
              {error && (
                <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-4">
                  {error}
                </div>
              )}
              <form onSubmit={handleCreateAdmin} className="space-y-4">
                <div>
                  <label htmlFor="username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.username')}</label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    required
                    autoComplete="username"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('placeholders.username')}
                  />
                </div>

                <div>
                  <label htmlFor="displayName" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.displayName')}</label>
                  <input
                    id="displayName"
                    name="displayName"
                    type="text"
                    value={newDisplayName}
                    onChange={(e) => setNewDisplayName(e.target.value)}
                    required
                    autoComplete="name"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('placeholders.displayName')}
                  />
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.email')}</label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    autoComplete="email"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('placeholders.email')}
                  />
                </div>

                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.password')}</label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('labels.passwordHint')}
                  />
                </div>

                <div>
                  <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.confirmPassword')}</label>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  />
                </div>

                <div className="flex justify-end gap-3 mt-6">
                  <button
                    type="button"
                    onClick={() => {
                      setCreateModalOpen(false)
                      setNewUsername('')
                      setNewDisplayName('')
                      setNewEmail('')
                      setNewPassword('')
                      setConfirmPassword('')
                      setError(null)
                    }}
                    className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                    disabled={createLoading}
                  >
                    {t('cancel')}
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                    disabled={createLoading}
                  >
                    {createLoading ? t('security.saving', { ns: 'settings' }) : t('createBtn')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )
      }

      {/* Reset Password Modal */}
      {
        resetPasswordModalOpen && resetPasswordUser && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass-card w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {t('resetPasswordTitle', { name: resetPasswordUser.display_name })}
              </h3>
              {error && (
                <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-4">
                  {error}
                </div>
              )}
              <form onSubmit={handleResetPassword} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.newPassword')}</label>
                  <input
                    type="password"
                    value={resetPasswordValue}
                    onChange={(e) => setResetPasswordValue(e.target.value)}
                    required
                    minLength={8}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('labels.passwordHint')}
                  />
                </div>

                <div className="flex justify-end gap-3 mt-6">
                  <button
                    type="button"
                    onClick={() => {
                      setResetPasswordModalOpen(false)
                      setResetPasswordValue('')
                      setResetPasswordUser(null)
                      setError(null)
                    }}
                    className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                    disabled={resetPasswordLoading}
                  >
                    {t('cancel')}
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50"
                    disabled={resetPasswordLoading}
                  >
                    {resetPasswordLoading ? t('security.saving', { ns: 'settings' }) : t('actions.resetPassword')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )
      }

      <ConfirmDialog
        isOpen={deleteState.isOpen}
        title={t('actions.deleteTitle')}
        description={t('actions.deleteConfirm', { name: deleteState.admin?.username })}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        onConfirm={handleDeleteAdmin}
        onClose={() => setDeleteState({ isOpen: false, admin: null })}
        variant="danger"
      />
    </div >
  )
}
