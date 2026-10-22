package fixture

import org.springframework.stereotype.Component
import reactor.core.publisher.Mono
import reactor.core.scheduler.Schedulers
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch

@Component
class AuditJob {
    val recorded = ConcurrentLinkedQueue<String>()

    @Volatile
    var latch: CountDownLatch = CountDownLatch(1)

    fun record(id: String) {
        Mono.fromRunnable<Void> {
            recorded.add(id)
            latch.countDown()
        }.subscribeOn(Schedulers.boundedElastic()).subscribe()
    }
}
