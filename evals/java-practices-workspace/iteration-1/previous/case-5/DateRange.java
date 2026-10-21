import java.util.Date;
import java.util.Objects;

public final class DateRange {
  private final long startMillis;
  private final long endMillis;

  public DateRange(Date start, Date end) {
    long capturedStart = Objects.requireNonNull(start, "start").getTime();
    long capturedEnd = Objects.requireNonNull(end, "end").getTime();
    if (capturedEnd < capturedStart) {
      throw new IllegalArgumentException("end must be at or after start");
    }
    startMillis = capturedStart;
    endMillis = capturedEnd;
  }

  public Date start() {
    return new Date(startMillis);
  }

  public Date end() {
    return new Date(endMillis);
  }

  public long durationMillis() {
    return Math.subtractExact(endMillis, startMillis);
  }

  @Override
  public boolean equals(Object other) {
    return other instanceof DateRange range
        && startMillis == range.startMillis
        && endMillis == range.endMillis;
  }

  @Override
  public int hashCode() {
    return 31 * Long.hashCode(startMillis) + Long.hashCode(endMillis);
  }
}
