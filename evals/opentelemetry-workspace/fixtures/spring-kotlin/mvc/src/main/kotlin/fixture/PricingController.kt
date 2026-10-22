package fixture

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController

@RestController
class PricingController {
    @GetMapping("/pricing/{id}")
    fun price(@PathVariable id: String): Map<String, Any> = mapOf("id" to id, "price" to 9.99)
}
