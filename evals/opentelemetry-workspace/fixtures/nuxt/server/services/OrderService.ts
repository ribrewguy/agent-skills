import { OrderRepository } from '../repositories/OrderRepository'
import { PricingClient } from '../clients/PricingClient'

export interface Order {
  id: string
  total: number
}

export class OrderService {
  constructor(
    private readonly repository = new OrderRepository(),
    private readonly pricing = new PricingClient(),
  ) {}

  async getOrder(id: string): Promise<Order | undefined> {
    if (id === 'boom') throw new Error('order lookup failed')
    const record = await this.repository.findById(id)
    if (!record) return undefined
    const price = await this.pricing.quote(id)
    console.info('order fetched', { 'order.id': id })
    runTask('audit', { payload: { id } }).catch((err) => console.warn('audit task failed', err))
    return { id: record.id, total: record.quantity * price }
  }
}

export const orderService = new OrderService()
