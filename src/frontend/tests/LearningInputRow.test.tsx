import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import type { BoardSymbol } from '../src/types';

// Mock Smartbar (heavy dependency)
const smartbarSelectSymbol = vi.hoisted(() => vi.fn());
vi.mock('../src/components/board/Smartbar', () => ({
  Smartbar: ({
    onSelectSymbol,
  }: {
    onSelectSymbol: (s: Record<string, unknown>) => void;
  }) => {
    smartbarSelectSymbol(onSelectSymbol);
    return <div data-testid="smartbar-mock" />;
  },
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: 'en' },
  }),
}));

import { LearningInputRow } from '../src/components/learning/LearningInputRow';

const defaultProps = {
  input: '',
  onInputChange: vi.fn(),
  onSubmit: vi.fn(),
  voiceEnabled: false,
  isRecording: false,
  hasRecording: false,
  isLoading: false,
  isStartingSession: false,
  boardId: null,
  startRecording: vi.fn().mockResolvedValue(undefined),
  stopRecording: vi.fn(),
  sendRecording: vi.fn().mockResolvedValue(undefined),
  discardRecording: vi.fn(),
};

function renderRow(overrides: Partial<typeof defaultProps> = {}) {
  return render(<LearningInputRow {...defaultProps} {...overrides} />);
}

describe('LearningInputRow', () => {
  it('renders the text input field', () => {
    renderRow();
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('renders the submit button', () => {
    renderRow();
    // The form submit button has aria-label 'sendMessage'
    const form = screen.getByRole('textbox').closest('form')!;
    const submitBtn = form.querySelector('button[type="submit"]')!;
    expect(submitBtn).toBeInTheDocument();
  });

  it('reflects the input value', () => {
    renderRow({ input: 'Hello world' });
    expect(screen.getByRole('textbox')).toHaveValue('Hello world');
  });

  it('calls onInputChange when the user types', () => {
    const onInputChange = vi.fn();
    renderRow({ onInputChange });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'new' } });
    expect(onInputChange).toHaveBeenCalledWith('new');
  });

  it('calls onSubmit when the form is submitted', () => {
    const onSubmit = vi.fn((e) => e.preventDefault());
    renderRow({ input: 'test', onSubmit });
    const form = screen.getByRole('textbox').closest('form')!;
    fireEvent.submit(form);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('disables the submit button when input is empty', () => {
    renderRow({ input: '' });
    const form = screen.getByRole('textbox').closest('form')!;
    const submitBtn = form.querySelector('button[type="submit"]')!;
    expect(submitBtn).toBeDisabled();
  });

  it('enables the submit button when input has text', () => {
    renderRow({ input: 'hi' });
    const form = screen.getByRole('textbox').closest('form')!;
    const submitBtn = form.querySelector('button[type="submit"]')!;
    expect(submitBtn).not.toBeDisabled();
  });

  it('disables input when isLoading is true', () => {
    renderRow({ isLoading: true });
    expect(screen.getByRole('textbox')).toBeDisabled();
  });

  it('disables input when isRecording is true', () => {
    renderRow({ isRecording: true });
    expect(screen.getByRole('textbox')).toBeDisabled();
  });

  it('disables input when isStartingSession is true', () => {
    renderRow({ isStartingSession: true });
    expect(screen.getByRole('textbox')).toBeDisabled();
  });

  it('renders mic button when voiceEnabled is true and not recording', () => {
    renderRow({ voiceEnabled: true, isRecording: false, hasRecording: false });
    expect(screen.getByRole('button', { name: /start recording/i })).toBeInTheDocument();
  });

  it('renders stop button when recording is active', () => {
    renderRow({ voiceEnabled: true, isRecording: true, hasRecording: false });
    expect(screen.getByRole('button', { name: /stop recording/i })).toBeInTheDocument();
  });

  it('renders send and discard buttons when a recording is ready', () => {
    renderRow({ voiceEnabled: true, isRecording: false, hasRecording: true });
    expect(screen.getByRole('button', { name: /send recording/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /discard recording/i })).toBeInTheDocument();
  });

  it('calls startRecording when the mic button is clicked', () => {
    const startRecording = vi.fn().mockResolvedValue(undefined);
    renderRow({ voiceEnabled: true, startRecording });
    screen.getByRole('button', { name: /start recording/i }).click();
    expect(startRecording).toHaveBeenCalledTimes(1);
  });

  it('calls stopRecording when the stop button is clicked', () => {
    const stopRecording = vi.fn();
    renderRow({ voiceEnabled: true, isRecording: true, stopRecording });
    screen.getByRole('button', { name: /stop recording/i }).click();
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it('calls sendRecording when the send recording button is clicked', async () => {
    const sendRecording = vi.fn().mockResolvedValue(undefined);
    renderRow({ voiceEnabled: true, hasRecording: true, sendRecording });
    screen.getByRole('button', { name: /send recording/i }).click();
    expect(sendRecording).toHaveBeenCalledTimes(1);
  });

  it('calls discardRecording when the discard button is clicked', () => {
    const discardRecording = vi.fn();
    renderRow({ voiceEnabled: true, hasRecording: true, discardRecording });
    screen.getByRole('button', { name: /discard recording/i }).click();
    expect(discardRecording).toHaveBeenCalledTimes(1);
  });
});