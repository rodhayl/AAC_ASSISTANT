import { describe, expect, it } from 'vitest';

import { STAFF_ROLES, canManageBoard, isStaffUser } from '../src/lib/roles';

describe('isStaffUser', () => {
  it('accepts teacher and admin', () => {
    expect(isStaffUser({ user_type: 'teacher' })).toBe(true);
    expect(isStaffUser({ user_type: 'admin' })).toBe(true);
  });

  it('rejects non-staff roles', () => {
    expect(isStaffUser({ user_type: 'student' })).toBe(false);
    expect(isStaffUser({ user_type: 'standard' })).toBe(false);
  });

  it('rejects unknown roles instead of failing open', () => {
    expect(isStaffUser({ user_type: 'superuser' })).toBe(false);
    expect(isStaffUser({ user_type: '' })).toBe(false);
  });

  it('handles a missing or null user', () => {
    expect(isStaffUser(null)).toBe(false);
    expect(isStaffUser(undefined)).toBe(false);
    expect(isStaffUser({ user_type: undefined })).toBe(false);
    expect(isStaffUser({ user_type: null })).toBe(false);
  });

  it('ignores extra fields on the user object', () => {
    expect(
      isStaffUser({ user_type: 'admin', id: 1, username: 'boss' }),
    ).toBe(true);
  });
});

describe('STAFF_ROLES', () => {
  it('holds exactly the backend staff set', () => {
    expect([...STAFF_ROLES]).toEqual(['admin', 'teacher']);
  });
});

describe('canManageBoard', () => {
  const owner = { id: 7, user_type: 'teacher' as const };
  const stranger = { id: 8, user_type: 'teacher' as const };
  const admin = { id: 9, user_type: 'admin' as const };
  const student = { id: 7, user_type: 'student' as const };

  it('lets the owner manage the board regardless of role', () => {
    expect(canManageBoard(owner, 7)).toBe(true);
    expect(canManageBoard(student, 7)).toBe(true);
  });

  it('lets an admin manage any board', () => {
    expect(canManageBoard(admin, 7)).toBe(true);
    expect(canManageBoard(admin, 12345)).toBe(true);
    // Even when the achievement owner id is absent (created_by null): the
    // backend lets admins edit system achievements, but the UI keeps the
    // caller's explicit ``created_by &&`` guard, so the helper must not
    // secretly widen that call site by itself.
    expect(canManageBoard(admin, undefined)).toBe(true);
  });

  it('rejects a non-owner stranger', () => {
    expect(canManageBoard(stranger, 7)).toBe(false);
    expect(canManageBoard({ id: 8, user_type: 'student' }, 7)).toBe(false);
  });

  it('rejects anonymous users even when an owner id is present', () => {
    expect(canManageBoard(null, 7)).toBe(false);
    expect(canManageBoard(undefined, 7)).toBe(false);
    expect(canManageBoard({ user_type: undefined }, 7)).toBe(false);
  });

  it('rejects an owner id of null for a non-admin (board.user_id vs created_by)', () => {
    expect(canManageBoard(owner, null)).toBe(false);
    expect(canManageBoard(owner, undefined)).toBe(false);
  });
});
