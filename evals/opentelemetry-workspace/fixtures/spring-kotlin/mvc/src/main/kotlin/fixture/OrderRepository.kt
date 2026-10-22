package fixture

import org.springframework.stereotype.Repository

data class Order(val id: String, val quantity: Int)

@Repository
class OrderRepository {
    private val orders: Map<String, Order> = (1..100).associate { it.toString() to Order(it.toString(), it % 5 + 1) }

    fun findById(id: String): Order? = orders[id]
}
