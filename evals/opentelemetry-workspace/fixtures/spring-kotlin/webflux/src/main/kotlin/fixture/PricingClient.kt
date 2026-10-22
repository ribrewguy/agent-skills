package fixture

import org.springframework.core.env.Environment
import org.springframework.stereotype.Component
import org.springframework.web.reactive.function.client.WebClient
import reactor.core.publisher.Mono

@Component
class PricingClient(private val env: Environment, builder: WebClient.Builder) {
    private val client: WebClient = builder.build()

    fun quote(id: String): Mono<Double> =
        Mono.defer {
            val port = env.getRequiredProperty("local.server.port")
            client.get().uri("http://localhost:$port/pricing/{id}", id).retrieve()
                .bodyToMono(Map::class.java)
                .map { (it["price"] as Number).toDouble() }
        }
}
