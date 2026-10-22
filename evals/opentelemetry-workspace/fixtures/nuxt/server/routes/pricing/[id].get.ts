export default defineEventHandler((event) => ({ id: getRouterParam(event, 'id'), price: 9.99 }))
