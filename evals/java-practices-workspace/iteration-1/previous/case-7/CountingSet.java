import java.util.AbstractSet;
import java.util.Collection;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Objects;
import java.util.Set;

public final class CountingSet<E> extends AbstractSet<E> {
  private final Set<E> elements = new HashSet<>();
  private long totalAdded;

  public CountingSet() {}

  public long totalAdded() {
    return totalAdded;
  }

  @Override
  public boolean add(E element) {
    if (elements.contains(element)) {
      return false;
    }
    if (totalAdded == Long.MAX_VALUE) {
      throw new ArithmeticException("insertion count overflow");
    }
    if (elements.add(element)) {
      totalAdded++;
      return true;
    }
    return false;
  }

  @Override
  public boolean addAll(Collection<? extends E> values) {
    Objects.requireNonNull(values, "values");
    boolean changed = false;
    for (E value : values) {
      changed |= add(value);
    }
    return changed;
  }

  @Override
  public Iterator<E> iterator() {
    return elements.iterator();
  }

  @Override
  public int size() {
    return elements.size();
  }

  @Override
  public boolean contains(Object value) {
    return elements.contains(value);
  }

  @Override
  public boolean remove(Object value) {
    return elements.remove(value);
  }

  @Override
  public void clear() {
    elements.clear();
  }
}
