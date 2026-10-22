import { orderService } from '../../services/OrderService'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')!
  const order = await orderService.getOrder(id)
  if (!order) throw createError({ statusCode: 404, statusMessage: 'Not Found' })
  return order
})
