# Spring (MVC and WebFlux)

## Approach

Spring Boot takes a PKCS12 key store. `local-https setup <dir> --jvm` writes
`.cert/myapp.p12` next to the PEM pair; the mkcert password is `changeit`, read
from an env var so it is never hard-coded in a tracked file. WebFlux uses the
same properties.

## application.yml

```yaml
server:
  address: myapp-local
  port: 8443
  ssl:
    enabled: true
    key-store: file:.cert/myapp.p12
    key-store-type: PKCS12
    key-store-password: ${LOCAL_HTTPS_P12_PASSWORD:changeit}
```

The relative `file:` path resolves from the working directory: launch from the
server's directory (`mvn spring-boot:run` or `gradle bootRun` run there). Put
this block in an `application-local.yml` profile so production config is
untouched.

## Callers

- A Nuxt or Node client calling this server needs `NODE_EXTRA_CA_CERTS`.
- A JVM client (a `RestClient`, `WebClient`, or `HttpClient`) needs the mkcert
  root in the JDK's cacerts: `mkcert -install` with `JAVA_HOME` set imports it.
  With several JDKs, import for each, or pass
  `-Djavax.net.ssl.trustStore=<path>`. Never install a trust-all
  `TrustManager` or `HostnameVerifier`.

## Footguns

- A cert whose SANs omit the subdomain you bind (`rest.myapp-local`) fails with
  a hostname mismatch: add the subdomain to the declaration and rerun `setup`.
- A forgotten `server.address` binds every interface and prints `localhost`.
- Tests that start the app on a random port over plain HTTP are fine; this rule
  covers servers a person or agent launches to run the app.
