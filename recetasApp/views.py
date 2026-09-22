import math
import secrets
import time
import unicodedata
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import (
    Receta,
    Valoracion,
    Comentario,
    CATEGORIA_CHOICES,
    CHEF_CHOICES,
    normalizar_nombre,
    validar_nombre_completo,
)
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


def _volver(request):
    """Vuelve a la página desde donde se hizo la acción (si es segura)."""
    destino = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect('lista_recetas')


def _buscar_voto_por_nombre(receta, nombre):
    """
    Busca un voto de la receta con ese nombre sin distinguir mayúsculas/minúsculas.
    Se compara en Python para que también funcione con tildes y ñ (SQLite no lo hace bien).
    """
    clave = nombre.casefold()
    for voto in receta.valoraciones.all():
        if voto.nombre.casefold() == clave:
            return voto
    return None


def _sin_tildes(texto):
    """
    Quita tildes y pone en minúsculas, para poder comparar 'platano' con 'plátano'.
    """
    texto = (texto or '').casefold()
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )


def inicio(request):
    return render(request, 'inicio.html', {
        'nombre_guardado': request.session.get('nombre_votante', ''),
        'aviso_nombre': request.session.pop('aviso_nombre', None),
    })


def lista_recetas(request):
    query = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '')
    chef = request.GET.get('chef', '')
    solo_favoritas = request.GET.get('favoritas', '')
    orden = request.GET.get('orden', 'recientes')
    if orden not in ('recientes', 'nombre', 'valoradas'):
        orden = 'recientes'
    if chef not in dict(CHEF_CHOICES):
        chef = ''

    recetas = Receta.objects.all()
    if categoria:
        recetas = recetas.filter(categoria=categoria)
    if chef:
        recetas = recetas.filter(chef=chef)
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

    if query:
        # Búsqueda en nombre e ingredientes, ignorando tildes y mayúsculas/minúsculas
        clave = _sin_tildes(query)
        recetas = [
            r for r in recetas
            if clave in _sin_tildes(r.nombre) or clave in _sin_tildes(r.ingredientes)
        ]
        total_recetas = len(recetas)
    else:
        total_recetas = recetas.count()

    # Paginación: 12 recetas por página
    paginator = Paginator(recetas, 12)
    numero_pagina = request.GET.get('page')
    recetas = paginator.get_page(numero_pagina)

    return render(request, 'lista.html', {
        'recetas': recetas,
        'categorias': CATEGORIA_CHOICES,
        'chefs': CHEF_CHOICES,
        'query': query,
        'categoria_actual': categoria,
        'chef_actual': chef,
        'solo_favoritas': solo_favoritas,
        'total_recetas': total_recetas,
        'orden_actual': orden,
        'nombre_guardado': request.session.get('nombre_votante', ''),
        'aviso_nombre': request.session.pop('aviso_nombre', None),
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
        'aviso_nombre': request.session.pop('aviso_nombre', None),
        'conflicto': request.session.pop('conflicto_voto', None),
        'comentarios': receta.comentarios.all(),
        'mis_comentarios': request.session.get('comentarios', []),
        'aviso_comentario': request.session.pop('aviso_comentario', None),
        'borrador_comentario': request.session.pop('borrador_comentario', ''),
    })


@require_POST
def cambiar_nombre(request):
    """
    Cambia el nombre del votante guardado en la sesión.
    - Si viene corregir=1: es un error de tipeo, se corrige el nombre en los votos ya hechos.
    - Si no: es otra persona usando el mismo navegador, se empieza sin votos previos.
    """
    nuevo = normalizar_nombre(request.POST.get('nombre', '')[:100])

    try:
        validar_nombre_completo(nuevo)
    except ValidationError as e:
        request.session['aviso_nombre'] = e.messages[0]
        return _volver(request)

    votos = request.session.get('votos', {})

    if request.POST.get('corregir') == '1':
        for receta_id, voto_id in list(votos.items()):
            voto = Valoracion.objects.filter(id=voto_id).first()
            if not voto:
                votos.pop(receta_id, None)
                continue
            # Si ya existe otro voto con ese nombre en la receta, no se toca
            choque = any(
                v.nombre.casefold() == nuevo.casefold()
                for v in voto.receta.valoraciones.exclude(id=voto.id)
            )
            if choque:
                continue
            voto.nombre = nuevo
            voto.save()

        # También se corrige el nombre en los comentarios hechos desde este navegador
        ids = request.session.get('comentarios', [])
        if ids:
            for c in Comentario.objects.filter(id__in=ids):
                c.nombre = nuevo
                c.save()
    else:
        votos = {}
        request.session['comentarios'] = []

    request.session['votos'] = votos
    request.session['nombre_votante'] = nuevo
    return _volver(request)


@require_POST
def quitar_nombre(request):
    """
    Quita el nombre de este navegador. Sin nombre no se puede votar ni comentar.
    Los votos y comentarios ya publicados se quedan como están.
    """
    request.session.pop('nombre_votante', None)
    request.session['votos'] = {}
    request.session['comentarios'] = []
    return _volver(request)


@require_POST
def comentar_receta(request, receta_id):
    receta = get_object_or_404(Receta, id=receta_id)
    destino = f"{reverse('detalle_receta', args=[receta.id])}#comentarios"

    nombre = request.session.get('nombre_votante', '')
    texto = request.POST.get('texto', '').strip()[:500]

    if not nombre:
        request.session['aviso_comentario'] = 'Pon tu nombre y apellido para poder comentar.'
        request.session['borrador_comentario'] = texto
        return redirect(destino)

    try:
        validar_nombre_completo(nombre)
    except ValidationError as e:
        request.session['aviso_comentario'] = e.messages[0]
        request.session['borrador_comentario'] = texto
        return redirect(destino)

    if not texto:
        request.session['aviso_comentario'] = 'Escribe un comentario antes de enviarlo.'
        return redirect(destino)

    comentario = Comentario.objects.create(receta=receta, nombre=nombre, texto=texto)
    ids = request.session.get('comentarios', [])
    ids.append(comentario.id)
    request.session['comentarios'] = ids
    return redirect(destino)


@require_POST
def borrar_comentario(request, comentario_id):
    comentario = get_object_or_404(Comentario, id=comentario_id)
    receta_id = comentario.receta_id
    ids = request.session.get('comentarios', [])

    # Lo puede borrar quien lo escribió (desde este navegador) o quien tenga la sesión de edición
    if comentario.id in ids or request.session.get('autenticado'):
        comentario.delete()
        if comentario.id in ids:
            ids.remove(comentario.id)
            request.session['comentarios'] = ids

    return redirect(f"{reverse('detalle_receta', args=[receta_id])}#comentarios")


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
    nombre = normalizar_nombre(request.POST.get('nombre', '')[:100])
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
            request.session['aviso_voto'] = 'Escribe tu nombre y apellido para poder votar.'
            return redirect('detalle_receta', receta_id=receta.id)

        try:
            validar_nombre_completo(nombre)
        except ValidationError as e:
            request.session['aviso_voto'] = e.messages[0]
            return redirect('detalle_receta', receta_id=receta.id)

        existente = _buscar_voto_por_nombre(receta, nombre)
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
            request.session['nombre_votante'] = voto.nombre

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
