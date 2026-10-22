export class PricingClient {
  async quote(id: string): Promise<number> {
    const port = process.env.NITRO_PORT || process.env.PORT || '3000'
    const body = await $fetch<{ id: string; price: number }>(`http://localhost:${port}/pricing/${id}`)
    return body.price
  }
}
