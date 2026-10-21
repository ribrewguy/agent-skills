import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public final class ShipmentSnapshot {
  private record ParcelValue(String sku, int quantity) {}

  private final String id;
  private final List<ParcelValue> parcels;
  private final byte[] label;

  public ShipmentSnapshot(String id, List<Parcel> parcels, byte[] label) {
    if (id == null || id.isBlank()) {
      throw new IllegalArgumentException("id must be nonblank");
    }
    Objects.requireNonNull(parcels, "parcels");
    Objects.requireNonNull(label, "label");
    List<ParcelValue> values = new ArrayList<>(parcels.size());
    for (Parcel parcel : parcels) {
      Objects.requireNonNull(parcel, "parcel");
      String sku = parcel.sku();
      int quantity = parcel.quantity();
      if (sku == null || sku.isBlank() || quantity <= 0) {
        throw new IllegalArgumentException("invalid parcel");
      }
      values.add(new ParcelValue(sku, quantity));
    }
    this.id = id;
    this.parcels = List.copyOf(values);
    this.label = label.clone();
  }

  public String id() {
    return id;
  }

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
    return other instanceof ShipmentSnapshot snapshot
        && id.equals(snapshot.id)
        && parcels.equals(snapshot.parcels)
        && Arrays.equals(label, snapshot.label);
  }

  @Override
  public int hashCode() {
    return 31 * Objects.hash(id, parcels) + Arrays.hashCode(label);
  }
}
