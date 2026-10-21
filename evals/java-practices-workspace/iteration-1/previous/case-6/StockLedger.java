import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class StockLedger {
  private final Map<String, Integer> counts;

  public StockLedger(Map<String, Integer> initial) {
    Objects.requireNonNull(initial, "initial");
    Map<String, Integer> copy = new HashMap<>();
    for (Map.Entry<String, Integer> entry : initial.entrySet()) {
      String key = entry.getKey();
      Integer count = entry.getValue();
      requireKey(key);
      Objects.requireNonNull(count, "count");
      if (count < 0) {
        throw new IllegalArgumentException("initial count must be nonnegative");
      }
      copy.put(key, count);
    }
    counts = copy;
  }

  public void reserve(Map<String, Integer> request) {
    Objects.requireNonNull(request, "request");
    Map<String, Integer> deductions = new HashMap<>();
    for (Map.Entry<String, Integer> entry : request.entrySet()) {
      String key = entry.getKey();
      Integer count = entry.getValue();
      requireKey(key);
      Objects.requireNonNull(count, "count");
      Integer available = counts.get(key);
      if (available == null || count <= 0 || count > available) {
        throw new IllegalArgumentException("unknown item or invalid reservation: " + key);
      }
      deductions.put(key, count);
    }
    for (Map.Entry<String, Integer> entry : deductions.entrySet()) {
      String key = entry.getKey();
      counts.put(key, counts.get(key) - entry.getValue());
    }
  }

  public Map<String, Integer> stock() {
    return Collections.unmodifiableMap(new HashMap<>(counts));
  }

  private static void requireKey(String key) {
    if (key == null || key.isBlank()) {
      throw new IllegalArgumentException("item key must be nonblank");
    }
  }
}
