import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

/** Immutable snapshot. Callers must not modify inputs during construction. */
public final class ShipmentSnapshot {
    private final String id;
    private final List<ParcelValue> parcels;
    private final byte[] label;

    public ShipmentSnapshot(String id, List<Parcel> parcels, byte[] label) {
        this.id = Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        Objects.requireNonNull(parcels, "parcels");
        this.label = Objects.requireNonNull(label, "label").clone();
        List<ParcelValue> values = new ArrayList<>();
        for (Parcel parcel : new ArrayList<>(parcels)) {
            Objects.requireNonNull(parcel, "parcel");
            String sku = parcel.sku();
            int quantity = parcel.quantity();
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("parcel needs a nonblank SKU and positive quantity");
            }
            values.add(new ParcelValue(sku, quantity));
        }
        this.parcels = List.copyOf(values);
    }

    public String id() {
        return id;
    }

    /** Returns an unmodifiable list of fresh mutable Parcel copies. */
    public List<Parcel> parcels() {
        List<Parcel> copies = new ArrayList<>(parcels.size());
        for (ParcelValue parcel : parcels) {
            copies.add(new Parcel(parcel.sku(), parcel.quantity()));
        }
        return List.copyOf(copies);
    }

    public byte[] label() {
        return label.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof ShipmentSnapshot that
                && id.equals(that.id)
                && parcels.equals(that.parcels)
                && Arrays.equals(label, that.label);
    }

    @Override
    public int hashCode() {
        return 31 * Objects.hash(id, parcels) + Arrays.hashCode(label);
    }

    private record ParcelValue(String sku, int quantity) {}
}
