package fixture

import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import reactor.core.publisher.Mono

data class OrderView(val id: String, val total: Double)

@Service
class OrderService(
    private val repository: OrderRepository,
    private val pricing: PricingClient,
    private val audit: AuditJob,
) {
    private val log = LoggerFactory.getLogger(OrderService::class.java)

    fun getOrder(id: String): Mono<OrderView> = Mono.defer {
        if (id == "boom") return@defer Mono.error<OrderView>(IllegalStateException("order lookup failed"))
        repository.findById(id).flatMap { order ->
            pricing.quote(id).map { price ->
                log.atInfo().addKeyValue("order.id", id).log("order fetched")
                audit.record(id)
                OrderView(order.id, order.quantity * price)
            }
        }
    }
}
