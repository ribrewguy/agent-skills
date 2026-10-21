# Java design and defensive boundaries

Use for Java implementation and review, alongside the entrypoint's defaults.
These are the owner's selected Bloch-inspired preferences, adapted to supported
modern Java features and the repository's actual contracts. The book's
[publisher overview and contents](https://www.informit.com/store/effective-java-9780134685991)
locate the relevant topics; Bloch's
[API-design article](https://www.infoq.com/articles/API-Design-Joshua-Bloch/)
and [design interview](https://www.artima.com/articles/josh-bloch-on-design)
provide primary explanations of his approach. The guidance below is an original
engineering checklist, not a reproduction of the book.

## Construction and ownership

Choose an immutable value when identity is its contents: snapshots, options,
identifiers, commands and monetary values are common candidates. Keep fields
private/final, finish validation during construction, and avoid escaping `this`
or invoking overridable behavior before initialization completes. Control
subclassing when extension could invalidate the contract.

Choose a named factory when naming/representation/control of construction helps;
choose a builder when many optional arguments obscure intent. Keep simple
constructors simple. Do not turn every class into a singleton or add a builder
for two obvious arguments. Inject a collaborator such as a clock, policy or
resource supplier when its behavior needs substitution; a container is optional.

For mutable collaborators, identify who may modify each reachable object. Own
the state an immutable object promises to preserve. The
[Java immutability strategy](https://docs.oracle.com/javase/tutorial/essential/concurrency/imstrat.html)
describes encapsulation and alias control; use API features available at the
project's target release.

| Boundary value | Decision |
|---|---|
| Immutable scalar/value | Retain/share; needless copying adds no protection |
| Array or mutable date | Copy into a trusted representation on input; copy mutable output |
| Collection structure | Snapshot if callers retain mutation rights; a backed wrapper is insufficient |
| Mutable collection elements/keys/values | Snapshot elements, convert to immutable values, or document a genuine ownership transfer |
| Existing public live-view API | Preserve its contract; propose an explicit API change if snapshots are desired |

Perform checks on the copies/values actually retained. Copying after checking a
mutable input can retain a different value from the one validated. Avoid
subclass-controlled copying, callbacks and repeated reads when a trusted snapshot
is needed. A copy does not promise an atomic snapshot of a concurrently modified
object graph; require an appropriate ownership/synchronization contract.

The [collection documentation](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)
distinguishes structure from element state. `List.copyOf` protects a snapshot of
references; mutable elements remain mutable. Null rejection, iteration order and
duplicate treatment are part of the API contract, not incidental details to
change while adding copies. Reusing an already immutable collection is safe;
do not require a distinct identity just to prove copying.

## Records and value behavior

[Records](https://docs.oracle.com/en/java/javase/25/language/records.html) provide
final component references and generated methods. Snapshot mutable constructor
components and override accessors where necessary to preserve ownership. An
unmodifiable list of mutable elements still exposes mutable state. Arrays also
need deliberate content-based equality/hashing when the value contract demands
it; default record equality compares array references.

Preserve the [Object contracts](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html):
equal values need equal hashes, with reflexive, symmetric, transitive and
consistent equality. Test HashMap/HashSet behavior, not only direct `equals`.
Avoid mutable identity fields in keys and asymmetric inheritance-based equality.
Use comparator helpers instead of subtraction that can overflow.

For [BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html),
numeric ordering and scale-sensitive equality differ. Choose the domain's scale
policy and normalize consistently if numeric-value equality is intended. Keep
currency/unit identity meaningful and define rounding explicitly. Avoid binary
floating-point conversions for exact money; string/decimal inputs or well-defined
integer minor units preserve the intended representation.

## Defensive operations and API shape

Validate nulls, bounds and cross-field constraints at public boundaries with
appropriate exceptions. Keep error messages useful without exposing secrets.
Validate an entire batch before committing changes, or prepare replacement state
and publish it after success. Specify weaker guarantees when external effects
cannot be rolled back; do not claim a local copy makes remote calls transactional.

For a purposefully mutable single-owner ledger or cache, contain mutation and
test failure-state preservation. Do not replace a required in-place API with a
new immutable return type without authorization. Synchronization, safe publication
and resource ownership remain separate design decisions.

Favor a forwarding wrapper over inheriting concrete implementation behavior for
instrumentation or policy. Review self-calls such as inherited bulk operations:
delegating `addAll` into an overridden `add` can double count. Abstract extension
points intentionally designed for implementation remain useful; do not ban all
inheritance. Document any extension assumptions.

Use parameterized collections and interfaces at API boundaries. Introduce enums
or domain types when they prevent invalid combinations; keep boolean arguments
where their meaning is clear. Return empty collections for empty queries.
[Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html)
fits a possibly absent single result; it is not a blanket replacement for every
field, argument, collection or exception. Preserve existing null/result contracts
unless the change explicitly includes API migration.

Use try-with-resources for owned closeable resources; document borrowed-resource
ownership. Preserve causes and avoid catching errors only to return a misleading
success/absence. Keep streams free of hidden shared-state mutation and use a loop
where it expresses control flow more clearly. Avoid introducing native Java
serialization for new trust boundaries; if a legacy contract requires it, review
deserialization invariants separately.

## Behavioral evidence

Probe the promise, not a keyword such as `final`:

- Mutate original arrays, collection structures and nested elements after
  construction; verify the snapshot retains its value.
- Mutate returned mutable objects; verify subsequent reads retain the invariant.
- Supply invalid cross-field/batch inputs; verify rejection leaves prior state
  intact. Test valid mutation as a control.
- Use equivalent values as hash keys; check ordering, arrays and decimal scale
  according to the declared domain contract.
- Exercise wrapper bulk operations, duplicates, removal and reinsertion to catch
  delegation/counting defects.

Passing formatting, static analysis and coverage does not establish these
properties. Keep the established tooling gates and add focused behavioral tests.
