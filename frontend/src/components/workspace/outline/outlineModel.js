export function normalizeOutlineText(value = '') {
  const match = value.match(/```[a-zA-Z]*\s*([\s\S]*?)```/);
  return (match?.[1] ?? value).trim();
}

export function parseOutlineText(value = '') {
  const normalized = normalizeOutlineText(value);
  if (!normalized) return { outlineObj: {}, parseError: false };
  try {
    return { outlineObj: JSON.parse(normalized), parseError: false };
  } catch {
    return { outlineObj: {}, parseError: true };
  }
}

export function updateOutlineJson(text, updater) {
  const outline = text ? JSON.parse(normalizeOutlineText(text)) : {};
  updater(outline);
  return JSON.stringify(outline, null, 2);
}

export function moveKeyEvent(text, index, direction) {
  return updateOutlineJson(text, (outline) => {
    const events = [...(outline.key_events || [])];
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target >= 0 && target < events.length) {
      [events[index], events[target]] = [events[target], events[index]];
    }
    outline.key_events = events;
  });
}
