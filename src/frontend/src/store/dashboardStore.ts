import { create } from 'zustand';
import api, { extractError } from '../lib/api';
import i18n from '../i18n/index';

interface DashboardStats {
  learningStreak: number;
  achievementCount: number;
  totalPoints: number;
}

interface ActivityItem {
  type: string;
  topic: string;
  timestamp: string;
}

interface LearningHistoryItem {
  topic: string;
  created_at: string;
}

interface DashboardState {
  stats: DashboardStats | null;
  recentActivity: ActivityItem[];
  isLoading: boolean;
  error: string | null;

  fetchDashboardData: (userId: number) => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  stats: null,
  recentActivity: [],
  isLoading: false,
  error: null,

  fetchDashboardData: async (userId: number) => {
    set({ isLoading: true, error: null });
    try {
      // Fetch multiple endpoints in parallel
      const [achievementsRes, pointsRes, learningHistoryRes] = await Promise.all([
        api.get(`/achievements/user/${userId}`),
        api.get(`/achievements/user/${userId}/points`),
        // Keep the history window bounded while leaving enough rows for a
        // meaningful streak calculation when a user has several sessions per day.
        api.get(`/learning/history/${userId}`, { params: { limit: 100 } })
      ]);

      const achievements = achievementsRes.data;
      const totalPoints = pointsRes.data;
      const learningHistoryData = learningHistoryRes.data;

      // Only count unlocked achievements: the user endpoint also returns locked
      // ones (with progress) so the dashboard's "badges earned" card must not
      // count trophies the student has not earned yet.
      const earnedAchievements = achievements.filter(
        (a: { earned_at: string | null }) => a.earned_at != null,
      );

      // Extract sessions array from response (API returns { sessions: [...] })
      const learningHistory: LearningHistoryItem[] = learningHistoryData.sessions || learningHistoryData || [];

      // Calculate streak from learning history
      const learningStreak = calculateStreak(learningHistory);

      // Map learning history to activity items. The topic is kept raw so the
      // page can localize the activity label in the active UI language.
      const recentActivity: ActivityItem[] = learningHistory.map((session) => ({
        type: 'learning',
        topic: session.topic,
        timestamp: session.created_at
      }));

      set({
        stats: {
          learningStreak,
          achievementCount: earnedAchievements.length,
          totalPoints
        },
        recentActivity,
        isLoading: false
      });
    } catch (error: unknown) {
      set({ error: extractError(error, i18n.t('dashboard:errors.loadFailed')), isLoading: false });
    }
  }
}));

function calculateStreak(sessions: LearningHistoryItem[]): number {
  if (sessions.length === 0) return 0;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  const sessionDates = sessions
    .map(s => {
      const date = new Date(s.created_at);
      date.setHours(0, 0, 0, 0);
      return date.getTime();
    })
    .filter((date, index, self) => self.indexOf(date) === index) // unique dates
    .sort((a, b) => b - a); // descending

  let streak = 0;
  let checkDate = today.getTime();

  for (const sessionDate of sessionDates) {
    const daysDiff = Math.floor((checkDate - sessionDate) / (1000 * 60 * 60 * 24));
    
    if (daysDiff === 0 || daysDiff === 1) {
      streak++;
      checkDate = sessionDate;
    } else {
      break;
    }
  }

  return streak;
}
