Review this Java service and propose focused corrections, with a corrected export method or equivalent code. Contract: a single owner invokes methods sequentially; the Writer is borrowed and must remain open; audit() deliberately returns a live read-only view for existing consumers. export rejects a null row collection or null elements before output, writes rows in input order, and records only rows whose write completed normally. Errors must remain observable. Explain the failure guarantee you can honestly offer. No changes to tooling or public signatures.
public final class ExportService {
 private final java.io.Writer writer;
 private final java.util.List<String> audit = new java.util.ArrayList<>();
 public ExportService(java.io.Writer writer) { this.writer = writer; }
 public void export(java.util.List<String> rows) throws java.io.IOException {
  rows.parallelStream().forEach(row -> {
   audit.add(row);
   try { writer.write(row); } catch (java.io.IOException ignored) { }
  });
 }
 public java.util.List<String> audit() { return java.util.Collections.unmodifiableList(audit); }
}
Write review.md.
