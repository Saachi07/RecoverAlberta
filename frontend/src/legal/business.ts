// Single source of truth for who runs Rebuildr. Legal pages and the footer read
// from here. TODO (owner): confirm every value below before launch.
// PIPEDA and Alberta PIPA expect a named contact for privacy questions.
export const BUSINESS = {
  productName: "Rebuildr",
  // TODO: legal name of the person or entity operating the service.
  operatorName: "Rebuildr (student project, Alberta, Canada)",
  // TODO: a mailing address. Leave "" to show "available on request".
  mailingAddress: "",
  // TODO: confirm this mailbox exists and is monitored. The old Terms used
  // legal@/copyright@rebuildr.com, the old Privacy page used privacy@rebuildr.app.
  contactEmail: "privacy@rebuildr.app",
  jurisdiction: "Alberta, Canada",
  // Bump when any legal page changes materially. Keep in sync with
  // CURRENT_TERMS_VERSION in backend/app/blueprints/terms.py.
  legalVersion: "2026-10-18",
  legalDateLabel: "October 18, 2026",
} as const;
