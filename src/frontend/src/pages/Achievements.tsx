import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Trophy, Star, Lock, CheckCircle, Settings, Plus, Pencil, Trash2, Award, X, Users } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import api, { extractError } from '../lib/api'
import type { Achievement, AchievementFull, User } from '../types'
import { useTranslation } from 'react-i18next'
import { Button } from '../components/ui/button';
import { StatusMessage } from '../components/ui/StatusMessage';
import { IconButton } from '../components/ui/icon-button';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '../components/ui/dialog';
import {
  localizeAchievementDescription,
  localizeAchievementName,
} from '../lib/achievementLocalization'

import { SectionTitle } from '@/components/ui/SectionTitle';
import { FormLabel } from '@/components/ui/FormLabel';

interface AchievementFormData {
  name: string;
  description: string;
  category: string;
  points: number;
  icon: string;
  target_user_id?: number | null;
  criteria_type?: string | null;
  criteria_value?: number | null;
}

const EMOJI_OPTIONS = ['🏆', '⭐', '🎯', '🔥', '📚', '⚡', '🌟', '🎤', '📖', '💪', '🎨', '🎮', '🚀', '💎', '👑'];


export function Achievements() {
  const user = useAuthStore((state) => state.user)
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [allAchievements, setAllAchievements] = useState<AchievementFull[]>([])
  const [points, setPoints] = useState<number>(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showManage, setShowManage] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [editingAchievement, setEditingAchievement] = useState<AchievementFull | null>(null)
  const [showAwardModal, setShowAwardModal] = useState(false)
  const [awardingAchievementId, setAwardingAchievementId] = useState<number | null>(null)
  const [students, setStudents] = useState<User[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [criteriaTypes, setCriteriaTypes] = useState<string[]>([])
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null)
  const [studentSearch, setStudentSearch] = useState('')
  const [formData, setFormData] = useState<AchievementFormData>({
    name: '',
    description: '',
    category: 'custom',
    points: 10,
    icon: '🏆',
    target_user_id: null,
    criteria_type: null,
    criteria_value: null,
  })
  const dataRequestRef = useRef(0)
  const checkRequestRef = useRef(0)
  const managementRequestRef = useRef(0)
  const userContextRef = useRef('')
  const [dataContextKey, setDataContextKey] = useState<string | null>(null)
  const [managementContextKey, setManagementContextKey] = useState<string | null>(null)
  const { t } = useTranslation('achievements')

  const userContextKey = `${user?.id ?? 'anonymous'}:${user?.user_type ?? 'anonymous'}`
  userContextRef.current = userContextKey
  const visibleAchievements = dataContextKey === userContextKey ? achievements : []
  const visiblePoints = dataContextKey === userContextKey ? points : 0
  const visibleAllAchievements = managementContextKey === userContextKey ? allAchievements : []
  const visibleStudents = useMemo(
    () => managementContextKey === userContextKey ? students : [],
    [managementContextKey, students, userContextKey],
  )
  const visibleCategories = managementContextKey === userContextKey ? categories : []
  const visibleCriteriaTypes = managementContextKey === userContextKey ? criteriaTypes : []
  const isCurrentContext = (contextKey: string) => userContextRef.current === contextKey

  const filteredStudents = useMemo(() => {
    const search = studentSearch.trim().toLowerCase()
    if (!search) return visibleStudents
    return visibleStudents.filter((student) =>
      student.display_name.toLowerCase().includes(search) ||
      student.username.toLowerCase().includes(search),
    )
  }, [studentSearch, visibleStudents])

  const isTeacherOrAdmin = user?.user_type === 'teacher' || user?.user_type === 'admin'

  const loadData = useCallback(async () => {
    const contextKey = userContextKey
    const requestId = ++dataRequestRef.current
    if (!user?.id) {
      setAchievements([])
      setPoints(0)
      setDataContextKey(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [achRes, ptsRes] = await Promise.all([
        api.get(`/achievements/user/${user.id}`),
        api.get(`/achievements/user/${user.id}/points`)
      ])
      if (requestId !== dataRequestRef.current || !isCurrentContext(contextKey)) return
      if (!Array.isArray(achRes.data) || typeof ptsRes.data !== 'number') {
        throw new Error('Invalid achievements response format')
      }
      setAchievements(achRes.data)
      setPoints(ptsRes.data)
      setDataContextKey(contextKey)
    } catch (e: unknown) {
      if (requestId === dataRequestRef.current && isCurrentContext(contextKey)) {
        setError(extractError(e, t('errors.loadFailed')))
      }
    } finally {
      if (requestId === dataRequestRef.current && isCurrentContext(contextKey)) {
        setLoading(false)
      }
    }
  }, [t, user?.id, userContextKey])

  const loadAllStudents = async (): Promise<User[]> => {
    const loaded: User[] = []
    let skip = 0
    const pageSize = 500
    while (true) {
      const response = skip === 0
        ? await api.get('/users/students')
        : await api.get('/users/students', { params: { skip, limit: pageSize } })
      if (!Array.isArray(response.data)) {
        throw new Error('Invalid response format: expected array')
      }
      loaded.push(...(response.data as User[]))
      if (response.data.length < pageSize) return loaded
      skip += response.data.length
    }
  }

  const loadManagementData = useCallback(async () => {
    const contextKey = userContextKey
    const requestId = ++managementRequestRef.current
    setError(null)

    const labels = ['all achievements', 'students', 'categories', 'criteria types']
    const requests = [
      api.get('/achievements/'),
      loadAllStudents().then((data) => ({ data })),
      api.get('/achievements/categories'),
      api.get('/achievements/criteria-types'),
    ]
    const results = await Promise.allSettled(requests)
    if (requestId !== managementRequestRef.current || !isCurrentContext(contextKey)) return

    const [achievementsResult, studentsResult, categoriesResult, criteriaTypesResult] = results
    if (achievementsResult.status === 'fulfilled') {
      if (!Array.isArray(achievementsResult.value.data)) {
        throw new Error('Invalid response format: expected array')
      }
      setAllAchievements(achievementsResult.value.data)
    }
    if (studentsResult.status === 'fulfilled') setStudents(studentsResult.value.data)
    if (categoriesResult.status === 'fulfilled') {
      if (!Array.isArray(categoriesResult.value.data)) {
        throw new Error('Invalid response format: expected array')
      }
      setCategories(categoriesResult.value.data)
    }
    if (criteriaTypesResult.status === 'fulfilled') {
      if (!Array.isArray(criteriaTypesResult.value.data)) {
        throw new Error('Invalid response format: expected array')
      }
      setCriteriaTypes(criteriaTypesResult.value.data)
    }
    setManagementContextKey(contextKey)

    const failed = results.find((result) => result.status === 'rejected')
    if (failed?.status === 'rejected') {
      const failedIndex = results.indexOf(failed)
      console.error(`Failed to load ${labels[failedIndex]}`, failed.reason)
      setError(t('errors.managementLoadFailed'))
    }
  }, [t, userContextKey])

  useEffect(() => {
    void loadData()
    return () => {
      dataRequestRef.current += 1
      checkRequestRef.current += 1
    }
  }, [loadData])

  useEffect(() => {
    if (!showManage || !user) {
      managementRequestRef.current += 1
      return
    }
    void loadManagementData()
    return () => {
      managementRequestRef.current += 1
    }
  }, [showManage, loadManagementData, user])

  const handleCheck = async () => {
    if (!user) return
    const contextKey = userContextKey
    const requestId = ++checkRequestRef.current
    setLoading(true)
    setError(null)
    try {
      await api.post(`/achievements/user/${user.id}/check`)
      if (requestId !== checkRequestRef.current || !isCurrentContext(contextKey)) return
      await loadData()
    } catch (e: unknown) {
      if (requestId === checkRequestRef.current && isCurrentContext(contextKey)) {
        setError(extractError(e, t('errors.checkFailed')))
      }
    } finally {
      if (requestId === checkRequestRef.current && isCurrentContext(contextKey)) {
        setLoading(false)
      }
    }
  }

  const handleCreate = async () => {
    const contextKey = userContextKey
    try {
      await api.post('/achievements/', formData)
      if (!isCurrentContext(contextKey)) return
      setShowModal(false)
      resetForm()
      void loadManagementData()
    } catch (e: unknown) {
      if (isCurrentContext(contextKey)) setError(extractError(e, t('errors.createFailed')))
    }
  }

  const handleUpdate = async () => {
    // Only rendered inside the editor modal, which requires an achievement.
    const contextKey = userContextKey
    try {
      await api.put(`/achievements/${editingAchievement!.id}`, {
        name: formData.name,
        description: formData.description,
        category: formData.category,
        points: formData.points,
        icon: formData.icon,
        target_user_id: formData.target_user_id ?? null,
        criteria_type: formData.criteria_type ?? null,
        criteria_value: formData.criteria_value ?? null,
      })
      if (!isCurrentContext(contextKey)) return
      setShowModal(false)
      setEditingAchievement(null)
      resetForm()
      void loadManagementData()
    } catch (e: unknown) {
      if (isCurrentContext(contextKey)) setError(extractError(e, t('errors.updateFailed')))
    }
  }

  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const confirmDeleteAchievement = async () => {
    if (pendingDeleteId == null) return
    const contextKey = userContextKey
    setIsDeleting(true)
    try {
      await api.delete(`/achievements/${pendingDeleteId}`)
      if (!isCurrentContext(contextKey)) return
      setPendingDeleteId(null)
      void loadManagementData()
    } catch (e: unknown) {
      if (isCurrentContext(contextKey)) {
        setError(extractError(e, t('errors.deleteFailed')))
        setPendingDeleteId(null)
      }
    } finally {
      if (isCurrentContext(contextKey)) setIsDeleting(false)
    }
  }

  const handleDelete = (id: number) => {
    setPendingDeleteId(id)
  }

  const handleAward = async () => {
    const contextKey = userContextKey
    try {
      await api.post(`/achievements/${awardingAchievementId}/award`, { user_id: selectedStudentId })
      if (!isCurrentContext(contextKey)) return
      setShowAwardModal(false)
      setAwardingAchievementId(null)
      setSelectedStudentId(null)
      void loadManagementData()
    } catch (e: unknown) {
      // Surface the failure in the shared error banner instead of a native
      // alert() so the experience matches the rest of the app.
      if (isCurrentContext(contextKey)) setError(extractError(e, t('errors.awardFailed')))
    }
  }

  const openCreateModal = () => {
    resetForm()
    setEditingAchievement(null)
    setShowModal(true)
  }

  const openEditModal = (achievement: AchievementFull) => {
    setFormData({
      name: achievement.name,
      description: achievement.description,
      category: achievement.category,
      points: achievement.points,
      icon: achievement.icon,
      target_user_id: achievement.target_user_id ?? null,
      criteria_type: achievement.criteria_type ?? null,
      criteria_value: achievement.criteria_value ?? null,
    })
    setEditingAchievement(achievement)
    setShowModal(true)
  }

  const openAwardModal = (achievementId: number) => {
    setAwardingAchievementId(achievementId)
    setSelectedStudentId(null)
    setStudentSearch('')
    setShowAwardModal(true)
  }

  const resetForm = () => {
    setFormData({ name: '', description: '', category: 'custom', points: 10, icon: '🏆', target_user_id: null, criteria_type: null, criteria_value: null })
  }

  const nameIsEmpty = !formData.name.trim()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          {isTeacherOrAdmin && (
            <button
              onClick={() => setShowManage(!showManage)}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 ${showManage ? 'bg-brand/10 text-brand' : 'bg-muted text-foreground hover:bg-surface-hover'}`}
            >
              <Settings className="w-4 h-4" />
              {t('manage')}
            </button>
          )}
          <Button onClick={handleCheck} disabled={loading}  >
            {t('check')}
          </Button>
        </div>
      </div>

      <div className="bg-surface rounded-xl shadow-sm border border-border p-6 flex items-center gap-4">
        <div className="p-3 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg">
          <Star className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{t('totalPoints')}</p>
          <p className="text-2xl font-bold text-foreground">{visiblePoints}</p>
        </div>
      </div>

      {error && (
        <StatusMessage variant="error">{error}</StatusMessage>
      )}

      {/* Management Section */}
      {showManage && isTeacherOrAdmin && managementContextKey === userContextKey && (
        <div className="bg-surface rounded-xl shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <SectionTitle>{t('manageTitle')}</SectionTitle>
            <Button variant="success" onClick={openCreateModal}>
              <Plus />
              {t('create')}
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-xs uppercase text-muted-foreground border-b border-border">
                <tr>
                  <th className="px-4 py-3">{t('icon')}</th>
                  <th className="px-4 py-3">{t('name')}</th>
                  <th className="px-4 py-3">{t('category')}</th>
                  <th className="px-4 py-3">{t('points')}</th>
                  <th className="px-4 py-3">{t('type')}</th>
                  <th className="px-4 py-3">{t('actions')}</th>
                </tr>
              </thead>
              <tbody>
                {visibleAllAchievements.map(a => (
                  <tr key={a.id} className="border-b border-border hover:bg-surface-hover/50">
                    <td className="px-4 py-3 text-2xl">{a.icon}</td>
                    <td className="px-4 py-3 font-medium text-foreground">{localizeAchievementName(a.name, t)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t(`categories.${a.category}`, a.category)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{a.points}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded ${a.created_by ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-muted text-foreground hover:bg-surface-hover'}`}>
                        {a.created_by ? t('custom') : t('system')}
                      </span>
                      {a.is_manual ? (
                        <span className="ml-2 text-xs px-2 py-1 rounded bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300">{t('manual')}</span>
                      ) : (
                        <span className="ml-2 text-xs px-2 py-1 rounded bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" title={`${t(`criteria.${a.criteria_type}`, a.criteria_type ?? '')}: ${a.criteria_value}`}>
                          {t('auto')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <IconButton label={t('award')} onClick={() => openAwardModal(a.id)} className="p-2 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded">
                          <Award className="w-4 h-4" />
                        </IconButton>
                        {a.created_by && (a.created_by === user?.id || user?.user_type === 'admin') && (
                          <>
                            <IconButton label={t('edit')} onClick={() => openEditModal(a)} className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded">
                              <Pencil className="w-4 h-4" />
                            </IconButton>
                            <IconButton label={t('delete')} onClick={() => handleDelete(a.id)} className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded">
                              <Trash2 className="w-4 h-4" />
                            </IconButton>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* User Achievements Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand"></div>
        </div>
      ) : visibleAchievements.length === 0 ? (
        <div className="text-center py-12 bg-muted rounded-xl border-2 border-dashed border-border">
          <Trophy className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">{t('none')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {visibleAchievements.map((a) => {
            const isUnlocked = !!a.earned_at;
            return (
              <div
                key={a.name}
                className={`bg-surface rounded-xl shadow-sm border border-border p-6 relative overflow-hidden transition-all ${!isUnlocked ? 'opacity-70 grayscale' : ''}`}
              >
                {!isUnlocked && (
                  <div className="absolute top-4 right-4 text-muted-foreground">
                    <Lock className="w-5 h-5" />
                  </div>
                )}
                {isUnlocked && (
                  <div className="absolute top-4 right-4 text-green-500 dark:text-green-400">
                    <CheckCircle className="w-5 h-5" />
                  </div>
                )}

                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-2xl ${isUnlocked ? 'bg-brand/10' : 'bg-muted'}`}>
                    <span>{a.icon}</span>
                  </div>
                  <div>
                    <p className="font-semibold text-foreground">{localizeAchievementName(a.name, t)}</p>
                    <p className="text-xs text-muted-foreground">{t(`categories.${a.category}`, a.category)}</p>
                  </div>
                </div>
                <p className="text-foreground text-sm mb-4">{localizeAchievementDescription(a.name, a.description, t)}</p>

                {isUnlocked ? (
                  <p className="text-xs text-green-700 dark:text-green-400 font-medium">
                    {t('earnedAt', { date: new Date(a.earned_at!).toLocaleDateString() })}
                  </p>
                ) : (
                  <div className="mt-2">
                    <div className="w-full bg-muted rounded-full h-2.5">
                      <div
                        className="bg-brand h-2.5 rounded-full"
                        style={{ width: `${Math.min(a.progress || 0, 100)}%` }}
                      ></div>
                    </div>
                    <p className="text-xs text-right mt-1 text-muted-foreground">
                      {a.progress || 0}%
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <Dialog open onOpenChange={(open) => { if (!open) { setShowModal(false); setEditingAchievement(null); resetForm(); } }}>
          <DialogContent showCloseButton={false} className="max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <DialogTitle className="text-lg font-semibold text-foreground">
                {editingAchievement ? t('editTitle') : t('createTitle')}
              </DialogTitle>
              <button onClick={() => { setShowModal(false); setEditingAchievement(null); resetForm(); }} className="text-muted-foreground hover:text-foreground" aria-label={t('close')}>
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <FormLabel>{t('icon')}</FormLabel>
                <div className="flex flex-wrap gap-2">
                  {EMOJI_OPTIONS.map(emoji => (
                    <button key={emoji} type="button" onClick={() => setFormData({ ...formData, icon: emoji })}
                      className={`w-10 h-10 text-xl rounded-lg border-2 ${formData.icon === emoji ? 'border-brand bg-brand/10' : 'border-border'}`}>
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <FormLabel>{t('name')}</FormLabel>
                <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground" />
              </div>

              <div>
                <FormLabel>{t('description')}</FormLabel>
                <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground" rows={2} />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <FormLabel>{t('category')}</FormLabel>
                  <select value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })}
                    className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground">
                    {visibleCategories.map(cat => (
                      <option key={cat} value={cat}>{t(`categories.${cat}`, cat.charAt(0).toUpperCase() + cat.slice(1))}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <FormLabel>{t('points')}</FormLabel>
                  <input type="number" min={0} value={formData.points} onChange={e => setFormData({ ...formData, points: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground" />
                </div>
              </div>

              <div className="border-t border-border pt-4">
                <FormLabel className="mb-2">{t('awardType')}</FormLabel>
                <div className="flex gap-4 mb-3">
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                    <input type="radio" name="awardType" checked={!formData.criteria_type}
                      onChange={() => setFormData({ ...formData, criteria_type: null, criteria_value: null })}
                      className="text-brand focus:ring-brand" />
                    {t('manualAward')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                    <input type="radio" name="awardType" checked={!!formData.criteria_type}
                      onChange={() => setFormData({ ...formData, criteria_type: 'sessions_completed', criteria_value: 10 })}
                      className="text-brand focus:ring-brand" />
                    {t('automaticAward')}
                  </label>
                </div>

                {formData.criteria_type && (
                  <div className="grid grid-cols-2 gap-4 bg-background/50 p-4 rounded-lg">
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">{t('criteriaType')}</label>
                      <select value={formData.criteria_type} onChange={e => setFormData({ ...formData, criteria_type: e.target.value })}
                        className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-surface text-foreground">
                        {visibleCriteriaTypes.map(ct => (
                          <option key={ct} value={ct}>{t(`criteria.${ct}`, ct.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '))}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">{t('targetValue')}</label>
                      <input type="number" min={0} value={formData.criteria_value ?? ''} onChange={e => setFormData({ ...formData, criteria_value: parseFloat(e.target.value) || 0 })}
                        className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-surface text-foreground" />
                    </div>
                  </div>
                )}
              </div>

              {visibleStudents.length > 0 && (
                <div>
                  <FormLabel>
                    <Users className="w-4 h-4 inline mr-1" />
                    {t('targetUser')}
                  </FormLabel>
                  <select value={formData.target_user_id ?? ''} onChange={e => setFormData({ ...formData, target_user_id: e.target.value ? parseInt(e.target.value) : null })}
                    className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground">
                    <option value="">{t('allStudents')}</option>
                    {visibleStudents.map(s => <option key={s.id} value={s.id}>{s.display_name} ({s.username})</option>)}
                  </select>
                </div>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => { setShowModal(false); setEditingAchievement(null); resetForm(); }}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-surface-hover">
                {t('cancel')}
              </button>
              <Button onClick={editingAchievement ? handleUpdate : handleCreate} disabled={nameIsEmpty} >
                {editingAchievement ? t('save') : t('create')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Award Modal */}
      {showAwardModal && managementContextKey === userContextKey && (
        <Dialog open onOpenChange={(open) => { if (!open) { setShowAwardModal(false); setAwardingAchievementId(null); } }}>
          <DialogContent showCloseButton={false} className="max-w-sm p-6">
            <div className="flex justify-between items-center mb-4">
              <DialogTitle className="text-lg font-semibold text-foreground">{t('awardTitle')}</DialogTitle>
              <button onClick={() => { setShowAwardModal(false); setAwardingAchievementId(null); }} className="text-muted-foreground hover:text-foreground" aria-label={t('close')}>
                <X className="w-5 h-5" />
              </button>
            </div>
            {visibleAllAchievements.find((a) => a.id === awardingAchievementId) && (
              <p className="text-sm text-muted-foreground mb-4 flex items-center gap-2">
                <span className="text-xl">{visibleAllAchievements.find((a) => a.id === awardingAchievementId)!.icon}</span>
                {localizeAchievementName(visibleAllAchievements.find((a) => a.id === awardingAchievementId)!.name, t)}
              </p>
            )}

            <div className="mb-4">
              <FormLabel className="mb-2">{t('selectStudent')}</FormLabel>
              <input
                type="text"
                placeholder={t('searchStudent')}
                value={studentSearch}
                onChange={e => setStudentSearch(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded-t-lg bg-surface text-foreground focus:outline-none focus:ring-2 focus:ring-brand"
              />
              <div className="max-h-60 overflow-y-auto border-x border-b border-border rounded-b-lg bg-surface">
                {filteredStudents.length === 0 ? (
                  <div className="p-3 text-sm text-muted-foreground text-center">
                    {t('noStudents')}
                  </div>
                ) : (
                  filteredStudents.map(s => (
                    <div
                      key={s.id}
                      onClick={() => setSelectedStudentId(s.id)}
                      className={`p-3 cursor-pointer flex justify-between items-center hover:bg-brand/20 transition-colors ${selectedStudentId === s.id ? 'bg-brand/10' : ''}`}
                    >
                      <div>
                        <div className="font-medium text-foreground">{s.display_name}</div>
                        <div className="text-xs text-muted-foreground">@{s.username}</div>
                      </div>
                      {selectedStudentId === s.id && <CheckCircle className="w-4 h-4 text-brand" />}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => { setShowAwardModal(false); setAwardingAchievementId(null); }}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-surface-hover">
                {t('cancel')}
              </button>
              <Button variant="accent" onClick={handleAward} disabled={!selectedStudentId}>
                {t('award')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Delete Confirmation Modal */}
      {pendingDeleteId != null && managementContextKey === userContextKey && (
        <Dialog open onOpenChange={(open) => { if (!open) setPendingDeleteId(null) }}>
          <DialogContent showCloseButton={false} className="max-w-sm p-6">
            <div className="flex justify-between items-center mb-4">
              <DialogTitle className="text-lg font-semibold text-foreground">
                {t('deleteTitle')}
              </DialogTitle>
              <button onClick={() => setPendingDeleteId(null)} className="text-muted-foreground hover:text-foreground" aria-label={t('close')}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              {t('confirmDelete')}
            </p>
            {visibleAllAchievements.find((a) => a.id === pendingDeleteId) && (
              <p className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
                <span className="text-xl">{visibleAllAchievements.find((a) => a.id === pendingDeleteId)!.icon}</span>
                {localizeAchievementName(visibleAllAchievements.find((a) => a.id === pendingDeleteId)!.name, t)}
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setPendingDeleteId(null)}
                disabled={isDeleting}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-surface-hover disabled:opacity-50"
              >
                {t('cancel')}
              </button>
              <Button variant="danger" onClick={confirmDeleteAchievement} disabled={isDeleting}>
                {t('delete')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
