import { PASSWORD_RULES } from "../../lib/validation";

// Live checklist. Each rule gets a check mark and the word "met" or "not met"
// so the state never depends on color alone.
export function PasswordChecklist({ password, id }: { password: string; id: string }) {
  return (
    <ul id={id} className="pw-checklist" aria-label="Password requirements">
      {PASSWORD_RULES.map((r) => {
        const ok = r.test(password);
        return (
          <li key={r.id} className={ok ? "met" : "unmet"}>
            <span aria-hidden="true" className="pw-mark">{ok ? "✓" : "○"}</span>
            <span>{r.label}</span>
            <span className="sr-only">{ok ? " (met)" : " (not met)"}</span>
          </li>
        );
      })}
    </ul>
  );
}
