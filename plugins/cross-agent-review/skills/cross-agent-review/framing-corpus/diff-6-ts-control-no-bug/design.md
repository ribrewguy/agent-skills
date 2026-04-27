# Email template renderer

Add `renderEmailTemplate(templateName, vars)` in `api/services/email.ts`
that:

- Loads a template from `templates/email/<templateName>.html`.
- Substitutes variables: occurrences of `{{var}}` are replaced with
  `vars[var]` (HTML-escaped).
- Throws if the template file is missing.
- Throws if the template references a variable not in `vars`.
- Returns the rendered HTML string.
- 6 unit tests cover happy path, missing template, missing variable,
  HTML escaping of values, no-vars template, and a multi-variable template.
