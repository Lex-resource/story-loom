export function simpleDiff(oldStr, newStr) {
  const oldLines = (oldStr || '').split('\n');
  const newLines = (newStr || '').split('\n');
  const result = [];

  let i = 0;
  let j = 0;
  while (i < oldLines.length || j < newLines.length) {
    if (i < oldLines.length && j < newLines.length) {
      if (oldLines[i] === newLines[j]) {
        result.push({ type: 'unchanged', value: oldLines[i] });
        i += 1;
        j += 1;
      } else {
        let found = false;
        for (let k = 1; k < 5; k += 1) {
          if (i + k < oldLines.length && oldLines[i + k] === newLines[j]) {
            for (let x = 0; x < k; x += 1) {
              result.push({ type: 'removed', value: oldLines[i + x] });
            }
            i += k;
            found = true;
            break;
          }
          if (j + k < newLines.length && oldLines[i] === newLines[j + k]) {
            for (let x = 0; x < k; x += 1) {
              result.push({ type: 'added', value: newLines[j + x] });
            }
            j += k;
            found = true;
            break;
          }
        }
        if (!found) {
          result.push({ type: 'removed', value: oldLines[i] });
          result.push({ type: 'added', value: newLines[j] });
          i += 1;
          j += 1;
        }
      }
    } else if (i < oldLines.length) {
      result.push({ type: 'removed', value: oldLines[i] });
      i += 1;
    } else {
      result.push({ type: 'added', value: newLines[j] });
      j += 1;
    }
  }
  return result;
}
