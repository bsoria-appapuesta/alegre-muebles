from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from typing import Optional, List
import re
import json
import os

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# --- CONFIGURACIÓN BASE DE DATOS ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./alegre.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- TABLAS DE LA BASE DE DATOS ---
class ClienteModel(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    servicio = Column(String, nullable=False)
    monto_total = Column(Float, default=0.0)
    anticipo = Column(Float, default=0.0)
    gastos_extra = Column(Float, default=0.0)
    costo_materiales = Column(Float, default=0.0)
    fecha_anticipo = Column(String, nullable=True)
    saldo_financiar = Column(Float, default=0.0)
    es_plan_cuotas = Column(Boolean, default=False)
    cuotas_json = Column(Text, default="[]")
    medidas_json = Column(Text, default="{}")
    estado_produccion = Column(String, default="Pendiente")

class StockModel(Base):
    __tablename__ = "stock"
    id_articulo = Column(String, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    cantidad = Column(Float, default=0.0)
    precio_costo = Column(Float, default=0.0)

class ProductoEstandarModel(Base):
    __tablename__ = "productos_estandar"
    codigo = Column(String, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    cantidad = Column(Float, default=1.0)
    costo_real = Column(Float, default=0.0)
    costo_total = Column(Float, default=0.0) # Precio Venta
    gastos_extra = Column(Float, default=0.0) # Flete + Gastos

class EntregaModel(Base):
    __tablename__ = "entregas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cliente_id = Column(Integer, nullable=True)
    cliente = Column(String, nullable=False)
    servicio = Column(String, nullable=False)
    monto_total = Column(Float, default=0.0)
    costo_materiales = Column(Float, default=0.0)
    gastos_extra = Column(Float, default=0.0)
    fecha_entrega = Column(String, nullable=False)
    estado = Column(String, default="Entregado")

Base.metadata.create_all(bind=engine)

# --- POBLAR DATOS INICIALES ---
def inicializar_base_datos():
    db = SessionLocal()
    try:
        if db.query(StockModel).count() == 0:
            db.add_all([
                StockModel(id_articulo="PL-001", nombre="Placas MDF 18mm", categoria="Placas", cantidad=20.0, precio_costo=25000.0),
                StockModel(id_articulo="CT-001", nombre="Canto PVC 22mm", categoria="Cantos", cantidad=150.0, precio_costo=350.0),
                StockModel(id_articulo="HR-001", nombre="Bisagras Cazoleta", categoria="Herrajes", cantidad=80.0, precio_costo=1200.0)
            ])
        if db.query(ProductoEstandarModel).count() == 0:
            db.add_all([
                ProductoEstandarModel(codigo="PROD-001", nombre="Mueble Bajo Mesada Estándar", cantidad=5.0, costo_real=45000.0, costo_total=85000.0, gastos_extra=7000.0),
                ProductoEstandarModel(codigo="PROD-002", nombre="Alacena 2 Puertas", cantidad=3.0, costo_real=32000.0, costo_total=60000.0, gastos_extra=4000.0)
            ])
        db.commit()
    finally:
        db.close()

inicializar_base_datos()

app = FastAPI(title="Alegre Muebles - Sistema MRP")

if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

USUARIO_CORRECTO = "admin"
PASSWORD_CORRECTO = "alegra123"

def obtener_ruta_logo():
    if os.path.exists("static"):
        for archivo in os.listdir("static"):
            if archivo.lower().startswith("imagen"):
                return f"/static/{archivo}"
    return "/static/imagen"

# --- MODELOS PYDANTIC ---
class ClienteCreate(BaseModel):
    nombre: str
    telefono: str
    servicio: str
    monto_total: float
    anticipo: float
    gastos_extra: Optional[float] = 0.0
    es_plan_cuotas: bool
    cantidad_cuotas: Optional[int] = 1
    alto_mm: Optional[float] = 1800
    ancho_mm: Optional[float] = 1200
    profundidad_mm: Optional[float] = 500

    @field_validator('telefono')
    def validar_telefono(cls, v):
        if not re.match(r'^\d+$', str(v).strip()):
            raise ValueError('El teléfono debe contener únicamente dígitos numéricos.')
        return v.strip()

class ClienteUpdate(BaseModel):
    nombre: str
    telefono: str
    servicio: str
    monto_total: float
    anticipo: float
    gastos_extra: Optional[float] = 0.0
    es_plan_cuotas: bool
    cantidad_cuotas: Optional[int] = 1
    alto_mm: Optional[float] = 1800
    ancho_mm: Optional[float] = 1200
    profundidad_mm: Optional[float] = 500

class PagoCuota(BaseModel):
    cliente_id: int
    numero_cuota: int
    fecha_pago: Optional[str] = None

class ProducirMueble(BaseModel):
    cliente_id: int

class NuevoInsumo(BaseModel):
    id_articulo: str
    nombre: str
    categoria: str
    cantidad: float
    precio_costo: float

class InsumoUpdate(BaseModel):
    nombre: str
    categoria: str
    cantidad: float
    precio_costo: float

class ProductoEstandarCreate(BaseModel):
    codigo: str
    nombre: str
    cantidad: float
    costo_real: float
    costo_total: float
    gastos_extra: Optional[float] = 0.0

class ProductoEstandarUpdate(BaseModel):
    nombre: str
    cantidad: float
    costo_real: float
    costo_total: float
    gastos_extra: Optional[float] = 0.0

class VenderEstandar(BaseModel):
    codigo: str
    comprador: str

# --- AUTENTICACIÓN ---
@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/panel")

@app.get("/login", response_class=HTMLResponse)
def login_get(error: Optional[str] = None):
    logo_path = obtener_ruta_logo()
    mensaje_error = f'<p style="color: #d32f2f; font-size: 14px; margin-bottom: 15px;">{error}</p>' if error else ''
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Iniciar Sesión - Alegre Muebles</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; }}
            html, body {{ background-color: #ffffff !important; color: #000000 !important; margin: 0; padding: 16px; font-family: 'Inter', sans-serif; min-height: 100vh; }}
            body {{ display: flex; align-items: center; justify-content: center; }}
            .login-card {{ background: #f9f9f9; border: 1px solid #e0e0e0; padding: 28px 20px; border-radius: 12px; width: 100%; max-width: 380px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
            .logo-container {{ background: #ffffff; padding: 12px; border-radius: 8px; border: 1px solid #e0e0e0; display: inline-block; margin-bottom: 16px; }}
            .logo-container img {{ width: 80px; height: 80px; object-fit: contain; display: block; }}
            h2 {{ margin: 0 0 8px 0; font-size: 22px; font-weight: 700; text-align: center; color: #000000 !important; }}
            p.sub {{ color: #666666 !important; font-size: 13px; text-align: center; margin-bottom: 24px; }}
            label {{ font-size: 13px; font-weight: 600; color: #333333 !important; display: block; margin-bottom: 6px; text-align: left; }}
            input {{ width: 100%; background: #ffffff !important; color: #000000 !important; border: 1px solid #cccccc; padding: 12px 14px; font-size: 16px; border-radius: 6px; margin-bottom: 18px; outline: none; }}
            input:focus {{ border-color: #000000; }}
            button {{ width: 100%; background: #000000 !important; color: #ffffff !important; font-weight: 700; border: none; padding: 14px; border-radius: 6px; font-size: 15px; cursor: pointer; }}
            button:hover {{ background: #333333 !important; }}
        </style>
    </head>
    <body>
        <div class="login-card">
            <div class="logo-container">
                <img src="{logo_path}" alt="Logo Alegre Muebles" onerror="this.src='https://via.placeholder.com/80?text=Logo'">
            </div>
            <h2>Alegre Muebles</h2>
            <p class="sub">Sistema MRP & Gestión Operativa</p>
            {mensaje_error}
            <form action="/login" method="post" style="text-align: left;">
                <label>Usuario</label>
                <input type="text" name="username" required>
                <label>Contraseña</label>
                <input type="password" name="password" required>
                <button type="submit">Iniciar Sesión</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/login")
def login_post(username: str = Form(...), password: str = Form(...)):
    if username == USUARIO_CORRECTO and password == PASSWORD_CORRECTO:
        response = RedirectResponse(url="/panel", status_code=303)
        response.set_cookie(key="sesion_activa", value="true")
        return response
    return RedirectResponse(url="/login?error=Usuario+o+contraseña+incorrectos", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sesion_activa")
    return response

# --- ENDPOINTS REST ---
@app.get("/productos-estandar/")
def listar_productos_estandar():
    db = SessionLocal()
    try:
        return [
            {
                "codigo": p.codigo,
                "nombre": p.nombre,
                "cantidad": getattr(p, "cantidad", 1.0) or 1.0,
                "costo_real": p.costo_real,
                "costo_total": p.costo_total,
                "gastos_extra": getattr(p, "gastos_extra", 0.0) or 0.0
            } for p in db.query(ProductoEstandarModel).all()
        ]
    finally:
        db.close()

@app.post("/productos-estandar/")
def crear_producto_estandar(prod: ProductoEstandarCreate):
    db = SessionLocal()
    try:
        cod = prod.codigo.strip().upper()
        if db.query(ProductoEstandarModel).filter(ProductoEstandarModel.codigo == cod).first():
            return {"error": "El código ya existe."}
        db.add(ProductoEstandarModel(
            codigo=cod,
            nombre=prod.nombre.strip(),
            cantidad=prod.cantidad,
            costo_real=prod.costo_real,
            costo_total=prod.costo_total,
            gastos_extra=prod.gastos_extra
        ))
        db.commit()
        return {"mensaje": "Producto estandarizado guardado."}
    finally:
        db.close()

@app.put("/productos-estandar/{codigo}")
def editar_producto_estandar(codigo: str, prod: ProductoEstandarUpdate):
    db = SessionLocal()
    try:
        p = db.query(ProductoEstandarModel).filter(ProductoEstandarModel.codigo == codigo.strip().upper()).first()
        if not p: return {"error": "No encontrado"}
        p.nombre = prod.nombre.strip()
        p.cantidad = prod.cantidad
        p.costo_real = prod.costo_real
        p.costo_total = prod.costo_total
        p.gastos_extra = prod.gastos_extra
        db.commit()
        return {"mensaje": "Actualizado."}
    finally:
        db.close()

@app.delete("/productos-estandar/{codigo}")
def eliminar_producto_estandar(codigo: str):
    db = SessionLocal()
    try:
        p = db.query(ProductoEstandarModel).filter(ProductoEstandarModel.codigo == codigo.strip().upper()).first()
        if not p: return {"error": "No encontrado"}
        db.delete(p)
        db.commit()
        return {"mensaje": "Eliminado."}
    finally:
        db.close()

@app.post("/vender-estandar/")
def vender_producto_estandar(v: VenderEstandar):
    db = SessionLocal()
    try:
        p = db.query(ProductoEstandarModel).filter(ProductoEstandarModel.codigo == v.codigo.strip().upper()).first()
        if not p: return {"error": "Producto no encontrado"}
        
        cant_actual = getattr(p, "cantidad", 0.0) or 0.0
        if cant_actual <= 0:
            return {"error": "No hay stock disponible de este mueble."}

        p.cantidad = cant_actual - 1.0
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        
        db.add(EntregaModel(
            cliente=v.comprador.strip() or "Venta Mostrador Estándar",
            servicio=f"Mueble Estándar: {p.nombre} ({p.codigo})",
            monto_total=p.costo_total,
            costo_materiales=p.costo_real,
            gastos_extra=getattr(p, "gastos_extra", 0.0) or 0.0,
            fecha_entrega=fecha_hoy,
            estado="Entregado (Venta Estándar)"
        ))
        db.commit()
        return {"mensaje": "Venta registrada y stock descontado con éxito."}
    finally:
        db.close()

def cliente_to_dict(c: ClienteModel):
    return {
        "id": c.id, "nombre": c.nombre, "telefono": c.telefono, "servicio": c.servicio,
        "monto_total": c.monto_total, "anticipo": c.anticipo, "gastos_extra": c.gastos_extra,
        "costo_materiales": c.costo_materiales, "fecha_anticipo": c.fecha_anticipo,
        "saldo_financiar": c.saldo_financiar, "es_plan_cuotas": c.es_plan_cuotas,
        "cuotas": json.loads(c.cuotas_json), "medidas": json.loads(c.medidas_json),
        "estado_produccion": c.estado_produccion
    }

@app.get("/clientes/")
def listar_clientes():
    db = SessionLocal()
    try:
        return [cliente_to_dict(c) for c in db.query(ClienteModel).all()]
    finally:
        db.close()

@app.post("/clientes/")
def crear_cliente(cliente: ClienteCreate):
    db = SessionLocal()
    try:
        saldo = cliente.monto_total - cliente.anticipo
        fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
        cuotas_list = []
        if cliente.es_plan_cuotas and cliente.cantidad_cuotas > 0:
            monto_cuota = round(saldo / cliente.cantidad_cuotas, 2)
            cuotas_list = [{"numero": i, "monto": monto_cuota, "estado": "Pendiente", "fecha_pago": None} for i in range(1, cliente.cantidad_cuotas + 1)]

        nuevo = ClienteModel(
            nombre=cliente.nombre, telefono=cliente.telefono, servicio=cliente.servicio,
            monto_total=cliente.monto_total, anticipo=cliente.anticipo, gastos_extra=cliente.gastos_extra,
            costo_materiales=0.0, fecha_anticipo=fecha_hoy if cliente.anticipo > 0 else None,
            saldo_financiar=saldo, es_plan_cuotas=cliente.es_plan_cuotas,
            cuotas_json=json.dumps(cuotas_list),
            medidas_json=json.dumps({"alto_mm": cliente.alto_mm, "ancho_mm": cliente.ancho_mm, "profundidad_mm": cliente.profundidad_mm}),
            estado_produccion="Pendiente"
        )
        db.add(nuevo)
        db.commit()
        return {"mensaje": "Cliente registrado con éxito."}
    finally:
        db.close()

@app.put("/clientes/{cliente_id}")
def editar_cliente(cliente_id: int, cliente: ClienteUpdate):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == cliente_id).first()
        if not c: return {"error": "Cliente no encontrado"}
        
        c.nombre = cliente.nombre
        c.telefono = cliente.telefono
        c.servicio = cliente.servicio
        c.monto_total = cliente.monto_total
        c.anticipo = cliente.anticipo
        if cliente.anticipo > 0 and not c.fecha_anticipo:
            c.fecha_anticipo = datetime.now().strftime("%d/%m/%Y %H:%M")
        c.gastos_extra = cliente.gastos_extra
        c.es_plan_cuotas = cliente.es_plan_cuotas
        c.medidas_json = json.dumps({"alto_mm": cliente.alto_mm, "ancho_mm": cliente.ancho_mm, "profundidad_mm": cliente.profundidad_mm})

        saldo = max(0.0, cliente.monto_total - cliente.anticipo)
        cuotas_existentes = json.loads(c.cuotas_json)
        cuotas_pagadas = [q for q in cuotas_existentes if q.get("estado") == "Pagado"]
        total_pagado = sum(q["monto"] for q in cuotas_pagadas)
        saldo_restante = max(0.0, saldo - total_pagado)
        
        c.saldo_financiar = saldo_restante

        if cliente.es_plan_cuotas and cliente.cantidad_cuotas > len(cuotas_pagadas):
            cuotas_pendientes_cant = cliente.cantidad_cuotas - len(cuotas_pagadas)
            monto_cuota = round(saldo_restante / cuotas_pendientes_cant, 2) if cuotas_pendientes_cant > 0 else 0
            
            nuevas_cuotas = cuotas_pagadas.copy()
            for i in range(len(cuotas_pagadas) + 1, cliente.cantidad_cuotas + 1):
                nuevas_cuotas.append({"numero": i, "monto": monto_cuota, "estado": "Pendiente", "fecha_pago": None})
            c.cuotas_json = json.dumps(nuevas_cuotas)

        db.commit()
        return {"mensaje": "Cliente actualizado correctamente."}
    finally:
        db.close()

@app.delete("/clientes/{cliente_id}")
def eliminar_cliente(cliente_id: int):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == cliente_id).first()
        if not c: return {"error": "No encontrado"}
        db.delete(c)
        db.commit()
        return {"mensaje": "Eliminado."}
    finally:
        db.close()

@app.post("/pagar-cuota/")
def pagar_cuota(pago: PagoCuota):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == pago.cliente_id).first()
        if not c: return {"error": "No encontrado"}
        cuotas = json.loads(c.cuotas_json)
        for q in cuotas:
            if q["numero"] == pago.numero_cuota:
                q["estado"] = "Pagado"
                q["fecha_pago"] = pago.fecha_pago.strip() if pago.fecha_pago else datetime.now().strftime("%d/%m/%Y %H:%M")
                c.saldo_financiar = max(0, c.saldo_financiar - q["monto"])
                c.cuotas_json = json.dumps(cuotas)
                db.commit()
                return {"mensaje": "Cuota pagada con éxito."}
        return {"error": "Cuota no encontrada"}
    finally:
        db.close()

@app.get("/stock/")
def ver_stock():
    db = SessionLocal()
    try:
        return [{"id_articulo": i.id_articulo, "nombre": i.nombre, "categoria": i.categoria, "cantidad": i.cantidad, "precio_costo": i.precio_costo} for i in db.query(StockModel).all()]
    finally:
        db.close()

@app.post("/crear-insumo/")
def crear_insumo(insumo: NuevoInsumo):
    db = SessionLocal()
    try:
        id_clean = insumo.id_articulo.strip().upper()
        if db.query(StockModel).filter(StockModel.id_articulo == id_clean).first():
            return {"error": "El ID ya existe."}
        db.add(StockModel(id_articulo=id_clean, nombre=insumo.nombre, categoria=insumo.categoria, cantidad=insumo.cantidad, precio_costo=insumo.precio_costo))
        db.commit()
        return {"mensaje": "Insumo guardado."}
    finally:
        db.close()

@app.put("/stock/{id_articulo}")
def editar_insumo(id_articulo: str, insumo: InsumoUpdate):
    db = SessionLocal()
    try:
        i = db.query(StockModel).filter(StockModel.id_articulo == id_articulo.strip().upper()).first()
        if not i: return {"error": "Insumo no encontrado"}
        i.nombre = insumo.nombre
        i.categoria = insumo.categoria
        i.cantidad = insumo.cantidad
        i.precio_costo = insumo.precio_costo
        db.commit()
        return {"mensaje": "Insumo actualizado."}
    finally:
        db.close()

@app.delete("/stock/{id_articulo}")
def eliminar_insumo(id_articulo: str):
    db = SessionLocal()
    try:
        i = db.query(StockModel).filter(StockModel.id_articulo == id_articulo.strip().upper()).first()
        if not i: return {"error": "No encontrado"}
        db.delete(i)
        db.commit()
        return {"mensaje": "Insumo eliminado."}
    finally:
        db.close()

@app.get("/produccion/")
def ver_produccion():
    db = SessionLocal()
    try:
        return {"ordenes": [cliente_to_dict(c) for c in db.query(ClienteModel).all()]}
    finally:
        db.close()

@app.get("/calcular-despiece/")
def calcular_despiece_get(alto_mm: float, ancho_mm: float, profundidad_mm: float):
    db = SessionLocal()
    try:
        AREA_PLACA_M2 = 4.758
        superficie_total = (2*(alto_mm*profundidad_mm) + 2*(ancho_mm*profundidad_mm) + (alto_mm*ancho_mm)) / 1000000
        placas = round((superficie_total * 1.10) / AREA_PLACA_M2, 2)
        cantos = round(((2 * alto_mm) + (2 * ancho_mm)) / 1000, 2)
        
        insumos = db.query(StockModel).all()
        costo_placa = 25000.0
        costo_canto = 350.0
        for i in insumos:
            if "Placas" in i.nombre or "MDF" in i.nombre:
                costo_placa = i.precio_costo
            if "Canto" in i.nombre:
                costo_canto = i.precio_costo

        costo_estimado = round((placas * costo_placa) + (cantos * costo_canto), 2)
        return {"superficie_m2": round(superficie_total, 2), "placas_mdf": placas, "metros_canto": cantos, "costo_materiales": costo_estimado}
    finally:
        db.close()

@app.post("/iniciar-produccion/")
def iniciar_produccion(data: ProducirMueble):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == data.cliente_id).first()
        if not c: return {"error": "No encontrado"}
        m = json.loads(c.medidas_json)
        desp = calcular_despiece_get(m.get("alto_mm", 1800), m.get("ancho_mm", 1200), m.get("profundidad_mm", 500))
        c.costo_materiales = desp["costo_materiales"]

        for item in db.query(StockModel).all():
            if "Placas" in item.nombre or "MDF" in item.nombre:
                item.cantidad = round(max(0, item.cantidad - desp["placas_mdf"]), 2)
            if "Canto" in item.nombre:
                item.cantidad = round(max(0, item.cantidad - desp["metros_canto"]), 2)

        c.estado_produccion = "En Producción"
        db.commit()
        return {"mensaje": "Producción iniciada."}
    finally:
        db.close()

@app.post("/finalizar-produccion/")
def finalizar_produccion(data: ProducirMueble):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == data.cliente_id).first()
        if c:
            c.estado_produccion = "Listo para Entrega"
            db.commit()
            return {"mensaje": "Listo."}
        return {"error": "No encontrado"}
    finally:
        db.close()

@app.post("/entregar-mueble/")
def entregar_mueble(data: ProducirMueble):
    db = SessionLocal()
    try:
        c = db.query(ClienteModel).filter(ClienteModel.id == data.cliente_id).first()
        if c:
            c.estado_produccion = "Entregado"
            fecha_hoy = datetime.now().strftime("%Y-%m-%d")
            e = db.query(EntregaModel).filter(EntregaModel.cliente_id == c.id).first()
            if not e:
                db.add(EntregaModel(cliente_id=c.id, cliente=c.nombre, servicio=c.servicio, monto_total=c.monto_total, costo_materiales=c.costo_materiales, gastos_extra=c.gastos_extra, fecha_entrega=fecha_hoy, estado="Entregado"))
            else:
                e.fecha_entrega = fecha_hoy
            db.commit()
            return {"mensaje": "Entregado."}
        return {"error": "No encontrado"}
    finally:
        db.close()

@app.get("/entregas/")
def listar_entregas():
    db = SessionLocal()
    try:
        return [{"id": e.id, "cliente_id": e.cliente_id, "cliente": e.cliente, "servicio": e.servicio, "monto_total": e.monto_total, "costo_materiales": e.costo_materiales, "gastos_extra": e.gastos_extra, "fecha_entrega": e.fecha_entrega, "estado": e.estado} for e in db.query(EntregaModel).all()]
    finally:
        db.close()

# --- PANEL FRONTEND ---
@app.get("/panel", response_class=HTMLResponse)
def mostrar_panel(request: Request):
    if request.cookies.get("sesion_activa") != "true":
        return RedirectResponse(url="/login")

    logo_path = obtener_ruta_logo()

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alegre Muebles - Sistema MRP</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * {{ box-sizing: border-box; }}
            html, body {{ background-color: #ffffff !important; color: #000000 !important; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }}
            body {{ padding-top: 130px; }}
            
            .header-fixed {{ position: fixed; top: 0; left: 0; width: 100%; background: #ffffff !important; z-index: 1000; padding: 10px 16px 0 16px; border-bottom: 1px solid #e0e0e0; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }}
            .header-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; position: relative; }}
            
            .header-center-logo {{ display: flex; align-items: center; gap: 8px; background: #f5f5f5; border: 1px solid #e0e0e0; padding: 4px 10px; border-radius: 6px; }}
            .header-center-logo img {{ width: 26px; height: 26px; object-fit: contain; }}
            .header-center-logo span {{ color: #000000 !important; font-weight: 700; font-size: 13px; }}

            h1 {{ color: #000000 !important; font-size: 18px; margin: 0; font-weight: 700; white-space: nowrap; }}
            h2 {{ color: #000000 !important; font-size: 18px; margin-top: 0; }}
            
            .tab {{ display: flex; gap: 4px; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }}
            .tab::-webkit-scrollbar {{ display: none; }}
            .tab button {{ background-color: #f5f5f5; border: 1px solid #e0e0e0; border-bottom: none; border-radius: 8px 8px 0 0; outline: none; cursor: pointer; padding: 10px 14px; font-weight: 600; font-size: 13px; color: #666666; white-space: nowrap; flex-shrink: 0; }}
            .tab button:hover {{ background-color: #eeeeee; color: #000000; }}
            .tab button.active {{ background-color: #000000 !important; color: #ffffff !important; border-color: #000000; }}
            
            .container {{ padding: 16px; max-width: 1400px; margin: 0 auto; }}
            .tabcontent {{ display: none; padding: 16px; border: 1px solid #e0e0e0; background: #ffffff !important; border-radius: 0 0 10px 10px; }}
            
            .table-responsive {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 15px; border: 1px solid #e0e0e0; border-radius: 6px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; background: #ffffff !important; min-width: 650px; }}
            th, td {{ border: 1px solid #e0e0e0; padding: 10px 12px; text-align: left; color: #000000 !important; }}
            th {{ background-color: #f0f0f0 !important; color: #000000 !important; font-weight: 700; }}
            tfoot td {{ background-color: #f8f9fa !important; font-weight: 700; font-size: 13px; }}
            
            input, select {{ background: #ffffff !important; color: #000000 !important; border: 1px solid #cccccc; border-radius: 6px; padding: 10px 12px; font-size: 15px; width: 100%; margin-bottom: 12px; }}
            input:focus, select:focus {{ border-color: #000000; outline: none; }}
            
            .input-currency-wrapper {{ position: relative; display: flex; align-items: center; margin-bottom: 12px; }}
            .input-currency-wrapper span {{ position: absolute; left: 12px; font-weight: 600; color: #333; z-index: 2; pointer-events: none; }}
            .input-currency-wrapper input {{ padding-left: 28px !important; margin-bottom: 0 !important; }}

            .btn {{ background: #000000 !important; color: #ffffff !important; border: none; padding: 9px 14px; cursor: pointer; border-radius: 6px; font-weight: 600; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }}
            .btn:hover {{ background: #333333 !important; }}
            .btn-secondary {{ background: #f0f0f0 !important; color: #000000 !important; border: 1px solid #ccc; }}
            .btn-edit {{ background: #e3f2fd !important; color: #0d47a1 !important; border: 1px solid #bbdefb; padding: 6px 10px; cursor: pointer; border-radius: 5px; font-weight: 600; margin-right: 4px; font-size: 12px; }}
            .btn-edit:hover {{ background: #bbdefb !important; }}
            .btn-delete {{ background: #fff0f0 !important; color: #d32f2f !important; border: 1px solid #ffcdd2; padding: 6px 10px; cursor: pointer; border-radius: 5px; font-weight: 600; font-size: 12px; }}
            .btn-delete:hover {{ background: #ffe0e0 !important; }}
            
            .modal {{ display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.5); overflow-y: auto; padding: 12px; }}
            .modal-content {{ background-color: #ffffff !important; color: #000000 !important; margin: 20px auto; padding: 20px; border-radius: 12px; width: 100%; max-width: 600px; border: 1px solid #e0e0e0; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }}
            
            .card-summary {{ background:#f8f9fa; border:1px solid #e0e0e0; border-radius:8px; padding:15px; margin-bottom:15px; }}
            .badge-entregado {{ background-color: #e8f5e9 !important; color: #2e7d32 !important; border: 1px solid #a5d6a7; padding: 4px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }}

            .grid-medidas {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }}

            @media (max-width: 768px) {{
                body {{ padding-top: 135px; }}
                .header-top {{ align-items: center; }}
                .header-center-logo {{ display: none; }}
                h1 {{ font-size: 17px; }}
                .container {{ padding: 10px; }}
                .tabcontent {{ padding: 12px; }}
                .modal-content {{ padding: 16px; margin: 10px auto; }}
                .grid-medidas {{ grid-template-columns: 1fr; gap: 4px; }}
            }}

            @page {{
                size: A4 portrait;
                margin: 0;
            }}
            @media print {{
                html, body {{
                    background: #ffffff !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    height: 100% !important;
                    overflow: hidden !important;
                }}
                .header-fixed, .container, .modal, .no-print {{
                    display: none !important;
                }}
                #modalTicket {{
                    display: block !important;
                    position: absolute !important;
                    top: 0 !important;
                    left: 0 !important;
                    width: 100% !important;
                    height: 100% !important;
                    background: #ffffff !important;
                    padding: 0 !important;
                }}
                #modalTicket .modal-content {{
                    border: none !important;
                    box-shadow: none !important;
                    margin: 0 auto !important;
                    padding: 40px 20px !important;
                    max-width: 500px !important;
                    width: 100% !important;
                }}
                .btn-modal-actions {{
                    display: none !important;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header-fixed">
            <div class="header-top">
                <h1>Alegre Muebles</h1>
                
                <div class="header-center-logo">
                    <img src="{logo_path}" alt="Logo Alegre MRP" onerror="this.src='https://via.placeholder.com/28?text=M'">
                    <span>Alegre MRP</span>
                </div>

                <a href="/logout" class="btn" style="text-decoration:none; background:#f5f5f5 !important; color:#000000 !important; border:1px solid #ccc; font-size:12px; padding: 6px 10px;">🚪 Salir</a>
            </div>
            
            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'ClientesTab')">Clientes</button>
                <button class="tablinks" onclick="openTab(event, 'ProdEstandarTab')">Stock Estandarizados</button>
                <button class="tablinks" onclick="openTab(event, 'ProdTab')">Órdenes Producción</button>
                <button class="tablinks" onclick="openTab(event, 'BalanceTab')">Balances y Entregas</button>
                <button class="tablinks" onclick="openTab(event, 'StockTab')">Stock e Insumos</button>
            </div>
        </div>

        <div class="container">
            <!-- TAB CLIENTES -->
            <div id="ClientesTab" class="tabcontent" style="display: block;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom: 12px; flex-wrap: wrap;">
                    <h2>Gestión de Clientes</h2>
                    <button class="btn" onclick="abrirModalNuevoCliente()">+ Nuevo Cliente</button>
                </div>
                <div class="table-responsive">
                    <table id="tablaClientes">
                        <thead>
                            <tr><th>Cliente</th><th>Teléfono</th><th>Servicio</th><th>Monto Total</th><th>Anticipo</th><th>Saldo Pendiente</th><th>Estado</th><th>Cuotas</th><th>Acciones</th></tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>

            <!-- TAB STOCK DE ESTANDARIZADOS -->
            <div id="ProdEstandarTab" class="tabcontent">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom: 12px; flex-wrap: wrap;">
                    <h2>Stock de Muebles Estandarizados</h2>
                    <button class="btn" onclick="abrirModalNuevoEstandar()">+ Nuevo Mueble Estándar</button>
                </div>
                <div class="table-responsive">
                    <table id="tablaEstandar">
                        <thead>
                            <tr><th>Código</th><th>Mueble</th><th>Stock</th><th>Costo Real</th><th>Gastos / Flete</th><th>Precio Venta</th><th>Acciones</th></tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>

            <!-- TAB PRODUCCION -->
            <div id="ProdTab" class="tabcontent">
                <h2>Órdenes de Producción</h2>
                <div class="table-responsive">
                    <table id="tablaProduccion">
                        <thead>
                            <tr><th>Cliente</th><th>Servicio</th><th>Medidas (Alto x Ancho x Prof)</th><th>Estado</th><th>Acciones</th></tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>

            <!-- TAB BALANCES -->
            <div id="BalanceTab" class="tabcontent">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
                    <h2>Balances y Entregas</h2>
                    <button class="btn" style="background:#2e7d32 !important;" onclick="exportarBalancesExcel()">📊 Exportar a Excel (CSV)</button>
                </div>

                <div class="card-summary" style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
                    <div>
                        <label style="font-size:12px; font-weight:700; margin-bottom:4px;">Desde:</label>
                        <input type="date" id="filtroFechaDesde" style="width:auto; margin:0;" onchange="filtrarBalances()">
                    </div>
                    <div>
                        <label style="font-size:12px; font-weight:700; margin-bottom:4px;">Hasta:</label>
                        <input type="date" id="filtroFechaHasta" style="width:auto; margin:0;" onchange="filtrarBalances()">
                    </div>
                    <button class="btn btn-secondary" style="margin-top:auto;" onclick="limpiarFiltroFechas()">Limpiar Filtro</button>
                    
                    <div style="margin-left:auto; text-align:right; min-width: 140px;">
                        <span style="font-size:12px; color:#555;">Ganancia Neta:</span>
                        <h3 id="lblGananciaNeta" style="margin:2px 0 0 0; color:#2e7d32; font-size: 18px;">$0,00</h3>
                    </div>
                </div>

                <div class="table-responsive">
                    <table id="tablaBalances">
                        <thead>
                            <tr><th>Fecha</th><th>Cliente</th><th>Servicio</th><th>Monto Total</th><th>Costos Materiales</th><th>Gastos / Flete</th><th>Estado</th></tr>
                        </thead>
                        <tbody></tbody>
                        <tfoot>
                            <tr>
                                <td colspan="3" style="text-align:right;">TOTALES:</td>
                                <td id="sumMontoTotal">$0,00</td>
                                <td id="sumCostoMateriales">$0,00</td>
                                <td id="sumGastosExtra">$0,00</td>
                                <td>-</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div style="background:#ffffff; border:1px solid #e0e0e0; border-radius:8px; padding:12px; margin-top:18px; max-height:280px;">
                    <canvas id="chartBalances" style="max-height:250px;"></canvas>
                </div>
            </div>

            <!-- TAB STOCK E INSUMOS -->
            <div id="StockTab" class="tabcontent">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom: 12px; flex-wrap: wrap;">
                    <h2>Control de Stock e Insumos</h2>
                    <button class="btn" onclick="abrirModalNuevoInsumo()">+ Nuevo Insumo</button>
                </div>
                <div class="table-responsive">
                    <table id="tablaStock">
                        <thead>
                            <tr><th>ID</th><th>Nombre</th><th>Categoría</th><th>Cantidad</th><th>Costo Unitario</th><th>Total Invertido</th><th>Acciones</th></tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- MODAL CLIENTE -->
        <div id="modalCliente" class="modal">
            <div class="modal-content">
                <h3 id="modalClienteTitulo">Nuevo Cliente</h3>
                <form id="formCliente" onsubmit="guardarCliente(event)">
                    <input type="hidden" id="cli_id_edit" value="">
                    
                    <label>Nombre del Cliente</label><input type="text" id="cli_nombre" required>
                    <label>Teléfono (solo números)</label><input type="text" id="cli_telefono" required>
                    <label>Servicio / Descripción del Mueble</label><input type="text" id="cli_servicio" required>
                    
                    <label>Monto Total Presupuestado ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="cli_monto" class="input-moneda" placeholder="0" oninput="formatearMonedaInput(this)" required>
                    </div>

                    <label>Anticipo ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="cli_anticipo" class="input-moneda" placeholder="0" value="0" oninput="formatearMonedaInput(this)">
                    </div>

                    <label>¿Financiar saldo en Cuotas?</label>
                    <select id="cli_cuotas_check" onchange="toggleCuotasInput(this.value)">
                        <option value="false">No (Pago único al finalizar)</option>
                        <option value="true">Sí (Plan de Cuotas)</option>
                    </select>

                    <div id="divCantCuotas" style="display:none;">
                        <label>Cantidad de Cuotas</label>
                        <input type="number" id="cli_cant_cuotas" value="1" min="1" max="36">
                    </div>

                    <h4 style="margin: 15px 0 10px 0; font-size:14px;">Medidas para Despiece (mm)</h4>
                    <div class="grid-medidas">
                        <div><label style="font-size:12px;">Alto (mm)</label><input type="number" id="cli_alto" value="1800"></div>
                        <div><label style="font-size:12px;">Ancho (mm)</label><input type="number" id="cli_ancho" value="1200"></div>
                        <div><label style="font-size:12px;">Profundidad (mm)</label><input type="number" id="cli_prof" value="500"></div>
                    </div>

                    <div style="margin-top:20px; display:flex; gap:10px; justify-content:flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalCliente').style.display='none'">Cancelar</button>
                        <button type="submit" class="btn" id="btnGuardarCliente">Guardar Cliente</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- MODAL MUEBLE ESTÁNDAR -->
        <div id="modalEstandar" class="modal">
            <div class="modal-content">
                <h3 id="modalEstandarTitulo">Nuevo Mueble Estándar</h3>
                <form id="formEstandar" onsubmit="guardarEstandar(event)">
                    <input type="hidden" id="std_is_edit" value="false">
                    
                    <label>Código de Producto (ej. PROD-003)</label>
                    <input type="text" id="std_codigo" required>

                    <label>Nombre / Descripción del Mueble Estándar</label>
                    <input type="text" id="std_nombre" required>

                    <label>Cantidad Inicial en Stock (Unidades)</label>
                    <input type="number" step="1" id="std_cantidad" value="1" required>

                    <label>Costo Real de Fabricación ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="std_costo_real" class="input-moneda" placeholder="0" oninput="formatearMonedaInput(this)" required>
                    </div>

                    <label>Gastos Adicionales / Flete ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="std_gastos" class="input-moneda" placeholder="0" value="0" oninput="formatearMonedaInput(this)">
                    </div>

                    <div style="background:#f5f5f5; border:1px solid #ddd; padding:12px; border-radius:6px; margin-bottom:15px;">
                        <p style="margin:0 0 8px 0; font-size:12px; font-weight:700;">🚚 Calculadora de Flete por Km</p>
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                            <div>
                                <label style="font-size:11px;">Distancia (Km)</label>
                                <input type="number" id="flt_km" value="0" style="margin:0;" oninput="calcularFleteKM()">
                            </div>
                            <div>
                                <label style="font-size:11px;">Tarifa ($ / Km)</label>
                                <input type="number" id="flt_tarifa" value="500" style="margin:0;" oninput="calcularFleteKM()">
                            </div>
                        </div>
                    </div>

                    <label>Precio de Venta Sugerido ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="std_precio_venta" class="input-moneda" placeholder="0" oninput="formatearMonedaInput(this)" required>
                    </div>

                    <div style="margin-top:20px; display:flex; gap:10px; justify-content:flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalEstandar').style.display='none'">Cancelar</button>
                        <button type="submit" class="btn" id="btnGuardarEstandar">Guardar Mueble</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- MODAL REGISTRAR VENTA ESTÁNDAR -->
        <div id="modalVentaEstandar" class="modal">
            <div class="modal-content" style="max-width:420px;">
                <h3>Registrar Venta / Entrega</h3>
                <form id="formVentaEstandar" onsubmit="confirmarVentaEstandar(event)">
                    <input type="hidden" id="vta_std_codigo" value="">
                    <p style="font-size:13px; color:#555;" id="vta_std_info"></p>
                    
                    <label>Nombre del Comprador / Cliente</label>
                    <input type="text" id="vta_std_comprador" placeholder="Ingresa el nombre del comprador" required>

                    <div style="margin-top:20px; display:flex; gap:10px; justify-content:flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalVentaEstandar').style.display='none'">Cancelar</button>
                        <button type="submit" class="btn" style="background:#2e7d32 !important;">Confirmar Venta</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- MODAL PLAN DE CUOTAS -->
        <div id="modalCuotas" class="modal">
            <div class="modal-content">
                <h3 id="modalCuotasTitulo">Plan de Cuotas</h3>
                <div id="modalCuotasContenido"></div>
                <div style="margin-top:20px; text-align:right;">
                    <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalCuotas').style.display='none'">Cerrar</button>
                </div>
            </div>
        </div>

        <!-- MODAL RECIBO -->
        <div id="modalTicket" class="modal">
            <div class="modal-content" style="max-width: 460px; border: 1px solid #111; padding: 25px;">
                <div id="ticketImpresion">
                    <div style="text-align:center; border-bottom:2px solid #000; padding-bottom:12px; margin-bottom:15px;">
                        <img src="{logo_path}" alt="Logo Alegre" style="max-width:80px; height:auto; margin-bottom:6px;" onerror="this.style.display='none'">
                        <h2 style="margin:0 0 2px 0; font-size:20px; text-transform:uppercase; letter-spacing:1px;">ALEGRE MUEBLES</h2>
                        <p style="margin:0; font-size:12px; color:#333;">Fabricación de Muebles a Medida</p>
                        <p style="margin:6px 0 0 0; font-size:13px; font-weight:700; background:#f0f0f0; padding:4px; border-radius:4px;">RECIBO DE PAGO</p>
                    </div>
                    
                    <table style="width:100%; border:none; margin:0 0 15px 0; font-size:13px; min-width: 100%;">
                        <tr>
                            <td style="border:none; padding:3px 0; color:#555;"><strong>Fecha / Hora:</strong></td>
                            <td style="border:none; padding:3px 0; text-align:right; cursor:pointer;" id="tktFecha" title="Haz clic para modificar la fecha en este recibo" onclick="editarFechaComprobante(this)"></td>
                        </tr>
                        <tr>
                            <td style="border:none; padding:3px 0; color:#555;"><strong>Cliente:</strong></td>
                            <td style="border:none; padding:3px 0; text-align:right; font-weight:700;" id="tktCliente"></td>
                        </tr>
                        <tr>
                            <td style="border:none; padding:3px 0; color:#555;"><strong>Mueble / Servicio:</strong></td>
                            <td style="border:none; padding:3px 0; text-align:right;" id="tktServicio"></td>
                        </tr>
                    </table>

                    <div style="background:#f8f8f8; border:1px solid #e0e0e0; padding:12px; border-radius:6px; margin-bottom:15px; font-size:13px;">
                        <p style="margin:0 0 6px 0;" id="tktAnticipo"><strong>Anticipo Registrado:</strong> $0,00</p>
                        <p style="margin:0 0 6px 0;" id="tktDetalleCuota"><strong>Cuota Abonada:</strong> -</p>
                        <p style="margin:0;" id="tktCuotasRestantes"><strong>Cuotas Pendientes:</strong> -</p>
                    </div>

                    <div style="border-top:2px solid #000; padding-top:10px; text-align:right; margin-bottom:15px;">
                        <p style="margin:0 0 4px 0; font-size:15px;"><strong>Monto Abonado:</strong> <span id="tktMonto" style="font-size:18px; font-weight:700;"></span></p>
                        <p id="tktSaldoRestante" style="margin:0; font-size:12px; color:#555;"></p>
                    </div>

                    <div style="border-top:1px solid #ddd; padding-top:10px; margin-top:10px;">
                        <p style="margin:0 0 6px 0; font-size:12px; font-weight:700; color:#333;">Historial de Pagos de Cuotas:</p>
                        <div id="tktHistorialCuotas" style="font-size:11px; color:#444;"></div>
                    </div>

                    <div style="margin-top:25px; text-align:center; font-size:11px; color:#777; border-top:1px dashed #ccc; padding-top:10px;">
                        <p style="margin:0;">¡Muchas gracias por su confianza!</p>
                        <p style="margin:2px 0 0 0;">Alegre Muebles - Comprobante de Operación</p>
                    </div>
                </div>

                <div class="btn-modal-actions" style="margin-top:20px; display:flex; gap:10px; justify-content:flex-end;">
                    <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalTicket').style.display='none'">Cerrar</button>
                    <button type="button" class="btn" onclick="window.print()">🖨️ Imprimir Recibo</button>
                </div>
            </div>
        </div>

        <!-- MODAL STOCK -->
        <div id="modalStock" class="modal">
            <div class="modal-content">
                <h3 id="modalStockTitulo">Nuevo Insumo</h3>
                <form id="formStock" onsubmit="guardarInsumo(event)">
                    <input type="hidden" id="stk_is_edit" value="false">
                    <label>ID Artículo (ej. PL-002)</label><input type="text" id="stk_id" required>
                    <label>Nombre del Material / Insumo</label><input type="text" id="stk_nombre" required>
                    <label>Categoría (Placas, Cantos, Herrajes, etc.)</label><input type="text" id="stk_categoria" required>
                    <label>Cantidad Disponible</label><input type="number" step="0.01" id="stk_cantidad" required>
                    
                    <label>Precio Costo Unitario ($)</label>
                    <div class="input-currency-wrapper">
                        <span>$</span>
                        <input type="text" id="stk_costo" class="input-moneda" placeholder="0" oninput="formatearMonedaInput(this)" required>
                    </div>

                    <div style="margin-top:20px; display:flex; gap:10px; justify-content:flex-end;">
                        <button type="button" class="btn btn-secondary" onclick="document.getElementById('modalStock').style.display='none'">Cancelar</button>
                        <button type="submit" class="btn" id="btnGuardarStock">Guardar Insumo</button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            let clientesGlobales = [];
            let stockGlobal = [];
            let estandarGlobal = [];
            let entregasGlobales = [];
            let chartBalancesInstance = null;

            function openTab(evt, tabName) {{
                let tabcontent = document.getElementsByClassName("tabcontent");
                for (let i = 0; i < tabcontent.length; i++) tabcontent[i].style.display = "none";
                let tablinks = document.getElementsByClassName("tablinks");
                for (let i = 0; i < tablinks.length; i++) tablinks[i].className = tablinks[i].className.replace(" active", "");
                document.getElementById(tabName).style.display = "block";
                evt.currentTarget.className += " active";
            }}

            function toggleCuotasInput(val) {{
                document.getElementById('divCantCuotas').style.display = (val === 'true') ? 'block' : 'none';
            }}

            const formatoARS = new Intl.NumberFormat('es-AR', {{ style: 'currency', currency: 'ARS' }});

            function formatearMonedaInput(input) {{
                let val = input.value.replace(/[^0-9]/g, '');
                if (!val) {{
                    input.value = '';
                    return;
                }}
                input.value = parseInt(val, 10).toLocaleString('es-AR');
            }}

            function parseMonedaValue(valStr) {{
                if (!valStr) return 0;
                let num = valStr.toString().replace(/\\./g, '').replace(/,/g, '.');
                return parseFloat(num) || 0;
            }}

            function calcularFleteKM() {{
                let km = parseFloat(document.getElementById('flt_km').value) || 0;
                let tarifa = parseFloat(document.getElementById('flt_tarifa').value) || 0;
                let totalFlete = km * tarifa;
                
                let inputGastos = document.getElementById('std_gastos');
                inputGastos.value = totalFlete;
                formatearMonedaInput(inputGastos);
            }}

            async function cargarDatos() {{
                let resC = await fetch('/clientes/');
                clientesGlobales = await resC.json();
                let tbodyC = document.querySelector("#tablaClientes tbody");
                tbodyC.innerHTML = "";
                clientesGlobales.forEach(c => {{
                    let esEntregado = c.estado_produccion === 'Entregado';
                    let badgeEstado = esEntregado 
                        ? `<span class="badge-entregado">✔ Entregado</span>`
                        : `<span style="background:#f0f0f0; padding:3px 8px; border-radius:4px; font-size:12px;">${{c.estado_produccion}}</span>`;

                    let botonCuotas = c.es_plan_cuotas 
                        ? `<button class="btn btn-secondary" onclick="verCuotasCliente(${{c.id}})">Cuotas (${{c.cuotas.length}})</button>`
                        : `<span style="font-size:12px; color:#666;">Contado</span>`;

                    tbodyC.innerHTML += `<tr>
                        <td><strong>${{c.nombre}}</strong></td>
                        <td>${{c.telefono}}</td>
                        <td>${{c.servicio}}</td>
                        <td>${{formatoARS.format(c.monto_total)}}</td>
                        <td><strong style="color:#2e7d32;">${{formatoARS.format(c.anticipo)}}</strong></td>
                        <td><strong style="color:${{c.saldo_financiar > 0 ? '#d32f2f' : '#2e7d32'}}">${{formatoARS.format(c.saldo_financiar)}}</strong></td>
                        <td>${{badgeEstado}}</td>
                        <td>${{botonCuotas}}</td>
                        <td style="white-space: nowrap;">
                            <button class="btn-edit" onclick="abrirModalEditarCliente(${{c.id}})">✏️</button>
                            <button class="btn-delete" onclick="eliminarCliente(${{c.id}})">🗑️</button>
                        </td>
                    </tr>`;
                }});

                let resEst = await fetch('/productos-estandar/');
                estandarGlobal = await resEst.json();
                let tbodyEst = document.querySelector("#tablaEstandar tbody");
                tbodyEst.innerHTML = "";
                estandarGlobal.forEach(p => {{
                    let badgeStock = p.cantidad > 0 
                        ? `<span style="font-weight:700; color:#2e7d32;">${{p.cantidad}} unid.</span>`
                        : `<span style="font-weight:700; color:#d32f2f;">Sin Stock</span>`;

                    tbodyEst.innerHTML += `<tr>
                        <td><code>${{p.codigo}}</code></td>
                        <td><strong>${{p.nombre}}</strong></td>
                        <td>${{badgeStock}}</td>
                        <td>${{formatoARS.format(p.costo_real)}}</td>
                        <td>${{formatoARS.format(p.gastos_extra)}}</td>
                        <td><strong style="color:#2e7d32;">${{formatoARS.format(p.costo_total)}}</strong></td>
                        <td style="white-space: nowrap;">
                            <button class="btn" style="background:#2e7d32 !important; margin-right:4px;" onclick="abrirModalVentaEstandar('${{p.codigo}}')">📦 Vender</button>
                            <button class="btn-edit" onclick="abrirModalEditarEstandar('${{p.codigo}}')">✏️</button>
                            <button class="btn-delete" onclick="eliminarEstandar('${{p.codigo}}')">🗑️</button>
                        </td>
                    </tr>`;
                }});

                let resS = await fetch('/stock/');
                stockGlobal = await resS.json();
                let tbodyS = document.querySelector("#tablaStock tbody");
                tbodyS.innerHTML = "";
                stockGlobal.forEach(s => {{
                    tbodyS.innerHTML += `<tr>
                        <td><code>${{s.id_articulo}}</code></td>
                        <td>${{s.nombre}}</td>
                        <td>${{s.categoria}}</td>
                        <td>${{s.cantidad}}</td>
                        <td>${{formatoARS.format(s.precio_costo)}}</td>
                        <td><strong>${{formatoARS.format(s.cantidad * s.precio_costo)}}</strong></td>
                        <td style="white-space: nowrap;">
                            <button class="btn-edit" onclick="abrirModalEditarInsumo('${{s.id_articulo}}')">✏️</button>
                            <button class="btn-delete" onclick="eliminarInsumo('${{s.id_articulo}}')">🗑️</button>
                        </td>
                    </tr>`;
                }});

                let resP = await fetch('/produccion/');
                let prodData = await resP.json();
                let tbodyP = document.querySelector("#tablaProduccion tbody");
                tbodyP.innerHTML = "";
                prodData.ordenes.forEach(o => {{
                    let m = o.medidas || {{}};
                    let botonAccion = '';

                    if(o.estado_produccion === 'Pendiente') {{
                        botonAccion = `<button class="btn" onclick="iniciarProd(${{o.id}})">Iniciar</button>`;
                    }} else if(o.estado_produccion === 'En Producción') {{
                        botonAccion = `<button class="btn" onclick="finalizarProd(${{o.id}})">Finalizar</button>`;
                    }} else if(o.estado_produccion === 'Listo para Entrega') {{
                        botonAccion = `<button class="btn" onclick="entregarMueble(${{o.id}})">Entregar</button>`;
                    }} else {{
                        botonAccion = `<span class="badge-entregado">✔ Entregado</span>`;
                    }}

                    tbodyP.innerHTML += `<tr>
                        <td><strong>${{o.nombre}}</strong></td>
                        <td>${{o.servicio}}</td>
                        <td>${{m.alto_mm||1800}}x${{m.ancho_mm||1200}}x${{m.profundidad_mm||500}} mm</td>
                        <td><span style="background:#f0f0f0; padding:3px 8px; border-radius:4px; font-size:12px;">${{o.estado_produccion}}</span></td>
                        <td>${{botonAccion}}</td>
                    </tr>`;
                }});

                let resE = await fetch('/entregas/');
                entregasGlobales = await resE.json();
                filtrarBalances();
            }}

            function filtrarBalances() {{
                let desde = document.getElementById('filtroFechaDesde').value;
                let hasta = document.getElementById('filtroFechaHasta').value;

                let filtradas = entregasGlobales.filter(e => {{
                    if (!e.fecha_entrega) return true;
                    if (desde && e.fecha_entrega < desde) return false;
                    if (hasta && e.fecha_entrega > hasta) return false;
                    return true;
                }});

                let tbodyB = document.querySelector("#tablaBalances tbody");
                tbodyB.innerHTML = "";
                
                let totIngresos = 0;
                let totMateriales = 0;
                let totGastos = 0;

                filtradas.forEach(e => {{
                    totIngresos += e.monto_total || 0;
                    totMateriales += e.costo_materiales || 0;
                    totGastos += e.gastos_extra || 0;

                    tbodyB.innerHTML += `<tr>
                        <td>${{e.fecha_entrega}}</td>
                        <td><strong>${{e.cliente}}</strong></td>
                        <td>${{e.servicio}}</td>
                        <td>${{formatoARS.format(e.monto_total)}}</td>
                        <td>${{formatoARS.format(e.costo_materiales)}}</td>
                        <td>${{formatoARS.format(e.gastos_extra)}}</td>
                        <td><span class="badge-entregado">${{e.estado}}</span></td>
                    </tr>`;
                }});

                document.getElementById('sumMontoTotal').innerText = formatoARS.format(totIngresos);
                document.getElementById('sumCostoMateriales').innerText = formatoARS.format(totMateriales);
                document.getElementById('sumGastosExtra').innerText = formatoARS.format(totGastos);

                let gananciaNeta = totIngresos - (totMateriales + totGastos);
                document.getElementById('lblGananciaNeta').innerText = formatoARS.format(gananciaNeta);

                actualizarGraficoBalances(totIngresos, totMateriales, totGastos, gananciaNeta);
            }}

            function limpiarFiltroFechas() {{
                document.getElementById('filtroFechaDesde').value = '';
                document.getElementById('filtroFechaHasta').value = '';
                filtrarBalances();
            }}

            function actualizarGraficoBalances(ingresos, materiales, gastos, ganancia) {{
                let ctx = document.getElementById('chartBalances').getContext('2d');
                if (chartBalancesInstance) chartBalancesInstance.destroy();

                chartBalancesInstance = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: ['Cobrado', 'Materiales', 'Gastos/Flete', 'Ganancia Neta'],
                        datasets: [{{
                            label: 'Monto ($ ARS)',
                            data: [ingresos, materiales, gastos, ganancia],
                            backgroundColor: ['#1976d2', '#d32f2f', '#f57c00', '#2e7d32']
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }}
                    }}
                }});
            }}

            function exportarBalancesExcel() {{
                if (entregasGlobales.length === 0) {{
                    alert('No hay registros en balances para exportar.');
                    return;
                }}
                let csvContent = "data:text/csv;charset=utf-8,Fecha,Cliente/Comprador,Servicio/Mueble,Monto Total,Costo Materiales,Gastos Extra/Flete,Estado\\n";
                entregasGlobales.forEach(e => {{
                    csvContent += `"${{e.fecha_entrega}}","${{e.cliente}}","${{e.servicio}}",${{e.monto_total}},${{e.costo_materiales}},${{e.gastos_extra}},"${{e.estado}}"\\n`;
                }});
                let encodedUri = encodeURI(csvContent);
                let link = document.createElement("a");
                link.setAttribute("href", encodedUri);
                link.setAttribute("download", `balances_alegre_${{new Date().toISOString().slice(0,10)}}.csv`);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }}

            function abrirModalNuevoEstandar() {{
                document.getElementById('formEstandar').reset();
                document.getElementById('std_is_edit').value = 'false';
                document.getElementById('std_codigo').readOnly = false;
                document.getElementById('modalEstandarTitulo').innerText = 'Nuevo Mueble Estándar';
                document.getElementById('btnGuardarEstandar').innerText = 'Guardar Mueble';
                document.getElementById('modalEstandar').style.display = 'block';
            }}

            function abrirModalEditarEstandar(codigo) {{
                let p = estandarGlobal.find(item => item.codigo === codigo);
                if (!p) return;

                document.getElementById('std_is_edit').value = 'true';
                document.getElementById('modalEstandarTitulo').innerText = `Editar Mueble: ${{p.codigo}}`;
                document.getElementById('btnGuardarEstandar').innerText = 'Actualizar Mueble';

                document.getElementById('std_codigo').value = p.codigo;
                document.getElementById('std_codigo').readOnly = true;
                document.getElementById('std_nombre').value = p.nombre;
                document.getElementById('std_cantidad').value = p.cantidad || 1;

                let inputReal = document.getElementById('std_costo_real');
                inputReal.value = p.costo_real;
                formatearMonedaInput(inputReal);

                let inputGastos = document.getElementById('std_gastos');
                inputGastos.value = p.gastos_extra;
                formatearMonedaInput(inputGastos);

                let inputVenta = document.getElementById('std_precio_venta');
                inputVenta.value = p.costo_total;
                formatearMonedaInput(inputVenta);

                document.getElementById('modalEstandar').style.display = 'block';
            }}

            async function guardarEstandar(e) {{
                e.preventDefault();
                let isEdit = document.getElementById('std_is_edit').value === 'true';
                let codigo = document.getElementById('std_codigo').value.trim();

                let data = {{
                    codigo: codigo,
                    nombre: document.getElementById('std_nombre').value,
                    cantidad: parseFloat(document.getElementById('std_cantidad').value) || 0,
                    costo_real: parseMonedaValue(document.getElementById('std_costo_real').value),
                    gastos_extra: parseMonedaValue(document.getElementById('std_gastos').value),
                    costo_total: parseMonedaValue(document.getElementById('std_precio_venta').value)
                }};

                let url = isEdit ? `/productos-estandar/${{codigo}}` : '/productos-estandar/';
                let method = isEdit ? 'PUT' : 'POST';

                let res = await fetch(url, {{ method: method, headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data) }});
                let r = await res.json();
                if (r.error) alert(r.error); else {{ 
                    document.getElementById('modalEstandar').style.display = 'none'; 
                    document.getElementById('formEstandar').reset();
                    cargarDatos(); 
                }}
            }}

            async function eliminarEstandar(codigo) {{
                if (confirm('¿Eliminar producto estandarizado?')) {{
                    await fetch('/productos-estandar/' + codigo, {{ method: 'DELETE' }});
                    cargarDatos();
                }}
            }}

            function abrirModalVentaEstandar(codigo) {{
                let p = estandarGlobal.find(item => item.codigo === codigo);
                if (!p) return;

                if (p.cantidad <= 0) {{
                    alert('No hay stock disponible de este mueble para vender.');
                    return;
                }}

                document.getElementById('vta_std_codigo').value = p.codigo;
                document.getElementById('vta_std_info').innerText = `Mueble: ${{p.nombre}} | Precio Venta: ${{formatoARS.format(p.costo_total)}} | Stock: ${{p.cantidad}} unid.`;
                document.getElementById('vta_std_comprador').value = '';
                document.getElementById('modalVentaEstandar').style.display = 'block';
            }}

            async function confirmarVentaEstandar(e) {{
                e.preventDefault();
                let data = {{
                    codigo: document.getElementById('vta_std_codigo').value,
                    comprador: document.getElementById('vta_std_comprador').value
                }};
                let res = await fetch('/vender-estandar/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});
                let r = await res.json();
                if (r.error) alert(r.error); else {{
                    document.getElementById('modalVentaEstandar').style.display = 'none';
                    cargarDatos();
                    alert('¡Venta registrada con éxito y stock descontado!');
                }}
            }}

            function abrirModalNuevoCliente() {{
                document.getElementById('formCliente').reset();
                document.getElementById('cli_id_edit').value = '';
                document.getElementById('modalClienteTitulo').innerText = 'Nuevo Cliente';
                document.getElementById('btnGuardarCliente').innerText = 'Guardar Cliente';
                toggleCuotasInput('false');
                document.getElementById('modalCliente').style.display = 'block';
            }}

            function abrirModalEditarCliente(clienteId) {{
                let c = clientesGlobales.find(item => item.id === clienteId);
                if (!c) return;

                document.getElementById('cli_id_edit').value = c.id;
                document.getElementById('modalClienteTitulo').innerText = `Editar Cliente: ${{c.nombre}}`;
                document.getElementById('btnGuardarCliente').innerText = 'Actualizar Cambios';
                
                document.getElementById('cli_nombre').value = c.nombre;
                document.getElementById('cli_telefono').value = c.telefono;
                document.getElementById('cli_servicio').value = c.servicio;
                
                let inputMonto = document.getElementById('cli_monto');
                inputMonto.value = c.monto_total;
                formatearMonedaInput(inputMonto);

                let inputAnticipo = document.getElementById('cli_anticipo');
                inputAnticipo.value = c.anticipo;
                formatearMonedaInput(inputAnticipo);

                let isCuotas = c.es_plan_cuotas ? 'true' : 'false';
                document.getElementById('cli_cuotas_check').value = isCuotas;
                toggleCuotasInput(isCuotas);
                
                if (c.es_plan_cuotas) {{
                    document.getElementById('cli_cant_cuotas').value = c.cuotas.length || 1;
                }}

                let m = c.medidas || {{}};
                document.getElementById('cli_alto').value = m.alto_mm || 1800;
                document.getElementById('cli_ancho').value = m.ancho_mm || 1200;
                document.getElementById('cli_prof').value = m.profundidad_mm || 500;

                document.getElementById('modalCliente').style.display = 'block';
            }}

            async function guardarCliente(e) {{
                e.preventDefault();
                let clienteId = document.getElementById('cli_id_edit').value;
                let isEdit = clienteId !== '';

                let data = {{
                    nombre: document.getElementById('cli_nombre').value,
                    telefono: document.getElementById('cli_telefono').value,
                    servicio: document.getElementById('cli_servicio').value,
                    monto_total: parseMonedaValue(document.getElementById('cli_monto').value),
                    anticipo: parseMonedaValue(document.getElementById('cli_anticipo').value),
                    es_plan_cuotas: document.getElementById('cli_cuotas_check').value === 'true',
                    cantidad_cuotas: parseInt(document.getElementById('cli_cant_cuotas').value) || 1,
                    alto_mm: parseFloat(document.getElementById('cli_alto').value) || 1800,
                    ancho_mm: parseFloat(document.getElementById('cli_ancho').value) || 1200,
                    profundidad_mm: parseFloat(document.getElementById('cli_prof').value) || 500
                }};

                let url = isEdit ? `/clientes/${{clienteId}}` : '/clientes/';
                let method = isEdit ? 'PUT' : 'POST';

                let res = await fetch(url, {{ method: method, headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data) }});
                let r = await res.json();
                if (r.error) alert(r.error); else {{ 
                    document.getElementById('modalCliente').style.display = 'none'; 
                    document.getElementById('formCliente').reset();
                    cargarDatos(); 
                }}
            }}

            function abrirModalNuevoInsumo() {{
                document.getElementById('formStock').reset();
                document.getElementById('stk_is_edit').value = 'false';
                document.getElementById('stk_id').readOnly = false;
                document.getElementById('modalStockTitulo').innerText = 'Nuevo Insumo';
                document.getElementById('btnGuardarStock').innerText = 'Guardar Insumo';
                document.getElementById('modalStock').style.display = 'block';
            }}

            function abrirModalEditarInsumo(idArticulo) {{
                let s = stockGlobal.find(item => item.id_articulo === idArticulo);
                if (!s) return;

                document.getElementById('stk_is_edit').value = 'true';
                document.getElementById('modalStockTitulo').innerText = `Editar Insumo: ${{s.id_articulo}}`;
                document.getElementById('btnGuardarStock').innerText = 'Actualizar Insumo';

                document.getElementById('stk_id').value = s.id_articulo;
                document.getElementById('stk_id').readOnly = true;

                document.getElementById('stk_nombre').value = s.nombre;
                document.getElementById('stk_categoria').value = s.categoria;
                document.getElementById('stk_cantidad').value = s.cantidad;

                let inputCosto = document.getElementById('stk_costo');
                inputCosto.value = s.precio_costo;
                formatearMonedaInput(inputCosto);

                document.getElementById('modalStock').style.display = 'block';
            }}

            async function guardarInsumo(e) {{
                e.preventDefault();
                let isEdit = document.getElementById('stk_is_edit').value === 'true';
                let idArticulo = document.getElementById('stk_id').value.trim();

                let data = {{
                    id_articulo: idArticulo,
                    nombre: document.getElementById('stk_nombre').value,
                    categoria: document.getElementById('stk_categoria').value,
                    cantidad: parseFloat(document.getElementById('stk_cantidad').value),
                    precio_costo: parseMonedaValue(document.getElementById('stk_costo').value)
                }};

                let url = isEdit ? `/stock/${{idArticulo}}` : '/crear-insumo/';
                let method = isEdit ? 'PUT' : 'POST';

                let res = await fetch(url, {{ method: method, headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data) }});
                let r = await res.json();
                if (r.error) alert(r.error); else {{ 
                    document.getElementById('modalStock').style.display = 'none'; 
                    document.getElementById('formStock').reset();
                    cargarDatos(); 
                }}
            }}

            function verCuotasCliente(clienteId) {{
                let c = clientesGlobales.find(item => item.id === clienteId);
                if (!c) return;

                document.getElementById('modalCuotasTitulo').innerText = `Plan de Cuotas: ${{c.nombre}}`;
                let html = `<p style="font-size:13px; margin-bottom:15px;"><strong>Mueble:</strong> ${{c.servicio}} | <strong>Total:</strong> ${{formatoARS.format(c.monto_total)}} | <strong>Saldo Restante:</strong> ${{formatoARS.format(c.saldo_financiar)}}</p>`;
                
                html += `<div class="table-responsive"><table style="min-width: 500px;">
                    <thead>
                        <tr><th>Cuota</th><th>Monto</th><th>Estado</th><th>Fecha de Pago</th><th>Acción</th></tr>
                    </thead>
                    <tbody>`;
                
                let totalCuotas = c.cuotas.length;

                c.cuotas.forEach(q => {{
                    let esPagado = q.estado === 'Pagado';
                    let btnPagar = esPagado
                        ? `<button class="btn btn-secondary" onclick="imprimirReciboCuota(${{c.id}}, ${{q.numero}})">📄 Recibo</button>`
                        : `<button class="btn" onclick="pagarCuotaCliente(${{c.id}}, ${{q.numero}}, ${{q.monto}})">💰 Cobrar</button>`;

                    let fechaMostrar = q.fecha_pago || '-';
                    if (esPagado) {{
                        fechaMostrar = `<span style="cursor:pointer; text-decoration:underline;" title="Clic para editar fecha" onclick="editarFechaCuotaDirecta(${{c.id}}, ${{q.numero}}, '${{q.fecha_pago || ''}}')">${{q.fecha_pago}} ✏️</span>`;
                    }}

                    html += `<tr>
                        <td><strong>#${{q.numero}} de ${{totalCuotas}}</strong></td>
                        <td>${{formatoARS.format(q.monto)}}</td>
                        <td><span style="color:${{esPagado ? '#2e7d32' : '#d32f2f'}}; font-weight:600;">${{q.estado}}</span></td>
                        <td>${{fechaMostrar}}</td>
                        <td>${{btnPagar}}</td>
                    </tr>`;
                }});

                html += `</tbody></table></div>`;
                document.getElementById('modalCuotasContenido').innerHTML = html;
                document.getElementById('modalCuotas').style.display = 'block';
            }}

            async function pagarCuotaCliente(clienteId, numCuota, montoCuota) {{
                let d = new Date();
                let dia = String(d.getDate()).padStart(2, '0');
                let mes = String(d.getMonth() + 1).padStart(2, '0');
                let anio = d.getFullYear();
                let hora = String(d.getHours()).padStart(2, '0');
                let min = String(d.getMinutes()).padStart(2, '0');
                let fechaHoy = `${{dia}}/${{mes}}/${{anio}} ${{hora}}:${{min}}`;

                let fechaElegida = prompt(`Cobro de Cuota #${{numCuota}} (${{formatoARS.format(montoCuota)}}).\\nPuedes editar la fecha del comprobante antes de guardarla:`, fechaHoy);
                if (fechaElegida === null) return;

                let res = await fetch('/pagar-cuota/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ 
                        cliente_id: clienteId, 
                        numero_cuota: numCuota,
                        fecha_pago: fechaElegida.trim()
                    }})
                }});
                let r = await res.json();
                if (r.error) {{
                    alert(r.error);
                }} else {{
                    document.getElementById('modalCuotas').style.display = 'none';
                    await cargarDatos();
                    verCuotasCliente(clienteId);
                }}
            }}

            async function editarFechaCuotaDirecta(clienteId, numCuota, fechaActual) {{
                let nueva = prompt(`Modificar fecha de pago registrada para la Cuota #${{numCuota}}:`, fechaActual);
                if (nueva === null || nueva.trim() === '') return;

                let res = await fetch('/pagar-cuota/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        cliente_id: clienteId,
                        numero_cuota: numCuota,
                        fecha_pago: nueva.trim()
                    }})
                }});
                let r = await res.json();
                if (r.error) {{
                    alert(r.error);
                }} else {{
                    await cargarDatos();
                    verCuotasCliente(clienteId);
                }}
            }}

            function editarFechaComprobante(el) {{
                let nueva = prompt("Modificar fecha visible del comprobante antes de imprimir:", el.innerText);
                if (nueva !== null && nueva.trim() !== "") {{
                    el.innerText = nueva.trim();
                }}
            }}

            function imprimirReciboCuota(clienteId, numCuota) {{
                let c = clientesGlobales.find(item => item.id === clienteId);
                if (!c) return;

                let qActual = c.cuotas.find(q => q.numero === numCuota);
                if (!qActual) return;

                let totalCuotas = c.cuotas.length;
                let cuotasPagadas = c.cuotas.filter(q => q.estado === 'Pagado');
                let cuotasPendientesCant = c.cuotas.filter(q => q.estado !== 'Pagado').length;

                document.getElementById('tktFecha').innerText = qActual.fecha_pago || new Date().toLocaleString();
                document.getElementById('tktCliente').innerText = c.nombre;
                document.getElementById('tktServicio').innerText = c.servicio;
                document.getElementById('tktAnticipo').innerHTML = `<strong>Anticipo Registrado:</strong> ${{formatoARS.format(c.anticipo)}} (${{c.fecha_anticipo || '-'}})`;
                document.getElementById('tktDetalleCuota').innerHTML = `<strong>Cuota Abonada:</strong> Cuota #${{numCuota}} de ${{totalCuotas}}`;
                document.getElementById('tktCuotasRestantes').innerHTML = `<strong>Cuotas Pendientes:</strong> ${{cuotasPendientesCant}} cuota(s)`;
                document.getElementById('tktMonto').innerText = formatoARS.format(qActual.monto);
                document.getElementById('tktSaldoRestante').innerText = `Saldo pendiente restante: ${{formatoARS.format(c.saldo_financiar)}}`;

                let histHtml = '';
                if (cuotasPagadas.length > 0) {{
                    histHtml += `<table style="width:100%; border-collapse:collapse; margin-top:5px; font-size:11px; min-width:100%;">
                        <thead>
                            <tr style="background:#f0f0f0;">
                                <th style="border:1px solid #ddd; padding:4px;">Cuota</th>
                                <th style="border:1px solid #ddd; padding:4px;">Monto</th>
                                <th style="border:1px solid #ddd; padding:4px;">Fecha Cobro</th>
                            </tr>
                        </thead>
                        <tbody>`;
                    cuotasPagadas.forEach(qp => {{
                        histHtml += `<tr>
                            <td style="border:1px solid #ddd; padding:4px; text-align:center;">#${{qp.numero}}</td>
                            <td style="border:1px solid #ddd; padding:4px; text-align:right;">${{formatoARS.format(qp.monto)}}</td>
                            <td style="border:1px solid #ddd; padding:4px; text-align:center;">${{qp.fecha_pago || '-'}}</td>
                        </tr>`;
                    }});
                    histHtml += `</tbody></table>`;
                }} else {{
                    histHtml = `<p style="margin:0; color:#888;">No hay cobros previos registrados.</p>`;
                }}

                document.getElementById('tktHistorialCuotas').innerHTML = histHtml;
                document.getElementById('modalTicket').style.display = 'block';
            }}

            async function eliminarCliente(id) {{
                if(confirm('¿Eliminar cliente y sus datos?')) {{ await fetch('/clientes/'+id, {{method: 'DELETE'}}); cargarDatos(); }}
            }}

            async function eliminarInsumo(id) {{
                if(confirm('¿Eliminar insumo del stock?')) {{ await fetch('/stock/'+id, {{method: 'DELETE'}}); cargarDatos(); }}
            }}

            async function iniciarProd(id) {{
                await fetch('/iniciar-produccion/', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{cliente_id: id}}) }});
                cargarDatos();
            }}

            async function finalizarProd(id) {{
                await fetch('/finalizar-produccion/', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{cliente_id: id}}) }});
                cargarDatos();
            }}

            async function entregarMueble(id) {{
                await fetch('/entregar-mueble/', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{cliente_id: id}}) }});
                cargarDatos();
            }}

            cargarDatos();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
