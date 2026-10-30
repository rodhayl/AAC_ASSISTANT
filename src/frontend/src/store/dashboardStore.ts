import { create } from 'zustand';
import api from '../lib/api';

interface DashboardStats {
  boardCount: number;
  learningStreak: number;
  achievementCount: number;
  totalPoints: number;
}

interface ActivityItem {
  type: string;
  description: string;
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
        api.get(`/learning/history/${userId}`, { params: { limit: 5 } })
      ]);

      const achievements = achievementsRes.data;
      const totalPoints = pointsRes.data;
      const learningHistoryData = learningHistoryRes.data;

      // Extract sessions array from response (API returns { sessions: [...] })
      const learningHistory: LearningHistoryItem[] = learningHistoryData.sessions || learningHistoryData || [];

      // Calculate streak from learning history
      const learningStreak = calculateStreak(learningHistory);

      // Map learning history to activity items
      const recentActivity: ActivityItem[] = learningHistory.map((session) => ({
        type: 'learning',
        description: `Practiced "${session.topic}"`,
        timestamp: session.created_at
      }));

      set({
        stats: {
          boardCount: 0, // Will be populated from board store
          learningStreak,
          achievementCount: achievements.length,
          totalPoints
        },
        recentActivity,
        isLoading: false
      });
    } catch (error: unknown) {
      const detail = (() => {
        if (typeof error === 'object' && error && 'response' in error) {
          const r = error as { response?: { data?: { detail?: string } } };
          return r.response?.data?.detail || 'Failed to load dashboard data';
        }
        return 'Failed to load dashboard data';
      })();
      set({ error: detail, isLoading: false });
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
