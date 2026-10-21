import java.util.Date;
import java.util.Objects;

/** Stable legacy Date boundary; callers must synchronize concurrent input mutation. */
public final class DateRange {
    private final long startMillis;
    private final long endMillis;

    public DateRange(Date start, Date end) {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        long first = start.getTime();
        long last = end.getTime();
        if (last < first) {
            throw new IllegalArgumentException("end must be at or after start");
        }
        this.startMillis = first;
        this.endMillis = last;
    }

    public Date start() {
        return new Date(startMillis);
    }

    public Date end() {
        return new Date(endMillis);
    }

    /** @throws ArithmeticException if the duration exceeds Long.MAX_VALUE */
    public long durationMillis() {
        return Math.subtractExact(endMillis, startMillis);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof DateRange that
                && startMillis == that.startMillis && endMillis == that.endMillis;
    }

    @Override
    public int hashCode() {
        return 31 * Long.hashCode(startMillis) + Long.hashCode(endMillis);
    }
}
