The parallel stream mutates an unsynchronized ArrayList and a borrowed Writer concurrently, loses input order, adds audit entries before a write succeeds, and hides IOExceptions. Constructor null validation should make a missing writer fail immediately. Keep the documented live read-only audit view and borrowed Writer ownership. A sequential loop expresses the ordered effects directly.

Corrected equivalent class, with unchanged public signatures:

```java
public final class ExportService {
    private final java.io.Writer writer;
    private final java.util.List<String> audit = new java.util.ArrayList<>();

    public ExportService(java.io.Writer writer) {
        this.writer = java.util.Objects.requireNonNull(writer, "writer");
    }

    public void export(java.util.List<String> rows) throws java.io.IOException {
        java.util.Objects.requireNonNull(rows, "rows");
        // Snapshot and reject every null before any external output.
        java.util.List<String> snapshot = java.util.List.copyOf(rows);
        for (String row : snapshot) {
            writer.write(row);
            audit.add(row);
        }
    }

    public java.util.List<String> audit() {
        return java.util.Collections.unmodifiableList(audit);
    }
}
```

The service has a single sequential owner; callers must not modify the input list during snapshotting. Strings are immutable, so a structural snapshot suffices. Neither export nor the constructor closes or flushes the borrowed writer. Existing views from audit() continue to reflect subsequent completed writes while prohibiting mutation through the view.

Null collection/elements are rejected before output and leave audit unchanged. Valid rows are attempted in order. An IOException propagates unchanged and stops the batch. Previously completed writes and their audit entries remain; the failing write can already have emitted a partial row, which cannot be rolled back through Writer. That failing row is not audited, and later rows are not attempted. Successful write means writer.write returned normally, not durable delivery or flush. Unchecked failures likewise remain observable. A VM/resource failure while appending the audit could leave a completed write without an audit entry; this is not a transactional writer/audit operation.

Focused verification should use a recording Writer to check input order, rejection of a late null with no output, and preservation of old audit views. A Writer that emits part of a chosen row and then throws verifies exception propagation, completed-prefix audit entries, absence of the failing/later rows from audit, and that the borrowed writer remains open. No tooling changes or immutable redesign of the intentionally live view are needed.
