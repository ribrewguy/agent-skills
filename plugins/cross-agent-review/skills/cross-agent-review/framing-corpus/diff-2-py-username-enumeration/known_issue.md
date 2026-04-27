PLANTED BUG: Username enumeration via response disclosure

The endpoint returns 404 "No user with that email" when the email is unknown
and 401 "Incorrect password" when the email is known but password is wrong.
An attacker can enumerate registered emails by submitting login attempts
and watching the response code or message.

Severity: HIGH (security)

The design's "must NOT leak whether an email is registered" requirement is
directly violated. Both branches must return identical 401 responses (same
status, same code, same message).

Standard fix: collapse both branches into a single
`raise HTTPException(401, { code: 'InvalidCredentials', message: '...', requestId: ... })`.

OTHER REAL BUGS:
- The error responses don't match the design's standard error envelope shape
  ({ code, message, requestId }). HTTPException's default `detail` field is
  used instead. Severity: Medium. Technically a separate issue from the
  enumeration disclosure, though fixing the enumeration usually fixes this too.
