import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../store/authStore'
import api, { extractError } from '../lib/api'
import type { Board, StudentBoardSummary, User, UserPreferences } from '../types'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { StatusMessage } from '../components/ui/StatusMessage'
import { Toggle } from '../components/ui/Toggle'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { ResetPasswordModal } from '../components/common/ResetPasswordModal'
import { GuardianProfileModal } from '../components/students/GuardianProfileModal'
import { ChevronDown, Sparkles, Volume2 } from 'lucide-react'
import { LoadingState } from '../components/ui/LoadingState'
import { useToastStore } from '../store/toastStore'
import { FormLabel } from '@/components/ui/FormLabel'
import { Button } from '../components/ui/button';

type TriState = 'default' | 'true' | 'false'

interface CreateSafetyState {
  age: string
  filterLevel: 'default' | 'strict' | 'standard' | 'relaxed'
  forbiddenTopics: string
  triggerWords: string
  block_ai_chat: TriState
  block_board_ai: TriState
  block_custom_topics: TriState
  block_autogen_pictograms: TriState
  block_social_messaging: TriState
  sentinel_moderation: TriState
}

const DEFAULT_SAFETY: CreateSafetyState = {
  age: '',
  filterLevel: 'default',
  forbiddenTopics: '',
  triggerWords: '',
  block_ai_chat: 'default',
  block_board_ai: 'default',
  block_custom_topics: 'default',
  block_autogen_pictograms: 'default',
  block_social_messaging: 'default',
  sentinel_moderation: 'default',
}

// Mirrors the guardian-profile modal's feature-gate list and label keys.
const FEATURE_LOCK_FIELDS = [
  ['block_ai_chat', 'blockChat'],
  ['block_board_ai', 'blockBoardAI'],
  ['block_custom_topics', 'blockCustomTopics'],
  ['block_autogen_pictograms', 'blockAutogen'],
  ['block_social_messaging', 'blockSocial'],
] as const


