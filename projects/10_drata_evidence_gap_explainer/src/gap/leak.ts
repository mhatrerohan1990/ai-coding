const MIN_SECRET_LENGTH = 4;

export function findLeaks(text: string, secretValues: string[]): string[] {
  const leaks = new Set<string>();
  for (const secret of secretValues) {
    if (secret.length < MIN_SECRET_LENGTH) continue;
    if (text.includes(secret)) leaks.add(secret);
  }
  return [...leaks];
}
