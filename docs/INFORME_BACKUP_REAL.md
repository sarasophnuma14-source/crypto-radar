# Informe de la primera copia real · 2.1.0

Fecha: 2026-11-16. **Estado: NO EJECUTADA.** La base Neon de la 2.1 aún no existe (ver
`INFORME_DESPLIEGUE_AISLADO.md`). No hay ninguna copia real: no se inventa ninguna.

## Qué está probado en local

| Prueba | Resultado | Evidencia |
| --- | --- | --- |
| Copia con un rol de **solo lectura** (`radar_backup`) sobre una base 2.1 nueva | «Comparación con el origen: idéntica», con firma HMAC-SHA256 | `evidencia_piloto/lanzamiento/neon_privilegios_minimos_local.txt` |
| `backup verify` de esa copia | «Copia íntegra y restaurable… Firma HMAC verificada» | ídem |
| Sin clave, con otra clave, manipulada, incompleta, restauración interrumpida (SIGKILL en PostgreSQL), repetida | Todas rechazadas o recuperadas | `T23`, `T31`; `evidencia_piloto/preparacion/backup_inicial.txt` (15/15) |

## Procedimiento real, cuando exista la base

En la máquina de confianza (no en Render):

```bash
export DATABASE_URL='<URL directa de Neon 2.1 con el rol radar_backup>'   # desde el gestor de contraseñas
export CRYPTO_RADAR_BACKUP_KEY='<clave de copias, distinta de la TOTP>'
python main.py backup create --out ./copias
python main.py backup verify ./copias/<carpeta creada>
age -r <clave pública> -o copia.tar.age <(tar -C ./copias -c .)   # o gpg: la copia contiene datos personales
```

**Criterios de aceptación:**
- `verify` OK;
- el fichero cifrado se guarda en un almacenamiento con acceso restringido;
- la copia sin cifrar se borra de la máquina;
- se anotan la fecha, el tamaño y el SHA-256.

**Ensayo de restauración:** sobre una base vacía nueva (otra rama de Neon), con `backup restore … --target`. Después
se borra esa rama.

**RPO y RTO esperados** (`PLAN_BACKUP_RECUPERACION.md`):
- RPO ≤ 24 h con la copia diaria;
- RTO ≤ 30 min, contando los pasos manuales;
- **sin medir en Neon ni en Render.**
