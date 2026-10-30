import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import type { User, Board } from '../types'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { GuardianProfileModal } from '../components/students/GuardianProfileModal'
import { Sparkles, Volume2 } from 'lucide-react'

import { useNavigate } from 'react-router-dom'

export function Students() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const { t } = useTranslation(['students', 'settings'])
  const [students, setStudents] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editId, setEditId] = useState<number | null>(null)
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editUserType, setEditUserType] = useState<'student' | 'teacher' | 'admin'>('student')

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [guardianModalOpen, setGuardianModalOpen] = useState(false)
  const [selectedGuardianStudent, setSelectedGuardianStudent] = useState<User | null>(null)

  useEffect(() => {
    if (user && user.user_type === 'student') {
      navigate('/')
    }
  }, [user, navigate])

  const [newUsername, setNewUsername] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [createLoading, setCreateLoading] = useState(false)

  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [selectedStudent, setSelectedStudent] = useState<User | null>(null)
  const [availableBoards, setAvailableBoards] = useState<Board[]>([])
  const [assignedBoards, setAssignedBoards] = useState<Record<number, Board[]>>({})
  const [assignLoading, setAssignLoading] = useState(false)
  const [deleteState, setDeleteState] = useState<{ isOpen: boolean; student: User | null }>({ isOpen: false, student: null })

  const [resetPasswordModalOpen, setResetPasswordModalOpen] = useState(false)
  const [resetPasswordStudent, setResetPasswordStudent] = useState<User | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [resetPasswordLoading, setResetPasswordLoading] = useState(false)

  const [preferencesModalOpen, setPreferencesModalOpen] = useState(false)
  const [preferencesStudent, setPreferencesStudent] = useState<User | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [studentPreferences, setStudentPreferences] = useState<any>({ voice_mode_enabled: true })
  const [preferencesLoading, setPreferencesLoading] = useState(false)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await api.get('/auth/users', { params: { limit: 1000 } })
        const list: User[] = res.data
        const studentsList = list.filter(u => u.user_type === 'student')
        setStudents(studentsList)

        await Promise.all(studentsList.map(async (student) => {
          try {
            const assignedRes = await api.get('/boards/assigned', { params: { student_id: student.id } })
            setAssignedBoards(prev => ({ ...prev, [student.id]: assignedRes.data }))
          } catch {
            // Ignore errors for individual students
          }
        }));
      } catch (e: unknown) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const r = e as { response?: { data?: { detail?: any } } };
        const d = r.response?.data?.detail;
        let msg = t('errors.loadFailed');
        if (Array.isArray(d)) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          msg = d.map((err: any) => err.msg).join(', ');
        } else if (typeof d === 'string') {
          msg = d;
        } else if (d) {
          msg = JSON.stringify(d);
        }
        setError(msg)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [user, t])

  const loadAvailableBoards = async () => {
    try {
      const res = await api.get('/boards/', { params: { user_id: user?.id } })
      setAvailableBoards(res.data)
    } catch (e) {
      console.error('Failed to load boards:', e)
    }
  }

  const handleDeleteStudent = async () => {
    const s = deleteState.student
    if (!s) return

    try {
      await api.delete(`/auth/users/${s.id}`)
      setStudents(prev => prev.filter(x => x.id !== s.id))
      setDeleteState({ isOpen: false, student: null })
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.deleteFailed'))
      setDeleteState({ isOpen: false, student: null })
    }
  }

  const handleAssignBoard = async (boardId: number) => {
    if (!selectedStudent) return
    setAssignLoading(true)
    try {
      await api.post(`/boards/${boardId}/assign`, { student_id: selectedStudent.id })
      const assignedRes = await api.get('/boards/assigned', { params: { student_id: selectedStudent.id } })
      setAssignedBoards(prev => ({ ...prev, [selectedStudent.id]: assignedRes.data }))
      setAssignModalOpen(false)
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.assignFailed'))
    } finally {
      setAssignLoading(false)
    }
  }

  const handleUnassignBoard = async (studentId: number, boardId: number) => {
    try {
      await api.delete(`/boards/${boardId}/assign/${studentId}`)
      const assignedRes = await api.get('/boards/assigned', { params: { student_id: studentId } })
      setAssignedBoards(prev => ({ ...prev, [studentId]: assignedRes.data }))
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.unassignFailed'))
    }
  }

  const openAssignModal = async (student: User) => {
    setSelectedStudent(student)
    await loadAvailableBoards()
    setAssignModalOpen(true)
  }

  const openPreferencesModal = async (student: User) => {
    setPreferencesStudent(student)
    setPreferencesLoading(true)
    setPreferencesModalOpen(true)
    try {
      const res = await api.get(`/auth/users/${student.id}/preferences`)
      setStudentPreferences(res.data)
    } catch (e) {
      console.error(e)
      setStudentPreferences({ voice_mode_enabled: true })
    } finally {
      setPreferencesLoading(false)
    }
  }

  const saveStudentPreferences = async () => {
    if (!preferencesStudent) return
    setPreferencesLoading(true)
    try {
      await api.put(`/auth/users/${preferencesStudent.id}/preferences`, studentPreferences)
      setPreferencesModalOpen(false)
      setPreferencesStudent(null)
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.updateFailed'))
    } finally {
      setPreferencesLoading(false)
    }
  }

  const handleCreateStudent = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateLoading(true)
    setError(null)

    if (user?.user_type === 'admin' && newPassword !== confirmPassword) {
      setError(t('errors.passwordsDoNotMatch', { defaultValue: 'Passwords do not match' }))
      setCreateLoading(false)
      return
    }

    try {
      if (user?.user_type === 'admin') {
        await api.post('/auth/admin/create-user', {
          username: newUsername,
          password: newPassword,
          confirm_password: confirmPassword,
          display_name: newDisplayName,
          email: newEmail || undefined,
          user_type: 'student'
        })
      } else {
        await api.post('/auth/register', {
          username: newUsername,
          password: newPassword,
          display_name: newDisplayName,
          email: newEmail || undefined,
          user_type: 'student',
          created_by_teacher_id: user?.id
        })
      }

      const res = await api.get('/auth/users', { params: { limit: 1000 } })
      const list: User[] = res.data
      setStudents(list.filter(u => u.user_type === 'student'))

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

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetPasswordStudent) return
    setResetPasswordLoading(true)
    setError(null)
    try {
      await api.post('/users/reset-password', {
        user_id: resetPasswordStudent.id,
        new_password: resetPasswordValue
      })
      setResetPasswordModalOpen(false)
      setResetPasswordValue('')
      setResetPasswordStudent(null)
      // Optional: show success message
    } catch (e: unknown) {
      const errWithResponse = e as { response?: { data?: { detail?: string } } }
      setError(errWithResponse?.response?.data?.detail || t('errors.resetPasswordFailed', { defaultValue: 'Failed to reset password' }))
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
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.assigned')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{t('table.actions')}</th>
              </tr >
            </thead >
            <tbody className="divide-y divide-border dark:divide-white/5 bg-transparent">
              {students.map(s => (
                <tr key={s.id}>
                  <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">{s.display_name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{s.username}</td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    <div className="flex flex-wrap gap-2">
                      {(assignedBoards[s.id] || []).map(board => (
                        <span key={board.id} className="inline-flex items-center px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 text-xs">
                          {board.name}
                          <button
                            onClick={() => handleUnassignBoard(s.id, board.id)}
                            className="ml-1 text-indigo-500 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
                            aria-label={t('actions.unassignAria', { board: board.name })}
                            title={t('actions.unassignTitle')}
                          >×</button>
                        </span>
                      ))}
                      {(assignedBoards[s.id] || []).length === 0 && (
                        <span className="text-gray-400 dark:text-gray-500 text-xs">{t('noneAssigned')}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                    <div className="flex gap-2">
                      <button
                        onClick={() => openAssignModal(s)}
                        className="px-3 py-1 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30 rounded"
                        aria-label={t('actions.assignAria', { student: s.username })}
                        title={t('actions.assignTitle')}
                      >{t('assign')}</button>
                      <button
                        onClick={() => { setSelectedGuardianStudent(s); setGuardianModalOpen(true); }}
                        className="px-3 py-1 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded flex items-center gap-1"
                        title={t('guardianProfile', { defaultValue: 'Guardian Profile' })}
                        aria-label={t('guardianProfile', { defaultValue: 'Guardian Profile' })}
                      >
                        <Sparkles className="w-4 h-4" />
                        <span className="hidden sm:inline">AI</span>
                      </button>
                      <button
                        onClick={() => openPreferencesModal(s)}
                        className="px-3 py-1 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded flex items-center gap-1"
                        title={t('preferences', { defaultValue: 'Preferences' })}
                      >
                        <Volume2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => { setEditId(s.id); setEditDisplayName(s.display_name); setEditUserType(s.user_type); setError(null); }}
                        className="px-3 py-1 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded"
                        aria-label={t('actions.editAria', { student: s.username })}
                        title={t('actions.editTitle')}
                      >{t('edit')}</button>
                      <button
                        onClick={() => {
                          setResetPasswordStudent(s);
                          setResetPasswordModalOpen(true);
                          setResetPasswordValue('');
                          setError(null);
                        }}
                        className="px-3 py-1 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded"
                        aria-label={t('actions.resetPasswordAria', { student: s.username, defaultValue: `Reset password for ${s.username}` })}
                        title={t('actions.resetPasswordTitle', { defaultValue: 'Reset Password' })}
                      >{t('actions.resetPassword', { defaultValue: 'Reset Pwd' })}</button>
                      <button
                        onClick={() => setDeleteState({ isOpen: true, student: s })}
                        className="px-3 py-1 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                        aria-label={t('actions.deleteAria', { student: s.username })}
                        title={t('actions.deleteTitle')}
                      >{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table >
          {
            students.length === 0 && (
              <div className="p-6 text-center text-gray-500 dark:text-gray-400">{t('noStudents')}</div>
            )
          }
          {
            editId != null && (
              <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50" role="dialog" aria-modal="true">
                <div className="glass-card w-full max-w-md p-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('edit')}</h3>
                  {error && (
                    <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-4">
                      {error}
                    </div>
                  )}
                  <div className="space-y-3">
                    <input type="text" value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                    <select value={editUserType} onChange={(e) => setEditUserType(e.target.value as 'student' | 'teacher' | 'admin')} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                      <option value="student">{t('roles.student')}</option>
                      <option value="teacher">{t('roles.teacher')}</option>
                      <option value="admin">{t('roles.admin')}</option>
                    </select>
                  </div>
                  <div className="mt-4 flex justify-end gap-2">
                    <button onClick={() => setEditId(null)} className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">{t('cancel')}</button>
                    <button
                      onClick={async () => {
                        try {
                          const res = await api.put(`/auth/users/${editId}`, { display_name: editDisplayName, user_type: editUserType })
                          setStudents(prev => prev.map(x => x.id === editId ? res.data : x))
                          setEditId(null)
                        } catch (e: unknown) {
                          const errWithResponse = e as { response?: { data?: { detail?: string } } }
                          setError(errWithResponse?.response?.data?.detail || t('errors.updateFailed'))
                        }
                      }}
                      className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                    >{t('profile.save', { ns: 'settings' })}</button>
                  </div>
                </div>
              </div>
            )
          }

          {
            assignModalOpen && selectedStudent && (
              <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50" role="dialog" aria-modal="true">
                <div className="glass-card w-full max-w-md p-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                    {t('assignTitle', { name: selectedStudent.display_name })}
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {availableBoards.length === 0 ? (
                      <p className="text-gray-500 dark:text-gray-400 text-sm">{t('noBoardsAvail')}</p>
                    ) : (
                      availableBoards.map(board => {
                        const isAssigned = (assignedBoards[selectedStudent.id] || []).some(b => b.id === board.id)
                        return (
                          <button
                            key={board.id}
                            onClick={() => handleAssignBoard(board.id)}
                            disabled={isAssigned || assignLoading}
                            className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${isAssigned
                              ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed border-gray-200 dark:border-gray-600'
                              : 'hover:bg-indigo-50 dark:hover:bg-indigo-900/30 border-gray-200 dark:border-gray-600 hover:border-indigo-300 dark:hover:border-indigo-700'
                              }`}
                          >
                            <div className="font-medium text-gray-900 dark:text-gray-100">{board.name}</div>
                            {board.description && (
                              <div className="text-sm text-gray-500 dark:text-gray-400">{board.description}</div>
                            )}
                            {isAssigned && (
                              <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">{t('alreadyAssigned')}</div>
                            )}
                          </button>
                        )
                      })
                    )}
                  </div>
                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={() => setAssignModalOpen(false)}
                      className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                    >{t('close')}</button>
                  </div>
                </div>
              </div>
            )
          }

          {
            createModalOpen && (
              <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
                <div className="glass-card w-full max-w-md p-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                    {t('createTitle')}
                  </h3>
                  {error && (
                    <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-4">
                      {error}
                    </div>
                  )}
                  <form onSubmit={handleCreateStudent} className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.username')}</label>
                      <input
                        type="text"
                        value={newUsername}
                        onChange={(e) => setNewUsername(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        placeholder="student123"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.displayName')}</label>
                      <input
                        type="text"
                        value={newDisplayName}
                        onChange={(e) => setNewDisplayName(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        placeholder="Alex Smith"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.email')}</label>
                      <input
                        type="email"
                        value={newEmail}
                        onChange={(e) => setNewEmail(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        placeholder="alex@example.com"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.password')}</label>
                      <input
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        required
                        minLength={6}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        placeholder={t('labels.passwordHint')}
                      />
                    </div>

                    {user?.user_type === 'admin' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.confirmPassword', { defaultValue: 'Confirm Password' })}</label>
                        <input
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          required
                          minLength={6}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        />
                      </div>
                    )}

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
        </div >
      )
      }

      {
        resetPasswordModalOpen && resetPasswordStudent && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass-card w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {t('resetPasswordTitle', { name: resetPasswordStudent.display_name, defaultValue: `Reset Password for ${resetPasswordStudent.display_name}` })}
              </h3>
              {error && (
                <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm mb-4">
                  {error}
                </div>
              )}
              <form onSubmit={handleResetPassword} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('labels.newPassword', { defaultValue: 'New Password' })}</label>
                  <input
                    type="password"
                    value={resetPasswordValue}
                    onChange={(e) => setResetPasswordValue(e.target.value)}
                    required
                    minLength={8}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    placeholder={t('labels.passwordHint', { defaultValue: 'Min 8 chars, 1 uppercase, 1 lowercase, 1 number' })}
                  />
                </div>

                <div className="flex justify-end gap-3 mt-6">
                  <button
                    type="button"
                    onClick={() => {
                      setResetPasswordModalOpen(false)
                      setResetPasswordValue('')
                      setResetPasswordStudent(null)
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
                    {resetPasswordLoading ? t('security.saving', { ns: 'settings', defaultValue: 'Saving...' }) : t('actions.resetPassword', { defaultValue: 'Reset Password' })}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )
      }

      <GuardianProfileModal
        isOpen={guardianModalOpen}
        onClose={() => setGuardianModalOpen(false)}
        student={selectedGuardianStudent}
      />

      {
        preferencesModalOpen && preferencesStudent && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass-card w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                {t('preferencesTitle', { defaultValue: 'Preferences for' })} {preferencesStudent.display_name}
              </h3>

              {preferencesLoading ? (
                <div className="flex justify-center p-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-purple-50 rounded-lg">
                        <Volume2 className="w-5 h-5 text-purple-600" />
                      </div>
                      <div>
                        <p className="font-medium text-gray-900 dark:text-gray-100">{t('preferences.voiceMode', { defaultValue: 'Voice Mode' })}</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{t('preferences.voiceModeHelp', { defaultValue: 'Enable/disable voice features' })}</p>
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={studentPreferences.voice_mode_enabled}
                        onChange={(e) => setStudentPreferences({ ...studentPreferences, voice_mode_enabled: e.target.checked })}
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                    </label>
                  </div>

                  <div className="flex justify-end gap-3 mt-6">
                    <button
                      onClick={() => setPreferencesModalOpen(false)}
                      className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                    >
                      {t('cancel')}
                    </button>
                    <button
                      onClick={saveStudentPreferences}
                      className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                    >
                      {t('save')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      }

      <ConfirmDialog
        isOpen={deleteState.isOpen}
        onClose={() => setDeleteState({ isOpen: false, student: null })}
        onConfirm={handleDeleteStudent}
        title={`${t('delete')} ${deleteState.student?.username}?`}
        description={t('deleteConfirm', { name: deleteState.student?.username }) || `${t('delete')} ${deleteState.student?.username}?`}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="danger"
      />
    </div >
  )
}
