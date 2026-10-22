package fixture

import org.springframework.scheduling.annotation.Async
import org.springframework.stereotype.Component
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch

@Component
class AuditJob {
    val recorded = ConcurrentLinkedQueue<String>()

    @Volatile
    var latch: CountDownLatch = CountDownLatch(1)

    @Async
    fun record(id: String) {
        recorded.add(id)
        latch.countDown()
    }
}
