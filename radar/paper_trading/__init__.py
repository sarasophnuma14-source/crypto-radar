"""Paper trading de D_volmom_L28 (Fase 6 de la auditoría).

SOLO SIMULACIÓN. Este paquete no tiene ninguna ruta de código que envíe órdenes a un exchange: lee velas públicas,
simula las ejecuciones con el mismo motor que el backtest v2 (radar.edge.sim.Engine) y guarda un diario.
"""
REAL_ORDERS_ENABLED = False
