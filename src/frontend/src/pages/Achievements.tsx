import { useEffect, useState, useCallback } from 'react'
import { Trophy, Star, Lock, CheckCircle, Settings, Plus, Pencil, Trash2, Award, X, Users } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import api from '../lib/api'
import type { Achievement, AchievementFull, User } from '../types'
import { useTranslation } from 'react-i18next'

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
  const { user } = useAuthStore()
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
  const { t } = useTranslation('achievements')

  const isTeacherOrAdmin = user?.user_type === 'teacher' || user?.user_type === 'admin'

  const loadData = useCallback(async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      const [achRes, ptsRes] = await Promise.all([
        api.get(`/achievements/user/${user.id}`),
        api.get(`/achievements/user/${user.id}/points`)
      ])
      setAchievements(achRes.data)
      setPoints(ptsRes.data)
    } catch (e: unknown) {
      const detail = (() => {
        if (typeof e === 'object' && e && 'response' in e) {
          const r = e as { response?: { data?: { detail?: string } } }
          return r.response?.data?.detail || 'Failed to load achievements'
        }
        return 'Failed to load achievements'
      })()
      setError(detail)
    } finally {
      setLoading(false)
    }
  }, [user])

  const loadAllAchievements = useCallback(async () => {
    if (!isTeacherOrAdmin) return
    try {
      const res = await api.get('/achievements/')
      setAllAchievements(res.data)
    } catch (e) {
      console.error('Failed to load all achievements', e)
    }
  }, [isTeacherOrAdmin])

  const loadStudents = useCallback(async () => {
    if (!isTeacherOrAdmin) return
    try {
      // For teachers, get their students; for admins, get all users (via same endpoint with role check)
      const endpoint = '/users/students'
      const res = await api.get(endpoint)
      setStudents(res.data)
    } catch (e) {
      console.error('Failed to load students', e)
    }
  }, [isTeacherOrAdmin])

  const loadCategories = useCallback(async () => {
    if (!isTeacherOrAdmin) return
    try {
      const res = await api.get('/achievements/categories')
      setCategories(res.data)
    } catch (e) {
      console.error('Failed to load categories', e)
    }
  }, [isTeacherOrAdmin])

  const loadCriteriaTypes = useCallback(async () => {
    if (!isTeacherOrAdmin) return
    try {
      const res = await api.get('/achievements/criteria-types')
      setCriteriaTypes(res.data)
    } catch (e) {
      console.error('Failed to load criteria types', e)
    }
  }, [isTeacherOrAdmin])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    if (showManage) {
      loadAllAchievements()
      loadStudents()
      loadCategories()
      loadCriteriaTypes()
    }
  }, [showManage, loadAllAchievements, loadStudents, loadCategories, loadCriteriaTypes])

  const handleCheck = async () => {
    if (!user) return
    setLoading(true)
    setError(null)
    try {
      await api.post(`/achievements/user/${user.id}/check`)
      await loadData()
    } catch (e: unknown) {
      const detail = (() => {
        if (typeof e === 'object' && e && 'response' in e) {
          const r = e as { response?: { data?: { detail?: string } } }
          return r.response?.data?.detail || 'Failed to check achievements'
        }
        return 'Failed to check achievements'
      })()
      setError(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await api.post('/achievements/', formData)
      setShowModal(false)
      resetForm()
      loadAllAchievements()
    } catch (e) {
      console.error('Failed to create achievement', e)
    }
  }

  const handleUpdate = async () => {
    if (!editingAchievement) return
    try {
      await api.put(`/achievements/${editingAchievement.id}`, {
        name: formData.name,
        description: formData.description,
        category: formData.category,
        points: formData.points,
        icon: formData.icon,
        criteria_type: formData.criteria_type || null,
        criteria_value: formData.criteria_value || null,
      })
      setShowModal(false)
      setEditingAchievement(null)
      resetForm()
      loadAllAchievements()
    } catch (e) {
      console.error('Failed to update achievement', e)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('confirmDelete', 'Are you sure you want to delete this achievement?'))) return
    try {
      await api.delete(`/achievements/${id}`)
      loadAllAchievements()
    } catch (e) {
      console.error('Failed to delete achievement', e)
    }
  }

  const handleAward = async () => {
    if (!awardingAchievementId || !selectedStudentId) return
    try {
      await api.post(`/achievements/${awardingAchievementId}/award`, { user_id: selectedStudentId })
      setShowAwardModal(false)
      setAwardingAchievementId(null)
      setSelectedStudentId(null)
      loadAllAchievements()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to award'
      alert(msg)
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('title')}</h1>
          <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          {isTeacherOrAdmin && (
            <button
              onClick={() => setShowManage(!showManage)}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 ${showManage ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300' : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'}`}
            >
              <Settings className="w-4 h-4" />
              {t('manage', 'Manage')}
            </button>
          )}
          <button
            onClick={handleCheck}
            disabled={loading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {t('check')}
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 flex items-center gap-4">
        <div className="p-3 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg">
          <Star className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('totalPoints')}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{points}</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-4 rounded-lg">{error}</div>
      )}

      {/* Management Section */}
      {showManage && isTeacherOrAdmin && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('manageTitle', 'Manage Achievements')}</h2>
            <button onClick={openCreateModal} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2">
              <Plus className="w-4 h-4" />
              {t('create', 'Create')}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="text-xs uppercase text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <tr>
                  <th className="px-4 py-3">{t('icon', 'Icon')}</th>
                  <th className="px-4 py-3">{t('name', 'Name')}</th>
                  <th className="px-4 py-3">{t('category', 'Category')}</th>
                  <th className="px-4 py-3">{t('points', 'Points')}</th>
                  <th className="px-4 py-3">{t('type', 'Type')}</th>
                  <th className="px-4 py-3">{t('actions', 'Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {allAchievements.map(a => (
                  <tr key={a.id} className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-2xl">{a.icon}</td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{a.name}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{a.category}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{a.points}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded ${a.created_by ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'}`}>
                        {a.created_by ? t('custom', 'Custom') : t('system', 'System')}
                      </span>
                      {a.is_manual ? (
                        <span className="ml-2 text-xs px-2 py-1 rounded bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300">{t('manual', 'Manual')}</span>
                      ) : (
                        <span className="ml-2 text-xs px-2 py-1 rounded bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" title={`${a.criteria_type}: ${a.criteria_value}`}>
                          {t('auto', 'Auto')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openAwardModal(a.id)} className="p-2 text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded" title={t('award', 'Award')}>
                          <Award className="w-4 h-4" />
                        </button>
                        {a.created_by && (
                          <>
                            <button onClick={() => openEditModal(a)} className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded" title={t('edit', 'Edit')}>
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button onClick={() => handleDelete(a.id)} className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded" title={t('delete', 'Delete')}>
                              <Trash2 className="w-4 h-4" />
                            </button>
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
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : achievements.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-700">
          <Trophy className="w-12 h-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">{t('none')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {achievements.map((a, i) => {
            const isUnlocked = !!a.earned_at;
            return (
              <div
                key={i}
                className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 relative overflow-hidden transition-all ${!isUnlocked ? 'opacity-70 grayscale' : ''}`}
              >
                {!isUnlocked && (
                  <div className="absolute top-4 right-4 text-gray-400 dark:text-gray-500">
                    <Lock className="w-5 h-5" />
                  </div>
                )}
                {isUnlocked && (
                  <div className="absolute top-4 right-4 text-green-500">
                    <CheckCircle className="w-5 h-5" />
                  </div>
                )}

                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-2xl ${isUnlocked ? 'bg-indigo-50 dark:bg-indigo-900/30' : 'bg-gray-100 dark:bg-gray-700'}`}>
                    <span>{a.icon}</span>
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-gray-100">{a.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{a.category}</p>
                  </div>
                </div>
                <p className="text-gray-700 dark:text-gray-300 text-sm mb-4">{a.description}</p>

                {isUnlocked ? (
                  <p className="text-xs text-green-600 dark:text-green-400 font-medium">
                    {t('earnedAt', { date: new Date(a.earned_at!).toLocaleDateString() })}
                  </p>
                ) : (
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 mt-2">
                    <div
                      className="bg-indigo-600 h-2.5 rounded-full"
                      style={{ width: `${Math.min(a.progress || 0, 100)}%` }}
                    ></div>
                    <p className="text-xs text-right mt-1 text-gray-500">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingAchievement ? t('editTitle', 'Edit Achievement') : t('createTitle', 'Create Achievement')}
              </h3>
              <button onClick={() => { setShowModal(false); setEditingAchievement(null); resetForm(); }} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('icon', 'Icon')}</label>
                <div className="flex flex-wrap gap-2">
                  {EMOJI_OPTIONS.map(emoji => (
                    <button key={emoji} type="button" onClick={() => setFormData({ ...formData, icon: emoji })}
                      className={`w-10 h-10 text-xl rounded-lg border-2 ${formData.icon === emoji ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30' : 'border-gray-200 dark:border-gray-600'}`}>
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('name', 'Name')}</label>
                <input type="text" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('description', 'Description')}</label>
                <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" rows={2} />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('category', 'Category')}</label>
                  <select value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                    {categories.map(cat => (
                      <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('points', 'Points')}</label>
                  <input type="number" value={formData.points} onChange={e => setFormData({ ...formData, points: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('awardType', 'Award Type')}</label>
                <div className="flex gap-4 mb-3">
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                    <input type="radio" name="awardType" checked={!formData.criteria_type}
                      onChange={() => setFormData({ ...formData, criteria_type: null, criteria_value: null })}
                      className="text-indigo-600 focus:ring-indigo-500" />
                    {t('manualAward', 'Manual Award')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                    <input type="radio" name="awardType" checked={!!formData.criteria_type}
                      onChange={() => setFormData({ ...formData, criteria_type: 'sessions_completed', criteria_value: 10 })}
                      className="text-indigo-600 focus:ring-indigo-500" />
                    {t('automaticAward', 'Automatic Criteria')}
                  </label>
                </div>

                {formData.criteria_type && (
                  <div className="grid grid-cols-2 gap-4 bg-gray-50 dark:bg-gray-700/50 p-4 rounded-lg">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('criteriaType', 'Criteria')}</label>
                      <select value={formData.criteria_type} onChange={e => setFormData({ ...formData, criteria_type: e.target.value })}
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                        {criteriaTypes.map(ct => (
                          <option key={ct} value={ct}>{ct.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{t('targetValue', 'Target Value')}</label>
                      <input type="number" value={formData.criteria_value || ''} onChange={e => setFormData({ ...formData, criteria_value: parseFloat(e.target.value) || 0 })}
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" />
                    </div>
                  </div>
                )}
              </div>

              {!editingAchievement && students.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Users className="w-4 h-4 inline mr-1" />
                    {t('targetUser', 'For specific student (optional)')}
                  </label>
                  <select value={formData.target_user_id ?? ''} onChange={e => setFormData({ ...formData, target_user_id: e.target.value ? parseInt(e.target.value) : null })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100">
                    <option value="">{t('allStudents', 'All students')}</option>
                    {students.map(s => <option key={s.id} value={s.id}>{s.display_name} ({s.username})</option>)}
                  </select>
                </div>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => { setShowModal(false); setEditingAchievement(null); resetForm(); }}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                {t('cancel', 'Cancel')}
              </button>
              <button onClick={editingAchievement ? handleUpdate : handleCreate}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
                {editingAchievement ? t('save', 'Save') : t('create', 'Create')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Award Modal */}
      {showAwardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-sm mx-4">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('awardTitle', 'Award Achievement')}</h3>
              <button onClick={() => { setShowAwardModal(false); setAwardingAchievementId(null); }} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('selectStudent', 'Select Student')}</label>
              <input
                type="text"
                placeholder={t('searchStudent', 'Search student...')}
                value={studentSearch}
                onChange={e => setStudentSearch(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-t-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <div className="max-h-60 overflow-y-auto border-x border-b border-gray-300 dark:border-gray-600 rounded-b-lg bg-white dark:bg-gray-700">
                {students.filter(s =>
                  s.display_name.toLowerCase().includes(studentSearch.toLowerCase()) ||
                  s.username.toLowerCase().includes(studentSearch.toLowerCase())
                ).length === 0 ? (
                  <div className="p-3 text-sm text-gray-500 dark:text-gray-400 text-center">
                    {t('noStudents', 'No students found')}
                  </div>
                ) : (
                  students.filter(s =>
                    s.display_name.toLowerCase().includes(studentSearch.toLowerCase()) ||
                    s.username.toLowerCase().includes(studentSearch.toLowerCase())
                  ).map(s => (
                    <div
                      key={s.id}
                      onClick={() => setSelectedStudentId(s.id)}
                      className={`p-3 cursor-pointer flex justify-between items-center hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors ${selectedStudentId === s.id ? 'bg-indigo-100 dark:bg-indigo-900/50' : ''}`}
                    >
                      <div>
                        <div className="font-medium text-gray-900 dark:text-gray-100">{s.display_name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">@{s.username}</div>
                      </div>
                      {selectedStudentId === s.id && <CheckCircle className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => { setShowAwardModal(false); setAwardingAchievementId(null); }}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                {t('cancel', 'Cancel')}
              </button>
              <button onClick={handleAward} disabled={!selectedStudentId}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50">
                {t('award', 'Award')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
