package fixture

import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import reactor.core.publisher.Mono

@RestController
class OrderController(private val service: OrderService) {
    @GetMapping("/orders/{id}")
    fun get(@PathVariable id: String): Mono<ResponseEntity<OrderView>> =
        service.getOrder(id).map { ResponseEntity.ok(it) }.defaultIfEmpty(ResponseEntity.notFound().build())

    @GetMapping("/health")
    fun health(): String = "ok"
}
