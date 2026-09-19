import math
import secrets
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Receta, CATEGORIA_CHOICES, Valoracion
from .forms import RecetaForm

MAX_INTENTOS = 3
BLOQUEO_SEGUNDOS = 15 * 60


def requiere_login(vista):
    @wraps(vista)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('autenticado'):
            return redirect('iniciar_sesion')
        return vista(request, *args, **kwargs)
    return wrapper


def inicio(request):
    return render(request, 'inicio.html')


def lista_recetas(request):
    query = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '')
    solo_favoritas = request.GET.get('favoritas', '')
    orden = request.GET.get('orden', 'recientes')
    if orden not in ('recientes', 'nombre', 'valoradas'):
        orden = 'recientes'

    recetas = Receta.objects.all()
    if query:
        recetas = recetas.filter(nombre__icontains=query)
    if categoria:
        recetas = recetas.filter(categoria=categoria)
    if solo_favoritas:
        recetas = recetas.filter(favorito=True)

    if orden == 'nombre':
        recetas = recetas.order_by('nombre')
    elif orden == 'valoradas':
        recetas = recetas.annotate(
            prom=Avg('valoraciones__puntaje'),
            votos=Count('valoraciones'),
        ).order_by('-prom', '-votos', '-fecha_creacion')
    else:
        recetas = recetas.order_by('-fecha_creacion')

    return render(request, 'lista.html', {
        'recetas': recetas,
        'categorias': CATEGORIA_CHOICES,
        'query': query,
        'categoria_actual': categoria,
        'solo_favoritas': solo_favoritas,
        'total_recetas': recetas.count(),
        'orden_actual': orden,
    })


def detalle_receta(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)

    # Voto previo de este visitante en esta receta (si existe)
    mi_puntaje = 0
    voto_id = request.session.get('votos', {}).get(str(receta.id))
    if voto_id:
        voto = Valoracion.objects.filter(id=voto_id, receta=receta).first()
        if voto:
            mi_puntaje = voto.puntaje

    return render(request, 'detalle.html', {
        'receta': receta,
        'votantes': receta.valoraciones.order_by('-fecha'),
        'mi_puntaje': mi_puntaje,
        'nombre_guardado': request.session.get('nombre_votante', ''),
        'aviso': request.session.pop('aviso_voto', None),
        'conflicto': request.session.pop('conflicto_voto', None),
    })


@require_POST
def valorar_receta(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)
    votos = request.session.get('votos', {})

    # Quitar el voto (solo el que se hizo desde este navegador)
    if request.POST.get('accion') == 'quitar':
        voto_id = votos.get(str(receta.id))
        if voto_id:
            Valoracion.objects.filter(id=voto_id, receta=receta).delete()
            votos.pop(str(receta.id), None)
            request.session['votos'] = votos
        return redirect('detalle_receta', receta_id=receta.id)

    puntaje = request.POST.get('puntaje', '')
    nombre = request.POST.get('nombre', '').strip()[:100]
    confirmar = request.POST.get('confirmar') == '1'

    if not (puntaje.isdigit() and 1 <= int(puntaje) <= 5):
        return redirect('detalle_receta', receta_id=receta.id)
    puntaje = int(puntaje)

    voto_id = votos.get(str(receta.id))
    voto = Valoracion.objects.filter(id=voto_id, receta=receta).first() if voto_id else None

    if voto:
        # Ya había votado desde este navegador: se actualiza su voto
        voto.puntaje = puntaje
        voto.save()
        request.session['nombre_votante'] = voto.nombre
    else:
        nombre = nombre or request.session.get('nombre_votante', '')
        if not nombre:
            request.session['aviso_voto'] = 'Escribe tu nombre para poder votar.'
        else:
            existente = Valoracion.objects.filter(receta=receta, nombre__iexact=nombre).first()
            if existente:
                if confirmar:
                    # La persona confirmó que es ella: se cambia su valoración
                    existente.puntaje = puntaje
                    existente.save()
                    votos[str(receta.id)] = existente.id
                    request.session['votos'] = votos
                    request.session['nombre_votante'] = existente.nombre
                else:
                    # Se le pregunta antes de cambiar
                    request.session['conflicto_voto'] = {
                        'nombre': existente.nombre,
                        'actual': existente.puntaje,
                        'puntaje': puntaje,
                    }
            else:
                voto = Valoracion.objects.create(receta=receta, nombre=nombre, puntaje=puntaje)
                votos[str(receta.id)] = voto.id
                request.session['votos'] = votos
                request.session['nombre_votante'] = nombre

    return redirect('detalle_receta', receta_id=receta.id)


def _ip_cliente(request):
    return request.META.get('REMOTE_ADDR', 'desconocida')


def iniciar_sesion(request):
    ip = _ip_cliente(request)
    key_bloqueo = f'login_bloqueo:{ip}'
    key_intentos = f'login_intentos:{ip}'

    bloqueado_hasta = cache.get(key_bloqueo)
    if bloqueado_hasta:
        minutos = max(1, math.ceil((bloqueado_hasta - time.time()) / 60))
        return render(request, 'login.html', {'bloqueado': True, 'minutos': minutos})

    error = None
    if request.method == 'POST':
        clave = (request.POST.get('clave') or '').encode('utf-8')
        correcta = str(settings.CLAVE_ACCESO).encode('utf-8')

        if secrets.compare_digest(clave, correcta):
            cache.delete(key_intentos)
            request.session['autenticado'] = True
            return redirect('lista_recetas')

        intentos = (cache.get(key_intentos) or 0) + 1
        if intentos >= MAX_INTENTOS:
            cache.set(key_bloqueo, time.time() + BLOQUEO_SEGUNDOS, BLOQUEO_SEGUNDOS)
            cache.delete(key_intentos)
            return render(request, 'login.html', {
                'bloqueado': True,
                'minutos': BLOQUEO_SEGUNDOS // 60,
            })

        cache.set(key_intentos, intentos, BLOQUEO_SEGUNDOS)
        restantes = MAX_INTENTOS - intentos
        error = f"Contraseña incorrecta. Te quedan {restantes} intento{'s' if restantes != 1 else ''}."

    return render(request, 'login.html', {'error': error})


def cerrar_sesion(request):
    # Solo se cierra la sesión de edición; se conserva el nombre y los votos del visitante
    request.session.pop('autenticado', None)
    return redirect('lista_recetas')


@requiere_login
def agregar_receta(request):
    if request.method == 'POST':
        form = RecetaForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('lista_recetas')
    else:
        form = RecetaForm()
    return render(request, 'formulario.html', {'form': form, 'titulo': 'Agregar Receta'})


@requiere_login
def editar_receta(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)
    if request.method == 'POST':
        form = RecetaForm(request.POST, request.FILES, instance=receta)
        if form.is_valid():
            form.save()
            return redirect('lista_recetas')
    else:
        form = RecetaForm(instance=receta)
    return render(request, 'formulario.html', {'form': form, 'titulo': 'Editar Receta'})


@requiere_login
def eliminar_receta(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)
    if request.method == 'POST':
        receta.delete()
        return redirect('lista_recetas')
    return render(request, 'eliminar.html', {'receta': receta})


@requiere_login
@require_POST
def toggle_favorito(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)
    receta.favorito = not receta.favorito
    receta.save()

    # Volver a la misma página con los mismos filtros
    destino = request.META.get('HTTP_REFERER')
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect('lista_recetas')