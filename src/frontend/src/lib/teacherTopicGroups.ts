export type TeacherTopicItem = {
  createdBy: string;
  createdByUserId?: number;
};

export type TeacherTopicGroup<T extends TeacherTopicItem> = {
  teacher: string;
  teacherId?: number;
  topics: T[];
};

/**
 * Group saved topics by teacher only when at least two distinct non-empty
 * teacher names are present. Groups are sorted by descending topic count, then
 * by teacher name for deterministic rendering.
 */
export function groupTopicsByTeacher<T extends TeacherTopicItem>(
  topics: T[],
): TeacherTopicGroup<T>[] | null {
  const identities = new Map<string, { teacher: string; teacherId?: number }>();
  for (const topic of topics) {
    const teacher = topic.createdBy.trim();
    if (!teacher) continue;
    const identity = topic.createdByUserId != null
      ? `id:${topic.createdByUserId}`
      : `name:${teacher}`;
    if (!identities.has(identity)) identities.set(identity, { teacher, teacherId: topic.createdByUserId });
  }
  if (identities.size < 2) return null;

  const groups = Array.from(identities.entries()).map(([identity, { teacher, teacherId }]) => ({
    identity,
    teacher,
    teacherId,
    topics: topics.filter((topic) => {
      const topicName = topic.createdBy.trim();
      return topic.createdByUserId != null
        ? `id:${topic.createdByUserId}` === identity
        : `name:${topicName}` === identity;
    }),
  }));
  groups.sort(
    (left, right) => right.topics.length - left.topics.length || left.teacher.localeCompare(right.teacher),
  );
  return groups.map(({ identity, ...group }) => {
    void identity;
    return group;
  });
}
