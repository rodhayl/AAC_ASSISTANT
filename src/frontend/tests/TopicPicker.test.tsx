import { beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
// Real i18n so labels resolve to English and the shuffle-bag behavior is
// asserted against readable topic names.
import i18n, { ensureLocale } from '../src/i18n/index';
import {
  TopicPicker,
  type PickerRecentTopic,
  type PickerTopic,
} from '../src/components/learning/TopicPicker';
import {
  COMMON_TOPIC_KEYS,
  TOPIC_CANONICAL_NAME,
  TOPIC_EMOJI,
  findTopicPictogram,
  normalizeTopic,
} from '../src/lib/topicCatalog';
import type { LearningSymbolItem } from '../src/types';

beforeEach(async () => {
  await ensureLocale('en');
  await i18n.changeLanguage('en');
});

function makeTopic(overrides: Partial<PickerTopic> & { key: string }): PickerTopic {
  return {
    label: overrides.key,
    topic: overrides.key,
    purpose: 'practice',
    practiced: false,
    emoji: '💬',
    ...overrides,
  };
}

const allFresh: PickerTopic[] = COMMON_TOPIC_KEYS.map((key) =>
  makeTopic({ key, label: `Topic ${key}`, topic: TOPIC_CANONICAL_NAME[key], emoji: TOPIC_EMOJI[key] }),
);

describe('TopicPicker', () => {
  it('renders a card for every topic in the pool', () => {
    render(
      <TopicPicker
        topics={allFresh}
        recent={[]}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );
    expect(screen.getByText('What would you like to talk about?')).toBeInTheDocument();
    for (const topic of allFresh) {
      expect(screen.getByText(topic.label)).toBeInTheDocument();
    }
  });

  it('marks practiced topics and places them after fresh ones', () => {
    const practiced = makeTopic({ key: 'food', label: 'Food', practiced: true });
    const freshA = makeTopic({ key: 'a', label: 'Fresh A' });
    const freshB = makeTopic({ key: 'b', label: 'Fresh B' });
    const { container } = render(
      <TopicPicker
        topics={[practiced, freshA, freshB]}
        recent={[]}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );

    expect(screen.getByText('Practiced')).toBeInTheDocument();
    // Fresh cards come first; the practiced card is last in DOM order.
    const cards = container.querySelectorAll('[data-testid^="topic-card-"]');
    expect(cards).toHaveLength(3);
    expect(cards[2].getAttribute('data-testid')).toBe('topic-card-food');
  });

  it('refills the bag when every topic has been practiced', () => {
    const allPracticed = allFresh.map((topic) => ({ ...topic, practiced: true }));
    render(
      <TopicPicker
        topics={allPracticed}
        recent={[]}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );
    expect(screen.queryByText('Practiced')).not.toBeInTheDocument();
    for (const topic of allPracticed) {
      expect(screen.getByText(topic.label)).toBeInTheDocument();
    }
  });

  it('calls onSelect with the tapped topic and disables while starting', () => {
    const onSelect = vi.fn();
    render(
      <TopicPicker
        topics={allFresh}
        recent={[]}
        isStartingSession
        onSelect={onSelect}
        onContinueRecent={vi.fn()}
      />,
    );
    const card = screen.getByTestId('topic-card-general');
    fireEvent.click(card);
    expect(onSelect).not.toHaveBeenCalled();
    expect(card).toBeDisabled();
  });

  it('calls onSelect with the topic payload when a fresh card is tapped', () => {
    const onSelect = vi.fn();
    render(
      <TopicPicker
        topics={allFresh}
        recent={[]}
        isStartingSession={false}
        onSelect={onSelect}
        onContinueRecent={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('topic-card-food'));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'food', topic: 'food and dining' }),
    );
  });

  it('shows the saved-by label on cards when provided', () => {
    const savedTopic = makeTopic({
      key: 'saved-1',
      label: 'Astronomía',
      topic: 'Astronomía',
      sublabel: 'El cielo',
      savedBy: 'Ms. Johnson',
    });
    render(
      <TopicPicker
        topics={[savedTopic]}
        recent={[]}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );
    expect(screen.getByText('Saved by Ms. Johnson')).toBeInTheDocument();
  });

  it('omits the saved-by label when not provided (single teacher)', () => {
    const savedTopic = makeTopic({ key: 'saved-1', label: 'Astronomía', topic: 'Astronomía' });
    render(
      <TopicPicker
        topics={[savedTopic]}
        recent={[]}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Saved by/)).not.toBeInTheDocument();
  });

  it('renders continue chips for recent topics and reports taps', () => {
    const recent: PickerRecentTopic[] = [
      { topic: 'El espacio', purpose: 'Viaje al espacio' },
    ];
    const onContinueRecent = vi.fn();
    render(
      <TopicPicker
        topics={allFresh}
        recent={recent}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={onContinueRecent}
      />,
    );
    expect(screen.getByText('Continue')).toBeInTheDocument();
    const chip = screen.getByRole('button', { name: /El espacio/ });
    fireEvent.click(chip);
    expect(onContinueRecent).toHaveBeenCalledWith('El espacio', 'Viaje al espacio');
  });

  it('renders a continue chip for any recent topic it is given', () => {
    const recent: PickerRecentTopic[] = [{ topic: 'food and dining' }];
    render(
      <TopicPicker
        topics={allFresh}
        recent={recent}
        isStartingSession={false}
        onSelect={vi.fn()}
        onContinueRecent={vi.fn()}
      />,
    );
    // The parent (Learning page) removes pool topics from `recent`; the
    // component simply renders what it is given.
    expect(screen.getByRole('button', { name: /food and dining/ })).toBeInTheDocument();
  });
});

describe('topicCatalog helpers', () => {
  const symbols: LearningSymbolItem[] = [
    { id: 1, label: 'Comer', keywords: 'eat food', category: 'food', image_path: '/img/eat.png' },
    { id: 2, label: 'Coche', keywords: 'car', category: 'travel' },
  ];

  it('picks a symbol with an image for a matching topic', () => {
    const result = findTopicPictogram('food', symbols, '🍽️');
    expect(result.imagePath).toBe('/img/eat.png');
    expect(result.emoji).toBe('🍽️');
  });

  it('falls back to the emoji when no symbol matches', () => {
    const result = findTopicPictogram('shopping', symbols, '🛒');
    expect(result.imagePath).toBeUndefined();
    expect(result.emoji).toBe('🛒');
  });

  it('matches accents-insensitively', () => {
    expect(findTopicPictogram('travel', symbols, '🚗').imagePath).toBeUndefined();
    expect(normalizeTopic('  CómeR  ')).toBe('comer');
    expect(normalizeTopic('Food & Dining')).toBe('food & dining');
  });
});
