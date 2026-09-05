import { describe, expect, it } from 'vitest';
import { groupTopicsByTeacher } from '../src/lib/teacherTopicGroups';

type Topic = { createdBy: string; topic: string };

const topic = (createdBy: string, name: string): Topic => ({ createdBy, topic: name });

describe('groupTopicsByTeacher', () => {
  it('returns null for one or no non-empty teacher names', () => {
    expect(groupTopicsByTeacher([])).toBeNull();
    expect(groupTopicsByTeacher([topic('Teacher', 'One')])).toBeNull();
    expect(groupTopicsByTeacher([topic('  Teacher  ', 'One'), topic('', 'Two')])).toBeNull();
  });

  it('sorts groups by count and uses teacher name as a tie-breaker', () => {
    const groups = groupTopicsByTeacher([
      topic('Beta', 'B1'),
      topic('Alpha', 'A1'),
      topic('Alpha', 'A2'),
      topic('Gamma', 'G1'),
      topic('Gamma', 'G2'),
    ]);
    expect(groups?.map((group) => [group.teacher, group.topics.length])).toEqual([
      ['Alpha', 2],
      ['Gamma', 2],
      ['Beta', 1],
    ]);
  });
});
