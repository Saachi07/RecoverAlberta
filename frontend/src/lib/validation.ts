// Small, dependency-free validators shared by every form.
// Each validator returns an error message, or null when the value is fine.
// Messages say what to do, not just what is wrong.

export type Validator = (value: string) => string | null;

// Pragmatic email check: something@something.tld, no spaces. Real
// verification still happens when the confirmation email is sent.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function validateEmail(value: string): string | null {
  const v = value.trim();
  if (!v) return "Enter your email address.";
  if (!EMAIL_RE.test(v)) return "That doesn't look like an email address. It should look like name@example.com.";
  return null;
}

export function required(label: string): Validator {
  return (value) => (value.trim() ? null : `Enter ${label}.`);
}

// ---- Passwords -------------------------------------------------------------

export type PasswordRule = { id: string; label: string; test: (pw: string) => boolean };

// Keep in sync with the Supabase Auth password policy (Dashboard, Authentication,
// Policies). The client check is a convenience; Supabase is the enforcement point.
export const PASSWORD_RULES: PasswordRule[] = [
  { id: "length", label: "At least 8 characters", test: (p) => p.length >= 8 },
  { id: "lower", label: "A lowercase letter", test: (p) => /[a-z]/.test(p) },
  { id: "upper", label: "A capital letter", test: (p) => /[A-Z]/.test(p) },
  { id: "digit", label: "A number", test: (p) => /\d/.test(p) },
];

export function unmetPasswordRules(password: string): PasswordRule[] {
  return PASSWORD_RULES.filter((r) => !r.test(password));
}

export function validatePassword(value: string): string | null {
  if (!value) return "Choose a password.";
  const unmet = unmetPasswordRules(value);
  return unmet.length ? "Your password is missing a few things. See the checklist below." : null;
}

// ---- Phone numbers ---------------------------------------------------------

// Accepts "(780) 555-0123", "780-555-0123", "780.555.0123", "7805550123",
// "+1 780 555 0123", "1-780-555-0123". Returns the 10 digit NANP number or null.
export function parsePhone(input: string): string | null {
  const digits = input.replace(/\D/g, "");
  const national = digits.length === 11 && digits.startsWith("1") ? digits.slice(1) : digits;
  if (national.length !== 10) return null;
  // NANP: area code and exchange cannot start with 0 or 1.
  if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(national)) return null;
  return national;
}

/** Canonical form to store on the backend: E.164, e.g. +17805550123. */
export function phoneToE164(input: string): string | null {
  const n = parsePhone(input);
  return n ? `+1${n}` : null;
}

/** Friendly display form: (780) 555-0123. Returns the input untouched if it can't be parsed. */
export function formatPhone(input: string): string {
  const n = parsePhone(input);
  return n ? `(${n.slice(0, 3)}) ${n.slice(3, 6)}-${n.slice(6)}` : input;
}

export function validatePhone(value: string): string | null {
  if (!value.trim()) return null; // phone fields in this app are optional
  return parsePhone(value) ? null : "Enter a 10 digit phone number, like (780) 555-0123. Dashes and spaces are fine.";
}

// ---- Counting --------------------------------------------------------------

export function charsLeft(value: string, max: number): number {
  return max - value.length;
}
