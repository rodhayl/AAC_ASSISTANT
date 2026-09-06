import { describe, expect, it } from 'vitest';

import { STAFF_ROLES, isStaffUser } from '../src/lib/roles';

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
