import asyncio
import logging
import math
import random
from typing import Union, Tuple, List, Optional
from playwright.async_api import Page, Locator

logger = logging.getLogger('KCKY_InputHumanizer')

def _ease_in_out(t: float) -> float:
    """
    Función de suavizado para el movimiento (Hermite smoothstep).
    """
    return t * t * (3 - 2 * t)

def _bezier_curve(start: Tuple[float, float], end: Tuple[float, float], num_points: int = 20) -> List[Tuple[float, float]]:
    """
    Genera una curva de Bézier cúbica con puntos de control aleatorios
    para simular una trayectoria de ratón humana.
    """
    x1, y1 = start
    x2, y2 = end
    
    distance = math.hypot(x2 - x1, y2 - y1)
    
    # Magnitud del desplazamiento para los puntos de control (10-30% de la distancia)
    offset_mag1 = distance * random.uniform(0.1, 0.3)
    offset_mag2 = distance * random.uniform(0.1, 0.3)
    
    # Dirección de la línea
    angle = math.atan2(y2 - y1, x2 - x1)
    
    # Ángulos perpendiculares para los puntos de control
    angle1 = angle + (math.pi / 2) * random.choice([1, -1])
    angle2 = angle + (math.pi / 2) * random.choice([1, -1])
    
    # Puntos de control (P1 y P2)
    # P1 cerca del inicio, P2 cerca del final
    cx1 = x1 + math.cos(angle1) * offset_mag1 + (x2 - x1) * 0.3
    cy1 = y1 + math.sin(angle1) * offset_mag1 + (y2 - y1) * 0.3
    
    cx2 = x1 + math.cos(angle2) * offset_mag2 + (x2 - x1) * 0.7
    cy2 = y1 + math.sin(angle2) * offset_mag2 + (y2 - y1) * 0.7

    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        # Aplicamos ease_in_out a t para variar la velocidad a lo largo de la curva
        ease_t = _ease_in_out(t)
        
        # Fórmula de Bézier cúbica
        u = 1 - ease_t
        tt = ease_t * ease_t
        uu = u * u
        uuu = uu * u
        ttt = tt * ease_t

        x = uuu * x1 + 3 * uu * ease_t * cx1 + 3 * u * tt * cx2 + ttt * x2
        y = uuu * y1 + 3 * uu * ease_t * cy1 + 3 * u * tt * cy2 + ttt * y2
        
        # Añadir jitter (±1-3px gaussiano)
        jitter_x = random.gauss(0, 1.5)
        jitter_y = random.gauss(0, 1.5)
        
        points.append((x + jitter_x, y + jitter_y))
        
    # Asegurar que el último punto es exactamente el destino final (con jitter)
    points[-1] = (x2 + random.gauss(0, 0.5), y2 + random.gauss(0, 0.5))
    
    return points

async def human_move_to(page: Page, x: float, y: float, **kwargs):
    """
    Mueve el ratón a coordenadas absolutas usando una curva de Bézier.
    """
    logger.debug(f"Moviendo ratón a ({x}, {y})")
    
    # Obtener posición actual. Playwright no expone la posición del ratón directamente,
    # así que asumimos que empieza en (0,0) si no sabemos, o intentamos evaluarla si
    # en algún punto el script inyectado guarda la posición. Para simplificar,
    # empezamos desde (random, random) o el centro de la pantalla si no hay histórico.
    # En un entorno real, mantendríamos un estado de la posición.
    # Como aproximación, usaremos el centro del viewport como fallback.
    
    viewport = page.viewport_size
    start_x = viewport['width'] / 2 if viewport else 800 / 2
    start_y = viewport['height'] / 2 if viewport else 600 / 2
    
    # Generar de 15 a 25 puntos
    num_points = random.randint(15, 25)
    points = _bezier_curve((start_x, start_y), (x, y), num_points)
    
    # Duración total: 200-600ms dependiendo de la distancia
    distance = math.hypot(x - start_x, y - start_y)
    total_duration_ms = min(max(200, distance * random.uniform(0.5, 1.5)), 600)
    delay_per_step = (total_duration_ms / num_points) / 1000.0
    
    for px, py in points:
        await page.mouse.move(px, py)
        # Pequeño jitter en el tiempo también
        await asyncio.sleep(delay_per_step * random.uniform(0.8, 1.2))
        
    # Asegurar la posición final
    await page.mouse.move(x, y)

