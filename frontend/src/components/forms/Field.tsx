import { ReactNode, useId, useState } from "react";
import { charsLeft } from "../../lib/validation";

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Returns an error message, or null. Runs when the user leaves the field. */
  validate?: (value: string) => string | null;
  required?: boolean;
  maxLength?: number;
  type?: string;
  autoComplete?: string;
  inputMode?: "text" | "email" | "tel" | "numeric";
  placeholder?: string;
  help?: ReactNode;
  disabled?: boolean;
  /** Set by the parent after a failed submit so every error shows at once. */
  forceShowError?: boolean;
  /** Called with the current error so the parent can build a "what's missing" list. */
  id?: string;
  /** Extra content rendered inside the field group (e.g. the password checklist). */
  children?: ReactNode;
  /** Transform on blur, e.g. tidy a phone number. */
  formatOnBlur?: (value: string) => string;
  multiline?: boolean;
  rows?: number;
  /** Rendered beside the input, e.g. a show/hide password button. */
  trailing?: ReactNode;
};

export function Field(props: Props) {
  const {
    label, value, onChange, validate, required, maxLength, type = "text", autoComplete,
    inputMode, placeholder, help, disabled, forceShowError, children, formatOnBlur,
    multiline, rows = 4, trailing,
  } = props;
  const autoId = useId();
  const id = props.id ?? autoId;
  const helpId = `${id}-help`;
  const errId = `${id}-err`;
  const countId = `${id}-count`;
  const [touched, setTouched] = useState(false);

  const error = validate ? validate(value) : null;
  const showError = !!error && (touched || !!forceShowError);
  const describedBy = [help ? helpId : "", showError ? errId : "", maxLength ? countId : ""].filter(Boolean).join(" ") || undefined;

  const shared = {
    id,
    value,
    disabled,
    placeholder,
    autoComplete,
    inputMode,
    maxLength,
    required,
    "aria-required": required || undefined,
    "aria-invalid": showError || undefined,
    "aria-describedby": describedBy,
    className: showError ? "input-invalid" : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value),
    onBlur: () => {
      setTouched(true);
      if (formatOnBlur) {
        const next = formatOnBlur(value);
        if (next !== value) onChange(next);
      }
    },
  };

  const left = maxLength ? charsLeft(value, maxLength) : null;

  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required ? (
          <span className="req" aria-hidden="true"> *</span>
        ) : (
          <span className="opt"> (optional)</span>
        )}
        {required && <span className="sr-only"> (required)</span>}
      </label>
      {multiline ? (
        <textarea rows={rows} {...(shared as React.TextareaHTMLAttributes<HTMLTextAreaElement>)} />
      ) : trailing ? (
        <div className="password-wrap">
          <input type={type} {...(shared as React.InputHTMLAttributes<HTMLInputElement>)} />
          {trailing}
        </div>
      ) : (
        <input type={type} {...(shared as React.InputHTMLAttributes<HTMLInputElement>)} />
      )}
      {help && <p id={helpId} className="field-help">{help}</p>}
      {maxLength && left !== null && (
        <p id={countId} className={`field-count${left <= Math.max(10, Math.floor(maxLength * 0.1)) ? " near-limit" : ""}`}>
          {left} {left === 1 ? "character" : "characters"} left
        </p>
      )}
      <p id={errId} className="field-error" role="alert" aria-live="polite">
        {showError ? error : ""}
      </p>
      {children}
    </div>
  );
}
