export interface OrderRecord {
  id: string
  quantity: number
}

const orders = new Map<string, OrderRecord>()
for (let i = 1; i <= 100; i++) {
  orders.set(String(i), { id: String(i), quantity: (i % 5) + 1 })
}

export class OrderRepository {
  async findById(id: string): Promise<OrderRecord | undefined> {
    return orders.get(id)
  }
}
