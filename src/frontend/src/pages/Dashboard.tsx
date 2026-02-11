import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useBoardStore } from '../store/boardStore';
import { useDashboardStore } from '../store/dashboardStore';
import { LayoutGrid, Trophy, Star, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '../lib/format';

export function Dashboard() {
  const { user } = useAuthStore();
  const { boards, assignedBoards, fetchBoards, fetchAssignedBoards } = useBoardStore();
  const { stats, recentActivity, fetchDashboardData, isLoading } = useDashboardStore();
  const { t } = useTranslation('dashboard');

  useEffect(() => {
    if (user) {
      fetchBoards(user.id);
      if (user.user_type === 'student') {
        fetchAssignedBoards(user.id);
      }
      fetchDashboardData(user.id);
    }
  }, [user, fetchBoards, fetchAssignedBoards, fetchDashboardData]);

  return (
    <div className="space-y-8">
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">{t('hero.welcome', { name: user?.display_name })}</h1>
        <p className="text-indigo-100">{t('hero.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('cards.myBoards')}</h3>
            <LayoutGrid className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">{isLoading ? '...' : boards.length}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('cards.activeBoards')}</p>
          <Link 
            to="/boards" 
            className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
          >
            {t('cards.manageBoards')} &rarr;
          </Link>
        </div>

        {user?.user_type === 'student' && (
          <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('cards.assignedBoards')}</h3>
              <LayoutGrid className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">{isLoading ? '...' : assignedBoards.length}</p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('cards.assignedSubtitle')}</p>
            <Link 
              to="/boards" 
              className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
            >
              {t('cards.viewBoards')} &rarr;
            </Link>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('cards.learningStreak')}</h3>
            <Star className="w-5 h-5 text-orange-500" />
          </div>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">{isLoading ? '...' : t('cards.days', { count: stats?.learningStreak || 0 })}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{stats?.learningStreak ? t('cards.keepWorking') : t('cards.startStreak')}</p>
          <Link 
            to="/learning" 
            className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
          >
            {t('cards.continueLearning')} &rarr;
          </Link>
        </div>

        <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('cards.achievements')}</h3>
            <Trophy className="w-5 h-5 text-yellow-500" />
          </div>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">{isLoading ? '...' : stats?.achievementCount || 0}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{stats?.achievementCount ? t('cards.badgesEarned') : t('cards.noBadges')}</p>
          <Link to="/achievements" className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300">
            {t('cards.viewAll')} &rarr;
          </Link>
        </div>
      </div>

      {user?.user_type === 'student' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="p-6 border-b border-gray-100 dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('assigned.title')}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t('assigned.subtitle')}</p>
          </div>
          {isLoading ? (
            <div className="p-6 grid grid-cols-1 gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-12 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />
              ))}
            </div>
          ) : assignedBoards.length > 0 ? (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {assignedBoards.slice(0, 6).map((b) => (
                <div key={b.id} className="p-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{b.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{b.description || t('assigned.noDescription')}</p>
                  </div>
                  <Link to={`/boards/${b.id}`} className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300">
                    {t('assigned.open')} &rarr;
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-6 text-gray-500 dark:text-gray-400">{t('assigned.none')}</div>
          )}
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-100 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('activity.recent')}</h3>
        </div>
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {isLoading ? (
            <div className="p-6 grid grid-cols-1 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 dark:bg-gray-700 animate-pulse rounded" />
              ))}
            </div>
          ) : recentActivity.length > 0 ? (
            recentActivity.map((activity, i) => (
              <div key={i} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center">
                <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg mr-4">
                  <Clock className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{activity.description}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {formatDateTime(activity.timestamp)}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">{t('activity.none')}</div>
          )}
        </div>
      </div>
    </div>
  );
}
