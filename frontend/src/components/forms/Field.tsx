import React, { forwardRef, ReactNode, useId, useState } from "react";
import { charsLeft } from "../../lib/validation";

export type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  validate?: (value: string) => string | null;
  required?: boolean;
  maxLength?: number;
  type?: string;
  autoComplete?: string;
  inputMode?: "text" | "email" | "tel" | "numeric";
  placeholder?: string;
  help?: ReactNode;
  disabled?: boolean;
  isLoading?: boolean; // Disables the field during submissions
  forceShowError?: boolean;
  id?: string;
  children?: ReactNode;
  formatOnBlur?: (value: string) => string;
  multiline?: boolean;
  rows?: number;
  trailing?: ReactNode;
  className?: string; 
};

export const Field = forwardRef<HTMLInputElement | HTMLTextAreaElement, FieldProps>(
  (props, ref) => {
    const {
      label, value, onChange, validate, required, maxLength, type = "text", autoComplete,
      inputMode, placeholder, help, disabled, isLoading, forceShowError, children, formatOnBlur,
      multiline, rows = 4, trailing, className = ""
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

    // Combine manual disabled state with the loading state
    const isDisabled = disabled || isLoading;

    const shared = {
      id,
      value,
      disabled: isDisabled,
      placeholder,
      autoComplete,
      inputMode,
      maxLength,
      required,
      "aria-required": required || undefined,
      "aria-invalid": showError || undefined,
      "aria-describedby": describedBy,
      // Merge original logic with Tailwind UX improvements
      className: `w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors ${
        showError 
          ? 'border-red-500 focus:border-red-500 focus:ring-red-200 input-invalid' 
          : 'border-gray-300 focus:border-blue-500'
      } ${className}`.trim(),
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

    // Fix for the broken Math.floor syntax in the original file
    const isNearLimit = left !== null && maxLength && left <= Math.max(10, Math.floor(maxLength * 0.1));

    return (
      <div className="flex flex-col w-full mb-4 field">
        <label htmlFor={id} className="mb-1 text-sm font-medium text-gray-700">
          {label}
          {required ? (
            <span className="req text-red-500" aria-hidden="true"> *</span>
          ) : (
            <span className="opt text-gray-400 font-normal"> (optional)</span>
          )}
          {required && <span className="sr-only"> (required)</span>}
        </label>
        
        {multiline ? (
          <textarea 
            ref={ref as React.Ref<HTMLTextAreaElement>} 
            rows={rows} 
            {...(shared as React.TextareaHTMLAttributes<HTMLTextAreaElement>)} 
          />
        ) : trailing ? (
          <div className="password-wrap relative flex items-center">
            <input 
              type={type} 
              ref={ref as React.Ref<HTMLInputElement>} 
              {...(shared as React.InputHTMLAttributes<HTMLInputElement>)} 
            />
            <div className="absolute right-3">
              {trailing}
            </div>
          </div>
        ) : (
          <input 
            type={type} 
            ref={ref as React.Ref<HTMLInputElement>} 
            {...(shared as React.InputHTMLAttributes<HTMLInputElement>)} 
          />
        )}
        
        {help && <p id={helpId} className="field-help text-sm text-gray-500 mt-1">{help}</p>}
        
        {maxLength && left !== null && (
          <p id={countId} className={`field-count text-sm mt-1 ${isNearLimit ? "text-amber-600 near-limit" : "text-gray-500"}`}>
            {left} {left === 1 ? "character" : "characters"} left
          </p>
        )}
        
        {showError && (
          <p id={errId} className="field-error mt-1 text-sm text-red-600" role="alert" aria-live="polite">
            {error}
          </p>
        )}
        
        {children}
      </div>
    );
  }
);

Field.displayName = 'Field';