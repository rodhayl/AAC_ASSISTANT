import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useBoardStore } from '../store/boardStore';
import { useDashboardStore } from '../store/dashboardStore';
import { LayoutGrid, Trophy, Star, Clock } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '../lib/format';

export function Dashboard() {
  const user = useAuthStore((state) => state.user);
  const boards = useBoardStore((state) => state.boards);
  const assignedBoards = useBoardStore((state) => state.assignedBoards);
  const fetchBoards = useBoardStore((state) => state.fetchBoards);
  const fetchAssignedBoards = useBoardStore((state) => state.fetchAssignedBoards);
  const stats = useDashboardStore((state) => state.stats);
  const recentActivity = useDashboardStore((state) => state.recentActivity);
  const fetchDashboardData = useDashboardStore((state) => state.fetchDashboardData);
  const isLoading = useDashboardStore((state) => state.isLoading);
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
        <p className="text-white">{t('hero.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">{t('cards.myBoards')}</h3>
            <LayoutGrid className="w-5 h-5 text-brand" />
          </div>
          <p className="text-3xl font-bold text-foreground mb-2">{isLoading ? '...' : boards.length}</p>
          <p className="text-sm text-muted-foreground mb-4">{t('cards.activeBoards')}</p>
          <Link 
            to="/boards" 
            className="text-sm font-medium text-brand hover:text-brand"
          >
            {t('cards.manageBoards')} &rarr;
          </Link>
        </div>

        {user?.user_type === 'student' && (
          <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">{t('cards.assignedBoards')}</h3>
              <LayoutGrid className="w-5 h-5 text-brand" />
            </div>
            <p className="text-3xl font-bold text-foreground mb-2">{isLoading ? '...' : assignedBoards.length}</p>
            <p className="text-sm text-muted-foreground mb-4">{t('cards.assignedSubtitle')}</p>
            <Link 
              to="/boards" 
              className="text-sm font-medium text-brand hover:text-brand"
            >
              {t('cards.viewBoards')} &rarr;
            </Link>
          </div>
        )}

        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">{t('cards.learningStreak')}</h3>
            <Star className="w-5 h-5 text-orange-500" />
          </div>
          <p className="text-3xl font-bold text-foreground mb-2">{isLoading ? '...' : t('cards.days', { count: stats?.learningStreak || 0 })}</p>
          <p className="text-sm text-muted-foreground mb-4">{stats?.learningStreak ? t('cards.keepWorking') : t('cards.startStreak')}</p>
          <Link 
            to="/learning" 
            className="text-sm font-medium text-brand hover:text-brand"
          >
            {t('cards.continueLearning')} &rarr;
          </Link>
        </div>

        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">{t('cards.achievements')}</h3>
            <Trophy className="w-5 h-5 text-yellow-500" />
          </div>
          <p className="text-3xl font-bold text-foreground mb-2">{isLoading ? '...' : stats?.achievementCount || 0}</p>
          <p className="text-sm text-muted-foreground mb-4">{stats?.achievementCount ? t('cards.badgesEarned') : t('cards.noBadges')}</p>
          <Link to="/achievements" className="text-sm font-medium text-brand hover:text-brand">
            {t('cards.viewAll')} &rarr;
          </Link>
        </div>
      </div>

      {user?.user_type === 'student' && (
        <div className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden">
          <div className="p-6 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground">{t('assigned.title')}</h3>
            <p className="text-sm text-muted-foreground">{t('assigned.subtitle')}</p>
          </div>
          {isLoading ? (
            <div className="p-6 grid grid-cols-1 gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-12 bg-muted animate-pulse rounded" />
              ))}
            </div>
          ) : assignedBoards.length > 0 ? (
            <div className="divide-y divide-border">
              {assignedBoards.slice(0, 6).map((b) => (
                <div key={b.id} className="p-4 flex items-center justify-between hover:bg-surface-hover transition-colors">
                  <div>
                    <p className="text-sm font-medium text-foreground">{b.name}</p>
                    <p className="text-xs text-muted-foreground">{b.description || t('assigned.noDescription')}</p>
                  </div>
                  <Link to={`/boards/${b.id}`} className="text-sm font-medium text-brand hover:text-brand">
                    {t('assigned.open')} &rarr;
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-6 text-muted-foreground">{t('assigned.none')}</div>
          )}
        </div>
      )}

      <div className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden">
        <div className="p-6 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">{t('activity.recent')}</h3>
        </div>
        <div className="divide-y divide-border">
          {isLoading ? (
            <div className="p-6 grid grid-cols-1 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-10 bg-muted animate-pulse rounded" />
              ))}
            </div>
          ) : recentActivity.length > 0 ? (
            recentActivity.map((activity, i) => (
              <div key={i} className="p-4 hover:bg-surface-hover transition-colors flex items-center">
                <div className="p-2 bg-muted rounded-lg mr-4">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{t('activity.practiced', { topic: activity.topic })}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(activity.timestamp)}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <div className="p-8 text-center text-muted-foreground">{t('activity.none')}</div>
          )}
        </div>
      </div>
    </div>
  );
}
