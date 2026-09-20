from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('recetas/', views.lista_recetas, name='lista_recetas'),
    path('agregar/', views.agregar_receta, name='agregar_receta'),
    path('editar/<int:receta_id>/', views.editar_receta, name='editar_receta'),
    path('eliminar/<int:receta_id>/', views.eliminar_receta, name='eliminar_receta'),
    path('receta/<int:receta_id>/', views.detalle_receta, name='detalle_receta'),
    path('login/', views.iniciar_sesion, name='iniciar_sesion'),
    path('logout/', views.cerrar_sesion, name='cerrar_sesion'),
    path('favorito/<int:receta_id>/', views.toggle_favorito, name='toggle_favorito'),
    path('valorar/<int:receta_id>/', views.valorar_receta, name='valorar_receta'),
    path('cambiar-nombre/', views.cambiar_nombre, name='cambiar_nombre'),
]
