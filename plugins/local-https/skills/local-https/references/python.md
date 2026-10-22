# Python

## Approach

Each Python server has a TLS option that takes the PEM pair. Keep the pair in
the server's directory and launch from there.

## uvicorn

```bash
uvicorn app.main:app --host myapp-local --port 8443 \
  --ssl-keyfile .cert/myapp-key.pem --ssl-certfile .cert/myapp.pem
```

## Flask

```python
app.run(host="myapp-local", port=8443,
        ssl_context=(".cert/myapp.pem", ".cert/myapp-key.pem"))
```

`flask run --cert .cert/myapp.pem --key .cert/myapp-key.pem` does the same.

## Django

`runserver` has no TLS option. Use `runserver_plus` from django-extensions with
`--cert-file`, or run plain `runserver` on a local port and front it:

```bash
local-https proxy 8443 8000 .
```

## Clients

`requests` and `httpx` read `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`; point both
at `$(mkcert -CAROOT)/rootCA.pem`. Never pass `verify=False`.

## Footguns

- Binding `0.0.0.0` hides the project host from the printed URL.
- A reloader subprocess re-reads the same flags; keep the cert paths relative
  to the working directory the server is launched from.
