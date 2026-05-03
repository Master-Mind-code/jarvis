/** Mots-passe acceptés pour le déverrouillage initial.
 *  Plusieurs variantes pour couvrir les approximations Whisper français. */
export const PASSWORDS = [
  "ouverture",
  "orion ouverture",
  "ouvre toi",
  "deverrouille",
  "orion ouvre",
];

export function normalizePwd(s: string): string {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function isPasswordMatch(input: string): boolean {
  const norm = normalizePwd(input);
  if (!norm) return false;
  return PASSWORDS.some((pwd) => norm === pwd || norm.includes(pwd));
}
