import { describe, expect, it } from "vitest";
import {
  charsLeft,
  formatPhone,
  parsePhone,
  phoneToE164,
  unmetPasswordRules,
  validateEmail,
  validatePassword,
  validatePhone,
} from "../validation";

describe("validateEmail", () => {
  it("accepts normal addresses, trimming whitespace", () => {
    expect(validateEmail("jane@example.com")).toBeNull();
    expect(validateEmail("  jane.doe+test@mail.ualberta.ca ")).toBeNull();
  });
  it("rejects empty and malformed addresses", () => {
    expect(validateEmail("")).not.toBeNull();
    expect(validateEmail("jane")).not.toBeNull();
    expect(validateEmail("jane@")).not.toBeNull();
    expect(validateEmail("jane@example")).not.toBeNull();
    expect(validateEmail("ja ne@example.com")).not.toBeNull();
  });
});

describe("password rules", () => {
  it("lists every unmet rule for an empty password", () => {
    expect(unmetPasswordRules("").map((r) => r.id)).toEqual(["length", "lower", "upper", "digit"]);
  });
  it("tracks rules individually as the user types", () => {
    expect(unmetPasswordRules("abcdefgh").map((r) => r.id)).toEqual(["upper", "digit"]);
    expect(unmetPasswordRules("Abcdefg1")).toEqual([]);
  });
  it("validatePassword mirrors the rules", () => {
    expect(validatePassword("")).not.toBeNull();
    expect(validatePassword("short1A")).not.toBeNull();
    expect(validatePassword("Longenough1")).toBeNull();
  });
});

describe("phone handling", () => {
  const same = "+17805550123";
  it("normalizes every common format to the same E.164 value", () => {
    for (const raw of ["(780) 555-0123", "780-555-0123", "780.555.0123", "7805550123", "+1 780 555 0123", "1-780-555-0123"]) {
      expect(phoneToE164(raw)).toBe(same);
    }
  });
  it("formats for display", () => {
    expect(formatPhone("7805550123")).toBe("(780) 555-0123");
    expect(formatPhone("nope")).toBe("nope");
  });
  it("rejects impossible numbers", () => {
    expect(parsePhone("555-0123")).toBeNull();
    expect(parsePhone("0805550123")).toBeNull();
    expect(parsePhone("78055501234")).toBeNull();
  });
  it("treats empty as valid because phone is optional", () => {
    expect(validatePhone("")).toBeNull();
    expect(validatePhone("123")).not.toBeNull();
  });
});

describe("charsLeft", () => {
  it("counts down and goes negative past the limit", () => {
    expect(charsLeft("hello", 10)).toBe(5);
    expect(charsLeft("hello", 3)).toBe(-2);
  });
});
