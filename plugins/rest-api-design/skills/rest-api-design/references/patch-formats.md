# Patch Formats — Detail

Reference for [Partial updates and PATCH](../SKILL.md#partial-updates-and-patch) in the main SKILL.md. Three formats, each with a distinct `Content-Type` and semantics. Read when picking which to support, when explaining the differences to a teammate, or when implementing optimistic concurrency via the JSON Patch `test` operation.

## The escalation

Most endpoints can start with the first format and escalate to the others only when the endpoint genuinely needs what they offer. The `Content-Type` is the contract — clients and servers must agree, and servers should reject unexpected ones with `415 UNSUPPORTED_MEDIA_TYPE`.

| Format | Media type | When to use |
|---|---|---|
| **Plain JSON partial** | `application/json` | Default. Body is a partial of the resource shape; missing fields mean "don't change." Simple, common. Ambiguity: you can't tell "don't change" from "set to null" unless you document a convention. |
| **JSON Merge Patch (RFC 7396)** | `application/merge-patch+json` | When you need **explicit null-means-delete semantics**. The body is a JSON document; `null` on a field tells the server to delete it, missing keys mean "don't change," nested objects merge recursively, arrays replace wholesale. Well-defined, easy to implement, resolves the null ambiguity. |
| **JSON Patch (RFC 6902)** | `application/json-patch+json` | When you need **array-element operations, conditional updates, or atomic multi-op**. Body is an array of operations (`add`, `remove`, `replace`, `move`, `copy`, `test`) referencing JSON Pointers into the resource. Use for resources with complex structure (documents, configurations, policies) or transactional compound edits. |

## Plain JSON partial — the default

What most APIs mean by `PATCH`. Missing keys are "leave alone."

```
PATCH /api/tasks/task_123
Content-Type: application/json

{ "title": "Updated title", "priority": "HIGH" }
```

## JSON Merge Patch — when "delete a field" needs an explicit signal

`null` means delete; missing means don't change.

```
PATCH /api/tasks/task_123
Content-Type: application/merge-patch+json

{ "description": null, "priority": "HIGH" }
```

This says: *delete the description, set priority to HIGH, leave everything else alone.* Clean convention when you have nullable optional fields and clients need to clear them. Arrays are replaced wholesale — no partial array updates.

## JSON Patch — array ops and atomic multi-step edits

```
PATCH /api/tasks/task_123
Content-Type: application/json-patch+json

[
  { "op": "replace", "path": "/title", "value": "Updated title" },
  { "op": "remove", "path": "/description" },
  { "op": "add", "path": "/labels/-", "value": "urgent" },
  { "op": "test", "path": "/version", "value": 7 }
]
```

This says: *replace title, remove description, append 'urgent' to labels, and (critically) verify version is still 7 — if not, the whole patch fails atomically with `409 CONFLICT`.*

The `test` operation is how JSON Patch gives you optimistic concurrency: pair it with a `version` field on your resources and you get safe concurrent edits without server-side locks. The handler:

1. Parses the patch operations.
2. Applies them in order (atomically — all or nothing).
3. If a `test` op fails (the asserted value doesn't match current state), the entire patch fails and the resource is unchanged.
4. Returns `409 CONFLICT` on `test` failure with `code: "PreconditionFailed"`.

This is the most-underrated feature of RFC 6902 and the strongest reason to support `application/json-patch+json` for resources where concurrent edits are a real concern (collaborative documents, multi-actor configurations, anything where two writers might race).

## Content negotiation across patch formats

An endpoint can accept multiple patch formats — declare the supported set in docs and branch on `Content-Type`. A reasonable progression:

1. Ship with plain JSON partial to start.
2. Add Merge Patch when the first nullable-field deletion comes up (or just start there if you know you'll need it).
3. Add JSON Patch only when a specific resource genuinely needs array-element ops or atomic multi-op — don't default to it for simple resources, it's a heavier contract for clients to construct.

Don't try to emulate Merge Patch or JSON Patch semantics under `application/json` — clients won't know which dialect you're speaking. If you need those semantics, declare the media type.

## Validation stays at the boundary regardless of format

Whichever format the endpoint accepts, parse into a typed representation and validate:

- **Merge Patch** — must respect your schema's type rules. A `null` on a non-nullable field is a validation failure.
- **JSON Patch** — operations must pass schema validation on the *result* of applying the patch (not just on individual ops in isolation).

Rejection returns the standard error envelope with a domain code:

- `InvalidPatchOperation` — the patch contains an unsupported op or a malformed shape.
- `InvalidJsonPointer` — a `path` doesn't resolve in the resource.
- `PreconditionFailed` — a `test` op failed.

## Decision flowchart

```
Need to delete a field via PATCH?
├── Yes → Merge Patch (or document a null-means-delete convention on plain JSON)
└── No → continue

Need array-element operations (insert at index, remove specific element, reorder)?
├── Yes → JSON Patch
└── No → continue

Need atomic multi-step edits with optimistic concurrency (test op)?
├── Yes → JSON Patch
└── No → Plain JSON partial
```

When in doubt, plain JSON partial is the right starting point. The cost of escalating later (adding a second supported `Content-Type` to the route) is small; the cost of starting with JSON Patch on a resource that didn't need it is a heavier client contract that nobody asked for.
