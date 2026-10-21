public class Parcel {
 private String sku; private int quantity;
 public Parcel(String sku, int quantity) {this.sku=sku; this.quantity=quantity;}
 public String sku(){return sku;} public int quantity(){return quantity;}
 public void setSku(String sku){this.sku=sku;} public void setQuantity(int quantity){this.quantity=quantity;}
}
