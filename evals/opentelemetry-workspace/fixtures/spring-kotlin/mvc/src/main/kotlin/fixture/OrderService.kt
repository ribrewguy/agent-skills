package fixture

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

@Service
class OrderService(
    private val repository: OrderRepository,
    private val pricing: PricingClient,
    private val audit: AuditJob,
) {
    private val log = LoggerFactory.getLogger(OrderService::class.java)

    suspend fun getOrder(id: String): OrderView? = withContext(Dispatchers.IO) {
        if (id == "boom") error("order lookup failed")
        val order = repository.findById(id) ?: return@withContext null
        val price = pricing.quote(id)
        log.atInfo().addKeyValue("order.id", id).log("order fetched")
        audit.record(id)
        OrderView(order.id, order.quantity * price)
    }
}

data class OrderView(val id: String, val total: Double)
