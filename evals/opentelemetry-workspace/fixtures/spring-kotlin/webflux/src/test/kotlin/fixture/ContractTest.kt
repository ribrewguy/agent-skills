package fixture

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.client.TestRestTemplate
import org.springframework.http.HttpStatus
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ContractTest(
    @Autowired val rest: TestRestTemplate,
    @Autowired val auditJob: AuditJob,
) {
    @Test
    fun `orders 42 returns total`() {
        val res = rest.getForEntity("/orders/42", Map::class.java)
        assertEquals(HttpStatus.OK, res.statusCode)
        assertEquals("42", res.body!!["id"])
        assertTrue(res.body!!.containsKey("total"))
    }

    @Test
    fun `orders 404 returns not found`() {
        assertEquals(HttpStatus.NOT_FOUND, rest.getForEntity("/orders/404", String::class.java).statusCode)
    }

    @Test
    fun `orders boom returns 500`() {
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, rest.getForEntity("/orders/boom", String::class.java).statusCode)
    }

    @Test
    fun `pricing returns price`() {
        val res = rest.getForEntity("/pricing/7", Map::class.java)
        assertEquals(HttpStatus.OK, res.statusCode)
        assertEquals("7", res.body!!["id"])
        assertTrue(res.body!!.containsKey("price"))
    }

    @Test
    fun `audit job runs`() {
        val latch = CountDownLatch(1)
        auditJob.latch = latch
        assertEquals(HttpStatus.OK, rest.getForEntity("/orders/43", String::class.java).statusCode)
        assertTrue(latch.await(10, TimeUnit.SECONDS))
        assertTrue(auditJob.recorded.contains("43"))
    }
}