async def human_click(page: Page, selector_or_locator: Union[str, Locator], **kwargs):
    """
    Realiza un clic humano en un elemento.
    """
    locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
    
    # Obtener el bounding box
    await locator.wait_for(state="visible")
    box = await locator.bounding_box()
    if not box:
        raise ValueError(f"No se pudo obtener el bounding box para el elemento.")
        
    width = box['width']
    height = box['height']
    
    # Elegir un punto aleatorio dentro del elemento (distribución normal alrededor del centro)
    center_x = box['x'] + width / 2
    center_y = box['y'] + height / 2
    
    target_x = random.gauss(center_x, width / 6)
    target_y = random.gauss(center_y, height / 6)
    
    # Limitar para asegurar que caiga dentro del elemento
    target_x = max(box['x'] + 1, min(target_x, box['x'] + width - 1))
    target_y = max(box['y'] + 1, min(target_y, box['y'] + height - 1))
    
    logger.debug(f"Clic humano en: ({target_x}, {target_y})")
    
    # Mover al punto
    await human_move_to(page, target_x, target_y)
    
    # Pequeña pausa antes del mousedown (30-80ms)
    await asyncio.sleep(random.uniform(0.03, 0.08))
    
    # Mousedown
    await page.mouse.down()
    
    # Duración del mousedown (50-120ms)
    await asyncio.sleep(random.uniform(0.05, 0.12))
    
    # Mouseup
    await page.mouse.up()
    
    # Retraso aleatorio después del clic (50-150ms)
    await asyncio.sleep(random.uniform(0.05, 0.15))

async def human_type(page: Page, selector_or_locator: Union[str, Locator], text: str, **kwargs):
    """
    Escribe texto con retrasos y errores simulados similares a los humanos.
    """
    # Clic en el elemento primero
    await human_click(page, selector_or_locator)
    
    logger.debug(f"Escribiendo texto: {text}")
    
    words = text.split(' ')
    for i, word in enumerate(words):
        # Escribir cada carácter en la palabra
        for char in word:
            # 5% de probabilidad de una breve vacilación
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.6))
                
            await page.keyboard.down(char)
            # Retraso de pulsación
            await asyncio.sleep(random.uniform(0.02, 0.06))
            await page.keyboard.up(char)
            
            # Retraso entre teclas (normal: μ=85ms, σ=35ms, clamped a [30, 200ms])
            inter_key_delay = random.gauss(85, 35)
            # Aumentar retraso para caracteres especiales
            if not char.isalnum():
                inter_key_delay *= random.uniform(1.2, 1.8)
                
            inter_key_delay_clamped = max(30, min(inter_key_delay, 200)) / 1000.0
            await asyncio.sleep(inter_key_delay_clamped)
            
        # Añadir espacio si no es la última palabra, más pausa entre palabras
        if i < len(words) - 1:
            await page.keyboard.press('Space')
            await asyncio.sleep(random.uniform(0.2, 0.4))

async def human_scroll(page: Page, direction: str = 'down', distance: int = 300, **kwargs):
    """
    Hace scroll de manera incremental simulando el uso de una rueda de ratón humana.
    """
    logger.debug(f"Scroll humano {direction} de {distance}px")
    
    scrolled = 0
    while scrolled < distance:
        # Pasos incrementales con delta variable (50-150px por paso)
        step = random.uniform(50, 150)
        
        # Añadir inercia: pasos más pequeños hacia el final
        remaining = distance - scrolled
        if remaining < step:
            step = remaining
        elif remaining < distance * 0.3:
            step *= random.uniform(0.5, 0.8)
            
        delta_y = step if direction == 'down' else -step
        
        # En Playwright, wheel delta = scroll delta
        await page.mouse.wheel(0, delta_y)
        scrolled += step
        
        # Retraso entre pasos: 30-80ms con jitter
        await asyncio.sleep(random.uniform(0.03, 0.08))
