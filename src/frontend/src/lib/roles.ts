/**
 * Single source of truth for "staff" (teacher/admin) UI gating.
 *
 * Mirrors the backend's STAFF_USER_TYPES (src/api/deps/auth.py). Keep the two
 * lists in sync; every frontend UI gate should go through isStaffUser or the
 * STAFF_ROLES constant instead of re-inlining the pair of literals.
 */

export const STAFF_ROLES = ['admin', 'teacher'] as const;
export type StaffRole = (typeof STAFF_ROLES)[number];

export type StaffCandidate = { user_type?: string | null } | null | undefined;

export function isStaffUser(user: StaffCandidate): boolean {
  if (!user?.user_type) return false;
  return (STAFF_ROLES as readonly string[]).includes(user.user_type);
}

/**
 * Single source for owner-or-admin UI gating on a board or an achievement.
 *
 * Backend ownership rules (boards: require_board_owner_or_admin; custom
 * achievements: created_by == user or admin) historically lived as inlined
 * ``user?.user_type === 'admin' || ownerId === user?.id`` predicates in five
 * frontend call sites; they must not drift. ``ownerId`` is intentionally
 * nullable (Board.user_id is always present, Achievement.created_by may be
 * null for system achievements, whose action buttons callers still gate with
 * an explicit ``created_by &&`` guard).
 */
export type ManageCandidate = {
  id?: number | null;
  user_type?: string | null;
} | null | undefined;

export function canManageBoard(
  user: ManageCandidate,
  ownerId: number | null | undefined,
): boolean {
  if (user?.user_type === 'admin') return true;
  if (!user?.id || ownerId == null) return false;
  return user.id === ownerId;
}
