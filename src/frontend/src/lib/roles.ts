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
