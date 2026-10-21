The parallel stream violates ordered writes and races on the shared Writer and ArrayList. Adding to audit before writing records failures as successes; swallowing IOException hides failures. Use sequential writes, validate and copy the complete input before output, and append to audit only after write returns normally. Keep the borrowed Writer open and preserve the intentionally live read-only audit view.

A complete corrected implementation is:

```java
public final class ExportService {
  private final java.io.Writer writer;
  private final java.util.List<String> audit = new java.util.ArrayList<>();

  public ExportService(java.io.Writer writer) {
    this.writer = java.util.Objects.requireNonNull(writer, "writer");
  }

  public void export(java.util.List<String> rows) throws java.io.IOException {
    java.util.Objects.requireNonNull(rows, "rows");
    java.util.List<String> validated = new java.util.ArrayList<>(rows.size());
    for (String row : rows) {
      validated.add(java.util.Objects.requireNonNull(row, "row"));
    }
    for (String row : validated) {
      writer.write(row);
      audit.add(row);
    }
  }

  public java.util.List<String> audit() {
    return java.util.Collections.unmodifiableList(audit);
  }
}
```

Null collection or element rejection happens before any output or audit mutation in that invocation. Valid rows are written in order without added delimiters. On IOException, the exception propagates, earlier successful writes remain audited, the failing row is not audited, and later rows are not attempted. A Writer may partially write a row before throwing, so output rollback or all-or-nothing export cannot be promised. A normal return from write does not prove durable delivery; buffered output may fail later when the owner flushes or closes it. This method neither flushes nor closes the borrowed Writer. Runtime failures also propagate; catastrophic failures such as allocation failure while appending audit cannot support transactional guarantees across output and audit. Existing audit views continue to reflect later successful writes. No synchronization is needed under the single-owner sequential contract.
