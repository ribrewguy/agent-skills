PLANTED BUG: TOCTOU race in claimBead

The check (lines reading `bead.status` and `bead.assignee`) and the update are
two separate database operations. Between them, another caller can also read
the bead, see it as available, and proceed to update. Both calls then return
`success: true`; both think they claimed the bead. The last update wins on
`assignee`, but both callers proceed believing they own the bead.

Severity: HIGH

The "atomicity under concurrent calls" requirement in the design is violated.
Tests of this function in isolation pass because they're single-threaded.
The race only manifests under concurrent production load.

Standard fix: use a conditional update (findOneAndUpdate with a filter on
status='ready' AND assignee=null) so the update only proceeds if the
state hasn't changed since the read.

OTHER REAL BUGS: none. This diff is otherwise correct.
