import java.util.AbstractSet;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

/** Single-owner Set counting successful insertions over its lifetime. */
public final class CountingSet<E> extends AbstractSet<E> {
    private final Set<E> elements = new HashSet<>();
    private long totalAdded;

    public CountingSet() {}

    public long totalAdded() {
        return totalAdded;
    }

    @Override
    public boolean add(E element) {
        boolean inserted = elements.add(element);
        if (inserted) {
            totalAdded++;
        }
        return inserted;
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
    public boolean contains(Object element) {
        return elements.contains(element);
    }

    @Override
    public boolean remove(Object element) {
        return elements.remove(element);
    }

    @Override
    public void clear() {
        elements.clear();
    }
}
