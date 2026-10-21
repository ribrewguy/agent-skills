Repair this Java 17 value API without changing its public components or signatures. Domain policy: currency is a nonnull uppercase three-letter code; amount is nonnull and may be negative. Numerically equal amounts in one currency represent the same value regardless of decimal scale. Different currencies are different values. Natural order is currency code then numeric amount, consistent with equality. plus rejects mismatched currencies and performs exact decimal addition. Supply Money.java and notes.md. Current draft:
public record Money(java.math.BigDecimal amount, String currency) implements Comparable<Money> {
 public int compareTo(Money other) { return amount.compareTo(other.amount); }
 public Money plus(Money other) { return new Money(new java.math.BigDecimal(amount.doubleValue()+other.amount.doubleValue()), currency); }
}
Do not add dependencies.