export function Students() {
  const user = useAuthStore((state) => state.user)
  const addToast = useToastStore((state) => state.addToast)
  const { t } = useTranslation(['students', 'settings'])
  const [students, setStudents] = useState<StudentBoardSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editId, setEditId] = useState<number | null>(null)
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editUserType, setEditUserType] = useState<'student' | 'teacher' | 'admin'>('student')

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [guardianModalOpen, setGuardianModalOpen] = useState(false)
  const [selectedGuardianStudent, setSelectedGuardianStudent] = useState<User | null>(null)

  const [newUsername, setNewUsername] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [showSafetySection, setShowSafetySection] = useState(false)
  const [newSafety, setNewSafety] = useState<CreateSafetyState>(DEFAULT_SAFETY)

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
  const [studentPreferences, setStudentPreferences] = useState<Pick<UserPreferences, 'voice_mode_enabled'>>({ voice_mode_enabled: true })
  const [preferencesLoading, setPreferencesLoading] = useState(false)
  const studentsLoadRequestRef = useRef(0)

  const loadStudents = useCallback(async (rethrow = false) => {
    const requestId = ++studentsLoadRequestRef.current
    setLoading(true)
    setError(null)
    try {
      const res = await api.get('/auth/users/student-summaries', {
        // Use the backend's maximum page size: admins with large rosters must
        // not silently lose students beyond the old hardcoded 100. The backend
        // caps the page at 500 and this page has no pagination UI yet.
        params: { limit: 500 },
      })
      const summaries = res.data as StudentBoardSummary[]
      if (requestId !== studentsLoadRequestRef.current) return
      setStudents(summaries)
      setAssignedBoards(
        Object.fromEntries(
          summaries.map((student) => [student.id, student.assigned_boards ?? []]),
        ),
      )
    } catch (e: unknown) {
      if (requestId !== studentsLoadRequestRef.current) return
      setError(extractError(e, t('errors.loadFailed')))
      if (rethrow) throw e
    } finally {
      if (requestId === studentsLoadRequestRef.current) {
        setLoading(false)
      }
    }
  }, [t])

  useEffect(() => {
    void loadStudents()
    return () => {
      // Invalidate a roster response when the authenticated user changes or
      // the page unmounts; a late result must not repopulate another session.
      studentsLoadRequestRef.current += 1
    }
  }, [loadStudents, user])

  const loadAvailableBoards = async () => {
    try {
      // Admins may assign any teacher's board, so list everything for them;
      // teachers stay scoped to their own boards.
      const params = user?.user_type === 'admin' ? undefined : { user_id: user?.id }
      const res = await api.get('/boards/', { params })
      setAvailableBoards(res.data)
    } catch (e) {
      setError(extractError(e, t('errors.loadBoardsFailed')))
      console.error('Failed to load boards:', e)
    }
  }

  const handleDeleteStudent = async () => {
    // Only rendered inside the confirm dialog, which requires a student.
    const s = deleteState.student!

    try {
      await api.delete(`/auth/users/${s.id}`)
      setStudents(prev => prev.filter(x => x.id !== s.id))
      setDeleteState({ isOpen: false, student: null })
      addToast(t('success.deleted'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.deleteFailed')))
      setDeleteState({ isOpen: false, student: null })
    }
  }

  const handleAssignBoard = async (boardId: number) => {
    // Only rendered inside the assign modal, which requires a selected student.
    const studentId = selectedStudent!.id
    setAssignLoading(true)
    try {
      await api.post(`/boards/${boardId}/assign`, { student_id: studentId })
      const board = availableBoards.find((candidate) => candidate.id === boardId)
      if (board) {
        setAssignedBoards((prev) => {
          const current = prev[studentId] || []
          if (current.some((assignedBoard) => assignedBoard.id === board.id)) {
            return prev
          }
          return {
            ...prev,
            [studentId]: [...current, board],
          }
        })
      }
      setAssignModalOpen(false)
      addToast(t('success.boardAssigned'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.assignFailed')))
    } finally {
      setAssignLoading(false)
    }
  }

  const handleUnassignBoard = async (studentId: number, boardId: number) => {
    try {
      await api.delete(`/boards/${boardId}/assign/${studentId}`)
      setAssignedBoards((prev) => ({
        ...prev,
        [studentId]: (prev[studentId] || []).filter((board) => board.id !== boardId),
      }))
      addToast(t('success.boardUnassigned'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.unassignFailed')))
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
      setStudentPreferences({ voice_mode_enabled: res.data.voice_mode_enabled ?? true })
    } catch (e) {
      console.error(e)
      setStudentPreferences({ voice_mode_enabled: true })
      addToast(t('errors.profileLoadFailed'), 'error')
    } finally {
      setPreferencesLoading(false)
    }
  }

  const saveStudentPreferences = async () => {
    // Only rendered inside the preferences modal, which requires a student.
    setPreferencesLoading(true)
    try {
      await api.put(`/auth/users/${preferencesStudent!.id}/preferences`, studentPreferences)
      setPreferencesModalOpen(false)
      setPreferencesStudent(null)
      addToast(t('success.saved'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.updateFailed')))
    } finally {
      setPreferencesLoading(false)
    }
  }

  const handleCreateStudent = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateLoading(true)
    setError(null)

    if (user?.user_type === 'admin' && newPassword !== confirmPassword) {
      setError(t('errors.passwordsDoNotMatch'))
      setCreateLoading(false)
      return
    }

    // Only send safety configuration when the teacher/admin actually set
    // something: a plain create keeps the automatic age-based floor and the
    // admin global policy, with no guardian profile row.
    const triStateToBool = (value: TriState) => value === 'true' ? true : value === 'false' ? false : undefined
    const safety = showSafetySection && (
      newSafety.age !== '' ||
      newSafety.filterLevel !== 'default' ||
      newSafety.forbiddenTopics.trim() !== '' ||
      newSafety.triggerWords.trim() !== '' ||
      newSafety.block_ai_chat !== 'default' ||
      newSafety.block_board_ai !== 'default' ||
      newSafety.block_custom_topics !== 'default' ||
      newSafety.block_autogen_pictograms !== 'default' ||
      newSafety.block_social_messaging !== 'default' ||
      newSafety.sentinel_moderation !== 'default'
    )
      ? {
          ...(newSafety.age ? { age: Number(newSafety.age) } : {}),
          ...(newSafety.filterLevel !== 'default' ? { content_filter_level: newSafety.filterLevel } : {}),
          forbidden_topics: newSafety.forbiddenTopics.split('\n').map((s) => s.trim()).filter(Boolean),
          trigger_words: newSafety.triggerWords.split('\n').map((s) => s.trim()).filter(Boolean),
          block_ai_chat: triStateToBool(newSafety.block_ai_chat),
          block_board_ai: triStateToBool(newSafety.block_board_ai),
          block_custom_topics: triStateToBool(newSafety.block_custom_topics),
          block_autogen_pictograms: triStateToBool(newSafety.block_autogen_pictograms),
          block_social_messaging: triStateToBool(newSafety.block_social_messaging),
          sentinel_moderation: triStateToBool(newSafety.sentinel_moderation),
        }
      : undefined

    try {
      if (user?.user_type === 'admin') {
        await api.post('/auth/admin/create-user', {
          username: newUsername,
          password: newPassword,
          confirm_password: confirmPassword,
          display_name: newDisplayName,
          email: newEmail || undefined,
          user_type: 'student',
          ...(safety ? { safety } : {}),
        })
      } else {
        // This staff route creates the student and atomically adds the
        // authenticated teacher to the student's roster. Public registration
        // intentionally creates an unassigned account, so using it here made
        // newly created students disappear from the teacher's list.
        await api.post('/users/students', {
          username: newUsername,
          password: newPassword,
          display_name: newDisplayName,
          email: newEmail || undefined,
          user_type: 'student',
          ...(safety ? { safety } : {}),
        })
      }

      await loadStudents(true)

      setNewUsername('')
      setNewDisplayName('')
      setNewEmail('')
      setNewPassword('')
      setConfirmPassword('')
      setNewSafety(DEFAULT_SAFETY)
      setShowSafetySection(false)
      setCreateModalOpen(false)
      addToast(t('success.created'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.createFailed')))
    } finally {
      setCreateLoading(false)
    }
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    // Only rendered inside the reset-password modal, which requires a student.
    setResetPasswordLoading(true)
    setError(null)
    try {
      await api.post('/users/reset-password', {
        user_id: resetPasswordStudent!.id,
        new_password: resetPasswordValue
      })
      setResetPasswordModalOpen(false)
      setResetPasswordValue('')
      setResetPasswordStudent(null)
      addToast(t('success.passwordReset'), 'success')
    } catch (e: unknown) {
      setError(extractError(e, t('errors.resetPasswordFailed')))
    } finally {
      setResetPasswordLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-foreground to-muted-foreground tracking-tight">{t('title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground font-medium">{t('subtitle')}</p>
        </div>
        <Button
          onClick={() => { setCreateModalOpen(true); setError(null); }}
          className="shadow-lg shadow-brand/25 hover:shadow-brand/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 font-medium"
        >
          <span className="mr-2">+</span>
          {t('create')}
        </Button>
      </div>

      {error && (
        <StatusMessage variant="error">{error}</StatusMessage>
      )}

      {loading ? (
        <LoadingState label={t('loading')} />
      ) : (
        <div className="glass-panel rounded-xl overflow-hidden">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background/50 border-b border-border/50">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('table.name')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('table.username')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('table.assigned')}</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('table.actions')}</th>
              </tr >
            </thead >
            <tbody className="divide-y divide-border bg-transparent">
              {students.map(s => (
                <tr key={s.id}>
                  <td className="px-6 py-4 text-sm text-foreground">{s.display_name}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">{s.username}</td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    <div className="flex flex-wrap gap-2">
                      {(assignedBoards[s.id] || []).map(board => (
                        <span key={board.id} className="inline-flex items-center px-2 py-1 rounded-md bg-brand/10 text-brand text-xs">
                          {board.name}
                          <button
                            onClick={() => handleUnassignBoard(s.id, board.id)}
                            className="ml-1 text-brand hover:text-brand"
                            aria-label={t('actions.unassignAria', { board: board.name })}
                            title={t('actions.unassignTitle')}
                          >×</button>
                        </span>
                      ))}
                      {(assignedBoards[s.id] || []).length === 0 && (
                        <span className="text-muted-foreground text-xs">{t('noneAssigned')}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    <div className="flex gap-2">
                      <button
                        onClick={() => openAssignModal(s)}
                        className="px-3 py-1 text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30 rounded"
                        aria-label={t('actions.assignAria', { student: s.username })}
                        title={t('actions.assignTitle')}
                      >{t('assign')}</button>
                      <button
                        onClick={() => { setSelectedGuardianStudent(s); setGuardianModalOpen(true); }}
                        className="px-3 py-1 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded flex items-center gap-1"
                        title={t('guardianProfile')}
                        aria-label={t('guardianProfile')}
                      >
                        <Sparkles className="w-4 h-4" />
                        <span className="hidden sm:inline">{t('ai')}</span>
                      </button>
                      <button
                        onClick={() => openPreferencesModal(s)}
                        className="px-3 py-1 text-muted-foreground hover:bg-surface-hover rounded flex items-center gap-1"
                        title={t('preferences.title')}
                        aria-label={t('preferences.title')}
                      >
                        <Volume2 className="w-4 h-4" />
                      </button>
                      {user?.user_type === 'admin' && (
                        <button
                          onClick={() => { setEditId(s.id); setEditDisplayName(s.display_name); setEditUserType(s.user_type); setError(null); }}
                          className="px-3 py-1 text-brand hover:bg-brand/20 rounded"
                          aria-label={t('actions.editAria', { student: s.username })}
                          title={t('actions.editTitle')}
                        >{t('edit')}</button>
                      )}
                      <button
                        onClick={() => {
                          setResetPasswordStudent(s);
                          setResetPasswordModalOpen(true);
                          setResetPasswordValue('');
                          setError(null);
                        }}
                        className="px-3 py-1 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded"
                        aria-label={t('actions.resetPasswordAria', { student: s.username })}
                        title={t('actions.resetPasswordTitle')}
                      >{t('actions.resetPassword')}</button>
                      {user?.user_type === 'admin' && (
                        <button
                          onClick={() => setDeleteState({ isOpen: true, student: s })}
                          className="px-3 py-1 text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                          aria-label={t('actions.deleteAria', { student: s.username })}
                          title={t('actions.deleteTitle')}
                        >{t('delete')}</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table >
          {
            students.length === 0 && (
              <div className="p-6 text-center text-muted-foreground">{t('noStudents')}</div>
            )
          }
          {
            editId != null && (
              <Dialog open onOpenChange={(open) => { if (!open) setEditId(null) }}>
                <DialogContent showCloseButton={false} className="max-w-md p-6">
                  <DialogHeader>
                    <DialogTitle className="text-lg font-semibold text-foreground">{t('edit')}</DialogTitle>
                  </DialogHeader>
                  {error && <StatusMessage variant="error" className="mb-4">{error}</StatusMessage>}
                  <div className="space-y-3">
                    <FormLabel htmlFor="edit-student-display-name">
                      {t('labels.displayName')}
                    </FormLabel>
                    <input id="edit-student-display-name" type="text" value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} required className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground" />
                    <FormLabel>
                      {t('role')}
                    </FormLabel>
                    <Select value={editUserType} onValueChange={(next) => { if (next != null) setEditUserType(next as 'student' | 'teacher' | 'admin'); }}>
                      <SelectTrigger aria-label={t('role')} name="edit_student_role" className="w-full text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="student">{t('roles.student')}</SelectItem>
                        <SelectItem value="teacher">{t('roles.teacher')}</SelectItem>
                        <SelectItem value="admin">{t('roles.admin')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="mt-4 flex justify-end gap-2">
                    <Button onClick={() => setEditId(null)} variant="ghost">{t('cancel')}</Button>
                    <Button
                      onClick={async () => {
                        try {
                          const res = await api.put(`/auth/users/${editId}`, { display_name: editDisplayName, user_type: editUserType })
                          // The PUT response is a bare User without the
                          // assigned_boards payload from the summaries endpoint;
                          // preserve the existing row's board chips.
                          setStudents(prev => prev.map(x => x.id === editId ? { ...res.data, assigned_boards: x.assigned_boards ?? [] } : x))
                          setEditId(null)
                          addToast(t('success.updated'), 'success')
                        } catch (e: unknown) {
                          setError(extractError(e, t('errors.updateFailed')))
                        }
                      }}
                    >{t('profile.save', { ns: 'settings' })}</Button>
                  </div>
                </DialogContent>
              </Dialog>
            )
          }

          {
            assignModalOpen && selectedStudent && (
              <Dialog open onOpenChange={(open) => { if (!open) setAssignModalOpen(false) }}>
                <DialogContent showCloseButton={false} className="max-w-md p-6">
                  <DialogHeader>
                    <DialogTitle className="text-lg font-semibold text-foreground">
                      {t('assignTitle', { name: selectedStudent.display_name })}
                    </DialogTitle>
                  </DialogHeader>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {availableBoards.length === 0 ? (
                      <p className="text-muted-foreground text-sm">{t('noBoardsAvail')}</p>
                    ) : (
                      availableBoards.map(board => {
                        const isAssigned = (assignedBoards[selectedStudent.id] || []).some(b => b.id === board.id)
                        return (
                          <button
                            key={board.id}
                            onClick={() => handleAssignBoard(board.id)}
                            disabled={isAssigned || assignLoading}
                            className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${isAssigned
                              ? 'bg-muted text-muted-foreground cursor-not-allowed border-border'
                              : 'hover:bg-brand/20 border-border hover:border-brand'
                              }`}
                          >
                            <div className="font-medium text-foreground">{board.name}</div>
                            {board.description && (
                              <div className="text-sm text-muted-foreground">{board.description}</div>
                            )}
                            {isAssigned && (
                              <div className="text-xs text-muted-foreground mt-1">{t('alreadyAssigned')}</div>
                            )}
                          </button>
                        )
                      })
                    )}
                  </div>
                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={() => setAssignModalOpen(false)}
                      className="px-4 py-2 text-foreground hover:bg-surface-hover rounded-lg"
                    >{t('close')}</button>
                  </div>
                </DialogContent>
              </Dialog>
            )
          }

          {
            createModalOpen && (
              <Dialog
                open
                onOpenChange={(open) => {
                  if (!open) {
                    setCreateModalOpen(false)
                    setNewUsername('')
                    setNewDisplayName('')
                    setNewEmail('')
                    setNewPassword('')
                    setConfirmPassword('')
                    setNewSafety(DEFAULT_SAFETY)
                    setShowSafetySection(false)
                    setError(null)
                  }
                }}
              >
                {/* The safety section can grow the form taller than the
                    viewport; the modal scrolls internally so the submit
                    button stays reachable on small screens. */}
                <DialogContent showCloseButton={false} className="max-w-md p-6 max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle className="text-lg font-semibold text-foreground">
                      {t('createTitle')}
                    </DialogTitle>
                  </DialogHeader>
                  {error && <StatusMessage variant="error" className="mb-4">{error}</StatusMessage>}
                  <form onSubmit={handleCreateStudent} className="space-y-4">
                    <div>
                      <FormLabel htmlFor="create-student-username">{t('labels.username')}</FormLabel>
                      <input
                        id="create-student-username"
                        type="text"
                        value={newUsername}
                        onChange={(e) => setNewUsername(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                        placeholder={t('placeholders.username')}
                      />
                    </div>

                    <div>
                      <FormLabel htmlFor="create-student-display-name">{t('labels.displayName')}</FormLabel>
                      <input
                        id="create-student-display-name"
                        type="text"
                        value={newDisplayName}
                        onChange={(e) => setNewDisplayName(e.target.value)}
                        required
                        className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                        placeholder={t('placeholders.displayName')}
                      />
                    </div>

                    <div>
                      <FormLabel htmlFor="create-student-email">{t('labels.email')}</FormLabel>
                      <input
                        id="create-student-email"
                        type="email"
                        value={newEmail}
                        onChange={(e) => setNewEmail(e.target.value)}
                        className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                        placeholder={t('placeholders.email')}
                      />
                    </div>

                    <div>
                      <FormLabel htmlFor="create-student-password">{t('labels.password')}</FormLabel>
                      <input
                        id="create-student-password"
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        required
                        minLength={8}
                        className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                        placeholder={t('labels.passwordHint')}
                      />
                    </div>

                    {user?.user_type === 'admin' && (
                      <div>
                        <FormLabel htmlFor="create-student-confirm-password">{t('labels.confirmPassword')}</FormLabel>
                        <input
                          id="create-student-confirm-password"
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          required
                          minLength={8}
                          className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                        />
                      </div>
                    )}

                    <div className="rounded-lg border border-border p-3">
                      <button
                        type="button"
                        onClick={() => setShowSafetySection((visible) => !visible)}
                        aria-expanded={showSafetySection}
                        className="flex w-full items-center justify-between text-sm font-semibold text-foreground"
                      >
                        <span>{t('createSafety')}</span>
                        <ChevronDown className={`w-4 h-4 transition-transform ${showSafetySection ? 'rotate-180' : ''}`} />
                      </button>
                      {showSafetySection && (
                        <div className="mt-3 space-y-3 border-t border-border pt-3" data-testid="create-safety-section">
                          <p className="text-xs text-muted-foreground">{t('createSafetyHelp')}</p>
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <FormLabel htmlFor="create-student-age">{t('age')}</FormLabel>
                              <input
                                id="create-student-age"
                                type="number"
                                min={1}
                                max={100}
                                value={newSafety.age}
                                onChange={(e) => setNewSafety({ ...newSafety, age: e.target.value })}
                                className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground"
                              />
                            </div>
                            <div>
                              <FormLabel htmlFor="create-student-filter-level">{t('contentFilterLevel')}</FormLabel>
                              <select
                                id="create-student-filter-level"
                                value={newSafety.filterLevel}
                                onChange={(e) => setNewSafety({ ...newSafety, filterLevel: e.target.value as CreateSafetyState['filterLevel'] })}
                                className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground"
                              >
                                <option value="default">{t('triStateDefault')}</option>
                                <option value="strict">{t('strict')}</option>
                                <option value="standard">{t('standard')}</option>
                                <option value="relaxed">{t('relaxed')}</option>
                              </select>
                            </div>
                          </div>
                          <div>
                            <FormLabel htmlFor="create-student-forbidden-topics">{t('forbiddenTopics')}</FormLabel>
                            <textarea
                              id="create-student-forbidden-topics"
                              rows={2}
                              value={newSafety.forbiddenTopics}
                              onChange={(e) => setNewSafety({ ...newSafety, forbiddenTopics: e.target.value })}
                              placeholder="astronomía"
                              className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground font-mono text-sm"
                            />
                          </div>
                          <div>
                            <FormLabel htmlFor="create-student-trigger-words">{t('triggerWords')}</FormLabel>
                            <textarea
                              id="create-student-trigger-words"
                              rows={2}
                              value={newSafety.triggerWords}
                              onChange={(e) => setNewSafety({ ...newSafety, triggerWords: e.target.value })}
                              placeholder="guerra"
                              className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground font-mono text-sm"
                            />
                          </div>
                          <div>
                            <span className="block text-sm font-medium text-foreground">{t('featureGates')}</span>
                            <p className="text-xs text-muted-foreground mt-0.5">{t('featureGatesHelp')}</p>
                          </div>
                          {FEATURE_LOCK_FIELDS.map(([key, labelKey]) => (
                            <div key={key} className="flex items-center justify-between gap-2 text-sm">
                              <span className="text-foreground">{t(labelKey)}</span>
                              <select
                                value={newSafety[key]}
                                onChange={(e) => setNewSafety({ ...newSafety, [key]: e.target.value as TriState })}
                                className="w-36 px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm"
                              >
                                <option value="default">{t('triStateDefault')}</option>
                                <option value="true">{t('triStateOn')}</option>
                                <option value="false">{t('triStateOff')}</option>
                              </select>
                            </div>
                          ))}
                          <div className="flex items-center justify-between gap-2 text-sm">
                            <span className="text-foreground">{t('sentinel')}</span>
                            <select
                              value={newSafety.sentinel_moderation}
                              onChange={(e) => setNewSafety({ ...newSafety, sentinel_moderation: e.target.value as TriState })}
                              className="w-36 px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm"
                            >
                              <option value="default">{t('triStateDefault')}</option>
                              <option value="true">{t('triStateOn')}</option>
                              <option value="false">{t('triStateOff')}</option>
                            </select>
                          </div>
                        </div>
                      )}
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
                          setNewSafety(DEFAULT_SAFETY)
                          setShowSafetySection(false)
                          setError(null)
                        }}
                        className="px-4 py-2 text-foreground hover:bg-surface-hover rounded-lg"
                        disabled={createLoading}
                      >
                        {t('cancel')}
                      </button>
                      <Button type="submit" disabled={createLoading}>
                        {createLoading ? t('security.saving', { ns: 'settings' }) : t('createBtn')}
                      </Button>
                    </div>
                  </form>
                </DialogContent>
              </Dialog>
            )
          }
        </div >
      )
      }

      {resetPasswordModalOpen && resetPasswordStudent && (
        <ResetPasswordModal
          user={resetPasswordStudent}
          value={resetPasswordValue}
          loading={resetPasswordLoading}
          error={error}
          t={t}
          onChange={setResetPasswordValue}
          onClose={() => { setResetPasswordModalOpen(false); setResetPasswordValue(''); setResetPasswordStudent(null); setError(null) }}
          onSubmit={handleResetPassword}
        />
      )}

      <GuardianProfileModal
        isOpen={guardianModalOpen}
        onClose={() => setGuardianModalOpen(false)}
        student={selectedGuardianStudent}
      />

      {
        preferencesModalOpen && preferencesStudent && (
          <Dialog open onOpenChange={(open) => { if (!open) setPreferencesModalOpen(false) }}>
            <DialogContent showCloseButton={false} className="max-w-md p-6">
              <DialogHeader>
                <DialogTitle className="text-lg font-semibold text-foreground">
                  {t('preferencesTitle')} {preferencesStudent.display_name}
                </DialogTitle>
              </DialogHeader>

              {preferencesLoading ? (
                <LoadingState size="sm" label={t('loading')} className="h-auto p-4" />
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-background/50 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                        <Volume2 className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{t('preferences.voiceMode')}</p>
                        <p className="text-sm text-muted-foreground">{t('preferences.voiceModeHelp')}</p>
                      </div>
                    </div>
                    <Toggle
                      checked={studentPreferences.voice_mode_enabled}
                      label={t('preferences.voiceMode')}
                      onChange={(checked) => setStudentPreferences({ ...studentPreferences, voice_mode_enabled: checked })}
                    />
                  </div>

                  <div className="flex justify-end gap-3 mt-6">
                    <button
                      onClick={() => setPreferencesModalOpen(false)}
                      className="px-4 py-2 text-foreground hover:bg-surface-hover rounded-lg"
                    >
                      {t('cancel')}
                    </button>
                    <Button onClick={saveStudentPreferences}>
                      {t('save')}
                    </Button>
                  </div>
                </div>
              )}
            </DialogContent>
          </Dialog>
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
