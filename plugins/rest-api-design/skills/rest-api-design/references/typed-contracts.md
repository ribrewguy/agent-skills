# Typed Contract Patterns — Examples

Reference for [Typed contract patterns](../SKILL.md#typed-contract-patterns) in the main SKILL.md. Three patterns shown in TypeScript, Python, Go, and Rust. The patterns apply in any typed language; the syntax is a detail.

## Discriminated unions for variants

Encode each variant explicitly so consumers get exhaustive type-narrowing.

### TypeScript

```typescript
type TaskStatus =
  | { type: 'pending' }
  | { type: 'in_progress'; assignee: string; startedAt: string }
  | { type: 'completed'; completedAt: string; completedBy: string }
  | { type: 'cancelled'; reason: string; cancelledAt: string }
```

### Python (Pydantic v2)

```python
from pydantic import BaseModel
from typing import Literal, Union
from datetime import datetime

class Pending(BaseModel):
    type: Literal["pending"]

class InProgress(BaseModel):
    type: Literal["in_progress"]
    assignee: str
    started_at: datetime

class Completed(BaseModel):
    type: Literal["completed"]
    completed_at: datetime
    completed_by: str

TaskStatus = Union[Pending, InProgress, Completed]
```

### Go

Tagged struct with a discriminator — Go's type system doesn't have sum types, so runtime branching on `Type` is idiomatic:

```go
type TaskStatus struct {
    Type        string     `json:"type"`
    Assignee    *string    `json:"assignee,omitempty"`
    StartedAt   *time.Time `json:"startedAt,omitempty"`
    CompletedAt *time.Time `json:"completedAt,omitempty"`
    CompletedBy *string    `json:"completedBy,omitempty"`
}
```

### Rust

```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum TaskStatus {
    Pending,
    InProgress { assignee: String, started_at: DateTime<Utc> },
    Completed { completed_at: DateTime<Utc>, completed_by: String },
    Cancelled { reason: String, cancelled_at: DateTime<Utc> },
}
```

## Input/output separation

Never use the same type for "what the client sends" and "what the server returns." Inputs are smaller (missing server-generated fields); outputs include `id`, timestamps, and derived fields.

### TypeScript

```typescript
interface CreateTaskInput {
  title: string
  description?: string
}

interface Task {
  id: string
  title: string
  description: string | null
  createdAt: string
  updatedAt: string
  createdBy: string
}
```

### Python

```python
class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None

class Task(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
```

### Go

```go
type CreateTaskInput struct {
    Title       string  `json:"title" validate:"required"`
    Description *string `json:"description,omitempty"`
}

type Task struct {
    ID          string    `json:"id"`
    Title       string    `json:"title"`
    Description *string   `json:"description"`
    CreatedAt   time.Time `json:"createdAt"`
    UpdatedAt   time.Time `json:"updatedAt"`
    CreatedBy   string    `json:"createdBy"`
}
```

## Branded / distinct types for IDs

Prevent accidentally passing a `UserId` where a `TaskId` is expected — cheap safety for IDs that flow across many module boundaries.

### TypeScript (branded)

```typescript
type TaskId = string & { readonly __brand: 'TaskId' }
type UserId = string & { readonly __brand: 'UserId' }
```

### Python (`NewType` — runtime-thin, static-only)

```python
from typing import NewType
TaskId = NewType("TaskId", str)
UserId = NewType("UserId", str)
```

### Go (named types)

```go
type TaskId string
type UserId string
```

### Rust (newtype pattern)

```rust
struct TaskId(String);
struct UserId(String);
```

Branded / distinct IDs are a judgment call — use them for IDs that cross module boundaries and where a mix-up would be silently accepted. Skip for internal-only IDs where a regular `string` is fine.

## Why these three patterns specifically

These three are the patterns that produce the largest correctness wins per type-line spent:

- **Discriminated unions** make the state machine explicit. Without them, a function handling all four `TaskStatus` variants typically has runtime branching on a string and no compiler enforcement that all cases are handled. With them, exhaustive matching is a compile error away.
- **Input/output separation** prevents accidental round-trip of server-owned fields (writing `id` or `createdAt` from the client side, for example). Without it, the API surface tends to leak — clients learn to send fields the server is supposed to manage.
- **Branded IDs** catch the most common API-layer bug: passing the right-shaped string to the wrong function. Without them, `getTask(userId)` typechecks; with them, the compiler catches the mix-up at the call site.

The patterns compose: a `Task` type uses `TaskId` for `id`, `UserId` for `createdBy` and `assigneeId`, and a `TaskStatus` discriminated union for `status`. The whole resource type then refuses to compile if anything's wrong, and the runtime never has to do the work of distinguishing.
