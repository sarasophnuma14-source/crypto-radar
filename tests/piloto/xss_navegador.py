"""XSS almacenado en el navegador real: un solicitante pone HTML/JS en «contacto» y «mensaje»; el administrador abre
su panel. Pasa si no se ejecuta nada (window.__pwn sin definir), no aparece ningún <img onerror> y el texto se ve
literal. Base SQLite temporal, servidor local en un puerto libre. Requiere Chromium + Playwright (node).
Uso: python tests/piloto/xss_navegador.py"""
import json, os, subprocess, sys, tempfile, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ.update({"CRYPTO_RADAR_DATA": tempfile.mkdtemp(prefix="cr-xss-"), "CRYPTO_RADAR_ACCOUNTS": "1",
                   "CRYPTO_RADAR_ADMIN_USER": "jefe.xss", "CRYPTO_RADAR_ADMIN_PASSWORD": "clave de la prueba xss 1",
                   "CRYPTO_RADAR_ADMIN_TOTP": "optional"})
os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(ROOT))
from http.server import ThreadingHTTPServer
from radar import auth, db, server
server.ACCOUNTS = True; db.init(); auth.ensure_admin()
P = '<img src=x onerror="window.__pwn=1"><script>window.__pwn=2</script><svg onload="window.__pwn=3">'
auth.request_access("victima.xss", "clave muy segura 123", contact=P, note=P, ip="10.0.0.1", consent=auth.POLICY_VERSION)
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{httpd.server_address[1]}"
JS = r"""
const { chromium } = require('playwright');
(async () => {
  const [base] = process.argv.slice(1);
  const br = await chromium.launch(); const pg = await br.newPage(); const dialogs = [];
  pg.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
  await pg.goto(base + '/entrar');
  await pg.fill('#loginForm [name=username]', 'jefe.xss'); await pg.fill('#loginForm [name=password]', 'clave de la prueba xss 1');
  await pg.click('#loginForm button[type=submit]'); await pg.waitForURL(/\/app/);
  await pg.click('button[data-view=settings]'); await pg.waitForSelector('#adminUsers table');
  await pg.waitForTimeout(800);
  const out = await pg.evaluate(() => ({ pwn: window.__pwn ?? null,
    imgs: document.querySelectorAll('#adminUsers img').length, svgs: document.querySelectorAll('#adminUsers svg[onload]').length,
    literal: document.querySelector('#adminUsers').textContent.includes('<script>window.__pwn=2</script>') }));
  out.dialogs = dialogs; console.log(JSON.stringify(out)); await br.close();
})().catch(e => { console.log(JSON.stringify({error: e.message})); process.exit(1); });
"""
r = subprocess.run(["node", "-e", JS, base], capture_output=True, text=True, timeout=120,
                   env=dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()))
res = json.loads((r.stdout.strip().splitlines() or ["{}"])[-1])
ok = res.get("pwn") is None and res.get("imgs") == 0 and res.get("svgs") == 0 and res.get("literal") and not res.get("dialogs")
print("XSS navegador:", "SIN EJECUCIÓN (OK)" if ok else "FALLO", res)
httpd.shutdown(); sys.exit(0 if ok else 1)
