import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** Mutable, single-owner ledger. Not thread-safe. */
public final class StockLedger {
    private final Map<String, Integer> stock;

    public StockLedger(Map<String, Integer> initial) {
        Map<String, Integer> snapshot = new LinkedHashMap<>(Objects.requireNonNull(initial, "initial"));
        for (Map.Entry<String, Integer> entry : snapshot.entrySet()) {
            validateKey(entry.getKey());
            int count = Objects.requireNonNull(entry.getValue(), "count");
            if (count < 0) {
                throw new IllegalArgumentException("initial counts must be nonnegative");
            }
        }
        stock = snapshot;
    }

    public void reserve(Map<String, Integer> request) {
        Map<String, Integer> snapshot = new LinkedHashMap<>(Objects.requireNonNull(request, "request"));
        for (Map.Entry<String, Integer> entry : snapshot.entrySet()) {
            String key = entry.getKey();
            validateKey(key);
            int count = Objects.requireNonNull(entry.getValue(), "count");
            Integer available = stock.get(key);
            if (available == null || count <= 0 || count > available) {
                throw new IllegalArgumentException("request requires known stock and positive available counts");
            }
        }
        for (Map.Entry<String, Integer> entry : snapshot.entrySet()) {
            stock.put(entry.getKey(), stock.get(entry.getKey()) - entry.getValue());
        }
    }

    public Map<String, Integer> stock() {
        return Collections.unmodifiableMap(new LinkedHashMap<>(stock));
    }

    private static void validateKey(String key) {
        Objects.requireNonNull(key, "key");
        if (key.isBlank()) {
            throw new IllegalArgumentException("key must not be blank");
        }
    }
}
