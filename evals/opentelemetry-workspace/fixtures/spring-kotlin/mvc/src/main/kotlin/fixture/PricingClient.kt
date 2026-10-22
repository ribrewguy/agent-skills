package fixture

import org.springframework.core.env.Environment
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import org.springframework.web.client.body

@Component
class PricingClient(private val env: Environment, builder: RestClient.Builder) {
    private val client: RestClient = builder.build()

    fun quote(id: String): Double {
        val port = env.getRequiredProperty("local.server.port")
        val body = client.get().uri("http://localhost:$port/pricing/{id}", id).retrieve().body<Map<String, Any>>()
        return (body!!["price"] as Number).toDouble()
    }
}
