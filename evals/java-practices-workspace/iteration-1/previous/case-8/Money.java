import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) implements Comparable<Money> {
  public Money {
    Objects.requireNonNull(amount, "amount");
    Objects.requireNonNull(currency, "currency");
    if (!currency.matches("[A-Z]{3}")) {
      throw new IllegalArgumentException("currency must be three uppercase letters");
    }
    amount = amount.stripTrailingZeros();
  }

  @Override
  public int compareTo(Money other) {
    Objects.requireNonNull(other, "other");
    int currencyOrder = currency.compareTo(other.currency);
    return currencyOrder != 0 ? currencyOrder : amount.compareTo(other.amount);
  }

  public Money plus(Money other) {
    Objects.requireNonNull(other, "other");
    if (!currency.equals(other.currency)) {
      throw new IllegalArgumentException("currency mismatch");
    }
    return new Money(amount.add(other.amount), currency);
  }
}
