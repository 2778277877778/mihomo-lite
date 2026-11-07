import asyncio, json
import httpx, websockets

BASE = "http://127.0.0.1:19090"
HEAD = {"Authorization": "Bearer smoke-test-token"}


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, headers=HEAD, timeout=5.0) as c:
        ver = (await c.get("/version")).json()
        cfg = (await c.get("/configs")).json()
        proxies = (await c.get("/proxies")).json()
        print("version:", ver)
        print("ports:", cfg.get("mixed-port"), cfg.get("port"), cfg.get("socks-port"), "mode:", cfg.get("mode"))
        print("proxy groups:", [k for k, v in proxies["proxies"].items() if v.get("type") in ("Selector", "URLTest", "Fallback")][:5])
        print("proxy count:", len(proxies["proxies"]))

    # Websocket traffic stream
    got = None
    try:
        async with websockets.connect("ws://127.0.0.1:19090/traffic?token=smoke-test-token", open_timeout=5) as ws:
            # generate traffic through mixed port
            try:
                async with httpx.AsyncClient(proxy="http://127.0.0.1:17890", timeout=8.0) as p:
                    r = await p.get("http://www.gstatic.com/generate_204")
                    print("proxied status:", r.status_code)
            except Exception as e:  # noqa: BLE001
                print("proxy test error:", type(e).__name__, e)
            got = await asyncio.wait_for(ws.recv(), timeout=8)
    except Exception as e:  # noqa: BLE001
        print("ws error:", type(e).__name__, e)
    print("traffic frame:", got)


asyncio.run(main())
