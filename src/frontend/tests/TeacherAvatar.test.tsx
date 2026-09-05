import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TeacherAvatar } from '../src/components/learning/TeacherAvatar';

describe('TeacherAvatar', () => {
  it('shows the initials of a multi-word name', () => {
    render(<TeacherAvatar name="Ms. Johnson" />);
    expect(screen.getByText('MJ')).toBeInTheDocument();
  });

  it('shows a single initial for a one-word name', () => {
    render(<TeacherAvatar name="María" />);
    expect(screen.getByText('M')).toBeInTheDocument();
  });

  it('falls back to a question mark for an empty name', () => {
    render(<TeacherAvatar name="" />);
    expect(screen.getByText('?')).toBeInTheDocument();
  });

  it('uses the same color for the same teacher', () => {
    const { container: first } = render(<TeacherAvatar name="Ms. Johnson" />);
    const { container: second } = render(<TeacherAvatar name="Ms. Johnson" />);
    expect(first.querySelector('span')?.className).toBe(second.querySelector('span')?.className);
  });
});
