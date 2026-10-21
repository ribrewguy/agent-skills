import java.math.BigDecimal;
import java.util.Objects;

/** Exact monetary value with numeric, scale-independent amount identity. */
public record Money(BigDecimal amount, String currency) implements Comparable<Money> {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency must be three uppercase ASCII letters");
        }
        amount = amount.stripTrailingZeros();
    }

    @Override
    public int compareTo(Money other) {
        Objects.requireNonNull(other, "other");
        int byCurrency = currency.compareTo(other.currency);
        return byCurrency != 0 ? byCurrency : amount.compareTo(other.amount);
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("currencies must match");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
